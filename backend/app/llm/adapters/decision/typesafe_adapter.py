"""
TypeSafe AI decision adapter.

TypeSafe exposes a single evaluation endpoint, ``POST /v1/systemone``: one ``state``
plus a map of typed questions in, typed answers with probability distributions out.
Nothing is generated, so the payload has no chat/streaming shape.
"""

import logging
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
from app.llm.errors import TimeoutError as LLMTimeoutError
from app.llm.types import DecisionAnswer, DecisionRequest, DecisionResponse, Usage
from app.models.model import ModelType, get_effective_model_base_url

from .base import BaseDecisionAdapter

logger = logging.getLogger(__name__)

DEFAULT_DECISION_REQUEST_TIMEOUT = 60.0
SYSTEMONE_PATH = "/systemone"


class TypeSafeDecisionAdapter(BaseDecisionAdapter):
    """调用 TypeSafe 决策模型端点

    ``base_url`` 可为包含或不包含版本段的 API 根地址（默认 ``https://api.typesafe.ai/v1``）。
    适配器会确保路径包含 ``/v1``，再拼接 ``/systemone``。
    """

    def _provider_value(self) -> str:
        provider = getattr(self.model_config, "provider", None)
        if hasattr(provider, "value"):
            return str(provider.value)
        return str(provider) if provider else ""

    def _get_endpoint(self) -> str:
        base_url = get_effective_model_base_url(
            self._provider_value(),
            ModelType.DECISION,
            getattr(self.model_config, "base_url", None),
        )
        if not base_url:
            raise ValueError("Decision model requires base_url to be configured")
        root = str(base_url).rstrip("/")
        if not root.endswith("/v1"):
            root += "/v1"
        return root + SYSTEMONE_PATH

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = getattr(self.model_config, "api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _build_payload(self, request: DecisionRequest) -> dict[str, Any]:
        return {
            "state": request.state,
            "model": request.model or str(self.model_config.model_id),
            "questions": {
                question_id: question.model_dump(exclude_none=True)
                for question_id, question in request.questions.items()
            },
        }

    def _parse_answers(self, data: dict[str, Any]) -> dict[str, DecisionAnswer]:
        answers: dict[str, DecisionAnswer] = {}
        raw_answers = data.get("answers")
        if not isinstance(raw_answers, dict):
            return answers

        for question_id, raw_answer in raw_answers.items():
            if not isinstance(raw_answer, dict):
                logger.warning(
                    "TypeSafe returned a non-object answer for question %s", question_id
                )
                continue
            try:
                answers[str(question_id)] = DecisionAnswer.model_validate(raw_answer)
            except Exception:
                logger.warning(
                    "TypeSafe returned an unparsable answer for question %s",
                    question_id,
                )
        return answers

    def _parse_usage(self, data: dict[str, Any]) -> Usage:
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return Usage()

        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return Usage(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            total_input_tokens=input_tokens,
        )

    def _map_http_error(self, exc: httpx.HTTPStatusError) -> LLMError:
        status = exc.response.status_code
        provider = self._provider_value() or None
        model = str(getattr(self.model_config, "model_id", "") or "") or None
        message = _error_message(exc.response)

        if status == 401:
            return AuthenticationError(message=message, provider=provider, model=model)
        if status == 402:
            return InsufficientQuotaError(
                message=message, provider=provider, model=model
            )
        if status == 429:
            return RateLimitError(message=message, provider=provider, model=model)
        if status in (400, 422):
            return InvalidRequestError(message=message, provider=provider, model=model)
        return ProviderError(
            message=message, status_code=status, provider=provider, model=model
        )

    async def decide(self, request: DecisionRequest, **kwargs: Any) -> DecisionResponse:
        if not request.questions:
            return DecisionResponse(
                model=str(request.model or self.model_config.model_id),
                answers={},
            )

        timeout = kwargs.get("timeout") or DEFAULT_DECISION_REQUEST_TIMEOUT
        provider = self._provider_value() or None
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
            raise self._map_http_error(exc) from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(
                message=f"TypeSafe request timed out after {timeout}s",
                timeout=timeout,
                provider=provider,
                model=model,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderError(
                message=f"TypeSafe request failed: {exc}",
                provider=provider,
                model=model,
            ) from exc

        if not isinstance(data, dict):
            raise ProviderError(
                message="TypeSafe returned an unexpected response body",
                provider=provider,
                model=model,
            )

        return DecisionResponse(
            model=str(data.get("model") or request.model or self.model_config.model_id),
            answers=self._parse_answers(data),
            usage=self._parse_usage(data),
        )


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"TypeSafe request failed with status {response.status_code}"

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message") or payload.get("error")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if detail is not None:
            return str(detail)
    return f"TypeSafe request failed with status {response.status_code}"
