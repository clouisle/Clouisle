import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.llm.adapters.video.luma import LumaVideoAdapter
from app.llm.errors import InvalidRequestError, ProviderError
from app.llm.types import ImageContent, TaskStatus, VideoGenerationRequest


REAL_ASYNC_CLIENT = httpx.AsyncClient


def adapter(**config):
    return LumaVideoAdapter(
        SimpleNamespace(
            model_id="ray-2",
            api_key="test-key",
            base_url="https://luma.invalid/v1/",
            config=config,
        )
    )


def mock_http(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *args, **kwargs: REAL_ASYNC_CLIENT(*args, transport=transport, **kwargs),
    )


def test_payload_reference_image_and_validation():
    luma = adapter()
    payload = luma._build_payload(
        VideoGenerationRequest(
            prompt="Orbit",
            duration=5.25,
            aspect_ratio="9:16",
            style="cinematic",
            camera_motion="pan left",
            motion_intensity=0.8,
            start_image=ImageContent(url="https://example.invalid/start.png"),
            seed=7,
            extra_params={"loop": True},
        )
    )

    assert payload == {
        "model": "ray-2",
        "prompt": (
            "Orbit\n\nStyle: cinematic\nCamera movement: pan left"
            "\nMotion intensity: 0.8"
        ),
        "duration": "5.2s",
        "aspect_ratio": "9:16",
        "keyframes": {
            "frame0": {
                "type": "image",
                "url": "https://example.invalid/start.png",
            }
        },
        "seed": 7,
        "loop": True,
    }
    minimal = luma._build_payload(VideoGenerationRequest(prompt="Orbit", duration=6))
    assert minimal["duration"] == "6s"
    assert "keyframes" not in minimal
    assert "seed" not in minimal

    with pytest.raises(InvalidRequestError):
        luma._build_payload(
            VideoGenerationRequest(
                prompt="Orbit", start_image=ImageContent(base64="cmVm")
            )
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("completed", TaskStatus.COMPLETED),
        ("failed", TaskStatus.FAILED),
        ("queued", TaskStatus.PENDING),
        ("pending", TaskStatus.PENDING),
        ("cancelled", TaskStatus.CANCELLED),
        ("canceled", TaskStatus.CANCELLED),
        (None, TaskStatus.PROCESSING),
    ],
)
def test_status_mapping(raw, expected):
    assert adapter()._map_status(raw) == expected


def test_video_and_error_shapes():
    luma = adapter()
    assert luma._extract_video_url({"assets": {"video": "one.mp4"}}) == "one.mp4"
    assert (
        luma._extract_video_url({"assets": {"video": {"url": "two.mp4"}}}) == "two.mp4"
    )
    assert (
        luma._extract_video_url({"assets": {"video": {"uri": "three.mp4"}}})
        == "three.mp4"
    )
    assert luma._extract_video_url({"assets": {"video": {"url": 1}}}) is None
    assert luma._extract_video_url({}) is None

    assert luma._extract_error({"failure_reason": {"message": "blocked"}}) == "blocked"
    assert luma._extract_error({"error": {"code": "quota"}}) == "quota"
    assert luma._extract_error({"error": {"detail": "bad"}}) == "{'detail': 'bad'}"
    assert luma._extract_error({"error": "failed"}) == "failed"
    assert luma._extract_error({}) is None


@pytest.mark.anyio
async def test_generate_success_failure_and_missing_id_with_mocked_http(monkeypatch):
    requests = []
    responses = iter(
        [
            {"id": 42},
            {"state": "completed", "assets": {"video": "video.mp4"}},
            {"id": "failed"},
            {"state": "failed", "failure_reason": {"message": "blocked"}},
            {},
        ]
    )

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=next(responses))

    mock_http(monkeypatch, handler)
    luma = adapter()
    succeeded = await luma.generate(VideoGenerationRequest(prompt="Orbit"))
    failed = await luma.generate(VideoGenerationRequest(prompt="Blocked"))
    with pytest.raises(ProviderError):
        await luma.generate(VideoGenerationRequest(prompt="Missing"))

    assert succeeded.task_id == "42"
    assert succeeded.status == TaskStatus.COMPLETED
    assert succeeded.video and succeeded.video.url == "video.mp4"
    assert succeeded.error is None
    assert failed.status == TaskStatus.FAILED
    assert failed.video is None
    assert failed.error == "blocked"
    assert requests[0].url == httpx.URL("https://luma.invalid/v1/generations")
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert json.loads(requests[0].content)["prompt"] == "Orbit"


@pytest.mark.anyio
async def test_polling_terminal_states_and_timeout_use_mocked_http_and_sleep(
    monkeypatch,
):
    responses = iter(
        [
            {"state": "queued"},
            {"state": "completed"},
            {"state": "failed"},
            {"state": "cancelled"},
        ]
    )
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=next(responses)))
    luma = adapter(poll_interval_seconds=1, task_timeout_seconds=5)

    with patch("asyncio.sleep", AsyncMock()) as sleep:
        assert (await luma.client.wait_for_generation("success"))[
            "state"
        ] == "completed"
        assert (await luma.client.wait_for_generation("failure"))["state"] == "failed"
        assert (await luma.client.wait_for_generation("cancelled"))[
            "state"
        ] == "cancelled"
    sleep.assert_awaited_once_with(1.0)

    mock_http(
        monkeypatch,
        lambda request: httpx.Response(200, json={"state": "processing"}),
    )
    with (
        patch("asyncio.sleep", AsyncMock()) as timeout_sleep,
        pytest.raises(ProviderError, match="timed out"),
    ):
        await luma.client.wait_for_generation("timeout")
    assert timeout_sleep.await_count == 6


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("slow"), httpx.ConnectError("offline")],
)
async def test_http_errors_are_translated(monkeypatch, error):
    def handler(request):
        raise error

    mock_http(monkeypatch, handler)
    with pytest.raises(ProviderError):
        await adapter().client.get_generation("task")
