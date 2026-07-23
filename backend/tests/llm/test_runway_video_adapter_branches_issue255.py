from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm.adapters.video.runway import RunwayVideoAdapter
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageContent, TaskStatus, VideoGenerationRequest


def adapter(model_id="gen4.5", **config):
    return RunwayVideoAdapter(
        SimpleNamespace(
            model_id=model_id,
            api_key="test-key",
            base_url="https://runway.invalid",
            config=config,
        )
    )


def mock_http(*responses):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.request.side_effect = [
        httpx.Response(
            200,
            request=httpx.Request("GET", "https://runway.invalid"),
            json=response,
        )
        for response in responses
    ]
    return client


def test_payload_options_reference_image_and_validation():
    runway = adapter()
    path, payload = runway._build_request(
        VideoGenerationRequest(
            prompt="Orbit",
            duration=5.6,
            aspect_ratio="unsupported",
            style="cinematic",
            camera_motion="pan left",
            seed=7,
            extra_params={"watermark": False},
        )
    )
    assert path == "/v1/text_to_video"
    assert payload == {
        "model": "gen4.5",
        "promptText": "Orbit\n\nStyle: cinematic\nCamera movement: pan left",
        "ratio": "1280:720",
        "duration": 6,
        "seed": 7,
        "watermark": False,
    }

    path, payload = adapter("gen4_turbo")._build_request(
        VideoGenerationRequest(
            prompt="Animate",
            aspect_ratio="9:16",
            start_image=ImageContent(url="https://example.invalid/reference.png"),
            seed=8,
            extra_params={"watermark": True},
        )
    )
    assert path == "/v1/image_to_video"
    assert payload["promptImage"] == "https://example.invalid/reference.png"
    assert payload["ratio"] == "720:1280"
    assert payload["seed"] == 8
    assert payload["watermark"] is True

    _, minimal_payload = adapter("gen4_turbo")._build_request(
        VideoGenerationRequest(
            prompt="Animate",
            start_image=ImageContent(url="https://example.invalid/reference.png"),
        )
    )
    assert "seed" not in minimal_payload

    with pytest.raises(InvalidRequestError, match="text-to-video"):
        adapter("gen4_turbo")._build_request(VideoGenerationRequest(prompt="Text"))
    with pytest.raises(InvalidRequestError, match="image-to-video"):
        adapter()._build_request(
            VideoGenerationRequest(
                prompt="Image", start_image=ImageContent(base64="cmVm")
            )
        )


@pytest.mark.anyio
async def test_generate_success_missing_id_and_status_responses():
    runway = adapter()
    runway.client = SimpleNamespace(
        create_task=AsyncMock(side_effect=[{"id": 123}, {}]),
        get_task=AsyncMock(
            side_effect=[
                {"status": "COMPLETED", "output": [{"uri": "video.mp4"}]},
                {"status": "THROTTLED", "failure": {"code": "quota"}},
                {"status": "FAILED", "error": "blocked"},
            ]
        ),
    )

    result = await runway.generate(VideoGenerationRequest(prompt="Orbit"))
    assert result.task_id == "123"
    assert result.status == TaskStatus.COMPLETED
    assert result.video and result.video.url == "video.mp4"
    assert result.error is None

    with pytest.raises(ProviderError):
        await runway.generate(VideoGenerationRequest(prompt="Orbit"))

    throttled = await runway.get_status("throttled")
    blocked = await runway.get_status("blocked")
    assert throttled.status == TaskStatus.FAILED
    assert throttled.error == "quota"
    assert blocked.error == "blocked"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SUCCEEDED", TaskStatus.COMPLETED),
        ("CANCELED", TaskStatus.CANCELLED),
        ("CANCELLED", TaskStatus.CANCELLED),
        ("PENDING", TaskStatus.PENDING),
        ("QUEUED", TaskStatus.PENDING),
        (None, TaskStatus.PROCESSING),
    ],
)
def test_status_mapping(raw, expected):
    assert adapter()._map_status(raw) == expected


def test_output_and_error_shapes():
    runway = adapter()
    assert runway._extract_video_url({"output": ["one.mp4"]}) == "one.mp4"
    assert runway._extract_video_url({"output": [{"url": "two.mp4"}]}) == "two.mp4"
    assert runway._extract_video_url({"output": [1, {}]}) is None
    assert runway._extract_video_url({"output": {"video": "three.mp4"}}) == "three.mp4"
    assert runway._extract_video_url({"output": {"videos": ["four.mp4"]}}) == "four.mp4"
    assert (
        runway._extract_video_url({"output": {"videos": [{"uri": "five.mp4"}]}})
        == "five.mp4"
    )
    assert runway._extract_video_url({"output": {"videos": [1]}}) is None
    assert runway._extract_video_url({"output": {"videos": [{"size": 1}]}}) is None
    assert runway._extract_video_url({"output": {"videos": []}}) is None
    assert runway._extract_video_url({"output": {"videos": "invalid"}}) is None
    assert runway._extract_video_url({"output": None}) is None
    assert runway._extract_error({"failure": {"message": "failed"}}) == "failed"
    assert (
        runway._extract_error({"failure": {"detail": "failed"}})
        == "{'detail': 'failed'}"
    )
    assert runway._extract_error({}) is None


@pytest.mark.anyio
async def test_polling_success_failure_and_timeout_use_mocked_http_and_sleep():
    runway = adapter(poll_interval_seconds=1, task_timeout_seconds=5)
    http_client = mock_http(
        {"status": "PENDING"},
        {"status": "SUCCEEDED", "output": ["video.mp4"]},
        {"status": "FAILED", "failure": "blocked"},
    )
    sleep = AsyncMock()
    with (
        patch("httpx.AsyncClient", return_value=http_client),
        patch("asyncio.sleep", sleep),
    ):
        succeeded = await runway.client.wait_for_task("success")
        failed = await runway.client.wait_for_task("failure")
    assert succeeded["status"] == "SUCCEEDED"
    assert failed["status"] == "FAILED"
    sleep.assert_awaited_once_with(1.0)

    timeout_client = mock_http(*[{"status": "PROCESSING"}] * 6)
    with (
        patch("httpx.AsyncClient", return_value=timeout_client),
        patch("asyncio.sleep", AsyncMock()) as timeout_sleep,
        pytest.raises(ProviderError, match="timed out"),
    ):
        await runway.client.wait_for_task("timeout")
    assert timeout_sleep.await_count == 6
