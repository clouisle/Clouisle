import pytest
from pydantic import ValidationError

from app.core import i18n
from app.schemas.response import (
    BusinessError,
    PageData,
    PageResponse,
    Response,
    ResponseCode,
    error,
    success,
)


def test_response_models_preserve_defaults_and_typed_page_data() -> None:
    response = Response[dict[str, int]](data={"count": 0})
    page = PageResponse[str](
        data=PageData(items=[], total=0, page=1, page_size=1),
    )

    assert response.model_dump() == {"code": 0, "data": {"count": 0}, "msg": "success"}
    assert page.data == PageData(items=[], total=0, page=1, page_size=1)


def test_response_models_reject_invalid_typed_data_and_missing_page_field() -> None:
    with pytest.raises(ValidationError):
        Response[dict[str, int]](data={"count": "zero"})

    with pytest.raises(ValidationError):
        PageData(items=[], total=0, page=1)


def test_business_error_retains_context_and_uses_message_precedence() -> None:
    error_instance = BusinessError(
        ResponseCode.FORBIDDEN,
        msg="Denied",
        msg_key="access_denied",
        status_code=403,
        data={"resource": "team"},
        request_id="request-1",
    )

    assert str(error_instance) == "Denied"
    assert error_instance.code is ResponseCode.FORBIDDEN
    assert error_instance.msg_key == "access_denied"
    assert error_instance.status_code == 403
    assert error_instance.data == {"resource": "team"}
    assert error_instance.kwargs == {"request_id": "request-1"}


def test_success_and_error_helpers_select_expected_message_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(i18n, "t", lambda key, **kwargs: f"{key}:{kwargs['name']}")
    monkeypatch.setattr(i18n, "get_code_message", lambda code: f"code:{code.value}")

    assert success({"id": 1}, msg_key="created", name="Ada") == {
        "code": ResponseCode.SUCCESS,
        "data": {"id": 1},
        "msg": "created:Ada",
    }
    assert error(ResponseCode.NOT_FOUND) == {
        "code": 4000,
        "data": None,
        "msg": "code:4000",
    }
    assert error(9999, msg_key="missing", name="Ada") == {
        "code": 9999,
        "data": None,
        "msg": "missing:Ada",
    }
