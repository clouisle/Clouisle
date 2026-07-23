import pytest

from app.api.v1.endpoints import login
from app.schemas.response import BusinessError, ResponseCode


@pytest.mark.anyio
async def test_validate_human_verification_requires_captcha_pair() -> None:
    with pytest.raises(BusinessError) as exc_info:
        await login.validate_human_verification("captcha-id", None)

    assert exc_info.value.code == ResponseCode.CAPTCHA_REQUIRED
    assert exc_info.value.msg_key == "captcha_required"


@pytest.mark.anyio
async def test_validate_human_verification_rejects_failed_captcha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify_captcha(captcha_id: str, captcha_token: str) -> bool:
        assert captcha_id == "captcha-id"
        assert captcha_token == "captcha-token"
        return False

    monkeypatch.setattr(login, "verify_captcha", fake_verify_captcha)

    with pytest.raises(BusinessError) as exc_info:
        await login.validate_human_verification("captcha-id", "captcha-token")

    assert exc_info.value.code == ResponseCode.CAPTCHA_INVALID
    assert exc_info.value.msg_key == "captcha_invalid"
