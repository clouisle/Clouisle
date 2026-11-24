"""
Mistral AI OCR adapter.

Mistral exposes a document endpoint, ``POST /v1/ocr``: a document or image in,
page-level Markdown plus optional structured blocks out. The request has no chat
shape at all, which is why OCR models are their own type rather than chat models
with an image part.
"""

import logging
from typing import Any, cast, get_args

import httpx

from app.llm.errors import ProviderError, TimeoutError as LLMTimeoutError
from app.llm.types import (
    MediaContent,
    OCRBlock,
    OCRBlockType,
    OCRPage,
    OCRRequest,
    OCRResponse,
    Usage,
)
from app.models.model import ModelType, get_effective_model_base_url

from .base import BaseOCRAdapter, map_http_error, provider_value

logger = logging.getLogger(__name__)

DEFAULT_OCR_REQUEST_TIMEOUT = 120.0
OCR_PATH = "/ocr"
_PDF_MIME_TYPE = "application/pdf"


def _as_bbox(raw: Any) -> tuple[float, float, float, float] | None:
    """Read either ``[x0, y0, x1, y1]`` or the corner-pair block form."""
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        try:
            return (float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3]))
        except (TypeError, ValueError):
            return None
    if isinstance(raw, dict):
        try:
            return (
                float(raw["top_left_x"]),
                float(raw["top_left_y"]),
                float(raw["bottom_right_x"]),
                float(raw["bottom_right_y"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _as_confidence(raw: Any) -> float | None:
    try:
        confidence = float(raw)
    except (TypeError, ValueError):
        return None
    return confidence if 0 <= confidence <= 1 else None


_OCR_BLOCK_TYPES = get_args(OCRBlockType)


def _as_block_type(raw: Any) -> OCRBlockType:
    """Keep known block kinds and fall back to plain text."""
    if isinstance(raw, str) and raw in _OCR_BLOCK_TYPES:
        return cast(OCRBlockType, raw)
    return "text"


def _as_block(raw: Any) -> OCRBlock | None:
    if not isinstance(raw, dict):
        return None
    text = raw.get("text")
    if text is None:
        text = raw.get("content")
    block_type = raw.get("type")
    return OCRBlock(
        type=_as_block_type(block_type),
        text=str(text) if text is not None else None,
        bbox=_as_bbox(raw.get("bbox") or raw.get("bounding_box")),
        confidence=_as_confidence(raw.get("confidence")),
    )


def _as_page(raw: Any, fallback_index: int) -> OCRPage | None:
    if not isinstance(raw, dict):
        return None
    dimensions = raw.get("dimensions")
    width: float | None = None
    height: float | None = None
    if isinstance(dimensions, dict):
        try:
            width = float(dimensions["width"])
            height = float(dimensions["height"])
        except (KeyError, TypeError, ValueError):
            width = height = None
    index = raw.get("index")
    blocks = raw.get("blocks")
    return OCRPage(
        index=index if isinstance(index, int) else fallback_index,
        markdown=str(raw.get("markdown") or ""),
        blocks=[
            block
            for block in (_as_block(item) for item in (blocks or []))
            if block is not None
        ],
        width=width,
        height=height,
    )


def _as_source_chunk(source: MediaContent) -> dict[str, Any]:
    """Build the ``document`` chunk Mistral expects for an image or a PDF."""
    is_pdf = (source.mime_type or "").split(";", 1)[0].strip().lower() == _PDF_MIME_TYPE
    if source.url:
        chunk_type = "document_url" if is_pdf else "image_url"
        return {
            "type": chunk_type,
            chunk_type: source.url,
            "document_name": source.filename,
        }
    if source.base64:
        mime_type = source.mime_type or ("image/jpeg" if not is_pdf else _PDF_MIME_TYPE)
        data_uri = f"data:{mime_type};base64,{source.base64}"
        chunk_type = "document_url" if is_pdf else "image_url"
        return {
            "type": chunk_type,
            chunk_type: data_uri,
            "document_name": source.filename,
        }
    raise ProviderError(message="OCR source carries no url or base64 payload")


class MistralOCRAdapter(BaseOCRAdapter):
    """调用 Mistral ``/v1/ocr`` 文档识别端点"""

    def _get_endpoint(self) -> str:
        base_url = get_effective_model_base_url(
            provider_value(self.model_config),
            ModelType.OCR,
            getattr(self.model_config, "base_url", None),
        )
        if not base_url:
            raise ValueError("OCR model requires base_url to be configured")
        return str(base_url).rstrip("/") + OCR_PATH

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = getattr(self.model_config, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_payload(self, request: OCRRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or str(self.model_config.model_id),
            "document": _as_source_chunk(request.source),
        }
        if request.pages:
            payload["pages"] = request.pages
        if request.include_blocks:
            payload["include_blocks"] = True
        if request.instruction:
            payload["document_annotation_prompt"] = request.instruction
        return payload

    def _parse_response(self, data: dict[str, Any], request: OCRRequest) -> OCRResponse:
        raw_pages = data.get("pages")
        pages = [
            page
            for page in (
                _as_page(raw, index)
                for index, raw in enumerate(
                    raw_pages if isinstance(raw_pages, list) else []
                )
            )
            if page is not None
        ]
        return OCRResponse(
            model=str(data.get("model") or request.model or self.model_config.model_id),
            pages=pages,
            # Mistral bills per page and reports no token usage.
            usage=Usage(),
        )

    async def recognize(self, request: OCRRequest, **kwargs: Any) -> OCRResponse:
        timeout = kwargs.get("timeout") or DEFAULT_OCR_REQUEST_TIMEOUT
        provider = provider_value(self.model_config) or None
        model = str(getattr(self.model_config, "model_id", "") or "") or None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._get_endpoint(),
                    headers=self._build_headers(),
                    json=self._build_payload(request),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise map_http_error(exc, provider, model) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                message=f"Mistral OCR request timed out after {timeout}s",
                timeout=timeout,
                provider=provider,
                model=model,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"Mistral OCR request failed: {exc}",
                provider=provider,
                model=model,
            ) from exc

        if not isinstance(data, dict):
            raise ProviderError(
                message="Mistral OCR returned an unexpected response body",
                provider=provider,
                model=model,
            )
        return self._parse_response(data, request)
