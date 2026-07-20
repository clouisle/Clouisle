from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
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
    QuotaExceededError as LLMQuotaExceededError,
    RateLimitError,
    TaskNotFoundError,
)
from app.llm.manager import ModelManager
from app.models.model import ModelProvider, ModelType
from app.services.usage_tracker import QuotaExceededError


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


@pytest.mark.anyio
async def test_get_model_config_supports_uuid_and_enabled_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(id=uuid4(), name="Model", is_enabled=True)
    queries = [
        SimpleNamespace(first=AsyncMock(return_value=model)),
        SimpleNamespace(first=AsyncMock(return_value=model)),
    ]
    filter_models = Mock(side_effect=queries)
    monkeypatch.setattr(manager_module.Model, "filter", filter_models)
    manager = ModelManager()

    assert await manager._get_model_config(str(model.id)) is model
    assert await manager._get_model_config(None, ModelType.RERANK) is model
    assert filter_models.call_args_list == [
        call(id=str(model.id)),
        call(model_type=ModelType.RERANK, is_default=True),
    ]


@pytest.mark.parametrize(
    ("provider", "adapter_name", "provider_hint"),
    [
        (ModelProvider.GOOGLE, "GeminiAdapter", None),
        (ModelProvider.DEEPSEEK, "DeepSeekAdapter", None),
        (ModelProvider.MOONSHOT, "MoonshotAdapter", None),
        (ModelProvider.OLLAMA, "OllamaAdapter", None),
        (ModelProvider.XAI, "XAIAdapter", None),
        (ModelProvider.ZHIPU, "OpenAICompatibleAdapter", "zhipu"),
        (ModelProvider.QWEN, "OpenAICompatibleAdapter", "qwen"),
        (ModelProvider.BAICHUAN, "OpenAICompatibleAdapter", "baichuan"),
        (ModelProvider.MINIMAX, "OpenAICompatibleAdapter", "minimax"),
        (ModelProvider.VOLCENGINE, "OpenAICompatibleAdapter", "volcengine"),
        (ModelProvider.SILICONFLOW, "OpenAICompatibleAdapter", "siliconflow"),
    ],
)
def test_get_chat_adapter_covers_remaining_registered_providers(
    monkeypatch: pytest.MonkeyPatch,
    provider: ModelProvider,
    adapter_name: str,
    provider_hint: str | None,
) -> None:
    created = Mock(return_value=adapter_name)
    monkeypatch.setattr(manager_module, adapter_name, created)
    config = SimpleNamespace(provider=provider)

    assert ModelManager()._get_chat_adapter(config) == adapter_name
    expected_kwargs = {} if provider_hint is None else {"provider_hint": provider_hint}
    created.assert_called_once_with(config, **expected_kwargs)


@pytest.mark.anyio
async def test_chat_stream_yields_chunks_and_maps_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(provider="openai", model_id="gpt-4o")

    async def stream(*_args, **_kwargs):
        yield "first"
        yield "second"

    manager = ModelManager()
    monkeypatch.setattr(manager, "_get_model_config", AsyncMock(return_value=config))
    monkeypatch.setattr(
        manager,
        "_get_chat_adapter",
        lambda _config: SimpleNamespace(chat_stream=stream),
    )
    assert [
        chunk
        async for chunk in manager.chat_stream([{"role": "user", "content": "hi"}])
    ] == [
        "first",
        "second",
    ]

    async def failing_stream(*_args, **_kwargs):
        yield "partial"
        raise TimeoutError("stream timed out")

    monkeypatch.setattr(
        manager,
        "_get_chat_adapter",
        lambda _config: SimpleNamespace(chat_stream=failing_stream),
    )
    with pytest.raises(ProviderError, match="stream timed out"):
        _ = [chunk async for chunk in manager.chat_stream([])]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "factory_name", "model_type", "adapter_method", "args", "expected"),
    [
        (
            "embed",
            "create_embedding_model",
            ModelType.EMBEDDING,
            "aembed_documents",
            (["a"],),
            [[0.1]],
        ),
        (
            "embed_query",
            "create_embedding_model",
            ModelType.EMBEDDING,
            "aembed_query",
            ("a",),
            [0.1],
        ),
        (
            "rerank",
            "create_rerank_adapter",
            ModelType.RERANK,
            "rerank",
            ("query", ["doc"]),
            "ranked",
        ),
    ],
)
async def test_direct_invocations_select_model_factory_and_forward_arguments(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    factory_name: str,
    model_type: ModelType,
    adapter_method: str,
    args: tuple,
    expected: object,
) -> None:
    config = SimpleNamespace(provider="openai", model_id="model")
    operation = AsyncMock(return_value=expected)
    manager = ModelManager()
    get_config = AsyncMock(return_value=config)
    monkeypatch.setattr(manager, "_get_model_config", get_config)
    monkeypatch.setattr(
        manager_module,
        factory_name,
        Mock(return_value=SimpleNamespace(**{adapter_method: operation})),
    )

    kwargs = {"top_n": 1, "temperature": 0} if method_name == "rerank" else {}
    assert (
        await getattr(manager, method_name)(*args, model_id="selected", **kwargs)
        == expected
    )
    get_config.assert_awaited_once_with("selected", model_type)
    if method_name == "rerank":
        operation.assert_awaited_once_with(*args, top_n=1, temperature=0)
    else:
        operation.assert_awaited_once_with(*args)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method_name", "factory_name", "model_type", "adapter_method", "payload"),
    [
        (
            "generate_image",
            "create_image_adapter",
            ModelType.TEXT_TO_IMAGE,
            "generate",
            {"prompt": "image"},
        ),
        (
            "generate_video",
            "create_video_adapter",
            ModelType.TEXT_TO_VIDEO,
            "generate",
            {"prompt": "video"},
        ),
        (
            "text_to_speech",
            "create_tts_adapter",
            ModelType.TTS,
            "synthesize",
            {"text": "speech"},
        ),
        (
            "generate_audio",
            "create_audio_generation_adapter",
            ModelType.AUDIO_GENERATION,
            "generate",
            {"prompt": "audio"},
        ),
        (
            "speech_to_text",
            "create_stt_adapter",
            ModelType.STT,
            "transcribe",
            {"audio": {"base64": "YQ==", "format": "wav"}},
        ),
    ],
)
async def test_media_invocations_build_requests_and_preserve_llm_errors(
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    factory_name: str,
    model_type: ModelType,
    adapter_method: str,
    payload: dict,
) -> None:
    config = SimpleNamespace(provider="custom", model_id="media-model")
    original = ProviderError(
        message="provider failed", provider="custom", model="media-model"
    )
    operation = AsyncMock(side_effect=original)
    manager = ModelManager()
    get_config = AsyncMock(return_value=config)
    monkeypatch.setattr(manager, "_get_model_config", get_config)
    monkeypatch.setattr(
        manager_module,
        factory_name,
        Mock(return_value=SimpleNamespace(**{adapter_method: operation})),
    )

    with pytest.raises(ProviderError) as exc_info:
        await getattr(manager, method_name)(payload, model_id="selected")

    assert exc_info.value is original
    get_config.assert_awaited_once_with("selected", model_type)
    assert not isinstance(operation.await_args.args[0], dict)


@pytest.mark.anyio
async def test_model_factories_and_get_embedding_return_selected_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = SimpleNamespace(model_id="embedding-model", is_enabled=True)
    manager = ModelManager()
    get_config = AsyncMock(return_value=config)
    monkeypatch.setattr(manager, "_get_model_config", get_config)
    chat_model = object()
    embedding_model = SimpleNamespace(aembed_query=AsyncMock(return_value=[0.2]))
    monkeypatch.setattr(
        manager_module, "create_chat_model", Mock(return_value=chat_model)
    )
    monkeypatch.setattr(
        manager_module, "create_embedding_model", Mock(return_value=embedding_model)
    )

    assert await manager.get_chat_model("chat") is chat_model
    assert await manager.get_embedding_model("embedding") is embedding_model
    assert await manager.get_embedding(
        "text", user_id=uuid4(), model_id="embedding"
    ) == {
        "embedding": [0.2],
        "model_id": "embedding-model",
    }


@pytest.mark.anyio
async def test_team_model_requires_enabled_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(id=uuid4(), name="GPT", is_enabled=True)
    manager = ModelManager()
    monkeypatch.setattr(manager, "_get_model_config", AsyncMock(return_value=model))
    query = SimpleNamespace(
        first=AsyncMock(side_effect=[None, SimpleNamespace(is_enabled=False)])
    )
    monkeypatch.setattr(manager_module.TeamModel, "filter", Mock(return_value=query))

    with pytest.raises(ModelNotFoundError, match="not authorized"):
        await manager._get_team_model("team", None)
    with pytest.raises(ModelDisabledError, match="disabled for team"):
        await manager._get_team_model("team", None)


@pytest.mark.anyio
async def test_team_chat_checks_quota_records_usage_and_maps_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(id=uuid4(), provider="openai", model_id="gpt-4o")
    team_model = SimpleNamespace(is_enabled=True)
    result = SimpleNamespace(usage=SimpleNamespace(total_tokens=7))
    adapter = SimpleNamespace(chat=AsyncMock(return_value=result))
    manager = ModelManager()
    monkeypatch.setattr(
        manager, "_get_team_model", AsyncMock(return_value=(model, team_model))
    )
    monkeypatch.setattr(manager, "_get_chat_adapter", lambda _config: adapter)
    record = AsyncMock()
    monkeypatch.setattr(manager, "_check_and_record_usage", record)
    quota = AsyncMock()
    monkeypatch.setattr(manager_module.usage_tracker, "check_quota_with_model", quota)

    assert (
        await manager.team_chat("team", [{"role": "user", "content": "hi"}]) is result
    )
    quota.assert_awaited_once_with(team_model)
    record.assert_awaited_once_with(
        team_id="team", model_id=str(model.id), tokens_used=7
    )

    quota.side_effect = QuotaExceededError("daily token quota exceeded", "daily_tokens")
    with pytest.raises(LLMQuotaExceededError) as exc_info:
        await manager.team_chat("team", [])
    assert exc_info.value.team_id == "team"


@pytest.mark.anyio
async def test_team_stream_and_usage_recording_use_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(id=uuid4(), provider="openai", model_id="gpt-4o")
    team_model = SimpleNamespace(is_enabled=True)

    async def stream(*_args, **_kwargs):
        yield "chunk"

    manager = ModelManager()
    monkeypatch.setattr(
        manager, "_get_team_model", AsyncMock(return_value=(model, team_model))
    )
    monkeypatch.setattr(
        manager,
        "_get_chat_adapter",
        lambda _config: SimpleNamespace(chat_stream=stream),
    )
    monkeypatch.setattr(
        manager_module.usage_tracker, "check_quota_with_model", AsyncMock()
    )
    record = AsyncMock()
    monkeypatch.setattr(manager, "_check_and_record_usage", record)
    monkeypatch.setattr("app.llm.token_counter.count_tokens", Mock(side_effect=[2, 3]))

    assert [chunk async for chunk in manager.team_chat_stream("team", [])] == ["chunk"]
    await manager.record_stream_usage("team", None, 8, 12)
    record.assert_awaited_once_with(
        team_id="team", model_id=str(model.id), tokens_used=5
    )


@pytest.mark.anyio
async def test_video_status_tries_enabled_models_and_handles_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = SimpleNamespace(provider="one", model_id="first")
    second = SimpleNamespace(provider="two", model_id="second")
    query = SimpleNamespace(order_by=AsyncMock(return_value=[first, second]))
    monkeypatch.setattr(manager_module.Model, "filter", Mock(return_value=query))
    first_adapter = SimpleNamespace(
        get_status=AsyncMock(
            side_effect=TaskNotFoundError(message="missing", task_id="task")
        )
    )
    second_adapter = SimpleNamespace(get_status=AsyncMock(return_value="ready"))
    monkeypatch.setattr(
        manager_module,
        "create_video_adapter",
        Mock(side_effect=[first_adapter, second_adapter]),
    )

    assert await ModelManager().get_video_status("task") == "ready"

    empty_query = SimpleNamespace(order_by=AsyncMock(return_value=[]))
    monkeypatch.setattr(manager_module.Model, "filter", Mock(return_value=empty_query))
    with pytest.raises(ModelNotFoundError):
        await ModelManager().get_video_status("task")
