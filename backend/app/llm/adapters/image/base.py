"""
图像生成适配器基类
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import math
from typing import Any

from app.core.i18n import t
from app.llm.errors import InvalidRequestError
from app.llm.types import ImageGenerationRequest, ImageGenerationResponse

_MISSING = object()


class BaseImageAdapter(ABC):
    """图像生成适配器基类"""

    model_config: Any

    @abstractmethod
    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """生成图像"""
        pass

    def _get_model_default_params(self) -> dict[str, Any]:
        default_params = getattr(self.model_config, "default_params", None)
        return default_params if isinstance(default_params, dict) else {}

    def _get_request_timeout(self) -> float:
        config = getattr(self.model_config, "config", None)
        timeout = config.get("timeout", 300) if isinstance(config, dict) else 300
        try:
            value = float(timeout)
        except (TypeError, ValueError) as exc:
            raise InvalidRequestError(
                message=t("invalid_request_timeout"), field="timeout"
            ) from exc
        if not math.isfinite(value) or value <= 0:
            raise InvalidRequestError(
                message=t("invalid_request_timeout"), field="timeout"
            )
        return value

    def _request_field_was_explicitly_set(
        self,
        request: ImageGenerationRequest,
        field_name: str,
    ) -> bool:
        return field_name in request.model_fields_set

    def _get_effective_param(
        self,
        request: ImageGenerationRequest,
        *,
        field_name: str | None = None,
        param_key: str,
        fallback: Any = None,
    ) -> Any:
        if field_name and self._request_field_was_explicitly_set(request, field_name):
            value = getattr(request, field_name, None)
            if value not in (None, ""):
                return value

        extra_params = (
            request.extra_params if isinstance(request.extra_params, dict) else {}
        )
        extra_value = extra_params.get(param_key, _MISSING)
        if extra_value not in (_MISSING, None, ""):
            return extra_value

        default_value = self._get_model_default_params().get(param_key, _MISSING)
        if default_value not in (_MISSING, None, ""):
            return default_value

        if field_name:
            field_value = getattr(request, field_name, None)
            if field_value not in (None, ""):
                return field_value

        return fallback

    def _get_effective_extra_params(
        self,
        request: ImageGenerationRequest,
        *,
        include_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        default_params = self._get_model_default_params()
        extra_params = (
            request.extra_params if isinstance(request.extra_params, dict) else {}
        )

        if include_keys is None:
            merged = dict(default_params)
            merged.update(extra_params)
            return merged

        merged = {
            key: value
            for key, value in default_params.items()
            if key in include_keys and value not in (None, "")
        }
        merged.update(
            {
                key: value
                for key, value in extra_params.items()
                if key in include_keys and value not in (None, "")
            }
        )
        return merged
