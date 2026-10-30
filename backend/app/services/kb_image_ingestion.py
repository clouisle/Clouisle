"""Enrich knowledge-base document text with bounded, authorized image analysis."""

from __future__ import annotations

import asyncio
import base64
import re
from typing import Any
from uuid import UUID

import bleach

from app.models.site_setting import SiteSetting
from app.services.document_processor import document_processor
from app.services.kb_image_understanding import (
    KBImageUnderstandingService,
    KBImageValidationError,
)

IMAGE_DEFAULTS = {
    "kb_image_understanding_enabled": False,
    "kb_image_understanding_model_id": "",
    "kb_image_ocr_model_id": "",
    "kb_image_understanding_allow_external": False,
    "kb_image_understanding_max_images": 8,
    "kb_image_understanding_max_image_bytes": 10 * 1024 * 1024,
    "kb_image_understanding_max_image_pixels": 20_000_000,
    "kb_image_understanding_concurrency": 2,
}


async def image_settings() -> dict[str, Any]:
    settings = await SiteSetting.get_values(IMAGE_DEFAULTS)
    for key, bounds in {
        "kb_image_understanding_max_images": (1, 20),
        "kb_image_understanding_max_image_bytes": (1, 50 * 1024 * 1024),
        "kb_image_understanding_max_image_pixels": (1, 40_000_000),
        "kb_image_understanding_concurrency": (1, 8),
    }.items():
        value = settings[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not bounds[0] <= value <= bounds[1]
        ):
            raise ValueError("invalid_image_understanding_settings")
    if not isinstance(
        settings["kb_image_understanding_enabled"], bool
    ) or not isinstance(settings["kb_image_understanding_allow_external"], bool):
        raise ValueError("invalid_image_understanding_settings")
    return settings


async def prepare_document(
    document: Any,
    *,
    clean_text: bool,
    settings: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Extract and enrich a document using one explicit settings snapshot."""
    kb = document.knowledge_base
    if document.file_path:
        if settings["kb_image_understanding_enabled"] and document.doc_type == "pdf":
            from app.services.kb_pdf_images import iter_pdf_pages

            content = await document_processor.read_file(document.file_path)

            def bounded_pages():
                collected = []
                images = 0
                for page in iter_pdf_pages(content):
                    if page.needs_visual_recognition:
                        images += 1
                        if images > settings["kb_image_understanding_max_images"]:
                            raise ValueError("image_count_exceeded")
                    collected.append(page)
                return collected

            pages = await asyncio.to_thread(bounded_pages)
            if any(page.needs_visual_recognition for page in pages):
                text, metadata = await ingest_pdf_pages(
                    {"file_size": len(content), "doc_type": "pdf"},
                    content=content,
                    kb_id=kb.id,
                    document_id=document.id,
                    settings=settings,
                    pages=pages,
                    clean_text=clean_text,
                )
            else:
                text, metadata = await document_processor.extract_text(
                    document.file_path,
                    document.doc_type,
                    clean_text=clean_text,
                    kb_id=kb.id,
                    document_id=document.id,
                )
        else:
            text, metadata = await document_processor.extract_text(
                document.file_path,
                document.doc_type,
                clean_text=clean_text,
                kb_id=kb.id,
                document_id=document.id,
            )
        if settings["kb_image_understanding_enabled"] and document.doc_type == "xlsx":
            content = await document_processor.read_file(document.file_path)
            text, metadata = await ingest_xlsx_images(
                text,
                metadata,
                content=content,
                kb_id=kb.id,
                document_id=document.id,
                settings=settings,
            )
    elif document.source_url:
        text, metadata = await document_processor.fetch_url_content(
            document.source_url,
            clean_text=clean_text,
        )
    else:
        raise ValueError("document_missing_source")
    text, metadata = await ingest_external_images(
        text,
        metadata,
        kb_id=kb.id,
        document_id=document.id,
        settings=settings,
    )
    return await enrich_document_images(
        text, metadata, team_id=kb.team_id, settings=settings
    )


async def ingest_external_images(
    text: str,
    metadata: dict[str, Any],
    *,
    kb_id: UUID,
    document_id: UUID,
    settings: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Fetch opted-in external Markdown images into authorized document storage."""
    if not (
        settings["kb_image_understanding_enabled"]
        and settings["kb_image_understanding_allow_external"]
    ):
        return text, metadata
    from app.services.kb_external_images import fetch_external_image

    pattern = re.compile(r"(!\[[^\]]*\]\()(https?://[^\s)]+)(\))", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    assets = list(metadata.get("media_assets") or [])
    if len(matches) + len(assets) > settings["kb_image_understanding_max_images"]:
        raise ValueError("image_count_exceeded")
    for match in reversed(matches):
        payload, mime = await fetch_external_image(
            match.group(2),
            max_image_bytes=settings["kb_image_understanding_max_image_bytes"],
            max_image_pixels=settings["kb_image_understanding_max_image_pixels"],
        )
        uri = f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"
        replacement, saved = await document_processor.replace_embedded_media_data_uris(
            match.group(1) + uri + match.group(3), kb_id=kb_id, document_id=document_id
        )
        text = text[: match.start()] + replacement + text[match.end() :]
        assets.extend(saved)
    metadata = dict(metadata)
    if assets:
        metadata["media_assets"] = assets
    return text, metadata


async def ingest_xlsx_images(
    text: str,
    metadata: dict[str, Any],
    *,
    content: bytes,
    kb_id: UUID,
    document_id: UUID,
    settings: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not settings["kb_image_understanding_enabled"]:
        return text, metadata
    from app.services.kb_xlsx_images import extract_xlsx_images

    images = await asyncio.to_thread(
        extract_xlsx_images,
        content,
        max_count=settings["kb_image_understanding_max_images"],
        max_image_bytes=settings["kb_image_understanding_max_image_bytes"],
    )
    assets = list(metadata.get("media_assets") or [])
    for image in images:
        label = f"Sheet {image.sheet_name}, cell {image.anchor}"
        uri = f"data:{image.content_type};base64,{base64.b64encode(image.data).decode('ascii')}"
        markdown, saved = await document_processor.replace_embedded_media_data_uris(
            f"![{label}]({uri})", kb_id=kb_id, document_id=document_id
        )
        for asset in saved:
            asset.update({"sheet": image.sheet_name, "anchor": image.anchor})
        assets.extend(saved)
        text += f"\n\n{markdown}"
    metadata = dict(metadata)
    if assets:
        metadata["media_assets"] = assets
    return text, metadata


async def ingest_pdf_pages(
    metadata: dict[str, Any],
    *,
    content: bytes,
    kb_id: UUID,
    document_id: UUID,
    settings: dict[str, Any],
    pages: list[Any] | None = None,
    clean_text: bool = True,
) -> tuple[str, dict[str, Any]]:
    from app.services.kb_pdf_images import iter_pdf_pages

    if pages is None:

        def bounded_pages():
            collected = []
            images = 0
            for page in iter_pdf_pages(content):
                if page.needs_visual_recognition:
                    images += 1
                    if images > settings["kb_image_understanding_max_images"]:
                        raise ValueError("image_count_exceeded")
                collected.append(page)
            return collected

        pages = await asyncio.to_thread(bounded_pages)
    elif (
        sum(page.needs_visual_recognition for page in pages)
        > settings["kb_image_understanding_max_images"]
    ):
        raise ValueError("image_count_exceeded")

    sections = []
    assets = []
    for page in pages:
        page_text = document_processor._clean_text(page.text, clean=clean_text)
        sections.append(f"## Page {page.page_number}\n\n{page_text}")
        if page.image_png is not None:
            uri = "data:image/png;base64," + base64.b64encode(page.image_png).decode(
                "ascii"
            )
            markup, saved = await document_processor.replace_embedded_media_data_uris(
                f"![Page {page.page_number}]({uri})",
                kb_id=kb_id,
                document_id=document_id,
            )
            for asset in saved:
                asset["page"] = page.page_number
                asset["native_text"] = bool(page.text.strip())
            assets.extend(saved)
            sections.append(markup)
    result_metadata = dict(metadata)
    result_metadata["format"] = "markdown"
    result_metadata["media_assets"] = assets
    return "\n\n".join(sections), result_metadata


async def enrich_document_images(
    text: str, metadata: dict[str, Any], *, team_id: UUID, settings: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Insert OCR and visual descriptions at the corresponding image reference.

    The caller controls publication and owns the image assets. Never treat model
    output as instructions and never expose image bytes in the result metadata.
    """
    if not settings["kb_image_understanding_enabled"]:
        if metadata.get("doc_type") == "image":
            raise ValueError("image_understanding_disabled")
        return text, metadata
    assets = metadata.get("media_assets") or []
    if not assets:
        return text, metadata
    if len(assets) > settings["kb_image_understanding_max_images"]:
        raise ValueError("image_count_exceeded")
    vision_setting = str(settings.get("kb_image_understanding_model_id") or "").strip()
    ocr_setting = str(settings.get("kb_image_ocr_model_id") or "").strip()
    try:
        vision_model_id = UUID(vision_setting) if vision_setting else None
        ocr_model_id = UUID(ocr_setting) if ocr_setting else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("invalid_image_understanding_settings") from exc
    if vision_model_id is None and ocr_model_id is None:
        raise ValueError("image_model_required")
    service = KBImageUnderstandingService(
        max_images=settings["kb_image_understanding_max_images"],
        max_image_bytes=settings["kb_image_understanding_max_image_bytes"],
        max_image_pixels=settings["kb_image_understanding_max_image_pixels"],
        concurrency=settings["kb_image_understanding_concurrency"],
    )
    payloads = await asyncio.gather(
        *(document_processor.read_file(asset["path"]) for asset in assets)
    )
    if vision_model_id is None:
        results = await service.extract_ocr_images(
            payloads, team_id=str(team_id), model_id=ocr_model_id
        )
    elif ocr_model_id is None or ocr_model_id == vision_model_id:
        results = await service.analyze_images(
            payloads, team_id=str(team_id), model_id=vision_model_id
        )
    else:
        results = await service.analyze_images_split(
            payloads,
            team_id=str(team_id),
            ocr_model_id=ocr_model_id,
            vision_model_id=vision_model_id,
        )
    records = []
    offsets: dict[str, int] = {}
    for asset, result in zip(assets, results, strict=True):
        url = asset["url"]
        description = bleach.clean(result.description, tags=[], strip=True).strip()
        ocr = bleach.clean(result.ocr_text, tags=[], strip=True).strip()
        parts = []
        if description:
            parts.append(f"Image description: {description}")
        if ocr:
            parts.append(f"Image text: {ocr}")
        annotation = "\n\n" + "\n".join(parts) if parts else ""
        if not parts and metadata.get("doc_type") == "image":
            raise KBImageValidationError(
                "No readable text was extracted from the image",
                code="image_no_text_extracted",
            )
        if annotation:
            image_pattern = re.compile(r"(!\[[^\]]*\]\(" + re.escape(url) + r"\))")
            match = image_pattern.search(text, offsets.get(url, 0))
            if not match:
                raise ValueError("image_reference_missing")
            text = text[: match.end()] + annotation + text[match.end() :]
            offsets[url] = match.end() + len(annotation)
        records.append(
            {
                "url": url,
                "description": description,
                "ocr_text": ocr,
                **{
                    key: asset[key]
                    for key in ("page", "sheet", "anchor")
                    if key in asset
                },
            }
        )
    metadata = dict(metadata)
    metadata["image_understanding"] = {
        "model_id": str(vision_model_id or ocr_model_id),
        "vision_model_id": str(vision_model_id) if vision_model_id else "",
        "ocr_model_id": str(ocr_model_id or vision_model_id),
        "images": records,
    }
    return text, metadata
