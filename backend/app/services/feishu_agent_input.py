"""Normalize Feishu message resources into private conversation attachments."""

import json
import mimetypes
from pathlib import PurePosixPath
from urllib.parse import quote

from app.models.asset import AssetScopeType, AssetSource, Asset
from app.schemas.agent import ChatRequest, FileUrl, ImageContent
from app.services.asset import asset_service
from app.services.wechat_agent_io import _store_upload


def parse_message(message: dict) -> tuple[str, list[dict]]:
    content = message.get("content") or {}
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return "", []
    if not isinstance(content, dict):
        return "", []
    kind = message.get("message_type")
    if kind == "text":
        return str(content.get("text") or "").strip(), []
    if kind in ("file", "image"):
        key = content.get("image_key" if kind == "image" else "file_key")
        return "", [
            {"kind": kind, "key": key, "name": content.get("file_name") or ""}
        ] if isinstance(key, str) and key else []
    if kind != "post":
        return "", []
    if "content" not in content:
        content = (
            content.get("zh_cn")
            or content.get("en_us")
            or next(iter(content.values()), {})
        )
    if not isinstance(content, dict):
        return "", []
    lines = [str(content.get("title") or "")]
    attachments = []
    for row in content.get("content") or []:
        texts = []
        for item in row:
            tag = item.get("tag")
            if tag in ("text", "a"):
                texts.append(str(item.get("text") or item.get("href") or ""))
            elif tag in ("img", "file"):
                kind = "image" if tag == "img" else "file"
                key = item.get("image_key" if kind == "image" else "file_key")
                if isinstance(key, str) and key:
                    attachments.append(
                        {"kind": kind, "key": key, "name": item.get("file_name") or ""}
                    )
        lines.append("".join(texts))
    for item in content.get("files") or []:
        key = item.get("file_key")
        if isinstance(key, str) and key and not item.get("is_folder"):
            if not any(attachment["key"] == key for attachment in attachments):
                attachments.append(
                    {"kind": "file", "key": key, "name": item.get("file_name") or ""}
                )
    return "\n".join(line for line in lines if line).strip(), attachments


async def prepare_input(receipt, session, agent, user, client):
    from app.services.feishu_agent_runtime import channel_error

    attachments = receipt.attachments or []
    if not attachments:
        return ChatRequest(message=receipt.text)
    if not agent.enable_attachments:
        raise channel_error("feishu_agent_attachments_disabled")
    config = agent.attachment_config or {}
    if len(attachments) > int(config.get("max_files") or 5):
        raise channel_error("feishu_agent_too_many_files")
    max_size = int(config.get("max_file_size") or 10 * 1024 * 1024)
    allowed = {str(ext).lower() for ext in config.get("allowed_extensions") or []}
    images, files = [], []
    for index, item in enumerate(attachments):
        key = (
            f"agent-attachments/{receipt.created_at:%Y/%m}/{receipt.id}-{index}-feishu"
        )
        asset = await Asset.filter(storage_key=key).first()
        if asset is None:
            raw, remote_name, mime = await client.download_message_resource(
                receipt.message_id, item["key"], kind=item["kind"], max_bytes=max_size
            )
            name = PurePosixPath(
                str(item.get("name") or remote_name or "attachment").replace("\\", "/")
            ).name
            if not PurePosixPath(name).suffix:
                name += mimetypes.guess_extension(mime) or ".bin"
            if allowed and PurePosixPath(name).suffix.lower() not in allowed:
                raise channel_error("feishu_agent_file_type_unsupported")
            await _store_upload(raw, key, mime)
            asset = await asset_service.register_bytes(
                storage_key=key,
                original_filename=name,
                content_type=mime,
                content=raw,
                source=AssetSource.UPLOAD,
                team_id=None,
                created_by_id=user.id,
                provenance={
                    "feishu_receipt_id": str(receipt.id),
                    "feishu_message_id": receipt.message_id,
                },
            )
        if asset.size > max_size:
            raise channel_error("feishu_agent_file_too_large")
        if (
            allowed
            and PurePosixPath(asset.original_filename).suffix.lower() not in allowed
        ):
            raise channel_error("feishu_agent_file_type_unsupported")
        ref = await asset_service.get_or_create_ref(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=session.conversation_id,
            asset=asset,
        )
        url = f"/api/v1/upload/files/{quote(asset.storage_key, safe='/')}"
        if item["kind"] == "image":
            images.append(ImageContent(asset_id=asset.id, asset_ref=ref.ref, url=url))
        else:
            files.append(
                FileUrl(
                    asset_id=asset.id,
                    asset_ref=ref.ref,
                    filename=asset.display_filename,
                    url=url,
                    size=asset.size,
                    mime_type=asset.content_type,
                )
            )
    return ChatRequest(
        message=receipt.text,
        images=images,
        file_urls=files,
        conversation_id=session.conversation_id,
    )
