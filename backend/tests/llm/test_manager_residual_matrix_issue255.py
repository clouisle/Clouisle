from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    InsufficientQuotaError,
    QuotaExceededError as LLMQuotaExceededError,
    ModelDisabledError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
    TaskNotFoundError,
)
from app.llm.manager import ModelManager
from app.schemas.response import BusinessError, ResponseCode
from app.models.model import ModelProvider, ModelType
from app.services.usage_tracker import QuotaExceededError


class StringProvider(Enum):
    UNKNOWN = "unknown"


def model(**overrides):
    values = {
        "id": "model-uuid",
        "name": "Test Model",
        "provider": "openai",
        "model_id": "test-model",
        "is_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def query(result):
    return SimpleNamespace(first=AsyncMock(return_value=result))


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        (
            "550e8400-e29b-41d4-a716-446655440000",
            "550e8400-e29b-41d4-a716-446655440000",
        ),
        ("openai/gpt-4o/preview", None),
        ("gpt-4o", None),
    ],
)
def test_parse_model_identifier_matrix(identifier, expected):
    assert ModelManager()._parse_model_identifier(identifier) == expected


@pytest.mark.asyncio
async def test_model_lookup_uuid_default_and_failure_matrix():
    manager = ModelManager()
    enabled = model()

    with patch("app.llm.manager.Model.filter", return_value=query(enabled)) as mocked:
        assert (
            await manager._get_model_config(str("550e8400-e29b-41d4-a716-446655440000"))
            is enabled
        )
        mocked.assert_called_once_with(
            id="550e8400-e29b-41d4-a716-446655440000",
            model_type=ModelType.CHAT,
        )

    with patch("app.llm.manager.Model.filter", return_value=query(enabled)) as mocked:
        assert await manager._get_model_config(None, ModelType.EMBEDDING) is enabled
        mocked.assert_called_once_with(model_type=ModelType.EMBEDDING, is_default=True)
    with pytest.raises(BusinessError) as exc_info:
        await manager._get_model_config("ambiguous-model")
    assert exc_info.value.code == ResponseCode.MODEL_NOT_FOUND
    assert exc_info.value.msg_key == "model_not_found"

    with patch("app.llm.manager.Model.filter", return_value=query(None)):
        with pytest.raises(ModelNotFoundError, match="No model found"):
            await manager._get_model_config(None, ModelType.RERANK)

    with patch(
        "app.llm.manager.Model.filter", return_value=query(model(is_enabled=False))
    ):
        with pytest.raises(ModelDisabledError, match="disabled"):
            await manager._get_model_config(None)


@pytest.mark.parametrize(
    ("provider", "constructor", "hint"),
    [
        (ModelProvider.OPENAI, "OpenAIAdapter", None),
        (ModelProvider.ANTHROPIC, "AnthropicAdapter", None),
        (ModelProvider.GOOGLE, "GeminiAdapter", None),
        (ModelProvider.DEEPSEEK, "DeepSeekAdapter", None),
        (ModelProvider.MOONSHOT, "MoonshotAdapter", None),
        (ModelProvider.OLLAMA, "OllamaAdapter", None),
        (ModelProvider.XAI, "XAIAdapter", None),
        (ModelProvider.AZURE_OPENAI, "OpenAICompatibleAdapter", "azure"),
        (ModelProvider.ZHIPU, "OpenAICompatibleAdapter", "zhipu"),
        (ModelProvider.QWEN, "OpenAICompatibleAdapter", "qwen"),
        (ModelProvider.BAICHUAN, "OpenAICompatibleAdapter", "baichuan"),
        (ModelProvider.MINIMAX, "OpenAICompatibleAdapter", "minimax"),
        (ModelProvider.VOLCENGINE, "OpenAICompatibleAdapter", "volcengine"),
        (ModelProvider.SILICONFLOW, "OpenAICompatibleAdapter", "siliconflow"),
        (ModelProvider.CUSTOM, "OpenAICompatibleAdapter", "custom"),
        (StringProvider.UNKNOWN, "OpenAICompatibleAdapter", None),
    ],
)
def test_chat_adapter_provider_matrix(provider, constructor, hint):
    manager = ModelManager()
    config = model(provider=provider)
    sentinel = object()

    with patch(f"app.llm.manager.{constructor}", return_value=sentinel) as factory:
        assert manager._get_chat_adapter(config) is sentinel

    if hint is None:
        factory.assert_called_once_with(config)
    else:
        factory.assert_called_once_with(config, provider_hint=hint)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (RuntimeError("resource does not exist"), ModelNotFoundError),
        (RuntimeError("invalid API key"), AuthenticationError),
        (RuntimeError("insufficient balance"), InsufficientQuotaError),
        (RuntimeError("rate_limit reached"), RateLimitError),
        (RuntimeError("token count exceeds max"), ContextLengthError),
        (RuntimeError("safety policy rejected input"), ContentFilterError),
        (RuntimeError("upstream unavailable"), ProviderError),
    ],
)
def test_handle_error_classification_matrix(error, expected):
    converted = ModelManager()._handle_error(error, "provider", "model")
    assert isinstance(converted, expected)
    assert converted.model == "model"


@pytest.mark.asyncio
async def test_team_model_authorization_matrix():
    manager = ModelManager()
    config = model()
    manager._get_model_config = AsyncMock(return_value=config)

    with patch("app.llm.manager.TeamModel.filter", return_value=query(None)):
        with pytest.raises(ModelNotFoundError, match="not authorized"):
            await manager._get_team_model("team-1", None)

    disabled = SimpleNamespace(is_enabled=False)
    with patch("app.llm.manager.TeamModel.filter", return_value=query(disabled)):
        with pytest.raises(ModelDisabledError, match="disabled for team"):
            await manager._get_team_model("team-1", None)

    enabled = SimpleNamespace(is_enabled=True)
    with patch("app.llm.manager.TeamModel.filter", return_value=query(enabled)):
        assert await manager._get_team_model("team-1", None) == (config, enabled)


@pytest.mark.asyncio
async def test_usage_quota_error_is_translated():
    manager = ModelManager()
    error = QuotaExceededError("daily limit", "daily_tokens")

    with patch.object(
        __import__("app.llm.manager", fromlist=["usage_tracker"]).usage_tracker,
        "check_and_record_usage",
        AsyncMock(side_effect=error),
    ):
        with pytest.raises(LLMQuotaExceededError) as raised:
            await manager._check_and_record_usage("team-1", "model-1", 42, 2)

    assert raised.value.quota_type == "daily_tokens"
    assert raised.value.team_id == "team-1"


@pytest.mark.asyncio
async def test_video_status_searches_candidates_and_returns_first_match():
    manager = ModelManager()
    first, second = model(id="first"), model(id="second")
    chain = Mock()
    chain.order_by = AsyncMock(return_value=[first, second])
    first_adapter = SimpleNamespace(
        get_status=AsyncMock(side_effect=TaskNotFoundError("missing"))
    )
    response = object()
    second_adapter = SimpleNamespace(get_status=AsyncMock(return_value=response))

    with (
        patch("app.llm.manager.Model.filter", return_value=chain) as filtered,
        patch(
            "app.llm.manager.create_video_adapter",
            side_effect=[first_adapter, second_adapter],
        ),
    ):
        assert await manager.get_video_status("task-1") is response

    filtered.assert_called_once_with(
        model_type=ModelType.TEXT_TO_VIDEO.value, is_enabled=True
    )
    chain.order_by.assert_awaited_once_with("-is_default", "sort_order", "name")


@pytest.mark.asyncio
async def test_video_status_explicit_model_preserves_llm_error_and_wraps_unknown():
    manager = ModelManager()
    config = model()
    manager._get_model_config = AsyncMock(return_value=config)

    adapter = SimpleNamespace(
        get_status=AsyncMock(side_effect=AuthenticationError("bad key"))
    )
    with patch("app.llm.manager.create_video_adapter", return_value=adapter):
        with pytest.raises(AuthenticationError, match="bad key"):
            await manager.get_video_status("task-1", "openai/video")

    adapter.get_status.side_effect = RuntimeError("offline")
    with patch("app.llm.manager.create_video_adapter", return_value=adapter):
        with pytest.raises(ProviderError, match="offline"):
            await manager.get_video_status("task-1", "openai/video")


@pytest.mark.asyncio
async def test_video_status_empty_and_exhausted_candidates():
    manager = ModelManager()
    chain = Mock()
    chain.order_by = AsyncMock(return_value=[])
    with (
        patch("app.llm.manager.Model.filter", return_value=chain),
        patch("app.llm.manager.t", return_value="no video model"),
    ):
        with pytest.raises(ModelNotFoundError, match="no video model"):
            await manager.get_video_status("task-1")

    config = model()
    chain.order_by.return_value = [config]
    adapter = SimpleNamespace(get_status=AsyncMock(side_effect=RuntimeError("offline")))
    with (
        patch("app.llm.manager.Model.filter", return_value=chain),
        patch("app.llm.manager.create_video_adapter", return_value=adapter),
    ):
        with pytest.raises(RuntimeError, match="offline"):
            await manager.get_video_status("task-1")
