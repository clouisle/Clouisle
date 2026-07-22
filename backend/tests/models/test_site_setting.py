import json
from unittest.mock import AsyncMock

import pytest

from app.models import site_setting
from app.models.site_setting import SiteSetting


class QueryDouble:
    def __init__(self, settings):
        self.settings = settings
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def __await__(self):
        async def result():
            return self.settings

        return result().__await__()


@pytest.mark.parametrize(
    ("value", "value_type", "expected"),
    [
        (None, "int", None),
        ("42", "int", 42),
        ("YES", "bool", True),
        ("no", "bool", False),
        ('{"enabled": true}', "json", {"enabled": True}),
        ("plain", "string", "plain"),
        ("plain", "unknown", "plain"),
    ],
)
def test_convert_value_handles_supported_types_and_defaults(
    value, value_type, expected
):
    assert SiteSetting._convert_value(value, value_type) == expected


@pytest.mark.parametrize(
    ("value", "value_type", "error"),
    [("not-an-int", "int", ValueError), ("not-json", "json", json.JSONDecodeError)],
)
def test_convert_value_propagates_invalid_stored_values(value, value_type, error):
    with pytest.raises(error):
        SiteSetting._convert_value(value, value_type)


@pytest.mark.asyncio
async def test_get_value_returns_default_or_converted_setting(monkeypatch):
    first = AsyncMock(
        side_effect=[
            None,
            type("Setting", (), {"value": "7", "value_type": "int"})(),
        ]
    )
    query = type("Query", (), {"first": first})()
    monkeypatch.setattr(SiteSetting, "filter", lambda **kwargs: query)

    assert await SiteSetting.get_value("missing", default="fallback") == "fallback"
    assert await SiteSetting.get_value("limit") == 7
    assert first.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "value_type", "stored"),
    [
        (True, "bool", "true"),
        (False, "bool", "false"),
        ({"a": 1}, "json", '{"a": 1}'),
        (None, "json", None),
        (12, "int", "12"),
        (None, "string", None),
    ],
)
async def test_set_value_creates_with_converted_value_and_defaults(
    monkeypatch, value, value_type, stored
):
    setting = object()
    get_or_create = AsyncMock(return_value=(setting, True))
    monkeypatch.setattr(SiteSetting, "get_or_create", get_or_create)

    assert await SiteSetting.set_value("key", value, value_type) is setting
    get_or_create.assert_awaited_once_with(
        key="key",
        defaults={
            "value": stored,
            "value_type": value_type,
            "category": "general",
            "description": None,
            "is_public": False,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("include_optional", [True, False])
async def test_set_value_updates_existing_setting(monkeypatch, include_optional):
    setting = type(
        "Setting",
        (),
        {
            "value": "old",
            "value_type": "string",
            "category": "existing-category",
            "description": "existing-description",
            "is_public": False,
            "save": AsyncMock(),
        },
    )()
    monkeypatch.setattr(
        SiteSetting, "get_or_create", AsyncMock(return_value=(setting, False))
    )
    category = "updated-category" if include_optional else None
    description = "updated-description" if include_optional else None

    result = await SiteSetting.set_value(
        "key", 3, "int", category, description, is_public=True
    )

    assert result is setting
    assert setting.value == "3"
    assert setting.value_type == "int"
    assert setting.category == (
        "updated-category" if include_optional else "existing-category"
    )
    assert setting.description == (
        "updated-description" if include_optional else "existing-description"
    )
    assert setting.is_public is True
    setting.save.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category", "public_only", "expected_filters"),
    [
        (None, False, []),
        ("auth", False, [{"category": "auth"}]),
        (None, True, [{"is_public": True}]),
        ("auth", True, [{"category": "auth"}, {"is_public": True}]),
    ],
)
async def test_get_all_by_category_filters_and_converts(
    monkeypatch, category, public_only, expected_filters
):
    settings = [
        type("Setting", (), {"key": "count", "value": "2", "value_type": "int"})(),
        type(
            "Setting",
            (),
            {"key": "enabled", "value": "yes", "value_type": "bool"},
        )(),
    ]
    query = QueryDouble(settings)
    monkeypatch.setattr(SiteSetting, "all", lambda: query)

    assert await SiteSetting.get_all_by_category(category, public_only) == {
        "count": 2,
        "enabled": True,
    }
    assert query.filters == expected_filters


@pytest.mark.asyncio
async def test_init_default_settings_creates_only_missing_settings(monkeypatch):
    defaults = {
        "existing": {
            "value": "old",
            "type": "string",
            "category": "general",
            "desc": "Existing",
            "public": False,
        },
        "missing": {
            "value": True,
            "type": "bool",
            "category": "auth",
            "desc": "Missing",
            "public": True,
        },
    }
    first = AsyncMock(side_effect=[object(), None])
    query = type("Query", (), {"first": first})()
    set_value = AsyncMock()
    monkeypatch.setattr(site_setting, "DEFAULT_SETTINGS", defaults)
    monkeypatch.setattr(SiteSetting, "filter", lambda **kwargs: query)
    monkeypatch.setattr(SiteSetting, "set_value", set_value)

    await site_setting.init_default_settings()

    set_value.assert_awaited_once_with(
        key="missing",
        value=True,
        value_type="bool",
        category="auth",
        description="Missing",
        is_public=True,
    )


def test_string_representation():
    setting = SiteSetting(key="theme", value="dark")
    assert str(setting) == "theme=dark"
