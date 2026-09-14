from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import models
from app.models.model import ModelProvider


class Query:
    def __init__(self, items=()):
        self.items = list(items)
        self.filters = []
        self.ordering = None

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def order_by(self, *fields):
        self.ordering = fields
        return self

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@pytest.mark.anyio
async def test_get_providers_handles_configured_and_missing_defaults(monkeypatch):
    configured = await models.get_providers()
    openai = next(item for item in configured["data"] if item["code"] == "openai")
    assert openai["name"] == "OpenAI"
    assert openai["base_url"] == "https://api.openai.com/v1"

    monkeypatch.setattr(models, "PROVIDER_DEFAULTS", {})
    fallback = await models.get_providers()
    custom = next(
        item for item in fallback["data"] if item["code"] == ModelProvider.CUSTOM.value
    )
    assert custom == {
        "code": ModelProvider.CUSTOM.value,
        "name": ModelProvider.CUSTOM.value,
        "base_url": None,
        "icon": ModelProvider.CUSTOM.value,
    }


@pytest.mark.anyio
async def test_get_available_models_filters_only_when_type_is_requested(monkeypatch):
    current_user = SimpleNamespace(id="user")
    unfiltered = Query([SimpleNamespace(name="chat")])
    monkeypatch.setattr(models.Model, "filter", lambda **_kwargs: unfiltered)

    result = await models.get_available_models(
        model_type=None, current_user=current_user
    )

    assert result["data"] == unfiltered.items
    assert unfiltered.filters == []
    assert unfiltered.ordering == ("sort_order", "name")

    filtered = Query([SimpleNamespace(name="embedding")])
    monkeypatch.setattr(models.Model, "filter", lambda **_kwargs: filtered)

    result = await models.get_available_models(
        model_type="embedding", current_user=current_user
    )

    assert result["data"] == filtered.items
    assert filtered.filters == [{"model_type": "embedding"}]
    assert filtered.ordering == ("sort_order", "name")
