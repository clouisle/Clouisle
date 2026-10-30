"""Durable, actor-authorized WeChat collection with per-item outcomes."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import timedelta
from uuid import uuid4

import httpx
from tortoise.expressions import F, Q
from tortoise.transactions import in_transaction

from app.core.i18n import set_language, t
from app.integrations.credentials import decrypt_secret
from app.integrations.wechat import WeChatAPIError, WeChatClient
from app.models.knowledge_base import Document, DocumentType, KnowledgeBase
from app.models.user import User
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeContent,
    WeChatKnowledgeItem,
    WeChatKnowledgeReceipt,
)
from app.schemas.response import BusinessError
from app.services.document_processor import document_processor
from app.services.wechat_connection import (
    check_binding_target,
    collection_error,
    utcnow,
)
from app.services.wechat_media import extract_media
from app.services.wechat_locks import CollectionBusy, collection_lock
from app.services.integration_features import enabled_features, require_feature

logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>\[\]（）]+")
LEASE = timedelta(minutes=3)


def split_items(payload: dict) -> list[dict]:
    """Preserve each attachment; text next to attachments is a caption, not a note."""
    parts = payload.get("item_list") or []
    texts = [
        str((part.get("text_item") or {}).get("text") or "").strip()
        for part in parts
        if part.get("type") == 1
    ]
    text = "\n\n".join(value for value in texts if value)
    attachments = [part for part in parts if part.get("type") != 1]
    if attachments:
        return [
            {"kind": "media", "item": part, "caption": text} for part in attachments
        ]
    urls = list(
        dict.fromkeys(
            match.rstrip(".,;。；，!?！？)") for match in URL_RE.findall(text)
        )
    )
    if urls:
        notes = URL_RE.sub("", text).strip()
        return [{"kind": "url", "url": url, "caption": notes} for url in urls]
    return [{"kind": "text", "text": text}] if text else [{"kind": "unsupported"}]


async def actor_target(receipt: WeChatKnowledgeReceipt):
    await require_feature("wechat", "knowledge_collection")
    binding = await WeChatKnowledgeBinding.filter(
        id=receipt.binding_id, status="connected"
    ).first()
    user = (
        await User.filter(id=receipt.user_id)
        .prefetch_related("roles__permissions")
        .first()
    )
    if not binding or not user or binding.user_id != receipt.user_id:
        raise collection_error("wechat_binding_disconnected")
    if binding.disconnected_at and receipt.created_at <= binding.disconnected_at:
        raise collection_error("wechat_binding_disconnected")
    kb = await check_binding_target(receipt.knowledge_base_id, user)
    return binding, user, kb


async def save_content(path: str, content: bytes):
    if document_processor._remote_mode():
        from app.services import upload_gateway

        async with upload_gateway.client() as gateway:
            response = await gateway.put(
                "/internal/uploads/save", params={"key": path}, content=content
            )
            response.raise_for_status()
    else:
        await document_processor.save_file(content, path)


async def text_for_input(
    spec: dict, receipt, kb, client: WeChatClient, item
) -> tuple[str, str, dict]:
    source = {
        "source": "wechat",
        "wechat_receipt_id": str(receipt.id),
        "wechat_item_index": item.item_index,
        "wechat_item_id": str(item.id),
    }
    if spec["kind"] == "text":
        text = spec["text"]
        return text, text.splitlines()[0][:100] or "WeChat note", source
    if spec["kind"] == "url":
        url = spec["url"]
        if len(url) > 1024:
            raise collection_error("wechat_url_invalid")
        text, metadata = await document_processor.fetch_url_content(url)
        if any(
            marker in text
            for marker in ("环境异常", "访问过于频繁", "完成验证后即可继续访问")
        ):
            raise collection_error("wechat_article_blocked")
        source.update(metadata)
        source["source_url"] = url
        if spec.get("caption"):
            source["wechat_caption"] = spec["caption"]
        return text, str(metadata.get("title") or url)[:255], source
    if spec["kind"] != "media":
        raise collection_error("wechat_type_unsupported")
    incoming = spec["item"]
    kind = incoming.get("type")
    if kind not in (2, 3, 4, 5):
        raise collection_error("wechat_type_unsupported")
    from app.api.v1.endpoints.knowledge_bases import get_kb_document_max_upload_size_mb

    limit = min(await get_kb_document_max_upload_size_mb(), 100) * 1024 * 1024
    transcript = str((incoming.get("voice_item") or {}).get("text") or "").strip()
    if kind == 3 and transcript and not (incoming.get("voice_item") or {}).get("media"):
        source["wechat_extraction"] = "wechat_transcript"
        source["wechat_caption"] = spec.get("caption", "")
        return transcript, transcript.splitlines()[0][:100], source
    raw, filename, mime = await client.download_media(incoming, limit)
    # Stable original path survives worker restart and is exposed via guarded
    # collection-source download, never through a public uploads URL.
    original = f"documents/{kb.id}/wechat/{item.id}/original/{filename}"
    await save_content(original, raw)
    item.original_path = original
    item.name = filename
    await item.save(update_fields=["original_path", "name"])
    source["wechat_original_path"] = original
    source["wechat_original_name"] = filename
    source["wechat_original_mime"] = mime
    source["wechat_original_size"] = len(raw)
    source["wechat_caption"] = spec.get("caption", "")
    doc_type = document_processor.get_document_type(filename, mime)
    if doc_type in ("txt", "markdown", "csv", "json", "html"):
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise collection_error("wechat_text_encoding") from exc
        if "\x00" in decoded:
            raise collection_error("wechat_binary_content")
    elif doc_type == "pdf" and not raw.lstrip().startswith(b"%PDF-"):
        raise collection_error("wechat_binary_content")
    elif doc_type in ("docx", "xlsx", "pptx") and not raw.startswith(b"PK"):
        raise collection_error("wechat_binary_content")
    if kind == 3 and transcript:
        text = transcript
        source["wechat_extraction"] = "wechat_transcript"
    elif kind in (2, 3, 5) or mime.startswith(("image/", "audio/", "video/")):
        text = await extract_media(
            raw,
            filename,
            mime,
            kind,
            str(kb.team_id),
            receipt.vision_model_id,
            receipt.stt_model_id,
        )
        source["wechat_extraction"] = "model_media_extraction"
    elif doc_type:
        text, metadata = await document_processor.extract_text(original, doc_type)
        source.update(metadata)
    else:
        raise collection_error("wechat_type_unsupported")
    return text, filename, source


async def document_source_fields(name: str, metadata: dict, content_path: str) -> dict:
    """Keep source identity separate from the extracted Markdown representation."""
    if metadata.get("source_url"):
        return {
            "name": name[:255],
            "doc_type": DocumentType.URL.value,
            "file_path": None,
            "file_size": None,
        }
    original = metadata.get("wechat_original_path")
    original_name = metadata.get("wechat_original_name")
    if original and original_name:
        doc_type = document_processor.get_document_type(
            original_name, metadata.get("wechat_original_mime")
        )
        if doc_type:
            size = metadata.get("wechat_original_size")
            if size is None:
                size = len(await document_processor.read_file(original))
            return {
                "name": original_name[:255],
                "doc_type": doc_type,
                "file_path": original,
                "file_size": size,
            }
    return {
        "name": (name if name.lower().endswith(".md") else name[:252] + ".md")[:255],
        "doc_type": DocumentType.MD.value,
        "file_path": content_path,
    }


async def claim_document(
    receipt, item, kb, text: str, name: str, metadata: dict
) -> tuple[Document, bool]:
    await require_feature("wechat", "knowledge_collection")
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        raise collection_error("wechat_empty_content")
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    path = f"documents/{kb.id}/wechat/{item.id}/content.md"
    await save_content(path, normalized.encode())
    source_fields = await document_source_fields(name, metadata, path)
    async with in_transaction() as db:
        claim, _ = await WeChatKnowledgeContent.get_or_create(
            knowledge_base_id=kb.id, content_hash=digest, using_db=db
        )
        claim = (
            await WeChatKnowledgeContent.filter(id=claim.id)
            .using_db(db)
            .select_for_update()
            .get()
        )
        existing = (
            await Document.filter(id=claim.document_id).using_db(db).first()
            if claim.document_id
            else None
        )
        if existing and existing.status == "completed":
            item.document_id, item.status = existing.id, "duplicate"
            item.name = name[:255]
            item.content_hash = digest
            await item.save(using_db=db)
            return existing, True
        if (
            claim.owner_item_id
            and claim.owner_item_id != item.id
            and claim.lease_expires_at
            and claim.lease_expires_at > utcnow()
        ):
            raise CollectionBusy()
        if existing:
            # An expired owner may resume; both content hashes refer to the same
            # durable document, and the receipt lease guards its active writer.
            document = existing
        else:
            document = await Document.create(
                id=item.id,
                using_db=db,
                knowledge_base_id=kb.id,
                **{"file_size": len(normalized.encode()), **source_fields},
                source_url=metadata.get("source_url"),
                uploaded_by_id=receipt.user_id,
                metadata=metadata,
                status="pending",
            )
            await (
                KnowledgeBase.filter(id=kb.id)
                .using_db(db)
                .update(document_count=F("document_count") + 1)
            )
        item.document_id, item.name, item.content_hash = document.id, name[:255], digest
        await item.save(using_db=db)
        claim.document_id, claim.owner_item_id, claim.lease_expires_at = (
            document.id,
            item.id,
            utcnow() + LEASE,
        )
        await claim.save(using_db=db)
    return document, False


async def process_item(receipt, index: int, spec: dict):
    item, _ = await WeChatKnowledgeItem.get_or_create(
        receipt_id=receipt.id, item_index=index
    )
    if item.status in ("completed", "duplicate", "error"):
        return item
    binding, _, kb = await actor_target(receipt)
    async with WeChatClient(binding.base_url, decrypt_secret(binding.token)) as client:
        if item.document_id:
            document = await Document.get(id=item.document_id)
            duplicate = False
        else:
            text, name, metadata = await text_for_input(spec, receipt, kb, client, item)
            text = document_processor._clean_text(text)
            if not text.strip():
                raise collection_error("wechat_empty_content")
            await actor_target(receipt)
            digest = hashlib.sha256(
                text.replace("\r\n", "\n").strip().encode()
            ).hexdigest()
            async with collection_lock(f"content:{kb.id}:{digest}"):
                document, duplicate = await claim_document(
                    receipt, item, kb, text, name, metadata
                )
        if duplicate:
            await document_processor.delete_file(
                f"documents/{kb.id}/wechat/{item.id}/content.md"
            )
            return item
        async with collection_lock(f"document:{document.id}"):
            await actor_target(receipt)
            from app.tasks.knowledge_base import _process_document

            if document.status != "completed":
                await _process_document(str(document.id), None)
            await document.refresh_from_db()
            try:
                await actor_target(receipt)
            except BusinessError as exc:
                if exc.msg_key == "integration_feature_disabled":
                    raise
                document.status = "error"
                document.error_message = "wechat_target_unavailable"
                await document.save(update_fields=["status", "error_message"])
                raise
            if document.status != "completed" or document.chunk_count < 1:
                raise collection_error("wechat_index_failed")
            item.status = "completed"
            await item.save(update_fields=["status"])
            await WeChatKnowledgeContent.filter(
                document_id=document.id, owner_item_id=item.id
            ).update(lease_expires_at=None)
    return item


async def heartbeat(receipt_id, owner):
    while True:
        await asyncio.sleep(30)
        held = await WeChatKnowledgeReceipt.filter(
            id=receipt_id, lease_owner=owner
        ).update(lease_expires_at=utcnow() + LEASE)
        if not held:
            raise CollectionBusy()
        items = await WeChatKnowledgeItem.filter(
            receipt_id=receipt_id, status="pending"
        ).values_list("id", flat=True)
        if items:
            await WeChatKnowledgeContent.filter(owner_item_id__in=items).update(
                lease_expires_at=utcnow() + LEASE
            )


async def reply_result(receipt, payload):
    if "knowledge_collection" not in await enabled_features("wechat"):
        return
    if receipt.reply_status != "pending":
        return
    try:
        binding, user, kb = await actor_target(receipt)
        set_language(user.locale or "en")
    except BusinessError as exc:
        if exc.msg_key == "integration_feature_disabled":
            return
        # Loss of target permission must not expose titles or indexed content.
        binding = await WeChatKnowledgeBinding.filter(
            id=receipt.binding_id, status="connected"
        ).first()
        if not binding:
            return
        text = t("wechat_target_unavailable")
    else:
        lines = [t("wechat_reply_heading", name=kb.name)]
        for result in receipt.results:
            label = t("wechat_item_" + result["status"])
            lines.append(
                f"{label}: {result.get('name') or result['index'] + 1}"
                + (f" — {t(result['error'])}" if result.get("error") else "")
            )
        text = "\n".join(lines)[:3500]
    if not payload.get("context_token"):
        receipt.reply_status = "unavailable"
        await receipt.save(update_fields=["reply_status"])
        return
    # Commit before send. A crash/timeout after transmission is ambiguous, so a
    # terminal sending state is not automatically resent and cannot double-send.
    claimed = await WeChatKnowledgeReceipt.filter(
        id=receipt.id, reply_status="pending"
    ).update(reply_status="sending")
    if not claimed:
        return
    try:
        async with WeChatClient(
            binding.base_url, decrypt_secret(binding.token)
        ) as client:
            await require_feature("wechat", "knowledge_collection")
            await client.send_text(
                binding.wechat_user_id, text, payload["context_token"]
            )
        state = "submitted"
    except BusinessError as exc:
        if exc.msg_key == "integration_feature_disabled":
            await WeChatKnowledgeReceipt.filter(
                id=receipt.id, reply_status="sending"
            ).update(reply_status="pending")
            return
        state = "unknown"
    except Exception:
        state = "unknown"
    await WeChatKnowledgeReceipt.filter(id=receipt.id).update(reply_status=state)


async def process_receipt(receipt_id: str) -> dict:
    try:
        async with collection_lock(f"receipt:{receipt_id}"):
            return await _process_receipt(receipt_id)
    except CollectionBusy:
        return {"status": "busy"}


async def _process_receipt(receipt_id: str) -> dict:
    if "knowledge_collection" not in await enabled_features("wechat"):
        return {"status": "pending"}
    owner = uuid4()
    claimed = (
        await WeChatKnowledgeReceipt.filter(id=receipt_id)
        .filter(Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lt=utcnow()))
        .update(lease_owner=owner, lease_expires_at=utcnow() + LEASE)
    )
    if not claimed:
        return {"status": "busy"}
    receipt = await WeChatKnowledgeReceipt.get(id=receipt_id)
    beat = asyncio.create_task(heartbeat(receipt.id, owner))
    try:
        payload = json.loads(decrypt_secret(receipt.payload))
        if receipt.status in ("completed", "error"):
            await reply_result(receipt, payload)
            return {"status": receipt.status}
        binding, user, _ = await actor_target(receipt)
        set_language(user.locale or "en")
        receipt.status = "processing"
        await receipt.save(update_fields=["status", "updated_at"])
        results = []
        for index, spec in enumerate(split_items(payload)):
            try:
                item = await process_item(receipt, index, spec)
            except CollectionBusy:
                raise
            except (httpx.HTTPError, OSError) as exc:
                # Leave the receipt recoverable after infrastructure failures.
                raise CollectionBusy() from exc
            except Exception as exc:
                if (
                    isinstance(exc, BusinessError)
                    and exc.msg_key == "integration_feature_disabled"
                ):
                    raise
                item = await WeChatKnowledgeItem.get(
                    receipt_id=receipt.id, item_index=index
                )
                key = (
                    exc.msg_key
                    if isinstance(exc, BusinessError) and exc.msg_key
                    else "wechat_processing_failed"
                )
                if isinstance(exc, WeChatAPIError) and exc.code == "file_too_large":
                    key = "file_too_large"
                item.status, item.last_error = "error", key
                await item.save(update_fields=["status", "last_error"])
            results.append(
                {
                    "index": index,
                    "name": item.name,
                    "status": item.status,
                    "document_id": str(item.document_id) if item.document_id else None,
                    "item_id": str(item.id),
                    "has_original": bool(item.original_path),
                    "error": item.last_error,
                }
            )
            receipt.results = results
            await receipt.save(update_fields=["results", "updated_at"])
        receipt.status = (
            "error"
            if all(result["status"] == "error" for result in results)
            else "completed"
        )
        await receipt.save(update_fields=["status", "updated_at"])
        from app.services.audit_log import AuditLogService

        await AuditLogService.log(
            user=user,
            action="collect_wechat_content",
            resource_type="wechat_receipt",
            resource_id=receipt.id,
            resource_name=None,
            operation="create",
            status="success" if receipt.status == "completed" else "failed",
            metadata={
                "knowledge_base_id": str(receipt.knowledge_base_id),
                "items": len(results),
            },
        )
        await reply_result(receipt, payload)
        return {"status": receipt.status, "results": receipt.results}
    except CollectionBusy:
        return {"status": "pending"}
    except BusinessError as exc:
        if exc.msg_key == "integration_feature_disabled":
            return {"status": "pending"}
        receipt.status, receipt.last_error = (
            "error",
            exc.msg_key or "wechat_processing_failed",
        )
        await receipt.save(update_fields=["status", "last_error", "updated_at"])
        await reply_result(receipt, json.loads(decrypt_secret(receipt.payload)))
        return {"status": "error"}
    finally:
        beat.cancel()
        await asyncio.gather(beat, return_exceptions=True)
        await WeChatKnowledgeReceipt.filter(id=receipt.id, lease_owner=owner).update(
            lease_owner=None, lease_expires_at=None
        )
