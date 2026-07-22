from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import models
from app.schemas.model import ModelProvider, ModelType, ModelUpdate
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def offset(self, value):
        self.calls.append(("offset", value))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def order_by(self, *values):
        self.calls.append(("order_by", values))
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def make_model(**overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "name": "Test model",
        "provider": ModelProvider.OPENAI.value,
        "model_id": "test-model",
        "model_type": ModelType.CHAT.value,
        "base_url": None,
        "api_key": "sk-test",
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
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_list_without_filters_and_update_with_nonempty_key():
    item = make_model()
    listing = Query([item], count=1)

    with patch.object(models.Model, "all", return_value=listing):
        response = await models.list_models(
            page=1,
            page_size=20,
            provider=None,
            model_type=None,
            is_enabled=None,
            search=None,
            current_user=SimpleNamespace(),
        )

    assert response["data"]["items"][0].id == item.id
    assert listing.calls == [
        ("offset", 0),
        ("limit", 20),
        ("order_by", ("sort_order", "-created_at")),
    ]

    refreshed = make_model(api_key="sk-replacement")
    with (
        patch.object(models.Model, "filter", return_value=Query(item)),
        patch.object(models.Model, "get", return_value=Query(refreshed)),
    ):
        response = await models.update_model(
            item.id,
            ModelUpdate(api_key="sk-replacement"),
            current_user=SimpleNamespace(),
        )

    item.update_from_dict.assert_awaited_once_with({"api_key": "sk-replacement"})
    assert response["data"].has_api_key is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model_type", "helper_name"),
    [
        (ModelType.EMBEDDING, "_test_embedding_model"),
        (ModelType.RERANK, "_test_rerank_model"),
        (ModelType.TEXT_TO_IMAGE, "_test_image_model"),
        (ModelType.TEXT_TO_VIDEO, "_test_video_model"),
    ],
)
async def test_saved_connection_dispatches_remaining_types(model_type, helper_name):
    item = make_model(model_type=model_type.value)
    with (
        patch.object(models.Model, "filter", return_value=Query(item)),
        patch.object(models, helper_name, new_callable=AsyncMock) as helper,
    ):
        response = await models.test_model_connection(
            item.id, current_user=SimpleNamespace()
        )

    helper.assert_awaited_once()
    assert response["data"].success is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected_key", "expected_success"),
    [
        ("404 unavailable", "model_test_model_not_accessible", False),
        ("model not found", "model_test_model_not_accessible", False),
        ("429 busy", "model_test_rate_limit_but_valid", True),
        ("request timeout", "model_test_connection_timeout", False),
        (
            "connection refused",
            "model_test_connection_failed_check_base_url",
            False,
        ),
        ("provider exploded", "model_test_unexpected_error", False),
    ],
)
async def test_saved_connection_maps_remaining_provider_errors(
    message, expected_key, expected_success
):
    item = make_model()
    with (
        patch.object(models.Model, "filter", return_value=Query(item)),
        patch.object(
            models, "_test_chat_model", AsyncMock(side_effect=RuntimeError(message))
        ),
        patch.object(models, "t", side_effect=lambda key, **_: key),
    ):
        response = await models.test_model_connection(
            item.id, current_user=SimpleNamespace()
        )

    assert response["data"].success is expected_success
    assert response["data"].message == expected_key


@pytest.mark.anyio
async def test_saved_connection_rejects_unhandled_enum_member(monkeypatch):
    item = make_model(model_type="future")

    class ExtendedModelType:
        CHAT = ModelType.CHAT
        EMBEDDING = ModelType.EMBEDDING
        RERANK = ModelType.RERANK
        TEXT_TO_IMAGE = ModelType.TEXT_TO_IMAGE
        TEXT_TO_VIDEO = ModelType.TEXT_TO_VIDEO
        TTS = ModelType.TTS
        AUDIO_GENERATION = ModelType.AUDIO_GENERATION
        STT = ModelType.STT

        def __new__(cls, value):
            return object.__new__(cls)

    monkeypatch.setattr(models, "ModelType", ExtendedModelType)
    monkeypatch.setattr(models.Model, "filter", MagicMock(return_value=Query(item)))

    with pytest.raises(BusinessError) as exc_info:
        await models.test_model_connection(item.id, current_user=SimpleNamespace())

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    assert exc_info.value.msg_key == "model_type_not_supported"


@pytest.mark.anyio
async def test_embedding_and_rerank_helpers_accept_nonempty_results():
    embedding = SimpleNamespace(aembed_query=AsyncMock(return_value=[0.1]))
    reranker = SimpleNamespace(
        rerank=AsyncMock(return_value=SimpleNamespace(results=[SimpleNamespace()]))
    )

    with patch(
        "app.llm.adapters.embedding.factory.create_embedding_model",
        return_value=embedding,
    ):
        await models._test_embedding_model(
            ModelProvider.OPENAI, "embed", "sk-test", None, {}
        )

    with patch("app.llm.adapters.rerank.create_rerank_adapter", return_value=reranker):
        await models._test_rerank_model(
            ModelProvider.OPENAI, "rerank", "sk-test", None, {}
        )

    embedding.aembed_query.assert_awaited_once_with("test")
    reranker.rerank.assert_awaited_once()
