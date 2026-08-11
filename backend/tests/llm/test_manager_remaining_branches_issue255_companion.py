from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.errors import LLMError, TaskNotFoundError
from app.llm.manager import ModelManager
from app.llm.types import (
    AudioGenerationRequest,
    ImageGenerationRequest,
    RerankResponse,
    STTRequest,
    TTSRequest,
    VideoGenerationRequest,
)
from app.models.model import ModelType


@pytest.fixture(autouse=True)
def allow_model_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ModelManager, "_ensure_model_endpoint_allowed", AsyncMock())


class SplitlessIdentifier(str):
    def split(self, separator=None, maxsplit=-1):
        return [str(self)]


def test_parse_model_identifier_accepts_only_uuid():
    manager = ModelManager()

    assert manager._parse_model_identifier("550e8400-e29b-41d4-a716-446655440000") == (
        "550e8400-e29b-41d4-a716-446655440000"
    )
    assert manager._parse_model_identifier("openai/gpt-4o") is None
    assert manager._parse_model_identifier(SplitlessIdentifier("openai/gpt-4o")) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    (
        "method_name",
        "factory_name",
        "adapter_method",
        "model_type",
        "payload",
        "request_type",
    ),
    [
        (
            "generate_image",
            "create_image_adapter",
            "generate",
            ModelType.TEXT_TO_IMAGE,
            {"prompt": "draw"},
            ImageGenerationRequest,
        ),
        (
            "generate_video",
            "create_video_adapter",
            "generate",
            ModelType.TEXT_TO_VIDEO,
            {"prompt": "animate"},
            VideoGenerationRequest,
        ),
        (
            "text_to_speech",
            "create_tts_adapter",
            "synthesize",
            ModelType.TTS,
            {"text": "hello"},
            TTSRequest,
        ),
        (
            "generate_audio",
            "create_audio_generation_adapter",
            "generate",
            ModelType.AUDIO_GENERATION,
            {"prompt": "waves"},
            AudioGenerationRequest,
        ),
        (
            "speech_to_text",
            "create_stt_adapter",
            "transcribe",
            ModelType.STT,
            {"audio": {"base64": "YQ=="}},
            STTRequest,
        ),
    ],
)
async def test_media_methods_coerce_dict_requests(
    method_name, factory_name, adapter_method, model_type, payload, request_type
):
    manager = ModelManager()
    model = SimpleNamespace(provider="provider", model_id="model")
    manager._get_model_config = AsyncMock(return_value=model)
    adapter_call = AsyncMock(return_value=object())
    adapter = SimpleNamespace(**{adapter_method: adapter_call})

    with patch(f"app.llm.manager.{factory_name}", return_value=adapter):
        await getattr(manager, method_name)(payload)

    manager._get_model_config.assert_awaited_once_with(None, model_type)
    assert isinstance(adapter_call.await_args.args[0], request_type)


@pytest.mark.anyio
async def test_video_status_handles_explicit_and_fallback_llm_errors():
    manager = ModelManager()
    model = SimpleNamespace(provider="provider", model_id="video")
    manager._get_model_config = AsyncMock(return_value=model)
    explicit_error = LLMError("explicit failure")

    with patch(
        "app.llm.manager.create_video_adapter",
        return_value=SimpleNamespace(get_status=AsyncMock(side_effect=explicit_error)),
    ):
        with pytest.raises(LLMError) as caught:
            await manager.get_video_status("task", model_id="provider/video")
    assert caught.value is explicit_error

    models = [
        SimpleNamespace(provider="first", model_id="one"),
        SimpleNamespace(provider="second", model_id="two"),
    ]
    query = MagicMock()
    query.order_by = AsyncMock(return_value=models)
    fallback_error = LLMError("fallback failure")
    adapters = [
        SimpleNamespace(
            get_status=AsyncMock(side_effect=TaskNotFoundError(task_id="task"))
        ),
        SimpleNamespace(get_status=AsyncMock(side_effect=fallback_error)),
    ]

    with (
        patch("app.llm.manager.Model.filter", return_value=query),
        patch("app.llm.manager.create_video_adapter", side_effect=adapters),
    ):
        with pytest.raises(LLMError) as caught:
            await manager.get_video_status("task")

    assert caught.value is fallback_error
    query.order_by.assert_awaited_once_with("-is_default", "sort_order", "name")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("reported_tokens", "counted_tokens"), [(7, []), (0, [2, 3, 4])]
)
async def test_team_rerank_records_reported_or_counted_tokens(
    reported_tokens, counted_tokens
):
    manager = ModelManager()
    model = SimpleNamespace(id="model-id", provider="provider", model_id="reranker")
    team_model = object()
    manager._get_team_model = AsyncMock(return_value=(model, team_model))
    manager._check_and_record_usage = AsyncMock()
    response = RerankResponse(model="reranker")
    response.usage.total_tokens = reported_tokens
    adapter = SimpleNamespace(rerank=AsyncMock(return_value=response))

    with (
        patch(
            "app.llm.manager.usage_tracker.check_quota_with_model",
            new_callable=AsyncMock,
        ) as check_quota,
        patch("app.llm.manager.create_rerank_adapter", return_value=adapter),
        patch(
            "app.llm.token_counter.count_tokens", side_effect=counted_tokens
        ) as count,
    ):
        result = await manager.team_rerank(
            "team-id", "query", ["first", "second"], top_n=1
        )

    assert result is response
    check_quota.assert_awaited_once_with(team_model)
    assert count.call_count == len(counted_tokens)
    expected_tokens = reported_tokens or sum(counted_tokens)
    manager._check_and_record_usage.assert_awaited_once_with(
        team_id="team-id", model_id="model-id", tokens_used=expected_tokens
    )
