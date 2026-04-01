"""
OpenAI DALL-E 图像生成适配器
"""

import logging

import httpx

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
                message="Custom image provider requires base_url",
                field="base_url",
                provider=self.provider,
                model=model_config.model_id,
            )
        self.base_url = (model_config.base_url or "https://api.openai.com/v1").rstrip("/")
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
                        message="Invalid API key",
                        provider=self.provider,
                        model=self.model_id,
                    )
                elif response.status_code == 429:
                    raise RateLimitError(
                        message="Rate limit exceeded",
                        provider=self.provider,
                        model=self.model_id,
                    )
                elif response.status_code == 400:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get(
                        "message", "Bad request"
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
                    message="Request timeout",
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

    def _build_payload(self, request: ImageGenerationRequest) -> dict:
        prompt = append_prompt_directives(
            request.prompt,
            f"Avoid: {request.negative_prompt}" if request.negative_prompt else None,
        )
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "n": request.num_images,
            "size": self._get_size(request.width, request.height),
        }

        if self.model_id in ["dall-e-3", "dall-e-2"]:
            payload["response_format"] = "url"
            if self.model_id == "dall-e-3":
                if request.style:
                    payload["style"] = request.style
                if request.quality:
                    payload["quality"] = request.quality
        else:
            if request.quality:
                payload["quality"] = request.quality

        if request.seed is not None:
            payload["seed"] = request.seed

        if request.extra_params:
            payload.update(request.extra_params)

        return payload

    def _get_size(self, width: int, height: int) -> str:
        """将宽高转换为 DALL-E 支持的尺寸"""
        # DALL-E 3 支持: 1024x1024, 1792x1024, 1024x1792
        # DALL-E 2 支持: 256x256, 512x512, 1024x1024
        if self.model_id == "dall-e-3":
            if width > height:
                return "1792x1024"
            elif height > width:
                return "1024x1792"
            else:
                return "1024x1024"
        elif self.model_id.startswith("gpt-image"):
            if width > height:
                return "1536x1024"
            elif height > width:
                return "1024x1536"
            else:
                return "1024x1024"
        else:  # dall-e-2
            if width <= 256 or height <= 256:
                return "256x256"
            elif width <= 512 or height <= 512:
                return "512x512"
            else:
                return "1024x1024"
