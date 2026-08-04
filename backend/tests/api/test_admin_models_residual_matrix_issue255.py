from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import models
from app.schemas.model import (
    ModelCreate,
    ModelProvider,
    ModelTestRequest,
    ModelType,
    ModelUpdate,
)
from app.schemas.response import BusinessError


class Query:
    def __init__(self, result=None, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def distinct(self):
        self.calls.append(("distinct", (), {}))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.result

    async def update(self, **kwargs):
        self.calls.append(("update", (), kwargs))
        return 1

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def make_model(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "name": "GPT",
        "provider": "openai",
        "model_id": "gpt-4o",
        "model_type": "chat",
        "base_url": None,
        "api_key": "sk-secret",
        "has_api_key": True,
        "context_length": None,
        "max_output_tokens": None,
        "input_price": None,
        "output_price": None,
        "default_params": None,
        "capabilities": None,
        "config": None,
        "is_enabled": True,
        "is_default": False,
        "sort_order": 0,
        "created_at": now,
        "updated_at": now,
        "update_from_dict": AsyncMock(),
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_crud_and_listing_residual_branches():
    item = make_model()
    listing = Query([item], count=1)
    default_query = Query()
    created = make_model(is_default=True)
    create_input = ModelCreate(
        name="New",
        provider=ModelProvider.OPENAI,
        model_id="gpt-new",
        model_type=ModelType.CHAT,
        api_key="sk-new",
        is_default=True,
    )

    with patch.object(models.Model, "all", return_value=listing):
        response = await models.list_models(
            page=2,
            page_size=5,
            provider=["openai"],
            model_type=["chat"],
            is_enabled=False,
            search="gpt",
            current_user=SimpleNamespace(),
        )
    assert response["data"]["total"] == 1
    assert ("offset", (5,), {}) in listing.calls
    assert sum(call[0] == "distinct" for call in listing.calls) == 2

    with (
        patch.object(models.Model, "filter", side_effect=[default_query]),
        patch.object(models.Model, "create", AsyncMock(return_value=created)) as create,
    ):
        response = await models.create_model(
            model_in=create_input, current_user=SimpleNamespace()
        )
    assert response["data"].is_default is True
    assert create.await_args.kwargs["provider"] == "openai"
    assert ("update", (), {"is_default": False}) in default_query.calls

    with patch.object(models.Model, "filter", return_value=Query(item)):
        assert (await models.get_model(item.id, current_user=SimpleNamespace()))[
            "data"
        ].id == item.id
        deleted = await models.delete_model(item.id, current_user=SimpleNamespace())
    assert deleted["data"].id == item.id
    item.delete.assert_awaited_once()


@pytest.mark.anyio
async def test_crud_rejections_and_update_variants():
    item = make_model()

    for endpoint, args in [
        (models.get_model, (uuid4(),)),
        (models.update_model, (uuid4(), ModelUpdate(name="x"))),
        (models.delete_model, (uuid4(),)),
        (models.test_model_connection, (uuid4(),)),
        (models.set_default_model, (uuid4(),)),
    ]:
        with (
            patch.object(models.Model, "filter", return_value=Query(None)),
            pytest.raises(BusinessError),
        ):
            await endpoint(*args, current_user=SimpleNamespace())

    refreshed = make_model(api_key=None, is_default=True)
    unset_defaults = Query()
    with (
        patch.object(models.Model, "filter", side_effect=[Query(item), unset_defaults]),
        patch.object(models.Model, "get", AsyncMock(return_value=refreshed)),
    ):
        await models.update_model(
            item.id,
            ModelUpdate(api_key="", is_default=True),
            current_user=SimpleNamespace(),
        )
    item.update_from_dict.assert_awaited_once_with(
        {"api_key": None, "is_default": True}
    )
    assert ("exclude", (), {"id": item.id}) in unset_defaults.calls

    with patch.object(
        models.Model, "filter", side_effect=[Query(item), unset_defaults]
    ):
        response = await models.set_default_model(
            item.id, current_user=SimpleNamespace()
        )
    assert response["data"].is_default is True
    item.save.assert_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model_type", "helper"),
    [
        (ModelType.CHAT, "_test_chat_model"),
        (ModelType.EMBEDDING, "_test_embedding_model"),
        (ModelType.RERANK, "_test_rerank_model"),
        (ModelType.TEXT_TO_IMAGE, "_test_image_model"),
        (ModelType.TEXT_TO_VIDEO, "_test_video_model"),
        (ModelType.TTS, "_test_tts_model"),
        (ModelType.AUDIO_GENERATION, "_test_audio_generation_model"),
    ],
)
async def test_config_dispatch_matrix(model_type, helper):
    request = ModelTestRequest(
        provider=ModelProvider.OPENAI,
        model_id="model",
        model_type=model_type,
        api_key="sk-key",
        default_params={"temperature": 0},
        config={"timeout": 1},
    )
    with patch.object(models, helper, new_callable=AsyncMock) as mocked:
        response = await models.test_model_config(
            request, current_user=SimpleNamespace()
        )
    mocked.assert_awaited_once()
    assert response["data"].success is True


@pytest.mark.anyio
async def test_saved_connection_validation_dispatch_and_errors():
    missing_key = make_model(api_key=None)
    with (
        patch.object(models.Model, "filter", return_value=Query(missing_key)),
        pytest.raises(BusinessError),
    ):
        await models.test_model_connection(
            missing_key.id, current_user=SimpleNamespace()
        )

    invalid_type = make_model(model_type="future")
    with (
        patch.object(models.Model, "filter", return_value=Query(invalid_type)),
        pytest.raises(BusinessError),
    ):
        await models.test_model_connection(
            invalid_type.id, current_user=SimpleNamespace()
        )

    stt = make_model(model_type=ModelType.STT.value)
    with (
        patch.object(models.Model, "filter", return_value=Query(stt)),
        patch.object(models, "_validate_api_key") as validate,
    ):
        response = await models.test_model_connection(
            stt.id, current_user=SimpleNamespace()
        )
    validate.assert_called_once()
    assert response["data"].success is True

    chat = make_model()
    with (
        patch.object(models.Model, "filter", return_value=Query(chat)),
        patch.object(
            models,
            "_test_chat_model",
            AsyncMock(side_effect=BusinessError(msg_key="bad")),
        ),
        pytest.raises(BusinessError),
    ):
        await models.test_model_connection(chat.id, current_user=SimpleNamespace())


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected", "success_value"),
    [
        ("401 denied", "invalid", False),
        ("404 missing", "accessible", False),
        ("429 rate limit", "rate", True),
        ("request timeout", "timeout", False),
        ("connection refused", "connection", False),
        ("strange failure", "unexpected", False),
    ],
)
async def test_config_exception_mapping(message, expected, success_value):
    request = ModelTestRequest(
        provider=ModelProvider.OPENAI,
        model_id="model",
        model_type=ModelType.CHAT,
        api_key="sk-key",
    )
    with (
        patch.object(
            models, "_test_chat_model", AsyncMock(side_effect=RuntimeError(message))
        ),
        patch.object(models, "t", side_effect=lambda key, **kwargs: key),
    ):
        response = await models.test_model_config(
            request, current_user=SimpleNamespace()
        )
    assert response["data"].success is success_value
    assert expected in response["data"].message


@pytest.mark.anyio
async def test_config_stt_unsupported_and_business_error():
    stt = SimpleNamespace(
        provider=ModelProvider.OLLAMA,
        model_id="stt",
        model_type=ModelType.STT,
        api_key=None,
        base_url=None,
        default_params=None,
        config=None,
    )
    with patch.object(models, "_validate_api_key") as validate:
        assert (await models.test_model_config(stt, current_user=SimpleNamespace()))[
            "data"
        ].success
    validate.assert_called_once()

    unsupported = SimpleNamespace(**{**stt.__dict__, "model_type": "future"})
    with pytest.raises(BusinessError):
        await models.test_model_config(unsupported, current_user=SimpleNamespace())


@pytest.mark.parametrize(
    ("provider", "key", "raises"),
    [
        (ModelProvider.OLLAMA, None, False),
        (ModelProvider.OPENAI, "bad", True),
        (ModelProvider.OPENAI, "sk-ok", False),
        (ModelProvider.ANTHROPIC, "bad", True),
        (ModelProvider.ANTHROPIC, "sk-ant-ok", False),
    ],
)
def test_api_key_validation(provider, key, raises):
    if raises:
        with pytest.raises(BusinessError):
            models._validate_api_key(provider, key)
    else:
        models._validate_api_key(provider, key)


@pytest.mark.anyio
async def test_embedding_rerank_and_audio_empty_results():
    embedding = SimpleNamespace(aembed_query=AsyncMock(return_value=[]))
    with (
        patch(
            "app.llm.adapters.embedding.factory.create_embedding_model",
            return_value=embedding,
        ),
        pytest.raises(BusinessError),
    ):
        await models._test_embedding_model(
            ModelProvider.OPENAI, "embed", "sk-key", None, {}
        )

    incompatible = SimpleNamespace(
        aembed_query=AsyncMock(
            side_effect=AttributeError("'str' object has no attribute 'data'")
        )
    )
    with (
        patch(
            "app.llm.adapters.embedding.factory.create_embedding_model",
            return_value=incompatible,
        ),
        pytest.raises(BusinessError),
    ):
        await models._test_embedding_model(
            ModelProvider.OPENAI, "embed", "sk-key", None, {}
        )

    other_error = AttributeError("other")
    embedding.aembed_query.side_effect = other_error
    with (
        patch(
            "app.llm.adapters.embedding.factory.create_embedding_model",
            return_value=embedding,
        ),
        pytest.raises(AttributeError) as exc,
    ):
        await models._test_embedding_model(
            ModelProvider.OPENAI, "embed", "sk-key", None, {}
        )
    assert exc.value is other_error

    reranker = SimpleNamespace(
        rerank=AsyncMock(return_value=SimpleNamespace(results=[]))
    )
    with (
        patch("app.llm.adapters.rerank.create_rerank_adapter", return_value=reranker),
        pytest.raises(BusinessError),
    ):
        await models._test_rerank_model(
            ModelProvider.OPENAI, "rerank", "sk-key", None, {}
        )

    empty_audio = SimpleNamespace(has_content=lambda: False)
    with (
        patch(
            "app.llm.adapters.audio.create_tts_adapter",
            return_value=SimpleNamespace(
                synthesize=AsyncMock(return_value=SimpleNamespace(audio=empty_audio))
            ),
        ),
        pytest.raises(BusinessError),
    ):
        await models._test_tts_model(
            ModelProvider.OPENAI, "tts", "sk-key", None, {}, {}
        )
    with (
        patch(
            "app.llm.adapters.audio.create_audio_generation_adapter",
            return_value=SimpleNamespace(
                generate=AsyncMock(return_value=SimpleNamespace(audio=empty_audio))
            ),
        ),
        pytest.raises(BusinessError),
    ):
        await models._test_audio_generation_model(
            ModelProvider.OPENAI, "audio", "sk-key", None, {}, {}
        )


@pytest.mark.anyio
async def test_chat_empty_response_uses_mocked_adapter_boundary():
    adapter = MagicMock()
    adapter.chat = AsyncMock(return_value=SimpleNamespace(content=""))
    with (
        patch("app.llm.adapters.chat.OpenAIAdapter", return_value=adapter),
        pytest.raises(BusinessError),
    ):
        await models._test_chat_model(
            ModelProvider.OPENAI, "chat", "sk-key", None, {}, {}
        )
