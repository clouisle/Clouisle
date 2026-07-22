import json
from types import SimpleNamespace

import httpx
import pytest

from app.llm.adapters.video.minimax import MiniMaxVideoAdapter
from app.llm.errors import ProviderError
from app.llm.types import TaskStatus, VideoGenerationRequest


def build_adapter(monkeypatch, handler, *, default_params=None):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    model = SimpleNamespace(
        model_id="MiniMax-Hailuo-2.3",
        api_key="test-key",
        base_url="https://minimax.test/v1",
        config={},
        default_params=default_params or {},
    )
    return MiniMaxVideoAdapter(model)


@pytest.mark.anyio
async def test_generate_posts_payload_and_downloads_completed_video(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/video_generation":
            return httpx.Response(200, json={"task_id": 42})
        if request.url.path == "/v1/query/video_generation":
            return httpx.Response(200, json={"status": "Success", "file_id": "file-1"})
        return httpx.Response(
            200,
            json={"file": {"download_url": "https://cdn.test/video.mp4"}},
        )

    adapter = build_adapter(
        monkeypatch,
        handler,
        default_params={"resolution": "720P", "ignored": True},
    )
    response = await adapter.generate(
        VideoGenerationRequest(
            prompt="Ocean waves",
            duration=6,
            style="cinematic",
            camera_motion="pan left",
            extra_params={"resolution": "1080P", "prompt_optimizer": None},
        )
    )

    payload = json.loads(requests[0].content)
    assert payload == {
        "resolution": "1080P",
        "model": "MiniMax-Hailuo-2.3",
        "prompt": "Ocean waves\n\nStyle: cinematic\nCamera movement: pan left",
        "duration": 6,
    }
    assert requests[1].url.params["task_id"] == "42"
    assert requests[2].url.params["file_id"] == "file-1"
    assert response.status == TaskStatus.COMPLETED
    assert response.video and response.video.url == "https://cdn.test/video.mp4"


@pytest.mark.anyio
async def test_generate_rejects_response_without_task_id(monkeypatch):
    adapter = build_adapter(
        monkeypatch, lambda _request: httpx.Response(200, json={"task_id": ""})
    )

    with pytest.raises(ProviderError):
        await adapter.generate(VideoGenerationRequest(prompt="Ocean waves"))


@pytest.mark.parametrize(
    ("task", "file_data", "expected_status", "expected_error"),
    [
        ({"status": "Success"}, None, TaskStatus.FAILED, True),
        (
            {"status": "Success", "file_id": "file-1"},
            {"file": []},
            TaskStatus.FAILED,
            True,
        ),
        (
            {"status": "Failed", "base_resp": {"status_msg": "blocked"}},
            None,
            TaskStatus.FAILED,
            "blocked",
        ),
        ({"status": "Fail", "base_resp": []}, None, TaskStatus.FAILED, True),
        ({"status": "Queueing"}, None, TaskStatus.PENDING, None),
    ],
)
@pytest.mark.anyio
async def test_get_status_covers_missing_output_and_failure_details(
    monkeypatch, task, file_data, expected_status, expected_error
):
    def handler(request):
        if request.url.path == "/v1/files/retrieve":
            return httpx.Response(200, json=file_data)
        return httpx.Response(200, json=task)

    response = await build_adapter(monkeypatch, handler).get_status("task-1")

    assert response.status == expected_status
    if isinstance(expected_error, str):
        assert response.error == expected_error
    elif expected_error:
        assert response.error
    else:
        assert response.error is None


def test_status_and_response_helpers_reject_invalid_values():
    assert MiniMaxVideoAdapter._map_status("failed") == TaskStatus.FAILED
    assert MiniMaxVideoAdapter._map_status(None) == TaskStatus.PENDING
    assert MiniMaxVideoAdapter._extract_video_url({}) is None
    assert MiniMaxVideoAdapter._extract_video_url({"file": {"download_url": 1}}) is None
    assert (
        MiniMaxVideoAdapter._extract_video_url({"file": {"download_url": ""}}) is None
    )
    assert MiniMaxVideoAdapter._extract_error({}) is None
    assert MiniMaxVideoAdapter._extract_error({"base_resp": {"status_msg": 1}}) is None
    assert MiniMaxVideoAdapter._extract_error({"base_resp": {"status_msg": ""}}) is None
