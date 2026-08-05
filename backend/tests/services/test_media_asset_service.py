import base64
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageContent, VideoContent
from app.services.media_asset_service import MediaAssetService


media_module = importlib.import_module("app.services.media_asset_service")


@pytest.mark.asyncio
async def test_normalize_none_and_format_boundaries() -> None:
    service = MediaAssetService()

    assert await service.normalize_image(None) is None
    assert await service.normalize_video(None) is None
    assert service._split_data_url("aW1hZ2U=") == (None, "aW1hZ2U=")
    assert service._get_image_mime_type(ImageContent(format="jpg")) == "image/jpeg"


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


@pytest.mark.asyncio
async def test_normalize_image_registers_generated_asset_and_scoped_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_id = uuid4()
    team_id = uuid4()
    user_id = uuid4()
    save_upload = AsyncMock(
        return_value={
            "url": "/api/v1/upload/files/generated-images/2026/08/image.png",
            "storage_key": "generated-images/2026/08/image.png",
            "filename": "image.png",
        }
    )
    asset = SimpleNamespace(id=uuid4())
    binding = SimpleNamespace(ref="a1b2")
    asset_service = SimpleNamespace(
        register_bytes=AsyncMock(return_value=asset),
        get_or_create_ref=AsyncMock(return_value=binding),
    )
    monkeypatch.setattr(media_module, "save_generated_upload", save_upload)
    monkeypatch.setattr("app.services.asset.asset_service", asset_service)

    normalized = await MediaAssetService().normalize_image(
        ImageContent(base64=base64.b64encode(b"image").decode()),
        team_id=team_id,
        created_by_id=user_id,
        conversation_id=conversation_id,
    )

    assert normalized is not None
    assert normalized.asset_ref == "a1b2"
    asset_service.register_bytes.assert_awaited_once()
    register_kwargs = asset_service.register_bytes.await_args.kwargs
    assert register_kwargs["content"] == b"image"
    assert register_kwargs["team_id"] == team_id
    assert register_kwargs["created_by_id"] == user_id
    asset_service.get_or_create_ref.assert_awaited_once()
