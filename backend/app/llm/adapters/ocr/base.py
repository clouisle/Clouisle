"""
OCR adapter base class and shared HTTP error mapping.
"""

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.llm.errors import (
    AuthenticationError,
    InsufficientQuotaError,
    InvalidRequestError,
    LLMError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import OCRRequest, OCRResponse


def provider_value(model_config: Any) -> str:
    """Read the provider identifier off a model config or ORM model."""
    provider = getattr(model_config, "provider", None)
    if provider is None:
        return ""
    if hasattr(provider, "value"):
        return str(provider.value)
    return str(provider)


def error_message(response: httpx.Response, provider: str) -> str:
    """Extract a human-readable error message from a provider error body."""
    try:
        payload = response.json()
    except ValueError:
        return f"{provider} request failed with status {response.status_code}"

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
        if isinstance(detail, str):
            if detail.strip():
                return detail.strip()
        elif detail is not None:
            return str(detail)
    return f"{provider} request failed with status {response.status_code}"


def map_http_error(
    exc: httpx.HTTPStatusError, provider: str | None, model: str | None
) -> LLMError:
    """Map an HTTP status to the shared LLM error hierarchy."""
    status = exc.response.status_code
    label = provider or "OCR"
    message = error_message(exc.response, label)

    if status == 401:
        return AuthenticationError(message=message, provider=provider, model=model)
    if status == 402:
        return InsufficientQuotaError(message=message, provider=provider, model=model)
    if status == 429:
        return RateLimitError(message=message, provider=provider, model=model)
    if status in (400, 422):
        return InvalidRequestError(message=message, provider=provider, model=model)
    return ProviderError(
        message=message, status_code=status, provider=provider, model=model
    )


class BaseOCRAdapter(ABC):
    """文字识别模型适配器基类"""

    def __init__(self, model_config: Any):
        self.model_config = model_config

    @abstractmethod
    async def recognize(self, request: OCRRequest, **kwargs: Any) -> OCRResponse:
        """识别图像或文档中的文字，按页返回结果。"""
        raise NotImplementedError
