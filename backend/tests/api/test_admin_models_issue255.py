from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import models
from app.schemas.model import ModelCreate, ModelProvider, ModelType, ModelUpdate
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
async def test_create_model_rejects_duplicate(monkeypatch):
    monkeypatch.setattr(models.Model, "filter", MagicMock(return_value=Query(model())))

    with pytest.raises(BusinessError) as caught:
        await models.create_model(
            model_in=ModelCreate(
                name="GPT",
                provider=ModelProvider.OPENAI,
                model_id="gpt-4o",
                model_type=ModelType.CHAT,
            ),
            current_user=SimpleNamespace(),
        )

    assert caught.value.code == ResponseCode.ALREADY_EXISTS


@pytest.mark.anyio
async def test_create_default_model_clears_old_default_and_persists(monkeypatch):
    existing_query = Query(None)
    default_query = Query()
    created = model(is_default=True)
    filters = MagicMock(side_effect=[existing_query, default_query])
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
