"""Read Feishu document blocks and their authenticated media payloads."""

from __future__ import annotations

import base64
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from app.integrations.feishu import FeishuAPIError, FeishuClient
from app.integrations.feishu_content import (
    FeishuContent,
    UnsupportedContentError,
    content_limit_bytes,
    download_media,
    export_document,
)
from app.services import upload_gateway
from app.services.document_processor import (
    ALLOWED_MEDIA_MIME_TYPES,
    document_processor,
)


def _label(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def image_data_uri(content: bytes, content_type: str) -> str | None:
    mime = content_type.split(";", 1)[0].strip().lower()
    # Drive occasionally serves binary media with an octet-stream Content-Type.
    if mime == "application/octet-stream" or not mime:
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif content.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif content.startswith((b"GIF87a", b"GIF89a")):
            mime = "image/gif"
        elif content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            mime = "image/webp"
    if mime not in ALLOWED_MEDIA_MIME_TYPES:
        return None
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


async def extract_attachment_text(
    content: bytes, filename: str, content_type: str | None = None
) -> str | None:
    """Use the normal processor without allocating permanent document/media IDs.

    Embedded image data URIs deliberately remain in the returned Markdown. The
    importing document's staging transaction owns their eventual media assets.
    Unsupported binary formats are never decoded as if they were plain text.
    """
    doc_type = document_processor.get_document_type(filename, content_type)
    if doc_type is None:
        return None
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix
    path = f"documents/feishu-attachments/{uuid4().hex}{suffix}"
    try:
        if document_processor._remote_mode():
            async with upload_gateway.client() as gateway:
                response = await gateway.put(
                    "/internal/uploads/save", params={"key": path}, content=content
                )
                response.raise_for_status()
        else:
            await document_processor.save_file(content, path)
        text, _metadata = await document_processor.extract_text(
            path, doc_type, clean_text=False
        )
        return text
    finally:
        await document_processor.delete_file(path)


def _as_text_block(block: dict[str, Any], markdown: str) -> dict[str, Any]:
    # Retain IDs/children so the renderer still validates the complete block
    # graph, handles table cells/list nesting, and detects dangling children.
    return {
        **block,
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": markdown}}]},
    }


async def load_rich_content(
    client: FeishuClient, obj_type: str, token: str, title: str
) -> FeishuContent:
    # The documented export matrix includes doc/docx, not mindnote. The Docs
    # overview explicitly excludes Mindnote from the public API support scope:
    # https://open.feishu.cn/document/server-docs/docs/docs-overview
    if obj_type == "mindnote":
        raise UnsupportedContentError(
            "Feishu does not provide a public API to read or export Mindnote content"
        )
    if obj_type == "doc":
        exported = await export_document(client, token, "doc", "docx")
        return FeishuContent(f"{title}.docx", exported.content, exported.warnings)
    if obj_type != "docx":
        raise UnsupportedContentError(
            f"Unsupported Feishu rich content type: {obj_type}"
        )

    # Local import: feishu_knowledge dispatches back to this module.
    from app.services.feishu_knowledge import ImportProcessingError, blocks_to_markdown

    blocks = await client.get_docx_blocks(token)
    transformed: list[dict[str, Any]] = []
    warnings: list[str] = []
    media_cache: dict[str, tuple[bytes, str]] = {}
    limit = await content_limit_bytes()
    downloaded_bytes = 0
    files_by_id = {
        block.get("block_id"): block["file"]
        for block in blocks
        if block.get("block_type") == 23 and isinstance(block.get("file"), dict)
    }

    async def media(media_token: str) -> tuple[bytes, str]:
        nonlocal downloaded_bytes
        if media_token not in media_cache:
            payload = await download_media(client, media_token)
            downloaded_bytes += len(payload[0])
            if downloaded_bytes > limit:
                raise FeishuAPIError(
                    "Feishu document media exceeds the knowledge-base upload size limit"
                )
            media_cache[media_token] = payload
        return media_cache[media_token]

    async def attachment(file: dict[str, Any], block_id: str) -> str:
        media_token = file.get("token")
        if not isinstance(media_token, str) or not media_token:
            raise ImportProcessingError("Feishu attachment block has no media token")
        filename = str(file.get("name") or "Attachment")
        label = _label(filename)
        # Authentication and download errors must abort, not silently replace
        # revoked content with a successful partial import.
        content, mime = await media(media_token)
        image = image_data_uri(content, mime)
        if image is not None:
            return f"![{label}]({image})"
        try:
            text = await extract_attachment_text(content, filename, mime)
        except ValueError:
            warnings.append(f"attachment_extraction_failed:{block_id}")
            return f"Attachment: {label}\n\n[Attachment content could not be extracted; view the original document.]"
        if text is None:
            warnings.append(f"unsupported_attachment:{block_id}")
            return f"Attachment: {label}\n\n[This attachment format is not supported; view the original document.]"
        if not text.strip():
            warnings.append(f"empty_attachment:{block_id}")
            return f"Attachment: {label}\n\n[No extractable text was found in this attachment.]"
        return f"Attachment: {label}\n\n{text}"

    for block in blocks:
        block_id = str(block.get("block_id", ""))
        kind = block.get("block_type")
        if kind == 27:
            image = block.get("image")
            if (
                not isinstance(image, dict)
                or not isinstance(image.get("token"), str)
                or not image["token"]
            ):
                raise ImportProcessingError("Feishu image block has no media token")
            content, mime = await media(image["token"])
            uri = image_data_uri(content, mime)
            caption = image.get("caption") or {}
            label = _label(str(caption.get("content") or "Image"))
            if uri is None:
                warnings.append(f"unsupported_image:{block_id}")
                text = f"[Image {label} is in an unsupported format; view the original document.]"
            else:
                text = f"![{label}]({uri})"
            transformed.append(_as_text_block(block, text))
        elif kind == 23:
            file = block.get("file")
            if not isinstance(file, dict):
                raise ImportProcessingError(
                    "Feishu attachment block has no file payload"
                )
            transformed.append(_as_text_block(block, await attachment(file, block_id)))
        else:
            converted = block
            for key, value in block.items():
                if not isinstance(value, dict) or not isinstance(
                    value.get("elements"), list
                ):
                    continue
                elements = []
                changed = False
                for element in value["elements"]:
                    inline_file = element.get("file")
                    if isinstance(inline_file, dict):
                        source = files_by_id.get(inline_file.get("source_block_id"), {})
                        text = await attachment(
                            {**source, "token": inline_file.get("file_token")}, block_id
                        )
                        elements.append({"text_run": {"content": text}})
                        changed = True
                    else:
                        elements.append(element)
                if changed:
                    converted = {**converted, key: {**value, "elements": elements}}
            transformed.append(converted)

    markdown, block_warnings = blocks_to_markdown(transformed, title)
    content = markdown.encode("utf-8")
    if len(content) > limit:
        raise FeishuAPIError(
            "Feishu document content exceeds the knowledge-base upload size limit"
        )
    return FeishuContent(
        filename=f"{title}.md",
        content=content,
        warnings=list(dict.fromkeys([*warnings, *block_warnings])),
    )
