import pytest
from pydantic import ValidationError

from app.schemas.captcha import (
    CaptchaClickRequest,
    CaptchaPointerPoint,
    CaptchaProofResponse,
    CaptchaResponse,
    CaptchaVerifyRequest,
)


def test_captcha_response_applies_public_challenge_defaults():
    response = CaptchaResponse(captcha_id="captcha-1", challenge="challenge-1")

    assert response.model_dump() == {
        "captcha_id": "captcha-1",
        "challenge": "challenge-1",
        "prompt": "captcha_click_prompt",
        "expires_in": 300,
    }


def test_click_request_parses_pointer_data_and_uses_independent_defaults():
    request = CaptchaClickRequest(
        captcha_id="captcha-1",
        challenge="challenge-1",
        clicked_option="human_check",
        elapsed_ms=700,
        pointer=[{"x": 12, "y": 24, "t": 100}],
    )
    another_request = CaptchaClickRequest(
        captcha_id="captcha-2",
        challenge="challenge-2",
        clicked_option="human_check",
        elapsed_ms=800,
    )

    assert request.pointer == [CaptchaPointerPoint(x=12.0, y=24.0, t=100)]
    assert request.pointer[0].event == "move"
    assert another_request.pointer == []
    assert another_request.pointer is not request.pointer


def test_captcha_proof_and_verify_models_require_tokens():
    proof = CaptchaProofResponse(captcha_id="captcha-1", captcha_token="proof-token")
    verification = CaptchaVerifyRequest(captcha_id="captcha-1", token="verify-token")

    assert proof.model_dump() == {
        "captcha_id": "captcha-1",
        "captcha_token": "proof-token",
    }
    assert verification.model_dump() == {
        "captcha_id": "captcha-1",
        "token": "verify-token",
    }
    with pytest.raises(ValidationError):
        CaptchaVerifyRequest(captcha_id="captcha-1")
