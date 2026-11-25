"""
OCR through a chat-completions endpoint.

Some vision models are purpose-built for transcription (Qwen-OCR and gateways
exposing the same protocol). They recognize text when sent an image with no text
part at all, which is also the only shape this adapter ever sends: an OCR request
carries no prompt, so the provider's own transcription prompt applies. Page
selection and block structure are not expressible here, so the base adapter
rejects them instead of dropping them.

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
    """Inline the payload as a data URI; these endpoints take no file handle.

    ``OCRRequest`` guarantees a url or a base64 payload, so no other case is
    reachable here.
    """
    if source.url:
        return source.url
    mime_type = source.mime_type or _DEFAULT_IMAGE_MIME_TYPE
    return f"data:{mime_type};base64,{source.base64}"


def _as_text(content: Any) -> str:
    """Flatten a chat completion content value to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        ]
        if parts and all(isinstance(part, str) for part in parts):
            return "".join(parts)
    raise ValueError("missing or malformed completion text")


_ABSENT: Any = object()


def _usage_counter(raw: Any) -> int:
    """Read one usage counter.

    An omitted counter means zero: document endpoints report no usage at all. An
    explicit ``null`` or any non-integer is malformed instead, because it states
    nothing about what was billed. Booleans are rejected explicitly, since
    ``True`` would otherwise be recorded as one token.
    """
    if raw is _ABSENT:
        return 0
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise ValueError("malformed usage counter")
    return raw


def _as_usage(raw: Any) -> Usage:
    # An omitted ``usage`` object is normal (document endpoints bill per page);
    # anything else must actually look like usage, so a malformed body cannot be
    # recorded as a token charge.
    if raw is None:
        return Usage()
    if not isinstance(raw, dict):
        raise ValueError("malformed usage")
    prompt_tokens = _usage_counter(raw.get("prompt_tokens", _ABSENT))
    completion_tokens = _usage_counter(raw.get("completion_tokens", _ABSENT))
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=_usage_counter(raw.get("total_tokens", _ABSENT))
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
        if not isinstance(choices, list) or not choices:
            raise ValueError("missing completion choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ValueError("malformed completion message")
        return OCRResponse(
            model=str(data.get("model") or request.model or self.model_config.model_id),
            pages=[OCRPage(index=0, markdown=_as_text(message.get("content")).strip())],
            usage=_as_usage(data.get("usage")),
            # ``length`` means the provider ran out of output budget mid-page.
            truncated=choices[0].get("finish_reason") == "length",
        )

    async def _recognize(self, request: OCRRequest, **kwargs: Any) -> OCRResponse:
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

        return self._parse_http_response(response, request)
