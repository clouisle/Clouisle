from app.core import i18n
from app.schemas.response import BusinessError, ResponseCode, error, success


def test_success_uses_explicit_message_before_translation(monkeypatch):
    monkeypatch.setattr(i18n, "t", lambda key, **kwargs: f"translated:{key}")

    assert success(data={"ok": True}, msg="created") == {
        "code": ResponseCode.SUCCESS,
        "data": {"ok": True},
        "msg": "created",
    }
    assert success(msg_key="success") == {
        "code": ResponseCode.SUCCESS,
        "data": None,
        "msg": "translated:success",
    }


def test_error_message_priority_and_fallbacks(monkeypatch):
    calls = []

    def fake_t(key, **kwargs):
        calls.append(("t", key, kwargs))
        return f"translated:{key}:{kwargs.get('name', '')}"

    def fake_code_message(code):
        calls.append(("code", code, {}))
        return f"code:{int(code)}"

    monkeypatch.setattr(i18n, "t", fake_t)
    monkeypatch.setattr(i18n, "get_code_message", fake_code_message)

    assert error(ResponseCode.NOT_FOUND, msg="missing") == {
        "code": int(ResponseCode.NOT_FOUND),
        "data": None,
        "msg": "missing",
    }
    assert error(ResponseCode.NOT_FOUND, msg_key="not_found", name="kb") == {
        "code": int(ResponseCode.NOT_FOUND),
        "data": None,
        "msg": "translated:not_found:kb",
    }
    assert error(ResponseCode.PERMISSION_DENIED) == {
        "code": int(ResponseCode.PERMISSION_DENIED),
        "data": None,
        "msg": f"code:{int(ResponseCode.PERMISSION_DENIED)}",
    }
    assert error(9999, data={"reason": "boom"}) == {
        "code": 9999,
        "data": {"reason": "boom"},
        "msg": "translated:unknown_error:",
    }
    assert calls == [
        ("t", "not_found", {"name": "kb"}),
        ("code", ResponseCode.PERMISSION_DENIED, {}),
        ("t", "unknown_error", {}),
    ]


def test_business_error_preserves_response_metadata():
    exc = BusinessError(
        code=ResponseCode.EMAIL_EXISTS,
        msg_key="email_exists",
        status_code=409,
        data={"field": "email"},
        email="taken@example.com",
    )

    assert str(exc) == "email_exists"
    assert exc.code is ResponseCode.EMAIL_EXISTS
    assert exc.msg is None
    assert exc.msg_key == "email_exists"
    assert exc.status_code == 409
    assert exc.data == {"field": "email"}
    assert exc.kwargs == {"email": "taken@example.com"}
