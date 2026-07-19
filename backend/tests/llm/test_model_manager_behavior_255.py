from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.llm import manager as manager_module
from app.llm.errors import (
    AuthenticationError,
    ContentFilterError,
    ContextLengthError,
    InsufficientQuotaError,
    ModelDisabledError,
    ModelNotFoundError,
    ProviderError,
    RateLimitError,
)
from app.llm.manager import ModelManager
from app.models.model import ModelProvider, ModelType


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        (str(uuid4()), ("uuid", None, None)),
        ("openai/gpt-4o", (None, "openai", "gpt-4o")),
        ("openai/", (None, "openai", "")),
        ("gpt-4o", (None, None, None)),
    ],
)
def test_parse_model_identifier_accepts_only_uuid_or_provider_handle(
    identifier: str, expected: tuple[str | None, str | None, str | None]
) -> None:
    parsed = ModelManager()._parse_model_identifier(identifier)

    if expected[0] == "uuid":
        assert parsed == (identifier, None, None)
    else:
        assert parsed == expected


@pytest.mark.anyio
async def test_get_model_config_looks_up_handle_and_rejects_disabled_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        id=uuid4(),
        name="GPT-4o",
        is_enabled=False,
    )
    query = SimpleNamespace(first=AsyncMock(return_value=model))
    filter_models = Mock(return_value=query)
    monkeypatch.setattr(manager_module.Model, "filter", filter_models)

    with pytest.raises(ModelDisabledError) as exc_info:
        await ModelManager()._get_model_config("openai/gpt-4o", ModelType.CHAT)

    assert exc_info.value.model == str(model.id)
    filter_models.assert_called_once_with(
        provider="openai", model_id="gpt-4o", model_type=ModelType.CHAT
    )
    query.first.assert_awaited_once_with()


@pytest.mark.anyio
async def test_get_model_config_rejects_invalid_and_missing_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ModelManager()

    with pytest.raises(ModelNotFoundError, match="Invalid model identifier format"):
        await manager._get_model_config("gpt-4o")

    query = SimpleNamespace(first=AsyncMock(return_value=None))
    filter_models = Mock(return_value=query)
    monkeypatch.setattr(manager_module.Model, "filter", filter_models)

    with pytest.raises(ModelNotFoundError, match="No model found"):
        await manager._get_model_config(None, ModelType.EMBEDDING)

    filter_models.assert_called_once_with(
        model_type=ModelType.EMBEDDING, is_default=True
    )
    query.first.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("provider", "adapter_name", "provider_hint"),
    [
        (ModelProvider.OPENAI, "OpenAIAdapter", None),
        (ModelProvider.ANTHROPIC, "AnthropicAdapter", None),
        (ModelProvider.AZURE_OPENAI, "OpenAICompatibleAdapter", "azure"),
        (ModelProvider.CUSTOM, "OpenAICompatibleAdapter", "custom"),
        ("unregistered", "OpenAICompatibleAdapter", None),
    ],
)
def test_get_chat_adapter_selects_native_compatible_or_fallback_provider(
    monkeypatch: pytest.MonkeyPatch,
    provider: ModelProvider | str,
    adapter_name: str,
    provider_hint: str | None,
) -> None:
    created: list[tuple[str, tuple, dict]] = []

    def adapter_factory(name: str):
        def factory(*args, **kwargs):
            created.append((name, args, kwargs))
            return name

        return factory

    for name in ("OpenAIAdapter", "AnthropicAdapter", "OpenAICompatibleAdapter"):
        monkeypatch.setattr(manager_module, name, adapter_factory(name))

    config = SimpleNamespace(provider=provider)

    assert ModelManager()._get_chat_adapter(config) == adapter_name
    assert created == [
        (
            adapter_name,
            (config,),
            {} if provider_hint is None else {"provider_hint": provider_hint},
        )
    ]


@pytest.mark.parametrize(
    ("message", "error_type"),
    [
        ("NotFoundError: model does not exist", ModelNotFoundError),
        ("invalid API key", AuthenticationError),
        ("insufficient balance", InsufficientQuotaError),
        ("rate_limit reached", RateLimitError),
        ("maximum token context length", ContextLengthError),
        ("safety content filter", ContentFilterError),
        ("request timed out", ProviderError),
    ],
)
def test_handle_error_translates_provider_failures_to_llm_errors(
    message: str, error_type: type[Exception]
) -> None:
    error = ModelManager()._handle_error(Exception(message), "openai", "gpt-4o")

    assert isinstance(error, error_type)
    assert error.model == "gpt-4o"
    assert error.message == message
    if error_type is not ModelNotFoundError:
        assert error.provider == "openai"


@pytest.mark.anyio
async def test_chat_converts_messages_and_translates_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(provider="openai", model_id="gpt-4o")
    adapter = SimpleNamespace(chat=AsyncMock(side_effect=TimeoutError("timed out")))
    manager = ModelManager()
    monkeypatch.setattr(manager, "_get_model_config", AsyncMock(return_value=config))
    monkeypatch.setattr(manager, "_get_chat_adapter", lambda _config: adapter)

    with pytest.raises(ProviderError, match="timed out") as exc_info:
        await manager.chat([{"role": "user", "content": "hello"}])

    assert exc_info.value.provider == "openai"
    adapter.chat.assert_awaited_once()
    message = adapter.chat.await_args.args[0][0]
    assert message.role == "user"
    assert message.content == "hello"


@pytest.mark.anyio
async def test_generate_video_rejects_removed_image_inputs_before_model_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = ModelManager()
    get_config = AsyncMock()
    monkeypatch.setattr(manager, "_get_model_config", get_config)

    with pytest.raises(Exception) as exc_info:
        await manager.generate_video({"prompt": "animate this", "image": "data:image"})

    assert exc_info.value.code == "invalid_request"
    assert exc_info.value.field == "image"
    get_config.assert_not_awaited()
