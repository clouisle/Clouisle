"""Authorized, ephemeral multimodal views of scoped Assets."""

from __future__ import annotations

import base64
import json
import math
from typing import Any
from uuid import UUID

from app.llm.capabilities import get_effective_input_capabilities, normalize_mime_type
from app.llm.errors import InvalidRequestError
from app.llm.types import (
    AudioContent,
    ContentPart,
    ContentType,
    FileContent,
    ImageContent,
    VideoContent,
)
from app.models.asset import Asset, AssetScopeType
from app.services.asset import asset_service
from app.services.asset_access import resolve_authorized_asset_ref
from app.services.file_parser import FileParseConfig, file_parser_service

MAX_VIEW_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
MAX_SELECTION_SECONDS = 600


async def resolve_view_content(
    ref: str,
    *,
    scope_type: AssetScopeType,
    scope_id: UUID,
    user: Any,
    model_config: Any,
    agent: Any,
    extracted_text: bool = False,
    input_capabilities: Any = None,
    selection: dict[str, Any] | None = None,
    materialize: bool = True,
) -> tuple[Asset, ContentPart | None, str]:
    """Authorize a scoped ref and build native adapter content ephemerally."""
    from app.api.v1.endpoints.upload import UPLOAD_ROOT
    from app.services.upload_storage import get_upload_storage_backend

    asset = await resolve_authorized_asset_ref(
        ref,
        scope_type=scope_type,
        scope_id=scope_id,
        user=user,
        expected_team_id=getattr(agent, "team_id", None),
    )
    if scope_type == AssetScopeType.CONVERSATION:
        from app.models.asset import MessageAsset

        links = MessageAsset.filter(
            asset_id=asset.id, message__conversation_id=scope_id
        )
        if (
            await links.exists()
            and not await links.filter(message__is_active=True).exists()
        ):
            raise InvalidRequestError(
                "Asset is not available on the current conversation branch"
            )
    raw_mime_type = asset.content_type.split(";", 1)[0].strip().lower()
    modality = (
        ContentType.IMAGE
        if raw_mime_type.startswith("image/")
        else ContentType.AUDIO
        if raw_mime_type.startswith("audio/")
        else ContentType.VIDEO
        if raw_mime_type.startswith("video/")
        else ContentType.FILE
        if raw_mime_type == "application/pdf"
        else None
    )
    mime_type = (
        normalize_mime_type(raw_mime_type, modality, model_config)
        if modality
        else raw_mime_type
    )
    modality = (
        ContentType.IMAGE
        if mime_type.startswith("image/")
        else ContentType.AUDIO
        if mime_type.startswith("audio/")
        else ContentType.VIDEO
        if mime_type.startswith("video/")
        else ContentType.FILE
        if mime_type == "application/pdf"
        else None
    )
    can_extract = "parse" in asset_service.capabilities(asset)
    capabilities = input_capabilities or get_effective_input_capabilities(model_config)
    if extracted_text:
        if not can_extract:
            raise InvalidRequestError(f"Asset cannot be extracted as text: {mime_type}")
        modality = ContentType.TEXT
    elif (
        modality == ContentType.FILE
        and modality not in capabilities.modalities
        and can_extract
    ):
        # Preserve document attachment behavior on adapters without native file input.
        extracted_text = True
        modality = ContentType.TEXT
    elif modality is None and can_extract:
        # Text and office documents have no native multimodal serializer.
        extracted_text = True
        modality = ContentType.TEXT
    elif modality is None:
        raise InvalidRequestError(f"Unsupported asset MIME type {mime_type}")
    if modality not in capabilities.modalities:
        raise InvalidRequestError(
            f"Model adapter does not support {modality.value} input"
        )
    limits = capabilities.limits.get(modality)
    max_bytes = (
        min(MAX_VIEW_BYTES, limits.max_bytes)
        if limits and limits.max_bytes
        else MAX_VIEW_BYTES
    )
    if asset.size > max_bytes:
        raise InvalidRequestError("Asset exceeds model input byte limit")
    selection_used: dict[str, Any] | None = None
    content: bytes | None = None
    if selection is not None:
        if not isinstance(selection, dict):
            raise InvalidRequestError("Selection must be an object")
        if modality not in {
            ContentType.AUDIO,
            ContentType.VIDEO,
            ContentType.FILE,
        } and not (modality == ContentType.TEXT and raw_mime_type == "application/pdf"):
            raise InvalidRequestError(
                "Selection is supported only for audio, video, or documents"
            )
        if (
            modality in {ContentType.FILE, ContentType.TEXT}
            and raw_mime_type == "application/pdf"
        ):
            page_start = selection.get("page_start")
            page_end = selection.get("page_end")
            if (
                type(page_start) is not int
                or type(page_end) is not int
                or page_start < 1
                or page_end < page_start
            ):
                raise InvalidRequestError(
                    "Document selection requires valid page_start and page_end"
                )
            if page_end - page_start >= 50:
                raise InvalidRequestError("Document selection cannot exceed 50 pages")
            selection_used = {"page_start": page_start, "page_end": page_end}
        else:
            start = selection.get("start_seconds", 0)
            end = selection.get("end_seconds")
            if (
                not isinstance(start, (int, float))
                or isinstance(start, bool)
                or not math.isfinite(start)
                or start < 0
            ):
                raise InvalidRequestError(
                    "Selection start_seconds must be finite and non-negative"
                )
            if (
                not isinstance(end, (int, float))
                or isinstance(end, bool)
                or not math.isfinite(end)
                or end <= start
            ):
                raise InvalidRequestError(
                    "Selection end_seconds must be finite and greater than start_seconds"
                )
            if end - start > MAX_SELECTION_SECONDS:
                raise InvalidRequestError(
                    f"Selection cannot exceed {MAX_SELECTION_SECONDS} seconds"
                )
            selection_used = {"start_seconds": start, "end_seconds": end}
            mime_type = "audio/mp4" if modality == ContentType.AUDIO else "video/mp4"
    accepted = capabilities.mime_types.get(modality)
    if (
        accepted is not None
        and modality != ContentType.TEXT
        and mime_type not in accepted
    ):
        raise InvalidRequestError(
            f"Model adapter does not support MIME type {mime_type}"
        )
    if materialize:
        storage = await get_upload_storage_backend(UPLOAD_ROOT)
        content = await asset_service.read_bounded(
            asset, storage=storage, max_bytes=max_bytes
        )
    if materialize and selection_used:
        if "page_start" in selection_used:
            page_start = selection_used["page_start"]
            page_end = selection_used["page_end"]
            from io import BytesIO
            from pypdf import PdfReader, PdfWriter

            source = PdfReader(BytesIO(content))
            page_count = len(source.pages)
            if page_end > page_count:
                raise InvalidRequestError(
                    f"Document selection exceeds page count ({page_count})"
                )
            writer = PdfWriter()
            for page_num in range(page_start - 1, page_end):
                writer.add_page(source.pages[page_num])
            output = BytesIO()
            writer.write(output)
            content = output.getvalue()
            if len(content) > max_bytes:
                raise InvalidRequestError(
                    "Selected document exceeds model input byte limit"
                )
        else:
            start = selection_used["start_seconds"]
            end = selection_used["end_seconds"]
            import asyncio
            import tempfile
            from pathlib import Path
            from shutil import which

            ffmpeg = which("ffmpeg")
            if not ffmpeg:
                raise InvalidRequestError("Time-range selection requires ffmpeg")
            with tempfile.TemporaryDirectory(
                prefix="clouisle-asset-view-"
            ) as directory:
                source_path = Path(directory) / "source"
                output_path = Path(directory) / (
                    "selection.m4a"
                    if modality == ContentType.AUDIO
                    else "selection.mp4"
                )
                source_path.write_bytes(content)
                args = [
                    ffmpeg,
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    str(start),
                    "-i",
                    str(source_path),
                    "-t",
                    str(end - start),
                ]
                if modality == ContentType.AUDIO:
                    args += ["-vn", "-c:a", "aac", "-b:a", "128k"]
                else:
                    args += [
                        "-c:v",
                        "libx264",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                    ]
                proc = await asyncio.create_subprocess_exec(
                    *args,
                    "-fs",
                    str(max_bytes),
                    "-y",
                    str(output_path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    await asyncio.wait_for(proc.wait(), timeout=120)
                except (TimeoutError, asyncio.CancelledError) as error:
                    if proc.returncode is None:
                        proc.kill()
                    await proc.wait()
                    if isinstance(error, asyncio.CancelledError):
                        raise
                    raise InvalidRequestError(
                        "Media range processing timed out"
                    ) from None
                if proc.returncode != 0 or not output_path.is_file():
                    raise InvalidRequestError(
                        "Unable to derive requested media time range"
                    )
                if output_path.stat().st_size >= max_bytes:
                    raise InvalidRequestError(
                        "Selected media exceeds model input byte limit"
                    )
                content = output_path.read_bytes()

    if not materialize:
        selection_used = selection
        part = None
        modality_name = "text" if extracted_text else modality.value
        representation = {
            "kind": "extracted_text" if extracted_text else "native",
            "selection": selection_used,
        }
    elif modality == ContentType.TEXT and extracted_text:
        parsed = await file_parser_service.parse_file(
            content,
            asset.original_filename,
            FileParseConfig.model_validate(
                getattr(agent, "attachment_config", None) or {}
            ),
        )
        text = parsed.content[:MAX_TEXT_CHARS]
        part = ContentPart(
            type=ContentType.TEXT,
            text=f"[Extracted text from {asset.display_filename} ({mime_type}); truncated={bool(parsed.truncated or len(parsed.content) > MAX_TEXT_CHARS)}]\n{text}",
        )
        modality_name = "text"
        representation = {
            "kind": "extracted_text",
            "truncated": bool(parsed.truncated or len(parsed.content) > MAX_TEXT_CHARS),
        }
    else:
        common = {
            "base64": base64.b64encode(content).decode("ascii"),
            "mime_type": mime_type,
            "filename": asset.display_filename,
        }
        if modality == ContentType.IMAGE:
            part = ContentPart(
                type=modality,
                image=ImageContent(**common, format=mime_type.split("/", 1)[-1]),
            )
        elif modality == ContentType.AUDIO:
            part = ContentPart(
                type=modality,
                audio=AudioContent(**common, format=mime_type.split("/", 1)[-1]),
            )
        elif modality == ContentType.VIDEO:
            part = ContentPart(
                type=modality,
                video=VideoContent(**common, format=mime_type.split("/", 1)[-1]),
            )
        else:
            part = ContentPart(type=modality, file=FileContent(**common))
        modality_name = modality.value
        representation = {"kind": "native", "selection": selection_used}

    marker = json.dumps(
        {
            "version": 1,
            "kind": "asset.view",
            "ref": ref,
            "asset_id": str(asset.id),
            "scope_type": scope_type.value,
            "scope_id": str(scope_id),
            "modality": modality_name,
            "mime_type": raw_mime_type,
            "wire_mime_type": mime_type,
            "checksum": asset.checksum,
            "size": asset.size,
            "extracted_text": extracted_text,
            "selection": selection_used,
            "representation": representation,
        },
        ensure_ascii=False,
    )
    return asset, part, marker
