"""OpenAI Responses image generation adapter."""

from __future__ import annotations

from typing import Any

from app.core.i18n import t
from app.llm.adapters.media_utils import (
    append_prompt_directives,
    image_content_to_data_uri,
)
from app.llm.errors import (
    AuthenticationError,
    InvalidRequestError,
    LLMError,
    ProviderError,
    RateLimitError,
)
from app.llm.types import ImageGenerationRequest, ImageGenerationResponse
from app.llm.types.base import ImageContent
from app.llm.types.image import GeneratedImage
from app.models.model import Model

from .base import BaseImageAdapter

_RESPONSES_IMAGE_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
_RESPONSES_IMAGE_QUALITIES = {"low", "medium", "high", "auto"}
_RESPONSES_IMAGE_BACKGROUNDS = {"transparent", "opaque", "auto"}
_RESPONSES_IMAGE_FORMATS = {"png", "jpeg", "webp"}
_RESPONSES_IMAGE_EXTRA_KEYS = {
    "action",
    "background",
    "input_fidelity",
    "moderation",
    "output_compression",
    "output_format",
    "quality",
    "size",
}


class OpenAIResponsesImageAdapter(BaseImageAdapter):
    """Generate images through the Responses hosted image tool."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.base_url = (model_config.base_url or "https://api.openai.com/v1").rstrip(
            "/"
        )
        self.model_id = model_config.model_id
        self.provider = (
            model_config.provider.value
            if hasattr(model_config.provider, "value")
            else str(model_config.provider)
        )

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AsyncOpenAI,
            AuthenticationError as OpenAIAuthenticationError,
            BadRequestError,
            RateLimitError as OpenAIRateLimitError,
        )

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self._get_request_timeout(),
        )
        payload, output_format = self._build_payload(request)
        images: list[GeneratedImage] = []

        try:
            while len(images) < request.num_images:
                response = await client.responses.create(**payload)
                images.extend(self._parse_images(response, output_format))

            return ImageGenerationResponse(
                images=images[: request.num_images],
                model=self.model_id,
            )
        except LLMError:
            raise
        except OpenAIAuthenticationError as exc:
            raise AuthenticationError(
                message=t("invalid_api_key"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except OpenAIRateLimitError as exc:
            raise RateLimitError(
                message=t("rate_limit_exceeded"),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except BadRequestError as exc:
            raise InvalidRequestError(
                message=str(exc),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            raise ProviderError(
                message=str(exc),
                provider=self.provider,
                model=self.model_id,
            ) from exc
        except APIStatusError as exc:
            raise ProviderError(
                message=str(exc),
                status_code=exc.status_code,
                provider=self.provider,
                model=self.model_id,
            ) from exc
        finally:
            await client.close()

    def _build_payload(
        self, request: ImageGenerationRequest
    ) -> tuple[dict[str, Any], str]:
        prompt = append_prompt_directives(
            request.prompt,
            f"Style: {request.style}" if request.style else None,
            f"Avoid: {request.negative_prompt}" if request.negative_prompt else None,
        )
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        for index, image in enumerate(request.images or []):
            content.append(
                {
                    "type": "input_image",
                    "image_url": image_content_to_data_uri(
                        image,
                        provider=self.provider,
                        model=self.model_id,
                        field_name=f"images[{index}]",
                    ),
                    "detail": "auto",
                }
            )

        tool = self._build_tool(request)
        output_format = str(tool.get("output_format", "png"))
        return (
            {
                "model": self.model_id,
                "input": [{"role": "user", "content": content}],
                "tools": [tool],
                "tool_choice": {"type": "image_generation"},
            },
            output_format,
        )

    def _build_tool(self, request: ImageGenerationRequest) -> dict[str, Any]:
        tool: dict[str, Any] = {"type": "image_generation"}
        tool.update(
            self._get_effective_extra_params(
                request,
                include_keys=_RESPONSES_IMAGE_EXTRA_KEYS,
            )
        )

        if (
            self._request_field_was_explicitly_set(request, "width")
            or self._request_field_was_explicitly_set(request, "height")
            or "size" not in tool
        ):
            tool["size"] = self._get_size(request.width, request.height)

        quality = self._get_effective_param(
            request,
            field_name="quality",
            param_key="quality",
        )
        if quality:
            tool["quality"] = quality

        self._validate_choice("size", tool.get("size"), _RESPONSES_IMAGE_SIZES)
        self._validate_choice(
            "quality", tool.get("quality"), _RESPONSES_IMAGE_QUALITIES
        )
        self._validate_choice(
            "background", tool.get("background"), _RESPONSES_IMAGE_BACKGROUNDS
        )
        self._validate_choice(
            "output_format", tool.get("output_format"), _RESPONSES_IMAGE_FORMATS
        )

        compression = tool.get("output_compression")
        if compression is not None and (
            not isinstance(compression, int) or not 0 <= compression <= 100
        ):
            self._invalid_param("output_compression", compression)

        return tool

    def _parse_images(self, response: Any, output_format: str) -> list[GeneratedImage]:
        images: list[GeneratedImage] = []
        for item in getattr(response, "output", []) or []:
            item_type = (
                item.get("type")
                if isinstance(item, dict)
                else getattr(item, "type", None)
            )
            result = (
                item.get("result")
                if isinstance(item, dict)
                else getattr(item, "result", None)
            )
            if item_type == "image_generation_call" and result:
                images.append(
                    GeneratedImage(
                        image=ImageContent(base64=result, format=output_format)
                    )
                )

        if not images:
            raise InvalidRequestError(
                message="Responses API returned no generated image",
                provider=self.provider,
                model=self.model_id,
            )
        return images

    def _get_size(self, width: int, height: int) -> str:
        if width > height:
            return "1536x1024"
        if height > width:
            return "1024x1536"
        return "1024x1024"

    def _validate_choice(self, field: str, value: Any, allowed: set[str]) -> None:
        if value is not None and value not in allowed:
            self._invalid_param(field, value)

    def _invalid_param(self, field: str, value: Any) -> None:
        raise InvalidRequestError(
            message=f"Invalid {field}: {value}",
            field=field,
            provider=self.provider,
            model=self.model_id,
        )
