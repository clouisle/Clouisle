from unittest.mock import MagicMock

import pytest

from app.core import i18n
from app.schemas.response import BusinessError, ResponseCode, error, success


def test_success_prefers_explicit_message_over_translation(monkeypatch):
    translate = MagicMock(return_value="translated")
    monkeypatch.setattr(i18n, "t", translate)

    assert success(data={"id": 1}, msg="created", msg_key="ignored") == {
        "code": ResponseCode.SUCCESS,
        "data": {"id": 1},
        "msg": "created",
    }
    translate.assert_not_called()


def test_success_translates_message_key_with_format_arguments(monkeypatch):
    translate = MagicMock(return_value="Hello Ada")
    monkeypatch.setattr(i18n, "t", translate)

    assert success(msg_key="greeting", name="Ada")["msg"] == "Hello Ada"
    translate.assert_called_once_with("greeting", name="Ada")


@pytest.mark.parametrize(
    ("code", "msg", "msg_key", "expected", "translated_key", "uses_code_message"),
    [
        (ResponseCode.BAD_REQUEST, "direct", "ignored", "direct", None, False),
        (
            ResponseCode.BAD_REQUEST,
            None,
            "invalid_field",
            "translated",
            "invalid_field",
            False,
        ),
        (ResponseCode.NOT_FOUND, None, None, "code message", None, True),
        (4999, None, None, "translated", "unknown_error", False),
    ],
)
def test_error_selects_message_by_priority(
    monkeypatch,
    code,
    msg,
    msg_key,
    expected,
    translated_key,
    uses_code_message,
):
    translate = MagicMock(return_value="translated")
    code_message = MagicMock(return_value="code message")
    monkeypatch.setattr(i18n, "t", translate)
    monkeypatch.setattr(i18n, "get_code_message", code_message)

    result = error(code=code, msg=msg, msg_key=msg_key, data="details", field="name")

    assert result == {"code": int(code), "data": "details", "msg": expected}
    if translated_key is None:
        translate.assert_not_called()
    elif translated_key == "unknown_error":
        translate.assert_called_once_with(translated_key)
    else:
        translate.assert_called_once_with(translated_key, field="name")
    if uses_code_message:
        code_message.assert_called_once_with(code)
    else:
        code_message.assert_not_called()


def test_business_error_preserves_context_and_string_fallbacks():
    direct = BusinessError(
        code=ResponseCode.FORBIDDEN,
        msg="denied",
        msg_key="ignored",
        status_code=403,
        data={"reason": "policy"},
        resource="agent",
    )
    keyed = BusinessError(msg_key="translated_key")
    coded = BusinessError(code=4999)

    assert str(direct) == "denied"
    assert direct.status_code == 403
    assert direct.data == {"reason": "policy"}
    assert direct.kwargs == {"resource": "agent"}
    assert str(keyed) == "translated_key"
    assert str(coded) == "4999"
