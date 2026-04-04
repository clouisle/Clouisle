from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import httpx

from app.api.v1.endpoints.upload import infer_extension, save_generated_upload
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageContent, VideoContent


class MediaAssetService:
    """Normalize generated media into backend-served assets when needed."""

    IMAGE_CATEGORY = "generated-images"
    VIDEO_CATEGORY = "generated-videos"
    REMOTE_TIMEOUT = 60.0

    async def normalize_image(
        self, content: ImageContent | None
    ) -> ImageContent | None:
        if content is None:
            return None
        normalized = await self._normalize_media(
            content,
            category=self.IMAGE_CATEGORY,
            default_mime_type=self._get_image_mime_type(content),
        )
        return ImageContent(**normalized.model_dump(mode="json"))

    async def normalize_video(
        self, content: VideoContent | None
    ) -> VideoContent | None:
        if content is None:
            return None
        normalized = await self._normalize_media(
            content,
            category=self.VIDEO_CATEGORY,
            default_mime_type=self._get_video_mime_type(content),
        )
        return VideoContent(**normalized.model_dump(mode="json"))

    async def _normalize_media(
        self,
        content: ImageContent | VideoContent,
        *,
        category: str,
        default_mime_type: str,
    ) -> ImageContent | VideoContent:
        if content.base64:
            return await self._save_inline_media(
                content,
                category=category,
                default_mime_type=default_mime_type,
            )

        if content.file_path:
            return await self._save_local_media(
                content,
                category=category,
                default_mime_type=default_mime_type,
            )

        if content.url and self._should_mirror_remote_url(content.url):
            return await self._save_remote_media(
                content,
                category=category,
                default_mime_type=default_mime_type,
            )

        return self._strip_non_url_fields(content)

    async def _save_inline_media(
        self,
        content: ImageContent | VideoContent,
        *,
        category: str,
        default_mime_type: str,
    ) -> ImageContent | VideoContent:
        payload = content.base64 or ""
        detected_content_type, encoded = self._split_data_url(payload)
        content_type = detected_content_type or default_mime_type

        try:
            raw_bytes = base64.b64decode(encoded, validate=False)
        except Exception as exc:  # pragma: no cover - defensive
            raise InvalidRequestError(
                message=f"Invalid media base64 payload: {exc}"
            ) from exc

        upload_info = await save_generated_upload(
            content=raw_bytes,
            category=category,
            content_type=content_type,
            extension=infer_extension(content_type=content_type),
        )
        return self._build_url_only_content(content, upload_info["url"])

    async def _save_local_media(
        self,
        content: ImageContent | VideoContent,
        *,
        category: str,
        default_mime_type: str,
    ) -> ImageContent | VideoContent:
        file_path = Path(content.file_path or "")
        if not file_path.exists() or not file_path.is_file():
            raise InvalidRequestError(
                message=f"Media file not found: {content.file_path}"
            )

        async with aiofiles.open(file_path, "rb") as f:
            raw_bytes = await f.read()

        content_type = mimetypes.guess_type(file_path.name)[0] or default_mime_type
        upload_info = await save_generated_upload(
            content=raw_bytes,
            category=category,
            content_type=content_type,
            filename=file_path.name,
        )
        return self._build_url_only_content(content, upload_info["url"])

    async def _save_remote_media(
        self,
        content: ImageContent | VideoContent,
        *,
        category: str,
        default_mime_type: str,
    ) -> ImageContent | VideoContent:
        url = content.url or ""
        timeout = httpx.Timeout(self.REMOTE_TIMEOUT)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise ProviderError(
                    message=f"Failed to download generated media: {exc}"
                ) from exc

        content_type = (
            response.headers.get("content-type", "").split(";", 1)[0].strip()
            or default_mime_type
        )
        parsed = urlparse(url)
        remote_name = Path(parsed.path).name or None
        upload_info = await save_generated_upload(
            content=response.content,
            category=category,
            content_type=content_type,
            filename=remote_name,
        )
        return self._build_url_only_content(content, upload_info["url"])

    def _build_url_only_content(
        self,
        content: ImageContent | VideoContent,
        url: str,
    ) -> ImageContent | VideoContent:
        payload = content.model_dump(mode="json")
        payload["url"] = url
        payload["base64"] = None
        payload["file_path"] = None
        return content.__class__(**payload)

    def _strip_non_url_fields(
        self,
        content: ImageContent | VideoContent,
    ) -> ImageContent | VideoContent:
        payload = content.model_dump(mode="json")
        payload["base64"] = None
        payload["file_path"] = None
        return content.__class__(**payload)

    def _get_image_mime_type(self, content: ImageContent) -> str:
        image_format = (content.format or "png").lower()
        if image_format == "jpg":
            image_format = "jpeg"
        return f"image/{image_format}"

    def _get_video_mime_type(self, content: VideoContent) -> str:
        video_format = (content.format or "mp4").lower()
        return "video/quicktime" if video_format == "mov" else f"video/{video_format}"

    def _split_data_url(self, value: str) -> tuple[str | None, str]:
        if value.startswith("data:") and "," in value:
            header, encoded = value.split(",", 1)
            mime_type = header[5:].split(";", 1)[0] or None
            return mime_type, encoded
        return None, value

    def _should_mirror_remote_url(self, value: str) -> bool:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            return False
        return not value.startswith("/api/v1/upload/files/")


media_asset_service = MediaAssetService()
