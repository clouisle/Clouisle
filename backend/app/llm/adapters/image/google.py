"""
Google Gemini image-generation adapter.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import httpx

from app.llm.adapters.media_utils import append_prompt_directives
from app.llm.errors import ContentFilterError, InvalidRequestError, ProviderError
from app.llm.types import (
    GeneratedImage,
    ImageContent,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.models.model import Model

from .base import BaseImageAdapter

_GOOGLE_IMAGE_ASPECT_RATIOS: dict[str, float] = {
    "21:9": 21 / 9,
    "16:9": 16 / 9,
    "4:3": 4 / 3,
    "3:2": 3 / 2,
    "1:1": 1.0,
    "2:3": 2 / 3,
    "3:4": 3 / 4,
    "9:16": 9 / 16,
}
_GOOGLE_IMAGE_CONFIG_KEYS = {
    "aspect_ratio",
    "image_size",
    "person_generation",
    "prominent_people",
    "image_output_options",
    "output_mime_type",
    "output_compression_quality",
}
_GOOGLE_REFERENCE_IMAGE_KEYS = {"image", "images", "reference_images"}


class GoogleImageAdapter(BaseImageAdapter):
    """Google Gemini image-generation adapter for Nano Banana style models."""

    def __init__(self, model_config: Model):
        self.model_config = model_config
        self.api_key = model_config.api_key
        self.base_url = model_config.base_url
        self.model_id = model_config.model_id
        self.provider = (
            model_config.provider.value
            if hasattr(model_config.provider, "value")
            else str(model_config.provider)
        )

    async def generate(
        self, request: ImageGenerationRequest
    ) -> ImageGenerationResponse:
        from google import genai

        client_kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["http_options"] = {"base_url": self.base_url}
        client = genai.Client(**client_kwargs)

        reference_images, config_overrides = self._split_extra_params(request)
        contents = await self._build_contents(request, reference_images)

        images: list[GeneratedImage] = []
        for index in range(request.num_images):
            response = await client.aio.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=self._build_generation_config(
                    request,
                    seed_offset=index,
                    overrides=config_overrides,
                ),
            )
            images.extend(
                self._parse_generated_images(
                    response,
                    fallback_seed=request.seed + index
                    if request.seed is not None
                    else None,
                )
            )
            if len(images) >= request.num_images:
                break

        return ImageGenerationResponse(
            images=images[: request.num_images],
            model=self.model_id,
        )

    def _split_extra_params(
        self, request: ImageGenerationRequest
    ) -> tuple[list[ImageContent], dict[str, Any]]:
        extra_params = request.extra_params
        if not extra_params:
            return list(request.images or []), {}

        overrides = dict(extra_params)
        reference_images: list[ImageContent] = []

        for key in _GOOGLE_REFERENCE_IMAGE_KEYS:
            raw_value = overrides.pop(key, None)
            if not raw_value:
                continue
            if key == "image":
                raw_items = [raw_value]
            elif isinstance(raw_value, list):
                raw_items = raw_value
            else:
                raw_items = [raw_value]

            for item in raw_items:
                if isinstance(item, ImageContent):
                    reference_images.append(item)
                elif isinstance(item, dict):
                    reference_images.append(ImageContent.model_validate(item))
                else:
                    raise InvalidRequestError(
                        message=f"Unsupported Google reference image payload: {item!r}",
                        field=key,
                        provider=self.provider,
                        model=self.model_id,
                    )

        if request.images:
            return list(request.images), overrides

        return reference_images, overrides

    async def _build_contents(
        self,
        request: ImageGenerationRequest,
        reference_images: list[ImageContent],
    ) -> list[Any]:
        prompt = append_prompt_directives(
            request.prompt,
            f"Style: {request.style}" if request.style else None,
            f"Avoid: {request.negative_prompt}" if request.negative_prompt else None,
        )
        contents: list[Any] = [prompt]

        for image in reference_images:
            contents.append(await self._image_to_google_part(image))

        return contents

    def _build_generation_config(
        self,
        request: ImageGenerationRequest,
        *,
        seed_offset: int,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        config: dict[str, Any] = {
            "response_modalities": self._normalize_response_modalities(
                overrides.get("response_modalities")
            )
        }

        if request.seed is not None:
            config["seed"] = request.seed + seed_offset

        image_config = self._build_image_config(request, overrides)
        if image_config:
            config["image_config"] = image_config

        override_config = overrides.get("image_config")
        if isinstance(override_config, dict):
            config["image_config"] = {
                **config.get("image_config", {}),
                **override_config,
            }

        for key, value in overrides.items():
            if key in {"response_modalities", "image_config"}:
                continue
            if key in _GOOGLE_IMAGE_CONFIG_KEYS:
                config.setdefault("image_config", {})[key] = value
            else:
                config[key] = value

        return config

    def _build_image_config(
        self,
        request: ImageGenerationRequest,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        image_config: dict[str, Any] = {}

        if request.width > 0 and request.height > 0 and "aspect_ratio" not in overrides:
            image_config["aspect_ratio"] = self._closest_aspect_ratio(
                request.width,
                request.height,
            )

        if self._supports_image_size() and "image_size" not in overrides:
            image_config["image_size"] = self._infer_image_size(
                request.width,
                request.height,
            )

        return image_config

    def _supports_image_size(self) -> bool:
        model_id = self.model_id.lower()
        return model_id.startswith("gemini-3")

    def _infer_image_size(self, width: int, height: int) -> str:
        max_dimension = max(width, height)
        if max_dimension <= 1024:
            return "1K"
        if max_dimension <= 2048:
            return "2K"
        return "4K"

    def _normalize_response_modalities(self, value: Any) -> list[str]:
        if isinstance(value, list):
            normalized = [str(item).split(".")[-1].upper() for item in value]
        else:
            normalized = ["TEXT", "IMAGE"]

        if "IMAGE" not in normalized:
            normalized.append("IMAGE")
        if "TEXT" not in normalized:
            normalized.insert(0, "TEXT")
        return normalized

    async def _image_to_google_part(self, image: ImageContent) -> Any:
        from google.genai import types

        mime_type = self._guess_mime_type(image)
        if image.base64:
            return types.Part.from_bytes(
                data=self._decode_base64(image.base64),
                mime_type=mime_type,
            )
        if image.file_path:
            return types.Part.from_bytes(
                data=Path(image.file_path).read_bytes(),
                mime_type=mime_type,
            )
        if image.url:
            if image.url.startswith("data:"):
                inline_mime, inline_data = self._parse_data_uri(image.url)
                return types.Part.from_bytes(data=inline_data, mime_type=inline_mime)
            if image.url.startswith(("http://", "https://")):
                data, remote_mime = await self._fetch_remote_image(image.url, mime_type)
                return types.Part.from_bytes(data=data, mime_type=remote_mime)
            return types.Part.from_uri(file_uri=image.url, mime_type=mime_type)

        raise InvalidRequestError(
            message="Google reference image must include url, base64, or file_path",
            field="images",
            provider=self.provider,
            model=self.model_id,
        )

    async def _fetch_remote_image(
        self, url: str, fallback_mime: str
    ) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(
                    message=f"Failed to fetch Google reference image: {exc}",
                    provider=self.provider,
                    model=self.model_id,
                ) from exc

        content_type = response.headers.get("content-type", fallback_mime).split(";")[0]
        return response.content, content_type or fallback_mime

    def _decode_base64(self, value: str) -> bytes:
        if value.startswith("data:"):
            _, decoded = self._parse_data_uri(value)
            return decoded
        return base64.b64decode(value)

    def _parse_data_uri(self, value: str) -> tuple[str, bytes]:
        header, encoded = value.split(",", 1)
        mime_type = header[5:].split(";", 1)[0] or "image/png"
        return mime_type, base64.b64decode(encoded)

    def _guess_mime_type(self, image: ImageContent) -> str:
        if image.file_path:
            guessed, _ = mimetypes.guess_type(image.file_path)
            if guessed:
                return guessed
        if image.url:
            guessed, _ = mimetypes.guess_type(image.url)
            if guessed:
                return guessed
        if image.format:
            normalized = "jpeg" if image.format == "jpg" else image.format
            return f"image/{normalized}"
        return "image/png"

    def _parse_generated_images(
        self,
        response: Any,
        *,
        fallback_seed: int | None,
    ) -> list[GeneratedImage]:
        images: list[GeneratedImage] = []
        candidates = getattr(response, "candidates", None) or []

        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            revised_prompt = "\n".join(
                part.text.strip()
                for part in parts
                if getattr(part, "text", None) and part.text.strip()
            ).strip() or None

            for part in parts:
                inline_data = getattr(part, "inline_data", None)
                data = getattr(inline_data, "data", None)
                mime_type = getattr(inline_data, "mime_type", None)
                if not data or not mime_type or not str(mime_type).startswith("image/"):
                    continue
                image_bytes = data if isinstance(data, bytes) else base64.b64decode(data)
                images.append(
                    GeneratedImage(
                        image=ImageContent(
                            base64=base64.b64encode(image_bytes).decode("utf-8"),
                            format=self._mime_to_format(str(mime_type)),
                        ),
                        revised_prompt=revised_prompt,
                        seed=fallback_seed,
                    )
                )

            finish_reason = str(getattr(candidate, "finish_reason", "")).upper()
            if ("SAFETY" in finish_reason or "BLOCK" in finish_reason) and not images:
                raise ContentFilterError(
                    message="Google image generation was blocked by safety filters",
                    provider=self.provider,
                    model=self.model_id,
                )

        if images:
            return images

        prompt_feedback = getattr(response, "prompt_feedback", None)
        if prompt_feedback is not None:
            block_reason = getattr(prompt_feedback, "block_reason", None)
            if block_reason:
                raise ContentFilterError(
                    message=f"Google image generation blocked: {block_reason}",
                    provider=self.provider,
                    model=self.model_id,
                )

        raise InvalidRequestError(
            message="Google image model returned no image output",
            provider=self.provider,
            model=self.model_id,
        )

    def _mime_to_format(self, mime_type: str) -> str:
        mime_type = mime_type.split(";", 1)[0].lower()
        if mime_type == "image/jpeg":
            return "jpeg"
        if mime_type == "image/webp":
            return "webp"
        return "png"

    def _closest_aspect_ratio(self, width: int, height: int) -> str:
        target = width / height
        return min(
            _GOOGLE_IMAGE_ASPECT_RATIOS,
            key=lambda ratio: abs(_GOOGLE_IMAGE_ASPECT_RATIOS[ratio] - target),
        )
