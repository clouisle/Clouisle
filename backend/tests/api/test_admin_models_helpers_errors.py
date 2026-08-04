from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import models as models_endpoint
from app.schemas.model import ModelCreate, ModelProvider, ModelType, ModelUpdate
from app.schemas.response import BusinessError, ResponseCode


@pytest.mark.parametrize(
    ("provider", "adapter_name", "provider_hint"),
    [
        (ModelProvider.OPENAI, "OpenAIAdapter", None),
        (ModelProvider.ANTHROPIC, "AnthropicAdapter", None),
        (ModelProvider.GOOGLE, "GeminiAdapter", None),
        (ModelProvider.XAI, "XAIAdapter", None),
        (ModelProvider.AZURE_OPENAI, "OpenAICompatibleAdapter", "azure"),
        (ModelProvider.DEEPSEEK, "DeepSeekAdapter", None),
        (ModelProvider.ZHIPU, "OpenAICompatibleAdapter", "zhipu"),
        (ModelProvider.QWEN, "OpenAICompatibleAdapter", "qwen"),
        (ModelProvider.BAICHUAN, "OpenAICompatibleAdapter", "baichuan"),
        (ModelProvider.MINIMAX, "OpenAICompatibleAdapter", "minimax"),
        (ModelProvider.CUSTOM, "OpenAICompatibleAdapter", "custom"),
        (ModelProvider.SILICONFLOW, "OpenAICompatibleAdapter", "siliconflow"),
    ],
)
@pytest.mark.anyio
async def test_chat_helper_selects_provider_adapter_and_forwards_config(
    provider, adapter_name, provider_hint
):
    from app.llm.adapters import chat as chat_adapters

    adapter = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="ok"))
    )
    adapter_class = Mock(return_value=adapter)

    with patch.object(chat_adapters, adapter_name, adapter_class):
        await models_endpoint._test_chat_model(
            provider,
            "model-id",
            "test-key",
            "https://example.test/v1",
            {"max_tokens": 123},
            {"timeout": 7},
        )

    temp_model = adapter_class.call_args.args[0]
    assert temp_model.provider == provider
    assert temp_model.default_params == {"max_tokens": 123}
    assert temp_model.max_output_tokens == 123
    assert temp_model.config == {"timeout": 7}
    if provider_hint is None:
        adapter_class.assert_called_once_with(temp_model)
    else:
        adapter_class.assert_called_once_with(temp_model, provider_hint=provider_hint)


@pytest.mark.anyio
async def test_chat_helper_rejects_empty_response():
    from app.llm.adapters import chat as chat_adapters

    adapter = SimpleNamespace(chat=AsyncMock(return_value=SimpleNamespace(content="")))
    with patch.object(chat_adapters, "OpenAIAdapter", return_value=adapter):
        with pytest.raises(BusinessError) as exc_info:
            await models_endpoint._test_chat_model(
                ModelProvider.OPENAI, "model-id", "sk-test", None, {}, {}
            )

    assert exc_info.value.msg_key == "model_test_empty_response"


@pytest.mark.anyio
async def test_embedding_helper_forwards_config_and_translates_incompatible_response():
    embedding = SimpleNamespace(
        aembed_query=AsyncMock(
            side_effect=AttributeError("'str' object has no attribute 'data'")
        )
    )

    with patch(
        "app.llm.adapters.embedding.factory.create_embedding_model",
        return_value=embedding,
    ) as create_embedding:
        with pytest.raises(BusinessError) as exc_info:
            await models_endpoint._test_embedding_model(
                ModelProvider.CUSTOM,
                "embed-model",
                "test-key",
                "https://example.test/v1",
                {"dimensions": 1024},
            )

    temp_model = create_embedding.call_args.args[0]
    assert temp_model.config == {"dimensions": 1024}
    assert exc_info.value.msg_key == "model_test_embedding_response_incompatible"


@pytest.mark.anyio
async def test_rerank_helper_forwards_config_and_rejects_empty_results():
    adapter = SimpleNamespace(
        rerank=AsyncMock(return_value=SimpleNamespace(results=[]))
    )

    with patch(
        "app.llm.adapters.rerank.create_rerank_adapter", return_value=adapter
    ) as create_adapter:
        with pytest.raises(BusinessError) as exc_info:
            await models_endpoint._test_rerank_model(
                ModelProvider.CUSTOM,
                "rerank-model",
                "test-key",
                "https://example.test/v1",
                {"timeout": 9},
            )

    temp_model = create_adapter.call_args.args[0]
    assert temp_model.config == {"timeout": 9}
    assert exc_info.value.msg_key == "model_test_empty_rerank_result"


@pytest.mark.parametrize(
    ("provider", "api_key"),
    [
        (ModelProvider.OPENAI, None),
        (ModelProvider.OPENAI, "not-openai"),
        (ModelProvider.ANTHROPIC, None),
        (ModelProvider.ANTHROPIC, "sk-wrong-prefix"),
    ],
)
def test_api_key_validation_rejects_invalid_known_formats(provider, api_key):
    with pytest.raises(BusinessError) as exc_info:
        models_endpoint._validate_api_key(provider, api_key)

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    assert exc_info.value.msg_key == "invalid_api_key_format"


@pytest.mark.parametrize(
    ("provider", "api_key"),
    [
        (ModelProvider.OPENAI, "sk-test"),
        (ModelProvider.ANTHROPIC, "sk-ant-test"),
        (ModelProvider.OLLAMA, None),
        (ModelProvider.CUSTOM, None),
    ],
)
def test_api_key_validation_accepts_supported_provider_rules(provider, api_key):
    models_endpoint._validate_api_key(provider, api_key)


@pytest.mark.parametrize(
    ("provider", "required"),
    [(ModelProvider.OLLAMA, False), (ModelProvider.OPENAI, True)],
)
def test_api_key_requirement_depends_on_provider(provider, required):
    assert models_endpoint._requires_api_key(provider) is required


@pytest.mark.anyio
async def test_create_model_allows_duplicate_provider_model_id():
    """Same provider/model_id may be configured multiple times."""
    created = SimpleNamespace(
        id=uuid4(),
        name="Duplicate",
        provider="openai",
        model_id="duplicate-model",
        model_type="chat",
        base_url=None,
        api_key=None,
        has_api_key=False,
        context_length=None,
        max_output_tokens=None,
        input_price=None,
        output_price=None,
        default_params=None,
        capabilities=None,
        config=None,
        is_enabled=True,
        is_default=False,
        sort_order=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    model_in = ModelCreate(
        name="Duplicate",
        provider=ModelProvider.OPENAI,
        model_id="duplicate-model",
        model_type=ModelType.CHAT,
    )

    with patch.object(models_endpoint.Model, "create", AsyncMock(return_value=created)):
        response = await models_endpoint.create_model(
            model_in=model_in, current_user=SimpleNamespace()
        )

    assert response["data"].id == created.id


@pytest.mark.parametrize(
    ("endpoint_name", "extra_args"),
    [
        ("get_model", ()),
        ("update_model", (ModelUpdate(name="Updated"),)),
        ("delete_model", ()),
        ("test_model_connection", ()),
        ("set_default_model", ()),
    ],
)
@pytest.mark.anyio
async def test_model_crud_endpoints_reject_missing_model(endpoint_name, extra_args):
    query = SimpleNamespace(first=AsyncMock(return_value=None))
    endpoint = getattr(models_endpoint, endpoint_name)

    with patch.object(models_endpoint.Model, "filter", return_value=query):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint(uuid4(), *extra_args, current_user=SimpleNamespace())

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == "model_not_found"
    assert exc_info.value.status_code == 404
