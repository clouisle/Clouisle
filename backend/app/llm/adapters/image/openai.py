"""
OpenAI DALL-E 图像生成适配器
"""

import logging
from typing import Any

import httpx

from app.core.i18n import t
from app.llm.adapters.media_utils import append_prompt_directives
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    InvalidRequestError,
    ProviderError,
    RateLimitError,
)
from app.models.model import Model
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from .base import BaseImageAdapter

logger = logging.getLogger(__name__)

_OPENAI_IMAGE_DEFAULT_PARAM_KEYS = {
    "background",
    "output_format",
    "output_compression",
}


class OpenAIImageAdapter(BaseImageAdapter):
    """OpenAI DALL-E 图像生成适配器"""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.provider = (
            model_config.provider.value
            if hasattr(model_config.provider, "value")
            else str(model_config.provider)
        )
        if self.provider == "custom" and not model_config.base_url:
            raise InvalidRequestError(
                message=t("custom_image_provider_requires_base_url"),
                field="base_url",
                provider=self.provider,
                model=model_config.model_id,
            )
        self.base_url = (model_config.base_url or "https://api.openai.com/v1").rstrip(
            "/"
        )
        self.model_id = model_config.model_id

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        """
        生成图像

        Args:
            request: 图像生成请求

        Returns:
            ImageGenerationResponse: 生成结果
        """
        payload = self._build_payload(request)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    self._build_url("/images/generations"),
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 401:
                    raise AuthenticationError(
                        message=t("invalid_api_key"),
                        provider=self.provider,
                        model=self.model_id,
                    )
                elif response.status_code == 429:
                    raise RateLimitError(
                        message=t("rate_limit_exceeded"),
                        provider=self.provider,
                        model=self.model_id,
                    )
                elif response.status_code == 400:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get(
                        "message", t("bad_request")
                    )
                    if (
                        "content_policy" in error_msg.lower()
                        or "safety" in error_msg.lower()
                    ):
                        raise ContentFilterError(
                            message=error_msg,
                            provider=self.provider,
                            model=self.model_id,
                        )
                    raise InvalidRequestError(
                        message=error_msg,
                        provider=self.provider,
                        model=self.model_id,
                    )
                elif response.status_code != 200:
                    raise ProviderError(
                        message=f"Image API error: {response.text}",
                        status_code=response.status_code,
                        provider=self.provider,
                        model=self.model_id,
                    )

                data = response.json()
                images = []

                for item in data.get("data", []):
                    image = GeneratedImage(
                        image=ImageContent(
                            url=item.get("url"),
                            base64=item.get("b64_json") or item.get("base64"),
                        ),
                        revised_prompt=item.get("revised_prompt"),
                    )
                    images.append(image)

                return ImageGenerationResponse(
                    images=images,
                    model=self.model_id,
                )

            except httpx.TimeoutException:
                raise ProviderError(
                    message=t("request_timeout"),
                    provider=self.provider,
                    model=self.model_id,
                )
            except httpx.RequestError as e:
                raise ProviderError(
                    message=f"Request error: {str(e)}",
                    provider=self.provider,
                    model=self.model_id,
                )

    def _build_url(self, path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        if self.base_url.endswith("/v1") and normalized.startswith("/v1/"):
            normalized = normalized[3:]
        return f"{self.base_url}{normalized}"

    def _build_payload(self, request: ImageGenerationRequest) -> dict[str, Any]:
        prompt = append_prompt_directives(
            request.prompt,
            f"Avoid: {request.negative_prompt}" if request.negative_prompt else None,
        )
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": prompt,
            "n": request.num_images,
            "size": self._get_size(request.width, request.height),
        }

        if self._is_dalle_model():
            payload["response_format"] = "url"
            if self.model_id == "dall-e-3":
                style = self._get_effective_param(
                    request,
                    field_name="style",
                    param_key="style",
                )
                if style:
                    payload["style"] = style

                quality = self._get_effective_param(
                    request,
                    field_name="quality",
                    param_key="quality",
                )
                if quality:
                    payload["quality"] = quality
        else:
            quality = self._get_effective_param(
                request,
                field_name="quality",
                param_key="quality",
            )
            if quality:
                payload["quality"] = quality

            provider_params = self._get_effective_extra_params(
                request,
                include_keys=_OPENAI_IMAGE_DEFAULT_PARAM_KEYS,
            )
            payload.update(provider_params)

        if request.seed is not None:
            payload["seed"] = request.seed

        passthrough_extra_params = dict(request.extra_params or {})
        for managed_key in _OPENAI_IMAGE_DEFAULT_PARAM_KEYS | {
            "quality",
            "style",
            "seed",
        }:
            passthrough_extra_params.pop(managed_key, None)
        payload.update(passthrough_extra_params)

        return payload

    def _is_dalle_model(self) -> bool:
        return self.model_id in {"dall-e-3", "dall-e-2"}

    def _get_size(self, width: int, height: int) -> str:
        """将宽高转换为 DALL-E / GPT Image 支持的尺寸"""
        if self.model_id == "dall-e-3":
            if width > height:
                return "1792x1024"
            if height > width:
                return "1024x1792"
            return "1024x1024"

        if self.model_id.startswith("gpt-image"):
            if width > height:
                return "1536x1024"
            if height > width:
                return "1024x1536"
            return "1024x1024"

        if width <= 256 or height <= 256:
            return "256x256"
        if width <= 512 or height <= 512:
            return "512x512"
        return "1024x1024"
