from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.adapters.image.minimax import MiniMaxImageAdapter
from app.llm.adapters.minimax_client import MiniMaxClient
from app.llm.adapters.video.minimax import MiniMaxVideoAdapter
from app.llm.errors import AuthenticationError, ProviderError
from app.llm.types import (
    ImageContent,
    ImageGenerationRequest,
    TaskStatus,
    VideoGenerationRequest,
)


def build_model(model_id: str, **kwargs):
    return SimpleNamespace(
        provider="minimax",
        model_id=model_id,
        api_key="test-key",
        base_url=kwargs.get("base_url"),
        default_params=kwargs.get("default_params", {}),
        config=kwargs.get("config", {}),
    )


def test_minimax_client_uses_domestic_default_and_normalizes_v1_path():
    client = MiniMaxClient(build_model("image-01"))
    assert client._build_url("/v1/image_generation") == (
        "https://api.minimax.chat/v1/image_generation"
    )
    assert client._headers()["Authorization"] == "Bearer test-key"


def test_minimax_client_maps_application_auth_error():
    client = MiniMaxClient(build_model("image-01"))
    with pytest.raises(AuthenticationError):
        client._raise_for_application_error(
            {"base_resp": {"status_code": 2049, "status_msg": "invalid key"}}
        )


def test_minimax_image_builds_reference_payload_and_parses_urls():
    adapter = MiniMaxImageAdapter(
        build_model("image-01", default_params={"aspect_ratio": "16:9"})
    )
    request = ImageGenerationRequest(
        prompt="A person in snow",
        num_images=2,
        images=[ImageContent(base64="cmVm", format="png")],
    )

    payload = adapter._build_payload(request)
    response = adapter._parse_response(
        {"data": {"image_urls": ["https://cdn.example/image.png"]}}, payload
    )

    assert payload["aspect_ratio"] == "16:9"
    assert "width" not in payload
    assert payload["subject_reference"] == [
        {
            "type": "character",
            "image_file": "data:image/png;base64,cmVm",
        }
    ]
    assert response.images[0].image.url == "https://cdn.example/image.png"


def test_minimax_image_rejects_empty_output():
    adapter = MiniMaxImageAdapter(build_model("image-01"))
    with pytest.raises(ProviderError):
        adapter._parse_response({"data": {}}, {"response_format": "url"})


@pytest.mark.anyio
async def test_minimax_video_resolves_successful_task_download():
    adapter = MiniMaxVideoAdapter(build_model("MiniMax-Hailuo-2.3"))
    adapter.client = SimpleNamespace(
        request=AsyncMock(
            side_effect=[
                {"status": "Success", "file_id": "file-1"},
                {"file": {"download_url": "https://cdn.example/video.mp4"}},
            ]
        )
    )

    response = await adapter.get_status("task-1")

    assert response.status == TaskStatus.COMPLETED
    assert response.video and response.video.url == "https://cdn.example/video.mp4"


def test_minimax_video_builds_first_frame_without_mapping_aspect_ratio():
    adapter = MiniMaxVideoAdapter(
        build_model(
            "MiniMax-Hailuo-2.3",
            default_params={"resolution": "1080P"},
        )
    )
    payload = adapter._build_payload(
        VideoGenerationRequest(
            prompt="Ocean waves",
            aspect_ratio="9:16",
            duration=6,
            start_image=ImageContent(url="https://example.com/start.png"),
        )
    )

    assert payload["resolution"] == "1080P"
    assert "aspect_ratio" not in payload
    assert payload["first_frame_image"] == "https://example.com/start.png"


def test_minimax_video_maps_provider_statuses():
    assert MiniMaxVideoAdapter._map_status("Preparing") == TaskStatus.PENDING
    assert MiniMaxVideoAdapter._map_status("Queueing") == TaskStatus.PENDING
    assert MiniMaxVideoAdapter._map_status("Processing") == TaskStatus.PROCESSING
    assert MiniMaxVideoAdapter._map_status("Success") == TaskStatus.COMPLETED
    assert MiniMaxVideoAdapter._map_status("Fail") == TaskStatus.FAILED
