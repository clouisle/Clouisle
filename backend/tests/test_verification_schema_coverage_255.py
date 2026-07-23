import pytest
from pydantic import ValidationError

from app.schemas.verification import (
    ResetPasswordConfirmRequest,
    SendVerificationRequest,
    VerificationResponse,
    VerifyCodeRequest,
    VerifyTokenRequest,
)


def test_verification_requests_keep_defaults_and_valid_contact_data():
    assert SendVerificationRequest(email="person@example.com").purpose == "register"
    assert (
        VerifyCodeRequest(email="person@example.com", code="123456").purpose
        == "register"
    )
    assert VerifyTokenRequest(token="reset-token").token == "reset-token"
    assert VerificationResponse(
        verified=True, email="person@example.com"
    ).model_dump() == {
        "verified": True,
        "email": "person@example.com",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"new_password": "ValidPass1!"},
        {"email": "person@example.com", "new_password": "ValidPass1!"},
        {"code": "123456", "new_password": "ValidPass1!"},
    ],
)
def test_reset_password_confirmation_requires_complete_code_or_token(payload):
    with pytest.raises(ValidationError, match="Either email and code, or token"):
        ResetPasswordConfirmRequest(**payload)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "person@example.com",
            "code": "123456",
            "new_password": "ValidPass1!",
        },
        {"token": "reset-token", "new_password": "ValidPass1!"},
    ],
)
def test_reset_password_confirmation_accepts_code_and_token_authentication(payload):
    request = ResetPasswordConfirmRequest(**payload)

    assert request.new_password == "ValidPass1!"
