import pytest

from app.api.v1.admin.endpoints.site_settings import _validate_setting_value
from app.api.v1.endpoints.site_settings import _normalize_enum, _normalize_hex_color
from app.schemas.response import BusinessError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dark", "dark"),
        ("light", "light"),
        ("bad", "system"),
        (None, "system"),
    ],
)
def test_normalize_enum_falls_back_for_invalid_values(value, expected):
    assert _normalize_enum(value, {"system", "light", "dark"}, "system") == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#abc", "#abc"),
        ("#abcd", "#abcd"),
        ("#A1B2C3", "#A1B2C3"),
        ("#A1B2C3CC", "#A1B2C3CC"),
        ("blue", ""),
        (None, ""),
    ],
)
def test_normalize_hex_color_falls_back_for_invalid_values(value, expected):
    assert _normalize_hex_color(value) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["system", "light", "dark"])
async def test_validate_theme_mode_accepts_known_values(value):
    await _validate_setting_value("theme_mode", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["auto", "", True])
async def test_validate_theme_mode_rejects_invalid_values(value):
    with pytest.raises(BusinessError):
        await _validate_setting_value("theme_mode", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["full", "name_only", "icon_only", "hidden"])
async def test_validate_branding_display_accepts_known_values(value):
    await _validate_setting_value("theme_branding_display", value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "theme_primary_color",
        "theme_card_color",
        "theme_sidebar_accent_foreground_color",
        "theme_navbar_hover_color",
        "theme_chart_5_color",
    ],
)
@pytest.mark.parametrize("value", ["#abc", "#abcd", "#123ABC", "#123ABC80", ""])
async def test_validate_theme_color_accepts_hex_or_empty(key, value):
    await _validate_setting_value(key, value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", ["blue", "#12", "#12345", "#1234567", " #123ABC80 ", 123]
)
async def test_validate_theme_color_rejects_invalid_values(value):
    with pytest.raises(BusinessError):
        await _validate_setting_value("theme_sidebar_color", value)
