import asyncio

import pytest

from app.api.v1.admin.endpoints.site_settings import _validate_setting_value
from app.api.v1.endpoints.site_settings import (
    _normalize_watermark_content,
    get_public_settings,
)
from app.models import SiteSetting
from app.models.site_setting import WATERMARK_SETTING_DEFAULTS
from app.schemas.response import BusinessError, ResponseCode


@pytest.fixture(autouse=True)
def _public_settings(monkeypatch):
    settings: dict[str, object] = {}

    monkeypatch.setattr(
        SiteSetting,
        "get_all_by_category",
        lambda public_only=True: asyncio.sleep(0, result=settings),
    )
    return settings


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [True, False])
async def test_validate_watermark_enabled_accepts_bools(value):
    await _validate_setting_value("watermark_enabled", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["true", 1, 0, None, []])
async def test_validate_watermark_enabled_rejects_non_bools(value):
    with pytest.raises(BusinessError) as error:
        await _validate_setting_value("watermark_enabled", value)
    assert error.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["x", "{username}", "{username} {date} {time}"])
async def test_validate_watermark_content_accepts_non_empty_strings(value):
    await _validate_setting_value("watermark_content", value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", ["", "   ", " {username}", "{username} ", "x" * 201, None, 12]
)
async def test_validate_watermark_content_rejects_invalid_values(value):
    with pytest.raises(BusinessError) as error:
        await _validate_setting_value("watermark_content", value)
    assert error.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_validate_watermark_content_accepts_max_length():
    await _validate_setting_value("watermark_content", "x" * 200)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("watermark_opacity", 1),
        ("watermark_opacity", 50),
        ("watermark_font_size", 10),
        ("watermark_font_size", 48),
        ("watermark_rotation", -90),
        ("watermark_rotation", 90),
        ("watermark_gap", 60),
        ("watermark_gap", 600),
    ],
)
async def test_validate_watermark_integers_accept_bounds(key, value):
    await _validate_setting_value(key, value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("watermark_opacity", 0),
        ("watermark_opacity", 51),
        ("watermark_font_size", 9),
        ("watermark_font_size", 49),
        ("watermark_rotation", -91),
        ("watermark_rotation", 91),
        ("watermark_gap", 59),
        ("watermark_gap", 601),
        ("watermark_gap", True),
        ("watermark_gap", "180"),
        ("watermark_gap", 180.0),
        ("watermark_gap", None),
    ],
)
async def test_validate_watermark_integers_reject_out_of_range_or_wrong_type(
    key, value
):
    with pytest.raises(BusinessError) as error:
        await _validate_setting_value(key, value)
    assert error.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", "#abc", "#abcd", "#A1B2C3", "#A1B2C3CC"])
async def test_validate_watermark_color_accepts_empty_or_hex(value):
    await _validate_setting_value("watermark_color", value)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["blue", " #fff", "#ff", 1, None])
async def test_validate_watermark_color_rejects_invalid_values(value):
    with pytest.raises(BusinessError) as error:
        await _validate_setting_value("watermark_color", value)
    assert error.value.code == ResponseCode.VALIDATION_ERROR


def test_normalize_watermark_content_rejects_blank_and_oversized():
    default = WATERMARK_SETTING_DEFAULTS["watermark_content"]
    assert _normalize_watermark_content("  ") == default
    assert _normalize_watermark_content("x" * 201) == default
    assert _normalize_watermark_content(None) == default
    assert _normalize_watermark_content("  {email} ") == "{email}"


@pytest.mark.asyncio
async def test_get_public_settings_returns_watermark_defaults(_public_settings):
    response = await get_public_settings()
    data = response["data"]
    assert data.watermark_enabled is False
    assert data.watermark_content == "{username} {date} {time}"
    assert data.watermark_opacity == 10
    assert data.watermark_font_size == 16
    assert data.watermark_rotation == -22
    assert data.watermark_gap == 120
    assert data.watermark_color == ""


@pytest.mark.asyncio
async def test_get_public_settings_clamps_watermark_integers(_public_settings):
    _public_settings.update(
        {
            "watermark_opacity": 999,
            "watermark_rotation": -120,
            "watermark_gap": 12,
            "watermark_font_size": "big",
        }
    )
    data = (await get_public_settings())["data"]
    assert data.watermark_opacity == 50
    assert data.watermark_rotation == -90
    assert data.watermark_gap == 60
    assert data.watermark_font_size == 16


@pytest.mark.asyncio
async def test_get_public_settings_normalizes_watermark_content_and_color(
    _public_settings,
):
    _public_settings.update(
        {
            "watermark_enabled": True,
            "watermark_content": "   ",
            "watermark_color": "blue",
        }
    )
    data = (await get_public_settings())["data"]
    assert data.watermark_enabled is True
    assert data.watermark_content == "{username} {date} {time}"
    assert data.watermark_color == ""

    _public_settings.update(
        {"watermark_content": " {username} ", "watermark_color": "#A1B2C3"}
    )
    data = (await get_public_settings())["data"]
    assert data.watermark_content == "{username}"
    assert data.watermark_color == "#A1B2C3"
