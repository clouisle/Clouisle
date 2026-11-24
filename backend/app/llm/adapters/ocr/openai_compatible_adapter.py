"""
OCR through a chat-completions endpoint.

Some vision models are purpose-built for transcription (Qwen-OCR and gateways
exposing the same protocol). They recognize text when sent an image with no text
part at all: an omitted instruction means the provider's own default prompt.
This adapter therefore serializes the image alone, and only appends a text part
when the caller supplies an instruction.

The wire format is the OpenAI chat shape, so this adapter also covers
``custom`` gateways that implement transcription-only image input.
"""

import logging
from typing import Any

import httpx

from app.llm.errors import ProviderError, TimeoutError as LLMTimeoutError
from app.llm.types import MediaContent, OCRPage, OCRRequest, OCRResponse, Usage
from app.models.model import ModelType, get_effective_model_base_url

from .base import BaseOCRAdapter, map_http_error, provider_value

logger = logging.getLogger(__name__)

DEFAULT_OCR_REQUEST_TIMEOUT = 120.0
CHAT_COMPLETIONS_PATH = "/chat/completions"
_DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"


def _as_data_uri(source: MediaContent) -> str:
    """Inline the payload as a data URI; these endpoints take no file handle."""
    if source.url:
        return source.url
    if not source.base64:
        raise ProviderError(message="OCR source carries no url or base64 payload")
    mime_type = source.mime_type or _DEFAULT_IMAGE_MIME_TYPE
    return f"data:{mime_type};base64,{source.base64}"


def _as_text(content: Any) -> str:
    """Flatten a chat completion content value to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    return ""


def _as_usage(raw: Any) -> Usage:
    if not isinstance(raw, dict):
        return Usage()
    prompt_tokens = int(raw.get("prompt_tokens", 0) or 0)
    completion_tokens = int(raw.get("completion_tokens", 0) or 0)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=int(raw.get("total_tokens", 0) or 0)
        or prompt_tokens + completion_tokens,
        total_input_tokens=prompt_tokens,
    )


class OpenAICompatibleOCRAdapter(BaseOCRAdapter):
    """调用 OpenAI 兼容的多模态聊天端点做文字识别

    The model is addressed with the image alone; page structure is whatever
    the model returns as text, so a response is a single page.
    """

    def _get_endpoint(self) -> str:
        base_url = get_effective_model_base_url(
            provider_value(self.model_config),
            ModelType.OCR,
            getattr(self.model_config, "base_url", None),
        )
        if not base_url:
            raise ValueError("OCR model requires base_url to be configured")
        return str(base_url).rstrip("/") + CHAT_COMPLETIONS_PATH

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = getattr(self.model_config, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_payload(self, request: OCRRequest) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        if request.instruction:
            content.append({"type": "text", "text": request.instruction})
        content.append(
            {"type": "image_url", "image_url": {"url": _as_data_uri(request.source)}}
        )
        default_params = getattr(self.model_config, "default_params", None) or {}
        payload: dict[str, Any] = {
            "model": request.model or str(self.model_config.model_id),
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        temperature = default_params.get("temperature")
        if temperature is not None:
            payload["temperature"] = temperature
        max_tokens = default_params.get("max_tokens") or getattr(
            self.model_config, "max_output_tokens", None
        )
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return payload

    def _parse_response(self, data: dict[str, Any], request: OCRRequest) -> OCRResponse:
        choices = data.get("choices")
        text = ""
        if isinstance(choices, list) and choices:
            message = (
                choices[0].get("message") if isinstance(choices[0], dict) else None
            )
            if isinstance(message, dict):
                text = _as_text(message.get("content")).strip()
        return OCRResponse(
            model=str(data.get("model") or request.model or self.model_config.model_id),
            pages=[OCRPage(index=0, markdown=text)],
            usage=_as_usage(data.get("usage")),
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
                message=f"OCR request timed out after {timeout}s",
                timeout=timeout,
                provider=provider,
                model=model,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"OCR request failed: {exc}",
                provider=provider,
                model=model,
            ) from exc

        if not isinstance(data, dict):
            raise ProviderError(
                message="OCR provider returned an unexpected response body",
                provider=provider,
                model=model,
            )
        return self._parse_response(data, request)
