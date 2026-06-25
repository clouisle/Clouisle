import pytest

from app.core import captcha as captcha_core
from app.schemas.response import BusinessError, ResponseCode
from app.api.v1.endpoints import login as login_endpoints


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_click_captcha_verifies_once(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(captcha_core, "get_redis", fake_get_redis)

    captcha_id, challenge, token = await captcha_core.generate_captcha()

    assert challenge == token
    assert await captcha_core.verify_captcha(captcha_id, token) is True
    assert await captcha_core.verify_captcha(captcha_id, token) is False


@pytest.mark.asyncio
async def test_click_captcha_rejects_wrong_or_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(captcha_core, "get_redis", fake_get_redis)

    captcha_id, _, _ = await captcha_core.generate_captcha()

    assert await captcha_core.verify_captcha(captcha_id, "wrong-token") is False
    assert await captcha_core.verify_captcha(captcha_id, "wrong-token") is False
    assert await captcha_core.verify_captcha("", "wrong-token") is False


@pytest.mark.asyncio
async def test_validate_human_verification_requires_click_token() -> None:
    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.validate_human_verification("captcha-id", None)

    assert exc_info.value.code == ResponseCode.CAPTCHA_REQUIRED


@pytest.mark.asyncio
async def test_validate_human_verification_rejects_invalid_click_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify_captcha(captcha_id: str, token: str) -> bool:
        return False

    monkeypatch.setattr(login_endpoints, "verify_captcha", fake_verify_captcha)

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.validate_human_verification("captcha-id", "bad-token")

    assert exc_info.value.code == ResponseCode.CAPTCHA_INVALID


@pytest.mark.asyncio
async def test_validate_human_verification_accepts_valid_click_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify_captcha(captcha_id: str, token: str) -> bool:
        return captcha_id == "captcha-id" and token == "valid-token"

    monkeypatch.setattr(login_endpoints, "verify_captcha", fake_verify_captcha)

    await login_endpoints.validate_human_verification("captcha-id", "valid-token")
