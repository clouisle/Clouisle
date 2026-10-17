"""One-way Wiki imports with durable dispatch and rollback-safe replacement.

A source owns a PostgreSQL session advisory lock for its entire run. Dispatch has
an expiring five-minute lease, refreshed every minute; expiry never steals a live
session lock. Lost workers release their session and the dispatcher republishes
expired jobs. Per-document processing runs inside a transaction: staged chunks
are invisible to retrieval until promoted, and failure retains the old index.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
from pathlib import PurePosixPath
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator
from urllib.parse import quote
from uuid import UUID, uuid4

import asyncpg
import httpx
from tortoise import connections
from tortoise.expressions import Q
from tortoise.functions import Sum
from tortoise.transactions import in_transaction

from app.core.i18n import t
from app.integrations.credentials import IntegrationSecretError
from app.integrations.feishu import FeishuAPIError, FeishuClient
from app.integrations.feishu_content import (
    FeishuContent,
    UnsupportedContentError,
    download_file,
)
from app.services.feishu_rich_content import load_rich_content
from app.services.feishu_tabular import load_tabular
from app.models.feishu_knowledge import FeishuKnowledgeDocument, FeishuKnowledgeSource
from app.models.knowledge_base import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services.document_processor import document_processor
from app.services.integration_config import get_builtin_integration
from app.services.lexical_store import (
    delete_document as delete_lexical_document,
    index_document,
)
from app.services import upload_gateway

vectors = importlib.import_module("app.services.vector_store")

logger = logging.getLogger(__name__)
LEASE_SECONDS = 300
_SQLITE_LOCKS: dict[UUID, asyncio.Lock] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceBusyError(RuntimeError):
    pass


class ImportProcessingError(RuntimeError):
    pass


class _ImportIndexingError(ImportProcessingError):
    pass


def public_error(error: Exception) -> str:
    """Never expose raw responses, credentials, provider messages or request URLs."""
    if isinstance(error, FeishuAPIError):
        if error.code == 99991672:
            return t(
                "feishu_knowledge_missing_api_permissions",
                scopes=", ".join(error.required_scopes)
                or t("feishu_knowledge_required_scopes_unknown"),
            )
        if error.permission_denied:
            return t("feishu_knowledge_resource_access_denied")
        return t(
            "feishu_knowledge_api_error",
            code=str(error.code or "unknown"),
            status=str(error.status_code or "200"),
        )
    if isinstance(error, BusinessError):
        return t(error.msg_key or "feishu_knowledge_sync_failed")[:500]
    if isinstance(error, httpx.HTTPError):
        return t("feishu_knowledge_connection_failed")
    if isinstance(error, _ImportIndexingError):
        return t("feishu_knowledge_processing_failed")
    if isinstance(error, ImportProcessingError):
        return t("feishu_knowledge_conversion_failed")
    return t("feishu_knowledge_sync_failed")


async def configured_client() -> FeishuClient:
    try:
        integration = await get_builtin_integration("feishu")
    except ValueError as exc:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_not_configured"
        ) from exc
    if not integration.is_enabled:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_knowledge_disabled"
        )
    app_id = integration.config.get("app_id")
    secret = integration.credentials.get("app_secret")
    if not app_id or not secret:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_not_configured"
        )
    try:
        return FeishuClient(app_id, secret)
    except IntegrationSecretError as exc:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_not_configured"
        ) from exc


@asynccontextmanager
async def source_lock(source_id: UUID) -> AsyncIterator[None]:
    database = connections.get("default")
    if database.capabilities.dialect == "sqlite":
        # SQLite is a development/test backend; production uses session locks.
        lock = _SQLITE_LOCKS.setdefault(source_id, asyncio.Lock())
        if lock.locked():
            raise SourceBusyError()
        async with lock:
            yield
        return
    key = int.from_bytes(
        hashlib.sha256(f"feishu-wiki:{source_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    # Dedicated sessions avoid reserving every ORM pool slot when several
    # sources run concurrently; each source also needs ORM transactions.
    connection = await asyncpg.connect(
        host=database.host,
        port=database.port,
        user=database.user,
        password=database.password,
        database=database.database,
        server_settings=database.server_settings,
        **database.extra,
    )
    try:
        acquired = await connection.fetchval(
            "SELECT pg_try_advisory_lock($1::bigint)", key
        )
        if not acquired:
            raise SourceBusyError()
        yield
    finally:
        await connection.close()


async def get_source(source_id: UUID) -> FeishuKnowledgeSource:
    source = (
        await FeishuKnowledgeSource.filter(id=source_id)
        .prefetch_related("knowledge_base")
        .first()
    )
    if source is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="feishu_knowledge_source_not_found",
            status_code=404,
        )
    return source


def source_output(source: FeishuKnowledgeSource) -> dict[str, Any]:
    return {
        "id": str(source.id),
        "knowledge_base_id": str(source.knowledge_base_id),
        "knowledge_base_name": source.knowledge_base.name,
        "space_id": source.space_id,
        "space_name": (source.last_result or {}).get("space_name"),
        "name": source.name,
        "interval_minutes": source.interval_minutes,
        "is_enabled": source.is_enabled,
        "status": source.status,
        "last_synced_at": source.last_synced_at,
        "last_error": source.last_error,
        "last_result": source.last_result,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


async def queue_source(source_id: UUID) -> FeishuKnowledgeSource:
    from app.tasks.feishu_knowledge import sync_source_task

    async with source_lock(source_id):
        source = await get_source(source_id)
        if not source.is_enabled:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST, msg_key="feishu_knowledge_disabled"
            )
        if (
            source.status in ("queued", "running")
            and source.lease_expires_at
            and source.lease_expires_at > utcnow()
        ):
            return source
        token = uuid4()
        source.dispatch_token = token
        source.lease_expires_at = utcnow() + timedelta(seconds=LEASE_SECONDS)
        source.status = "queued"
        source.last_error = None
        await source.save()
        try:
            sync_source_task.apply_async(
                args=[str(source.id), str(token)], task_id=str(token)
            )
        except Exception as exc:
            await FeishuKnowledgeSource.filter(
                id=source.id, dispatch_token=token
            ).update(
                status="error",
                dispatch_token=None,
                lease_expires_at=None,
                last_error=t("feishu_knowledge_publish_failed"),
                next_sync_at=utcnow(),
            )
            raise BusinessError(
                code=ResponseCode.INTERNAL_ERROR,
                msg_key="feishu_knowledge_publish_failed",
                status_code=503,
            ) from exc
        return source


async def dispatch_due_sources() -> dict[str, int]:
    now = utcnow()
    candidates = await FeishuKnowledgeSource.filter(
        Q(is_enabled=True, next_sync_at__lte=now)
        | Q(is_enabled=True, next_sync_at__isnull=True)
        | Q(
            is_enabled=True, status__in=["queued", "running"], lease_expires_at__lte=now
        )
    ).values_list("id", flat=True)
    queued = failed = 0
    for source_id in candidates:
        try:
            await queue_source(source_id)
            queued += 1
        except SourceBusyError:
            continue
        except Exception:
            failed += 1
            logger.warning("Could not dispatch Feishu source %s", source_id)
    return {"queued": queued, "failed": failed}


async def _heartbeat(source_id: UUID, token: UUID) -> None:
    while True:
        await asyncio.sleep(60)
        await FeishuKnowledgeSource.filter(id=source_id, dispatch_token=token).update(
            lease_expires_at=utcnow() + timedelta(seconds=LEASE_SECONDS)
        )


def _inline(elements: list[dict[str, Any]]) -> str:
    parts = []
    for element in elements:
        run = element.get("text_run")
        if isinstance(run, dict):
            text = str(run.get("content", ""))
            style = run.get("text_element_style") or {}
            if style.get("inline_code"):
                text = "`" + text.replace("`", "\\`") + "`"
            else:
                if style.get("bold"):
                    text = f"**{text}**"
                if style.get("italic"):
                    text = f"*{text}*"
                if style.get("strikethrough"):
                    text = f"~~{text}~~"
            link = style.get("link") or {}
            if link.get("url"):
                url = str(link["url"]).replace(")", "%29").replace("\n", "")
                text = f"[{text}]({url})"
            parts.append(text)
        elif isinstance(element.get("mention_doc"), dict):
            mention = element["mention_doc"]
            parts.append(
                f"[{mention.get('title') or 'Document'}]({mention.get('url') or ''})"
            )
        elif isinstance(element.get("equation"), dict):
            parts.append("$" + str(element["equation"].get("content", "")) + "$")
        elif isinstance(element.get("mention_user"), dict):
            parts.append("@" + str(element["mention_user"].get("user_id", "user")))
        elif isinstance(element.get("reminder"), dict):
            reminder = element["reminder"]
            times = {}
            for key in ("expire_time", "notify_time"):
                value = reminder.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, str)):
                    raise ImportProcessingError("Invalid Feishu reminder timestamp")
                try:
                    times[key] = int(value)
                except ValueError as exc:
                    raise ImportProcessingError(
                        "Invalid Feishu reminder timestamp"
                    ) from exc
            # Feishu specifies milliseconds. Keep the raw values as well: some
            # existing documents contain out-of-range notification timestamps.
            try:
                date = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                    milliseconds=times["expire_time"]
                )
                label = date.isoformat(timespec="milliseconds")
            except OverflowError:
                label = str(times["expire_time"]) + " ms since Unix epoch"
            details = [f"{key}={value} ms" for key, value in times.items()]
            for key in ("is_notify", "is_whole_day"):
                value = reminder.get(key, False)
                if not isinstance(value, bool):
                    raise ImportProcessingError("Invalid Feishu reminder flag")
                details.append(f"{key}={str(value).lower()}")
            if reminder.get("create_user_id"):
                details.append("create_user_id=" + str(reminder["create_user_id"]))
            parts.append(
                _inline(
                    [
                        {
                            "text_run": {
                                "content": f"Reminder: {label} ({'; '.join(details)})",
                                "text_element_style": reminder.get("text_element_style")
                                or {},
                            }
                        }
                    ]
                )
            )
        else:
            raise ImportProcessingError("Unsupported Feishu inline element")
    return "".join(parts)


def blocks_to_markdown(
    blocks: list[dict[str, Any]], title: str
) -> tuple[str, list[str]]:
    """Render docx text, headings, lists, code, quotes, todos and tables."""
    by_id: dict[str, dict[str, Any]] = {}
    child_ids: set[str] = set()
    for block in blocks:
        block_id = block.get("block_id")
        if not isinstance(block_id, str) or block_id in by_id:
            raise ImportProcessingError("Invalid or repeated Feishu block ID")
        by_id[block_id] = block
        child_ids.update(block.get("children") or [])
        if block.get("block_type") == 31:
            child_ids.update((block.get("table") or {}).get("cells") or [])
    warnings: list[str] = []
    active: set[str] = set()
    rendered: set[str] = set()

    def render(block_id: str, depth: int = 0) -> str:
        if block_id not in by_id or block_id in active:
            raise ImportProcessingError("Incomplete or cyclic Feishu document blocks")
        if block_id in rendered:
            return ""
        active.add(block_id)
        rendered.add(block_id)
        block = by_id[block_id]
        kind = block.get("block_type")
        children = block.get("children") or []
        key = {
            1: "page",
            2: "text",
            12: "bullet",
            13: "ordered",
            14: "code",
            15: "quote",
            17: "todo",
            19: "callout",
        }.get(kind)
        if isinstance(kind, int) and 3 <= kind <= 11:
            key = f"heading{kind - 2}"
        value = block.get(key, {}) if key else {}
        text = _inline(value.get("elements") or []) if isinstance(value, dict) else ""
        if kind == 31:
            table = block.get("table") or {}
            columns = (table.get("property") or {}).get("column_size")
            cells = table.get("cells") or children
            if not isinstance(columns, int) or columns < 1 or len(cells) % columns:
                raise ImportProcessingError("Invalid Feishu table dimensions")
            values = [
                render(cell).strip().replace("\n", "<br>").replace("|", "\\|")
                for cell in cells
            ]
            rows = [
                "| " + " | ".join(values[i : i + columns]) + " |"
                for i in range(0, len(values), columns)
            ]
            if rows:
                rows.insert(1, "| " + " | ".join(["---"] * columns) + " |")
            result = "\n".join(rows)
        elif kind == 14:
            # Feishu language IDs are numeric; preserve code without guessing a language.
            fence = "````" if "```" in text else "```"
            result = f"{fence}\n{text.rstrip()}\n{fence}"
        else:
            if isinstance(kind, int) and 3 <= kind <= 11:
                text = "#" * min(kind - 2, 6) + " " + text
            elif kind in (12, 13, 17):
                prefix = "- " if kind == 12 else "1. "
                if kind == 17:
                    prefix = (
                        "- [x] " if (value.get("style") or {}).get("done") else "- [ ] "
                    )
                text = prefix + text
            elif kind in (15, 19):
                text = "> " + text.replace("\n", "\n> ")
            elif kind == 22:
                text = "---"
            elif kind not in (1, 2, 24, 25, 32, 34):
                warning = f"unsupported_block:{kind}"
                if warning not in warnings:
                    warnings.append(warning)
                text = f"[Feishu block type {kind} is not imported; view the original document.]"
            nested = [render(child, depth + 1) for child in children]
            if kind in (12, 13, 17):
                nested = [
                    "\n".join("  " + line for line in child.splitlines())
                    for child in nested
                ]
            result = "\n\n".join(part for part in [text, *nested] if part)
        active.remove(block_id)
        return result

    roots = [block_id for block_id in by_id if block_id not in child_ids]
    body = "\n\n".join(render(block_id) for block_id in roots)
    if len(rendered) != len(by_id):
        raise ImportProcessingError("Feishu document has unreachable blocks")
    if not body.strip():
        raise ImportProcessingError("Feishu document has no importable content")
    return f"# {title}\n\n{body.strip()}\n", warnings


async def _recount_kb(kb_id: UUID) -> None:
    totals = (
        await Document.filter(knowledge_base_id=kb_id)
        .annotate(chunks=Sum("chunk_count"), tokens=Sum("token_count"))
        .group_by("knowledge_base_id")
        .values("chunks", "tokens")
    )
    await KnowledgeBase.filter(id=kb_id).update(
        document_count=await Document.filter(knowledge_base_id=kb_id).count(),
        total_chunks=int((totals[0].get("chunks") if totals else 0) or 0),
        total_tokens=int((totals[0].get("tokens") if totals else 0) or 0),
    )


async def _delete_projection(
    kb: KnowledgeBase,
    *,
    document_id: UUID | None = None,
    chunk_ids: list[str] | None = None,
) -> None:
    """Strict Qdrant deletion: unlike legacy helpers, failure is not swallowed."""
    client = await vectors._get_qdrant_client()
    # First-import rollback can erase the KB dimension after vectors exist.
    # The persisted stage token identifies them across managed collections.
    collections = await client.get_collections()
    collection_names = [
        item.name
        for item in collections.collections
        if item.name.startswith(vectors.settings.QDRANT_COLLECTION_PREFIX + "_")
    ]
    if document_id:
        selector = vectors.qmodels.FilterSelector(
            filter=vectors.qmodels.Filter(
                must=[
                    vectors.qmodels.FieldCondition(
                        key="document_id",
                        match=vectors.qmodels.MatchValue(value=str(document_id)),
                    )
                ]
            )
        )
    else:
        if not chunk_ids:
            return
        selector = vectors.qmodels.PointIdsList(points=chunk_ids)
    for collection in collection_names:
        await client.delete(
            collection_name=collection, points_selector=selector, wait=True
        )


async def _delete_import_file(kb_id: UUID, path: str) -> None:
    # Managed filenames end in the staging UUID; it also owns extracted media.
    stage_id = UUID(PurePosixPath(path).stem.rsplit("_", 1)[-1])
    await document_processor.delete_media_assets(kb_id, stage_id)
    await document_processor.delete_file(path)


async def _promote_media(stage: Document, final_id: UUID) -> None:
    """Keep immutable staged media, exposing it through the stable document URL."""
    stage.metadata = dict(stage.metadata or {})
    stage.metadata["feishu_media_document_id"] = str(stage.id)
    if stage.id == final_id:
        return
    old = f"/documents/{stage.id}/media/"
    new = f"/documents/{final_id}/media/"
    stage.metadata = json.loads(json.dumps(stage.metadata).replace(old, new))
    for chunk in await DocumentChunk.filter(document_id=stage.id):
        chunk.content = chunk.content.replace(old, new)
        if chunk.metadata:
            chunk.metadata = json.loads(json.dumps(chunk.metadata).replace(old, new))
        await chunk.save(update_fields=["content", "metadata"])


async def _cleanup_pending(mapping: FeishuKnowledgeDocument, kb: KnowledgeBase) -> None:
    # Retag only after DB commit. Before then orphan vectors remain addressable
    # by the persisted stage UUID and cannot hydrate to uncommitted chunks.
    if (
        mapping.staging_document_id
        and not mapping.pending_file_path
        and mapping.document_id
    ):
        chunk_ids = [
            str(value)
            for value in await DocumentChunk.filter(
                document_id=mapping.document_id
            ).values_list("id", flat=True)
        ]
        if chunk_ids:
            dimension = await vectors.get_kb_embedding_dimension(kb.id)
            client = await vectors._get_qdrant_client()
            await client.set_payload(
                collection_name=vectors._collection_name(dimension),
                payload={"document_id": str(mapping.document_id)},
                points=chunk_ids,
                wait=True,
            )
        if mapping.staging_document_id == mapping.document_id:
            mapping.staging_document_id = None
    if mapping.staging_document_id:
        await _delete_projection(kb, document_id=mapping.staging_document_id)
    if mapping.cleanup_chunk_ids:
        await _delete_projection(kb, chunk_ids=mapping.cleanup_chunk_ids)
    for path in (mapping.pending_file_path, mapping.obsolete_file_path):
        if path:
            await _delete_import_file(kb.id, path)
    mapping.staging_document_id = None
    mapping.cleanup_chunk_ids = []
    mapping.pending_file_path = None
    mapping.obsolete_file_path = None
    await mapping.save()


async def remove_import(mapping: FeishuKnowledgeDocument, kb: KnowledgeBase) -> None:
    await _cleanup_pending(mapping, kb)
    if mapping.document_id:
        document = await Document.filter(id=mapping.document_id).first()
        if document:
            # Hide before touching external stores. Failed cleanup remains retryable.
            document.status = DocumentStatus.ERROR.value
            await document.save(update_fields=["status"])
            await _delete_projection(kb, document_id=document.id)
            await delete_lexical_document(document.id, kb.team_id)
            if document.file_path:
                await _delete_import_file(kb.id, document.file_path)
            await document.delete()
    mapping.document_id = None
    mapping.content_hash = None
    await mapping.save()
    await _recount_kb(kb.id)


async def _save_import_file(content: bytes, path: str) -> None:
    if document_processor._remote_mode():
        async with upload_gateway.client() as client:
            response = await client.put(
                "/internal/uploads/save", params={"key": path}, content=content
            )
            response.raise_for_status()
    else:
        await document_processor.save_file(content, path)


async def import_content(
    source: FeishuKnowledgeSource,
    mapping: FeishuKnowledgeDocument,
    node: dict[str, Any],
    content: FeishuContent,
) -> bool:
    """Run the existing KB pipeline, committing only a completely indexed result."""
    from app.tasks.knowledge_base import _process_document

    kb = await KnowledgeBase.get(id=source.knowledge_base_id)
    await _cleanup_pending(mapping, kb)
    doc_type = document_processor.get_document_type(content.filename)
    if not doc_type:
        raise UnsupportedContentError("Unsupported imported file format")
    digest = hashlib.sha256(content.content).hexdigest()
    original = (
        await Document.filter(id=mapping.document_id).first()
        if mapping.document_id
        else None
    )
    if (
        mapping.content_hash == digest
        and original
        and original.status == DocumentStatus.COMPLETED.value
    ):
        original.name = str(node.get("title") or source.name)[:255]
        original.metadata = {
            **(original.metadata or {}),
            "feishu_node_token": node["node_token"],
            "feishu_source_url": f"https://feishu.cn/wiki/{quote(node['node_token'], safe='')}",
        }
        await original.save(update_fields=["name", "metadata"])
        mapping.node_token = node["node_token"]
        mapping.last_error = None
        await mapping.save()
        return False
    stage_id = uuid4()
    file_path = document_processor.get_storage_path(kb.id, f"{stage_id}.{doc_type}")
    mapping.staging_document_id = stage_id
    mapping.pending_file_path = file_path
    await mapping.save()
    await _save_import_file(content.content, file_path)
    try:
        async with in_transaction() as connection:
            # Serialize cached KB counters with other successful imports.
            await (
                KnowledgeBase.filter(id=kb.id)
                .using_db(connection)
                .select_for_update()
                .get()
            )
            stage = await Document.create(
                id=stage_id,
                knowledge_base_id=kb.id,
                name=str(node.get("title") or content.filename)[:255],
                doc_type=doc_type,
                file_path=file_path,
                file_size=len(content.content),
                uploaded_by_id=None,
                metadata={
                    "clean_text": False,
                    "feishu_staging": True,
                    "feishu_source_id": str(source.id),
                    "feishu_read_only": True,
                    "feishu_obj_token": mapping.obj_token,
                    "feishu_obj_type": mapping.obj_type,
                    "feishu_node_token": node["node_token"],
                    "feishu_source_url": f"https://feishu.cn/wiki/{quote(node['node_token'], safe='')}",
                },
            )
            result = await _process_document(str(stage_id), None)
            await stage.refresh_from_db()
            failed = (
                await DocumentChunk.filter(document_id=stage_id)
                .exclude(status="embedded")
                .exists()
            )
            if (
                result.get("status") != "success"
                or stage.status != DocumentStatus.COMPLETED.value
                or failed
                or not stage.chunk_count
            ):
                raise _ImportIndexingError()
            # The existing pipeline allows deferred lexical repair. Imports do not
            # advertise success until its synchronous lexical write has succeeded.
            await _promote_media(stage, original.id if original else stage.id)
            stage.metadata = dict(stage.metadata or {})
            stage.metadata.pop("feishu_staging", None)
            await stage.save(update_fields=["metadata"])
            old_ids: list[str] = []
            old_path = None
            if original:
                old_ids = [
                    str(value)
                    for value in await DocumentChunk.filter(
                        document_id=original.id
                    ).values_list("id", flat=True)
                ]
                old_path = original.file_path
                await delete_lexical_document(original.id, kb.team_id)
                await DocumentChunk.filter(document_id=original.id).delete()
                await DocumentChunk.filter(document_id=stage_id).update(
                    document_id=original.id
                )
                for field in (
                    "name",
                    "doc_type",
                    "file_path",
                    "file_size",
                    "status",
                    "error_message",
                    "chunk_count",
                    "token_count",
                    "metadata",
                    "processed_at",
                ):
                    setattr(original, field, getattr(stage, field))
                await original.save()
                await delete_lexical_document(stage_id, kb.team_id)
                await stage.delete()
                final = original
            else:
                final = stage
            await index_document(final.id)
            mapping.document_id = final.id
            mapping.node_token = node["node_token"]
            mapping.content_hash = digest
            mapping.last_error = None
            mapping.pending_file_path = None
            mapping.obsolete_file_path = old_path
            # Retain stage id until external cleanup finishes. After promotion it
            # catches orphan projections left by a worker lost before commit.
            mapping.cleanup_chunk_ids = old_ids
            await mapping.save()
            await _recount_kb(kb.id)
    except Exception:
        # Rollback restores old chunks/status/lexical index. New vectors cannot
        # hydrate without committed chunks and are deleted on this/next run.
        await mapping.refresh_from_db()
        with suppress(Exception):
            await _cleanup_pending(mapping, kb)
        raise
    await _cleanup_pending(mapping, kb)
    return True


async def _scan_source(
    source: FeishuKnowledgeSource, client: FeishuClient
) -> dict[str, Any]:
    kb = await KnowledgeBase.filter(
        id=source.knowledge_base_id, status=KnowledgeBaseStatus.ACTIVE.value
    ).first()
    if kb is None:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_knowledge_target_unavailable"
        )
    result: dict[str, Any] = {
        "scan_complete": True,
        "scanned": 0,
        "indexed": 0,
        "unchanged": 0,
        "removed": 0,
        "failed": 0,
        "unsupported": 0,
        "errors": [],
        "skipped": [],
        "warnings": [],
    }
    previous_result = getattr(source, "last_result", None) or {}
    if previous_result.get("space_name"):
        result["space_name"] = previous_result["space_name"]
    try:
        nodes = await client.list_wiki_nodes(source.space_id)
    except FeishuAPIError as exc:
        if exc.permission_denied and exc.resource_scope == "wiki_space":
            for mapping in await FeishuKnowledgeDocument.filter(source_id=source.id):
                await remove_import(mapping, kb)
                mapping.last_error = public_error(exc)
                await mapping.save()
        raise
    # Inventory is complete before any unseen object can be removed.
    seen: set[tuple[str, str]] = set()
    for node in nodes:
        key = (str(node["obj_type"]), str(node["obj_token"]))
        if key in seen:
            continue
        seen.add(key)
        result["scanned"] += 1
        node_title = str(node.get("title") or "")
        mapping, _ = await FeishuKnowledgeDocument.get_or_create(
            source_id=source.id,
            obj_type=key[0],
            obj_token=key[1],
            defaults={"node_token": node["node_token"]},
        )
        if key[0] not in {"doc", "docx", "sheet", "bitable", "file"}:
            result["unsupported"] += 1
            mapping.last_error = None
            await mapping.save()
            if len(result["skipped"]) < 100:
                result["skipped"].append(
                    {
                        "node_token": node["node_token"],
                        "node_title": node_title,
                        "type": key[0],
                        "reason": t("feishu_knowledge_unsupported_type", type=key[0]),
                    }
                )
            continue
        try:
            title = str(node.get("title") or source.name)
            if key[0] in {"sheet", "bitable"}:
                content = await load_tabular(client, key[0], key[1], title)
            elif key[0] == "file":
                content = await download_file(client, key[1])
            else:
                content = await load_rich_content(client, key[0], key[1], title)
            warnings = content.warnings
            changed = await import_content(source, mapping, node, content)
            result["indexed" if changed else "unchanged"] += 1
            if warnings and len(result["warnings"]) < 100:
                result["warnings"].append(
                    {
                        "node_token": node["node_token"],
                        "node_title": node_title,
                        "blocks": warnings,
                    }
                )
        except UnsupportedContentError:
            result["unsupported"] += 1
            mapping.last_error = None
            await mapping.save(update_fields=["last_error"])
            if len(result["skipped"]) < 100:
                result["skipped"].append(
                    {
                        "node_token": node["node_token"],
                        "node_title": node_title,
                        "type": key[0],
                        "reason": t("feishu_knowledge_unsupported_type", type=key[0]),
                    }
                )
        except Exception as exc:
            if isinstance(exc, FeishuAPIError) and exc.permission_denied:
                await remove_import(mapping, kb)
                result["removed"] += 1
            mapping.last_error = public_error(exc)
            await mapping.save(update_fields=["last_error"])
            result["failed"] += 1
            if len(result["errors"]) < 100:
                result["errors"].append(
                    {
                        "node_token": node["node_token"],
                        "node_title": node_title,
                        "error": mapping.last_error,
                    }
                )
    for mapping in await FeishuKnowledgeDocument.filter(source_id=source.id):
        if (mapping.obj_type, mapping.obj_token) not in seen:
            try:
                await remove_import(mapping, kb)
                await mapping.delete()
                result["removed"] += 1
            except Exception as exc:
                result["failed"] += 1
                mapping.last_error = public_error(exc)
                await mapping.save(update_fields=["last_error"])
                if len(result["errors"]) < 100:
                    result["errors"].append(
                        {"node_token": mapping.node_token, "error": mapping.last_error}
                    )
    return result


async def sync_source(
    source_id: UUID | str, dispatch_token: UUID | str | None = None
) -> dict[str, Any]:
    source_id = UUID(str(source_id))
    try:
        async with source_lock(source_id):
            source = await get_source(source_id)
            token = UUID(str(dispatch_token)) if dispatch_token else uuid4()
            if dispatch_token and source.dispatch_token != token:
                return {"status": "stale"}
            if not source.is_enabled:
                source.status = "idle"
                source.dispatch_token = None
                source.lease_expires_at = None
                await source.save()
                return {"status": "disabled"}
            source.dispatch_token = token
            source.status = "running"
            source.lease_expires_at = utcnow() + timedelta(seconds=LEASE_SECONDS)
            await source.save()
            heartbeat = asyncio.create_task(_heartbeat(source_id, token))
            try:
                client = await configured_client()
                result = await _scan_source(source, client)
                status = "error" if result["failed"] else "success"
                error = (
                    t("feishu_knowledge_partial_failure") if status == "error" else None
                )
                source.last_synced_at = utcnow()
            except Exception as exc:
                status = "error"
                error = public_error(exc)
                result = {
                    "failed": 1,
                    "scan_complete": False,
                    "errors": [{"error": error}],
                }
                logger.warning(
                    "Feishu source %s failed (%s)", source_id, type(exc).__name__
                )
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
            source.status = status
            source.last_error = error
            source.last_result = result
            source.dispatch_token = None
            source.lease_expires_at = None
            source.next_sync_at = utcnow() + timedelta(minutes=source.interval_minutes)
            await source.save()
            return {"status": status, **result}
    except SourceBusyError:
        return {"status": "busy"}
    except BusinessError as exc:
        if exc.code == ResponseCode.NOT_FOUND:
            return {"status": "deleted"}
        raise


async def delete_source(source_id: UUID) -> None:
    async with source_lock(source_id):
        source = await get_source(source_id)
        # Persist pause before destructive work. If external cleanup fails, a
        # scheduled/redelivered task must not re-import partially deleted data.
        source.is_enabled = False
        source.dispatch_token = None
        source.lease_expires_at = None
        source.status = "idle"
        await source.save()
        kb = await KnowledgeBase.get(id=source.knowledge_base_id)
        for mapping in await FeishuKnowledgeDocument.filter(source_id=source_id):
            await remove_import(mapping, kb)
            await mapping.delete()
        await source.delete()
        await _recount_kb(kb.id)
