from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
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
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.count_result = count
        self.calls = []

    def _chain(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return self

    def filter(self, *args, **kwargs):
        return self._chain("filter", *args, **kwargs)

    def distinct(self):
        return self._chain("distinct")

    def exclude(self, *args, **kwargs):
        return self._chain("exclude", *args, **kwargs)

    def offset(self, value):
        return self._chain("offset", value)

    def limit(self, value):
        return self._chain("limit", value)

    def order_by(self, *values):
        return self._chain("order_by", *values)

    async def first(self):
        return self.result

    async def count(self):
        return self.count_result

    async def update(self, **values):
        self.calls.append(("update", (), values))
        return 1

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def model(**overrides):
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


def translate_model_test_message(key, **kwargs):
    if key == "model_test_failed":
        return (
            f"{key}:{kwargs['provider']}:{kwargs['model']}:"
            f"{kwargs['model_type']}:{kwargs['error']}"
        )
    if key == "model_test_provider_error_details":
        return f"{key}:{kwargs['error']}"
    return key


def test_routes_require_model_specific_permissions():
    expected = {
        ("GET", ""): "admin:model:read",
        ("POST", ""): "admin:model:create",
        ("GET", "/{model_id}"): "admin:model:read",
        ("PUT", "/{model_id}"): "admin:model:update",
        ("DELETE", "/{model_id}"): "admin:model:delete",
        ("POST", "/{model_id}/test"): "admin:model:update",
        ("POST", "/{model_id}/set-default"): "admin:model:update",
        ("POST", "/test"): "admin:model:create",
    }

    actual = {}
    for route in models.router.routes:
        permission = route.dependant.dependencies[0].call.required_permission
        for method in route.methods:
            actual[(method, route.path)] = permission

    assert actual == expected


@pytest.mark.anyio
async def test_list_models_applies_filters_and_pagination(monkeypatch):
    item = model()
    query = Query([item], count=1)
    monkeypatch.setattr(models.Model, "all", MagicMock(return_value=query))

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
    assert response["data"]["page"] == 2
    assert response["data"]["items"][0].id == item.id
    assert [(name, kwargs) for name, _, kwargs in query.calls] == [
        ("filter", {"provider__in": ["openai"]}),
        ("distinct", {}),
        ("filter", {"model_type__in": ["chat"]}),
        ("distinct", {}),
        ("filter", {"is_enabled": False}),
        ("filter", {}),
        ("offset", {}),
        ("limit", {}),
        ("order_by", {}),
    ]
    assert query.calls[-3][1] == (5,)
    assert query.calls[-2][1] == (5,)


@pytest.mark.anyio
async def test_create_model_allows_duplicate_provider_model_id(monkeypatch):
    """Same provider/model_id may be configured multiple times."""
    created = model()
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(models.Model, "create", create)

    response = await models.create_model(
        model_in=ModelCreate(
            name="GPT",
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o",
            model_type=ModelType.CHAT,
        ),
        current_user=SimpleNamespace(),
    )

    assert response["data"].id == created.id


@pytest.mark.anyio
async def test_create_default_model_clears_old_default_and_persists(monkeypatch):
    default_query = Query()
    created = model(is_default=True)
    filters = MagicMock(side_effect=[default_query])
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(models.Model, "filter", filters)
    monkeypatch.setattr(models.Model, "create", create)

    response = await models.create_model(
        model_in=ModelCreate(
            name="GPT",
            provider=ModelProvider.OPENAI,
            model_id="gpt-4o",
            model_type=ModelType.CHAT,
            is_default=True,
        ),
        current_user=SimpleNamespace(),
    )

    assert response["data"].id == created.id
    assert default_query.calls == [("update", (), {"is_default": False})]
    assert create.await_args.kwargs["provider"] == "openai"
    assert create.await_args.kwargs["model_type"] == "chat"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "function,kwargs",
    [
        (models.get_model, {}),
        (models.update_model, {"model_in": ModelUpdate(name="New")}),
        (models.delete_model, {}),
        (models.set_default_model, {}),
    ],
)
async def test_model_mutations_report_missing_model(monkeypatch, function, kwargs):
    monkeypatch.setattr(models.Model, "filter", MagicMock(return_value=Query(None)))

    with pytest.raises(BusinessError) as caught:
        await function(uuid4(), current_user=SimpleNamespace(), **kwargs)

    assert caught.value.status_code == 404
    assert caught.value.code == ResponseCode.NOT_FOUND


@pytest.mark.anyio
async def test_update_model_clears_key_sets_default_and_saves(monkeypatch):
    item = model()
    default_query = Query()
    monkeypatch.setattr(
        models.Model, "filter", MagicMock(side_effect=[Query(item), default_query])
    )
    monkeypatch.setattr(models.Model, "get", MagicMock(return_value=Query(item)))

    response = await models.update_model(
        item.id,
        ModelUpdate(name="Updated", api_key="", is_default=True),
        current_user=SimpleNamespace(),
    )

    item.update_from_dict.assert_awaited_once_with(
        {"name": "Updated", "api_key": None, "is_default": True}
    )
    item.save.assert_awaited_once()
    assert default_query.calls == [
        ("exclude", (), {"id": item.id}),
        ("update", (), {"is_default": False}),
    ]
    assert response["data"].id == item.id


@pytest.mark.anyio
async def test_delete_and_set_default_persist(monkeypatch):
    deleted = model()
    defaulted = model()
    old_defaults = Query()
    monkeypatch.setattr(
        models.Model,
        "filter",
        MagicMock(side_effect=[Query(deleted), Query(defaulted), old_defaults]),
    )

    delete_response = await models.delete_model(
        deleted.id, current_user=SimpleNamespace()
    )
    default_response = await models.set_default_model(
        defaulted.id, current_user=SimpleNamespace()
    )

    deleted.delete.assert_awaited_once()
    assert delete_response["data"].id == deleted.id
    assert defaulted.is_default is True
    defaulted.save.assert_awaited_once()
    assert old_defaults.calls[-1] == ("update", (), {"is_default": False})
    assert default_response["data"].id == defaulted.id


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("model_type", "helper_name"),
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
async def test_config_connection_dispatches_supported_types(
    monkeypatch, model_type, helper_name
):
    helper = AsyncMock()
    monkeypatch.setattr(models, helper_name, helper)

    response = await models.test_model_config(
        ModelTestRequest(
            provider=ModelProvider.OPENAI,
            model_id="test-model",
            model_type=model_type,
            api_key="sk-test",
            default_params={"temperature": 0},
            config={"region": "test"},
        ),
        current_user=SimpleNamespace(),
    )

    helper.assert_awaited_once()
    assert response["data"].success is True
    assert response["data"].latency_ms >= 0


@pytest.mark.anyio
async def test_config_connection_stt_validates_key_without_provider(monkeypatch):
    validate = MagicMock()
    monkeypatch.setattr(models, "_validate_api_key", validate)

    response = await models.test_model_config(
        ModelTestRequest(
            provider=ModelProvider.OPENAI,
            model_id="whisper-test",
            model_type=ModelType.STT,
            api_key="sk-test",
        ),
        current_user=SimpleNamespace(),
    )

    validate.assert_called_once_with(ModelProvider.OPENAI, "sk-test")
    assert response["data"].success is True


@pytest.mark.anyio
async def test_stored_connection_rejects_missing_model_key_and_invalid_type(
    monkeypatch,
):
    missing_id = uuid4()
    no_key = model(api_key=None)
    bad_type = model(model_type="unsupported")
    monkeypatch.setattr(
        models.Model,
        "filter",
        MagicMock(side_effect=[Query(None), Query(no_key), Query(bad_type)]),
    )

    for model_id, code in [
        (missing_id, ResponseCode.NOT_FOUND),
        (no_key.id, ResponseCode.VALIDATION_ERROR),
        (bad_type.id, ResponseCode.VALIDATION_ERROR),
    ]:
        with pytest.raises(BusinessError) as caught:
            await models.test_model_connection(model_id, current_user=SimpleNamespace())
        assert caught.value.code == code


@pytest.mark.anyio
async def test_stored_connection_uses_persisted_config_and_translates_failure(
    monkeypatch,
):
    item = model(
        default_params={"temperature": 0},
        config={"region": "test"},
    )
    monkeypatch.setattr(models.Model, "filter", MagicMock(return_value=Query(item)))
    chat = AsyncMock()
    monkeypatch.setattr(models, "_test_chat_model", chat)
    monkeypatch.setattr(
        models, "t", MagicMock(side_effect=translate_model_test_message)
    )

    response = await models.test_model_connection(
        item.id, current_user=SimpleNamespace()
    )

    chat.assert_awaited_once_with(
        ModelProvider.OPENAI,
        item.model_id,
        item.api_key,
        item.base_url,
        item.default_params,
        item.config,
    )
    assert response["data"].success is True

    chat.side_effect = RuntimeError("401 Unauthorized")
    response = await models.test_model_connection(
        item.id, current_user=SimpleNamespace()
    )
    assert response["data"].success is False
    assert (
        response["data"].message
        == "model_test_failed:openai:gpt-4o:chat:model_test_invalid_api_key"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "expected_key", "expected_success"),
    [
        (RuntimeError("401 Unauthorized"), "model_test_invalid_api_key", False),
        (RuntimeError("404 not found"), "model_test_model_not_accessible", False),
        (RuntimeError("429 rate limit"), "model_test_rate_limit_but_valid", True),
        (RuntimeError("request timeout"), "model_test_connection_timeout", False),
        (
            RuntimeError("connection refused"),
            "model_test_connection_failed_check_base_url",
            False,
        ),
        (
            RuntimeError("provider exploded"),
            "model_test_provider_error_details:provider exploded",
            False,
        ),
    ],
)
async def test_config_connection_translates_provider_errors(
    monkeypatch, error, expected_key, expected_success
):
    monkeypatch.setattr(models, "_test_chat_model", AsyncMock(side_effect=error))
    translate = MagicMock(side_effect=translate_model_test_message)
    monkeypatch.setattr(models, "t", translate)

    response = await models.test_model_config(
        ModelTestRequest(
            provider=ModelProvider.OPENAI,
            model_id="test-model",
            model_type=ModelType.CHAT,
            api_key="sk-test",
        ),
        current_user=SimpleNamespace(),
    )

    assert response["data"].success is expected_success
    if expected_success:
        assert response["data"].message == expected_key
    else:
        assert response["data"].message == (
            f"model_test_failed:openai:test-model:chat:{expected_key}"
        )


@pytest.mark.anyio
async def test_config_connection_reports_incompatible_responses_without_credentials(
    monkeypatch,
):
    request = ModelTestRequest(
        provider=ModelProvider.DEEPSEEK,
        model_id="deepseek-chat",
        model_type=ModelType.CHAT,
        api_key="sk-live-secret",
    )
    chat = AsyncMock(
        side_effect=AttributeError("'str' object has no attribute 'choices'")
    )
    monkeypatch.setattr(models, "_test_chat_model", chat)
    monkeypatch.setattr(models, "t", translate_model_test_message)

    response = await models.test_model_config(request, current_user=SimpleNamespace())

    expected = (
        "model_test_failed:deepseek:deepseek-chat:chat:"
        "model_test_chat_response_incompatible"
    )
    assert response["data"].message == expected
    assert response["msg"] == expected

    chat.side_effect = RuntimeError("Provider rejected api_key=sk-live-secret")
    response = await models.test_model_config(request, current_user=SimpleNamespace())

    assert "sk-live-secret" not in response["data"].message
    assert "api_key=***" in response["data"].message


@pytest.mark.anyio
async def test_video_rate_limit_is_failure_and_business_error_propagates(monkeypatch):
    video = AsyncMock(side_effect=RuntimeError("429 rate limit"))
    monkeypatch.setattr(models, "_test_video_model", video)
    monkeypatch.setattr(
        models, "t", MagicMock(side_effect=translate_model_test_message)
    )
    request = ModelTestRequest(
        provider=ModelProvider.OPENAI,
        model_id="video-test",
        model_type=ModelType.TEXT_TO_VIDEO,
        api_key="sk-test",
    )

    response = await models.test_model_config(request, current_user=SimpleNamespace())
    assert response["data"].success is False
    assert response["data"].message == (
        "model_test_failed:openai:video-test:text_to_video:model_test_rate_limited"
    )

    error = BusinessError(
        code=ResponseCode.VALIDATION_ERROR, msg_key="model_test_empty_response"
    )
    video.side_effect = error
    with pytest.raises(BusinessError) as caught:
        await models.test_model_config(request, current_user=SimpleNamespace())
    assert caught.value is error


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["create", "update", "delete", "set_default"])
async def test_model_persistence_errors_propagate(monkeypatch, operation):
    error = RuntimeError("database unavailable")
    item = model()

    if operation == "create":
        monkeypatch.setattr(models.Model, "filter", MagicMock(return_value=Query(None)))
        monkeypatch.setattr(models.Model, "create", AsyncMock(side_effect=error))
        call = models.create_model(
            model_in=ModelCreate(
                name="Test",
                provider=ModelProvider.OPENAI,
                model_id="test-model",
                model_type=ModelType.CHAT,
            ),
            current_user=SimpleNamespace(),
        )
    else:
        monkeypatch.setattr(models.Model, "filter", MagicMock(return_value=Query(item)))
        if operation == "update":
            item.save.side_effect = error
            call = models.update_model(
                item.id,
                ModelUpdate(name="Updated"),
                current_user=SimpleNamespace(),
            )
        elif operation == "delete":
            item.delete.side_effect = error
            call = models.delete_model(item.id, current_user=SimpleNamespace())
        else:
            item.save.side_effect = error
            call = models.set_default_model(item.id, current_user=SimpleNamespace())

    with pytest.raises(RuntimeError, match="database unavailable"):
        await call
