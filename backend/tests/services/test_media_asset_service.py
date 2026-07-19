import base64
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageContent, VideoContent
from app.services.media_asset_service import MediaAssetService


media_module = importlib.import_module("app.services.media_asset_service")


@pytest.mark.asyncio
async def test_normalize_image_saves_inline_data_uri_with_detected_mime_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_upload = AsyncMock(return_value={"url": "/api/v1/upload/files/image.png"})
    monkeypatch.setattr(media_module, "save_generated_upload", save_upload)
    service = MediaAssetService()

    content = ImageContent(
        base64="data:image/jpeg;base64," + base64.b64encode(b"image").decode()
    )
    normalized = await service.normalize_image(content)

    assert normalized == ImageContent(url="/api/v1/upload/files/image.png")
    save_upload.assert_awaited_once_with(
        content=b"image",
        category="generated-images",
        content_type="image/jpeg",
        extension=".jpg",
    )


@pytest.mark.asyncio
async def test_normalize_video_saves_local_file_and_rejects_missing_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_upload = AsyncMock(return_value={"url": "/api/v1/upload/files/video.mov"})
    monkeypatch.setattr(media_module, "save_generated_upload", save_upload)
    media_file = tmp_path / "clip.mov"
    media_file.write_bytes(b"video")
    service = MediaAssetService()

    normalized = await service.normalize_video(VideoContent(file_path=str(media_file)))

    assert normalized == VideoContent(url="/api/v1/upload/files/video.mov")
    save_upload.assert_awaited_once_with(
        content=b"video",
        category="generated-videos",
        content_type="video/quicktime",
        filename="clip.mov",
    )
    with pytest.raises(InvalidRequestError, match="Media file not found"):
        await service.normalize_video(
            VideoContent(file_path=str(tmp_path / "missing.mp4"))
        )


@pytest.mark.asyncio
async def test_normalize_remote_media_mirrors_http_only_and_maps_download_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_upload = AsyncMock(return_value={"url": "/api/v1/upload/files/image.webp"})
    monkeypatch.setattr(media_module, "save_generated_upload", save_upload)
    response = SimpleNamespace(
        headers={"content-type": "image/webp; charset=utf-8"},
        content=b"remote-image",
        raise_for_status=lambda: None,
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            return response

    monkeypatch.setattr(media_module.httpx, "AsyncClient", lambda **_kwargs: Client())
    service = MediaAssetService()

    mirrored = await service.normalize_image(
        ImageContent(url="https://cdn.example.test/images/photo.webp")
    )
    retained = await service.normalize_image(
        ImageContent(url="/api/v1/upload/files/kept.png")
    )

    assert mirrored == ImageContent(url="/api/v1/upload/files/image.webp")
    assert retained == ImageContent(url="/api/v1/upload/files/kept.png")
    save_upload.assert_awaited_once_with(
        content=b"remote-image",
        category="generated-images",
        content_type="image/webp",
        filename="photo.webp",
    )

    class FailingClient(Client):
        async def get(self, _url):
            raise httpx.ConnectError("offline")

    monkeypatch.setattr(
        media_module.httpx, "AsyncClient", lambda **_kwargs: FailingClient()
    )
    with pytest.raises(ProviderError, match="Failed to download generated media"):
        await service.normalize_image(
            ImageContent(url="https://cdn.example.test/image.png")
        )
