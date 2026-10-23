"""Input/output mapping between WeChat messages and one durable Agent run.

Inbound media becomes private, conversation-scoped Assets authorized exactly
like a web chat upload; outbound artifacts use the verified iLink CDN upload
protocol for image/video/file items and an authenticated web conversation link
only for content the protocol cannot carry. No reasoning or tool internals are
ever forwarded.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from urllib.parse import quote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.i18n import set_language
from app.integrations.credentials import decrypt_secret
from app.integrations.wechat import WeChatAPIError, WeChatClient
from app.models.agent import Agent, Message
from app.models.asset import Asset, AssetScopeType, AssetSource
from app.models.user import User
from app.models.integration_delivery import IntegrationDelivery
from app.models.wechat_agent import (
    WeChatAgentReceipt,
    WeChatAgentSession,
)
from app.schemas.agent import ChatRequest, FileUrl, ImageContent
from app.schemas.response import BusinessError, ResponseCode
from app.services.asset import asset_service
from app.services.channel_artifacts import (
    authorize_output_asset,
    read_asset_bytes,
    resolve_run_assets,
)
from app.services.wechat_connection import utcnow
from app.services.wechat_media import extract_media
from app.services.integration_features import enabled_features, require_feature

logger = logging.getLogger(__name__)

WECHAT_TEXT_LIMIT = 3500
WECHAT_MEDIA_LIMIT = 20 * 1024 * 1024
ATTACHMENT_CATEGORY = "agent-attachments"
SEND_LEASE_SECONDS = 600
CDN_MEDIA_IMAGE, CDN_MEDIA_VIDEO, CDN_MEDIA_FILE = 1, 2, 3
ITEM_TEXT, ITEM_IMAGE, ITEM_VOICE, ITEM_FILE, ITEM_VIDEO = 1, 2, 3, 4, 5


def io_error(key: str, status: int = 400) -> BusinessError:
    return BusinessError(
        code=ResponseCode.VALIDATION_ERROR, msg_key=key, status_code=status
    )


def chunk_text(text: str) -> list[str]:
    """Split text on UTF-8 boundaries without losing any content."""
    data = text.encode("utf-8")
    if len(data) <= WECHAT_TEXT_LIMIT:
        return [text] if text else []
    chunks: list[bytes] = []
    start = 0
    while start < len(data):
        end = min(start + WECHAT_TEXT_LIMIT, len(data))
        if end < len(data):
            while end > start and (data[end] & 0xC0) == 0x80:
                end -= 1
        chunks.append(data[start:end])
        start = end
    return [chunk.decode("utf-8") for chunk in chunks]


def split_items(payload: dict) -> list[dict]:
    """Classify one WeChat message into text, media or URL parts."""
    parts = payload.get("item_list") or []
    texts = [
        str((part.get("text_item") or {}).get("text") or "").strip()
        for part in parts
        if part.get("type") == ITEM_TEXT
    ]
    text = "\n\n".join(value for value in texts if value)
    attachments = [part for part in parts if part.get("type") != ITEM_TEXT]
    if attachments:
        return [
            {"kind": "media", "item": part, "caption": text} for part in attachments
        ]
    if text:
        return [{"kind": "text", "text": text}]
    return [{"kind": "unsupported"}]


def _sanitize_name(name: str, fallback: str) -> str:
    from pathlib import PurePosixPath

    cleaned = PurePosixPath(str(name or "").replace("\\", "/")).name
    cleaned = cleaned.strip()[:200]
    if cleaned in ("", ".", ".."):
        return fallback
    return cleaned


def _attachment_limits(agent: Agent) -> tuple[int, int, set[str]]:
    config = getattr(agent, "attachment_config", None) or {}
    try:
        max_size = int(config.get("max_file_size") or 10 * 1024 * 1024)
    except (TypeError, ValueError):
        max_size = 10 * 1024 * 1024
    try:
        max_files = int(config.get("max_files") or 5)
    except (TypeError, ValueError):
        max_files = 5
    allowed = {
        str(ext).lower()
        for ext in (config.get("allowed_extensions") or [])
        if str(ext).startswith(".")
    }
    return max_size, max_files, allowed


def _ensure_extension(name: str, content_type: str) -> str:
    from pathlib import PurePosixPath

    if PurePosixPath(name).suffix:
        return name
    from app.api.v1.endpoints.upload import MIME_TO_EXT

    return name + MIME_TO_EXT.get(content_type, ".bin")


async def _store_upload(content: bytes, storage_key: str, content_type: str) -> None:
    """Persist bytes through the same storage path web uploads use."""
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.services.document_processor import document_processor
    from app.services.upload_storage import get_upload_storage_backend

    if document_processor._remote_mode():
        from app.services import upload_gateway

        async with upload_gateway.client() as gateway:
            response = await gateway.put(
                "/internal/uploads/save", params={"key": storage_key}, content=content
            )
            response.raise_for_status()
        return
    storage = await get_upload_storage_backend(UPLOAD_ROOT)
    await storage.save(storage_key, content, content_type=content_type)


async def _save_asset(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    user: User,
    receipt: WeChatAgentReceipt,
    index: int,
) -> Asset:
    """Register one immutable inbound original under a deterministic key.

    The storage key is derived from the durable receipt and the item index, so
    a retried normalization reuses the same private Asset instead of creating
    a duplicate. The original bytes are never rewritten.
    """
    from pathlib import PurePosixPath

    from app.api.v1.endpoints.upload import _validate_path_segment

    safe_name = _validate_path_segment(
        PurePosixPath(filename).name[:120] or "original", "filename"
    )
    created = receipt.created_at or utcnow()
    date_path = created.strftime("%Y/%m")
    # The existing GET route serves exactly category/YYYY/MM/filename, so the
    # deterministic identity lives in the filename itself.
    filename_key = f"{receipt.id}-{index}-{safe_name}"
    storage_key = f"{ATTACHMENT_CATEGORY}/{date_path}/{filename_key}"
    checksum = hashlib.sha256(content).hexdigest()
    existing = await Asset.filter(storage_key=storage_key).first()
    if existing is not None:
        if existing.checksum != checksum:
            raise io_error("wechat_agent_media_unsupported")
        return existing
    await _store_upload(content, storage_key, content_type)
    return await asset_service.register_bytes(
        storage_key=storage_key,
        original_filename=filename,
        content_type=content_type,
        content=content,
        source=AssetSource.UPLOAD,
        team_id=None,
        created_by_id=user.id,
        provenance={
            "wechat_receipt_id": str(receipt.id),
            "wechat_message_id": receipt.message_id,
            "wechat_item_index": index,
        },
    )


async def _retain_original(
    raw: bytes,
    filename: str,
    mime: str,
    receipt: WeChatAgentReceipt,
    user: User,
    index: int,
    kind: int,
) -> Asset:
    """Keep every inbound original as a private Asset, even when transcribed."""
    name = _ensure_extension(_sanitize_name(filename, f"wechat-{kind}.bin"), mime)
    return await _save_asset(
        raw, filename=name, content_type=mime, user=user, receipt=receipt, index=index
    )


async def _register_inbound_media(
    item: dict,
    *,
    agent: Agent,
    user: User,
    receipt: WeChatAgentReceipt,
    index: int,
    raw: tuple[bytes, str, str],
) -> Asset:
    kind = item.get("type")
    _, _, allowed = _attachment_limits(agent)
    if kind not in (ITEM_IMAGE, ITEM_FILE, ITEM_VIDEO):
        raise io_error("wechat_agent_media_unsupported")
    content, filename, mime = raw
    filename = _ensure_extension(_sanitize_name(filename, f"wechat-{kind}.bin"), mime)
    if allowed:
        from pathlib import PurePosixPath

        if PurePosixPath(filename).suffix.lower() not in allowed:
            raise io_error("wechat_agent_file_type_unsupported")
    if (kind == ITEM_IMAGE or mime.startswith("image/")) and not (
        await _agent_supports_vision(agent)
    ):
        raise io_error("wechat_agent_vision_required")
    return await _save_asset(
        content,
        filename=filename,
        content_type=mime,
        user=user,
        receipt=receipt,
        index=index,
    )


async def _agent_supports_vision(agent: Agent) -> bool:
    """Vision capability comes from the Agent's resolved authorized chat model."""
    from app.api.v1.endpoints.chat_helpers.model_utils import resolve_agent_chat_model

    try:
        resolution = await resolve_agent_chat_model(agent)
    except BusinessError:
        return False
    return resolution.supports_vision


async def _agent_vision_model_id(agent: Agent) -> str | None:
    """Resolve the Agent's authorized chat model id for vision extraction."""
    from app.api.v1.endpoints.chat_helpers.model_utils import resolve_agent_chat_model

    try:
        resolution = await resolve_agent_chat_model(agent)
    except BusinessError:
        return None
    return resolution.model_id if resolution.supports_vision else None


async def _transcribe_voice(
    path_bytes: bytes, filename: str, team_id: str, stt_model_id
) -> str:
    """Convert the downloaded voice media to MP3, then transcribe it."""
    import shutil
    import tempfile
    from pathlib import Path

    from app.services.wechat_media import audio_text, run_media_tool

    if not stt_model_id:
        raise io_error("wechat_stt_required")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise io_error("wechat_agent_media_unsupported")
    with tempfile.TemporaryDirectory(prefix="clouisle-agent-voice-") as temporary:
        root = Path(temporary)
        source = root / ("input" + Path(filename).suffix)
        source.write_bytes(path_bytes)
        audio = root / "audio.mp3"
        await run_media_tool(
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "48k",
            str(audio),
        )
        return await audio_text(audio, team_id, str(stt_model_id))


async def normalize_input(
    receipt: WeChatAgentReceipt,
    session: WeChatAgentSession,
    agent: Agent,
    user: User,
    client: WeChatClient,
):
    """Turn one durable WeChat receipt into a ChatRequest for the Agent runtime."""
    if not session.conversation_id:
        raise io_error("wechat_agent_conversation_missing")
    payload = json.loads(decrypt_secret(receipt.payload))
    if not getattr(agent, "enable_attachments", False):
        if any(
            part.get("type") != ITEM_TEXT for part in payload.get("item_list") or []
        ):
            raise io_error("wechat_agent_attachments_disabled")
    texts: list[str] = []
    images: list[ImageContent] = []
    files: list[FileUrl] = []
    max_size, max_files, _ = _attachment_limits(agent)
    media_count = 0
    caption_used = False
    specs = []
    messages = payload.get("batch_messages") or [payload]
    identifiers = payload.get("batch_receipt_ids") or [str(receipt.id)]
    for identifier, message in zip(identifiers, messages, strict=True):
        source = (
            receipt
            if identifier == str(receipt.id)
            else await WeChatAgentReceipt.get(id=identifier)
        )
        specs.extend(
            (source, index, spec) for index, spec in enumerate(split_items(message))
        )
    previous_source = None
    for source, position, spec in specs:
        if source.id != previous_source:
            caption_used = False
            previous_source = source.id
        if spec["kind"] == "unsupported":
            raise io_error("wechat_agent_media_unsupported")
        if spec["kind"] == "text":
            texts.append(spec["text"])
            continue
        item = spec["item"]
        kind = item.get("type")
        if kind not in (ITEM_IMAGE, ITEM_VOICE, ITEM_FILE, ITEM_VIDEO):
            raise io_error("wechat_agent_media_unsupported")
        if media_count >= max_files:
            raise io_error("wechat_agent_too_many_files")
        media_count += 1
        caption = spec.get("caption") or ""
        if kind == ITEM_VOICE:
            voice = item.get("voice_item") or {}
            transcript = str(voice.get("text") or "").strip()
            if transcript:
                # WeChat already transcribed this voice: no download needed.
                texts.append(transcript)
                if caption and not caption_used:
                    texts.append(caption)
                    caption_used = True
                continue
        raw, filename, mime = await client.download_media(item, max_size)
        if len(raw) > max_size:
            raise io_error("wechat_agent_file_too_large")
        if kind == ITEM_VOICE:
            # The original voice stays a private Asset even when only the
            # transcript is forwarded to the model.
            await _retain_original(raw, filename, mime, source, user, position, kind)
            texts.append(
                await _transcribe_voice(
                    raw, filename, str(agent.team_id), receipt.stt_model_id
                )
            )
            if caption and not caption_used:
                texts.append(caption)
                caption_used = True
            continue
        if kind == ITEM_VIDEO:
            vision_model_id = await _agent_vision_model_id(agent)
            if vision_model_id is None:
                raise io_error("wechat_agent_video_unsupported")
            await _retain_original(raw, filename, mime, source, user, position, kind)
            try:
                texts.append(
                    await extract_media(
                        raw,
                        filename,
                        mime,
                        ITEM_VIDEO,
                        str(agent.team_id),
                        vision_model_id,
                        receipt.stt_model_id,
                    )
                )
            except BusinessError as exc:
                raise io_error(exc.msg_key or "wechat_agent_video_unsupported") from exc
            if caption and not caption_used:
                texts.append(caption)
                caption_used = True
            continue
        asset = await _register_inbound_media(
            item,
            agent=agent,
            user=user,
            receipt=source,
            index=position,
            raw=(raw, filename, mime),
        )
        binding = await asset_service.get_or_create_ref(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=session.conversation_id,
            asset=asset,
        )
        url = f"/api/v1/upload/files/{quote(asset.storage_key, safe='/')}"
        if asset.content_type.lower().startswith("image/"):
            images.append(
                ImageContent(asset_id=asset.id, asset_ref=binding.ref, url=url)
            )
        else:
            files.append(
                FileUrl(
                    asset_id=asset.id,
                    asset_ref=binding.ref,
                    filename=asset.display_filename,
                    url=url,
                    size=asset.size,
                    mime_type=asset.content_type,
                )
            )
        if caption and not caption_used:
            texts.append(caption)
            caption_used = True
    message = "\n\n".join(value for value in texts if value).strip()
    return ChatRequest(
        message=message,
        images=images,
        file_urls=files,
        conversation_id=session.conversation_id,
        variables=receipt.variables or {},
    )


async def build_output(run, receipt, session, user) -> list[dict]:
    """Build WeChat delivery payloads for a terminal run's visible output."""
    payloads: list[dict] = []
    canonical = await Message.get_or_none(id=run.canonical_message_id)
    text = (
        (canonical.content or "").strip()
        if canonical is not None and canonical.conversation_id == run.conversation_id
        else ""
    )
    if text:
        payloads.extend({"kind": "text", "text": chunk} for chunk in chunk_text(text))
    agent = await Agent.filter(id=run.agent_id).first()
    if agent is not None:
        for asset in await resolve_run_assets(run, agent, user):
            payloads.append(
                {
                    "kind": "asset",
                    "asset_id": str(asset.id),
                    "filename": asset.display_filename,
                    "content_type": asset.content_type,
                    "size": asset.size,
                    "origin": "generated",
                }
            )
    return payloads


def _media_item_type(content_type: str) -> tuple[int, int, str]:
    lowered = content_type.lower()
    if lowered.startswith("image/"):
        return ITEM_IMAGE, CDN_MEDIA_IMAGE, "image_item"
    if lowered.startswith("video/"):
        return ITEM_VIDEO, CDN_MEDIA_VIDEO, "video_item"
    return ITEM_FILE, CDN_MEDIA_FILE, "file_item"


def _encrypt_media(content: bytes) -> tuple[bytes, str, str]:
    key = secrets.token_bytes(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(content) + padder.finalize()
    # iLink CDN media must be AES-128-ECB + PKCS7; the key is fresh per upload.
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return ciphertext, key.hex(), hashlib.md5(content).hexdigest()


async def _upload_asset_media(
    client: WeChatClient, asset: Asset, to_user_id: str
) -> dict:
    """Upload authorized Asset bytes and build the iLink media item.

    Implements the verified CDN protocol: reserve a slot, AES-128-ECB encrypt
    with PKCS7 padding, POST the ciphertext, then reference the returned
    download parameter inside the typed item.
    """
    content = await read_asset_bytes(asset)
    if not content:
        raise WeChatAPIError("empty_media")
    if len(content) > WECHAT_MEDIA_LIMIT:
        raise WeChatAPIError("file_too_large")
    ciphertext, aeskey_hex, raw_md5 = _encrypt_media(content)
    filekey = secrets.token_bytes(16).hex()
    item_type, media_type, shape = _media_item_type(asset.content_type)
    upload_url, _ = await client.get_upload_url(
        filekey=filekey,
        media_type=media_type,
        to_user_id=to_user_id,
        raw_size=len(content),
        raw_file_md5=raw_md5,
        file_size=len(ciphertext),
        aeskey=aeskey_hex,
    )
    download_param = await client.upload_media(upload_url, ciphertext)
    media = {
        "encrypt_query_param": download_param,
        "aes_key": base64.b64encode(aeskey_hex.encode("ascii")).decode(),
        "encrypt_type": 1,
    }
    if shape == "image_item":
        item = {
            "type": item_type,
            "image_item": {"media": media, "mid_size": len(ciphertext)},
        }
    elif shape == "video_item":
        item = {
            "type": item_type,
            "video_item": {"media": media, "video_size": len(ciphertext)},
        }
    else:
        item = {
            "type": item_type,
            "file_item": {
                "media": media,
                "file_name": asset.display_filename,
                "len": str(len(content)),
            },
        }
    return item


async def _binding_row(binding_id):
    from app.models.wechat_knowledge import WeChatKnowledgeBinding

    return await WeChatKnowledgeBinding.filter(id=binding_id).first()


async def _reload_user(user_id):
    from app.models.user import User

    return await User.filter(id=user_id).first()


async def _delivery_context(
    binding, delivery: IntegrationDelivery, receipt: WeChatAgentReceipt, user
):
    """Resolve and reauthorize the exact context for one delivery row.

    Each row belongs to a receipt whose agent, conversation and session may
    differ from the binding's current configuration, so everything is resolved
    from durable rows and rechecked before every send.
    """
    current = await _binding_row(binding.id) if binding is not None else None
    if (
        current is None
        or current.status != "connected"
        or current.user_id != receipt.user_id
    ):
        return None, "wechat_agent_binding_disconnected"
    if current.disconnected_at and receipt.created_at <= current.disconnected_at:
        return None, "wechat_agent_binding_disconnected"
    fresh_user = await _reload_user(receipt.user_id)
    if (
        fresh_user is None
        or not fresh_user.is_active
        or getattr(fresh_user, "approval_status", "approved") != "approved"
    ):
        return None, "wechat_agent_binding_disconnected"
    agent_id = receipt.agent_id
    if not agent_id:
        return None, "wechat_agent_config_missing"
    from app.services.wechat_purpose import authorized_agent

    try:
        agent = await authorized_agent(agent_id, fresh_user)
    except BusinessError as exc:
        return None, exc.msg_key or "agent_access_denied"
    if agent.status != "published":
        return None, "agent_access_denied"
    session = await WeChatAgentSession.filter(
        binding_id=receipt.binding_id, agent_id=agent_id
    ).first()
    conversation_id = None
    if receipt.run_id:
        run = await _run_row(receipt.run_id)
        conversation_id = run.conversation_id if run else None
    if conversation_id is None and session is not None:
        conversation_id = session.conversation_id
    if not conversation_id:
        return None, "wechat_agent_conversation_missing"
    if not session or not session.context_token:
        return None, "wechat_agent_context_missing"
    return (
        {
            "binding": current,
            "user": fresh_user,
            "agent": agent,
            "agent_id": agent_id,
            "session": session,
            "conversation_id": conversation_id,
            "context_token": decrypt_secret(session.context_token),
        },
        "",
    )


async def _run_row(run_id):
    from app.models.agent_run import AgentRun

    return await AgentRun.filter(id=run_id).first()


async def _send_payload(
    client: WeChatClient,
    payload: dict,
    context,
    client_id: str,
    binding,
) -> None:
    await require_feature("wechat", "agent_chat")
    kind = payload.get("kind")
    to_user = binding.wechat_user_id
    context_token = context["context_token"]
    if kind == "asset":
        asset = await authorize_output_asset(
            payload.get("asset_id"),
            conversation_id=context["conversation_id"],
            agent=context["agent"],
            user=context["user"],
        )
        if asset is None:
            raise WeChatAPIError("asset_unavailable")
        item = await _upload_asset_media(client, asset, to_user)
        await require_feature("wechat", "agent_chat")
        await client.send_media(to_user, context_token, item=item, client_id=client_id)
        return
    await client.send_text(
        to_user, str(payload.get("text") or ""), context_token, client_id=client_id
    )


async def _send_one(delivery: IntegrationDelivery, binding) -> None:
    if "agent_chat" not in await enabled_features("wechat"):
        await IntegrationDelivery.filter(id=delivery.id, status="sending").update(
            status="pending"
        )
        return
    receipt = await WeChatAgentReceipt.filter(id=delivery.receipt_id).first()
    if receipt is None:
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="unavailable", error="wechat_agent_binding_disconnected"
        )
        return
    context, key = await _delivery_context(binding, delivery, receipt, None)
    if context is None:
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="unavailable", error=key
        )
        return
    client_id = str(delivery.id)
    try:
        async with WeChatClient(
            context["binding"].base_url,
            decrypt_secret(context["binding"].token),
        ) as client:
            await _send_payload(
                client, delivery.payload or {}, context, client_id, context["binding"]
            )
    except asyncio.CancelledError:
        raise
    except (TimeoutError, asyncio.TimeoutError) as exc:
        from app.services.delivery_errors import error_detail

        # A crash or timeout after transmission is ambiguous: never blind-resend.
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="unknown", error_detail=error_detail(exc)
        )
        return
    except WeChatAPIError as exc:
        from app.services.delivery_errors import error_detail

        detail = error_detail(exc)
        cause = exc.__cause__
        if isinstance(cause, (TimeoutError, asyncio.TimeoutError)) or (
            cause is not None and cause.__class__.__name__ == "TimeoutException"
        ):
            # The request may already have reached WeChat: outcome is unknown.
            await IntegrationDelivery.filter(id=delivery.id).update(
                status="unknown", error_detail=detail
            )
            return
        code = exc.code if isinstance(exc.code, str) else str(exc.code)
        await IntegrationDelivery.filter(id=delivery.id).update(
            status="error", error=code, error_detail=detail
        )
        return
    except BusinessError as exc:
        if exc.msg_key == "integration_feature_disabled":
            await IntegrationDelivery.filter(id=delivery.id, status="sending").update(
                status="pending"
            )
            return
        from app.services.delivery_errors import error_detail

        await IntegrationDelivery.filter(id=delivery.id).update(
            status="error",
            error=exc.msg_key or "wechat_agent_media_unsupported",
            error_detail=error_detail(exc),
        )
        return
    await IntegrationDelivery.filter(id=delivery.id).update(
        status="sent", error=None, error_detail=None
    )


async def deliver_pending(binding, user) -> None:
    """Claim and send pending deliveries for one binding, one ACL check each.

    The user only seeds the locale; every row resolves its own receipt,
    session, conversation and credential so an older Agent's result is never
    sent through a newer session's conversation.
    """
    if "agent_chat" not in await enabled_features("wechat"):
        return
    set_language(getattr(user, "locale", None) or "en")
    from datetime import timedelta

    from tortoise.expressions import Q

    lease_cutoff = utcnow() - timedelta(seconds=SEND_LEASE_SECONDS)
    receipt_ids = await WeChatAgentReceipt.filter(binding_id=binding.id).values_list(
        "id", flat=True
    )
    if not receipt_ids:
        return
    # Only rows that still need action are loaded: a submitted, errored or
    # unavailable row is terminal and must never be rescanned every pass.
    rows = (
        await IntegrationDelivery.filter(
            provider_type="wechat", receipt_id__in=list(receipt_ids)
        )
        .filter(Q(status="pending") | Q(status="sending", updated_at__lt=lease_cutoff))
        .order_by("created_at", "sequence")
    )
    for row in rows:
        if row.status == "sending" and row.updated_at < lease_cutoff:
            # A crash left the claim behind: the outcome is unknown, so the row
            # is never blind-resent.
            await IntegrationDelivery.filter(
                id=row.id, status="sending", updated_at__lt=lease_cutoff
            ).update(status="unknown")
            continue
        if row.status != "pending":
            continue
        claimed = await IntegrationDelivery.filter(id=row.id, status="pending").update(
            status="sending"
        )
        if not claimed:
            continue
        await _send_one(row, binding)
