import pytest

from app.api.v1.endpoints import login as login_endpoints
from app.core import captcha as captcha_core
from app.schemas.captcha import CaptchaClickRequest
from app.schemas.response import BusinessError, ResponseCode


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    redis = FakeRedis()

    async def fake_get_redis() -> FakeRedis:
        return redis

    monkeypatch.setattr(captcha_core, "get_redis", fake_get_redis)
    return redis


@pytest.mark.asyncio
async def test_captcha_endpoint_does_not_leak_private_proof(
    fake_redis: FakeRedis,
) -> None:
    response = await login_endpoints.get_captcha()

    captcha_id = response["data"].captcha_id
    challenge = response["data"].challenge
    stored_nonce = fake_redis.values[f"captcha:{captcha_id}"]

    assert stored_nonce in challenge
    assert f"captcha-proof:{captcha_id}" not in fake_redis.values
    assert challenge != stored_nonce


@pytest.mark.asyncio
async def test_click_captcha_valid_proof_succeeds_once(fake_redis: FakeRedis) -> None:
    response = await login_endpoints.get_captcha()
    captcha_id = response["data"].captcha_id
    challenge = response["data"].challenge
    click_nonce = fake_redis.values[f"captcha:{captcha_id}"]

    proof_response = await login_endpoints.complete_captcha_click(
        CaptchaClickRequest(
            captcha_id=captcha_id,
            challenge=challenge,
            click_nonce=click_nonce,
            elapsed_ms=captcha_core.MIN_CLICK_ELAPSED_MS,
        )
    )

    assert proof_response["data"].captcha_token != challenge
    assert (
        await captcha_core.verify_captcha(
            captcha_id, proof_response["data"].captcha_token
        )
        is True
    )
    assert (
        await captcha_core.verify_captcha(
            captcha_id, proof_response["data"].captcha_token
        )
        is False
    )


@pytest.mark.asyncio
async def test_click_captcha_missing_or_invalid_proof_fails(
    fake_redis: FakeRedis,
) -> None:
    response = await login_endpoints.get_captcha()
    captcha_id = response["data"].captcha_id

    with pytest.raises(BusinessError) as missing_exc:
        await login_endpoints.validate_human_verification(captcha_id, None)
    assert missing_exc.value.code == ResponseCode.CAPTCHA_REQUIRED

    with pytest.raises(BusinessError) as invalid_exc:
        await login_endpoints.validate_human_verification(captcha_id, "bad-token")
    assert invalid_exc.value.code == ResponseCode.CAPTCHA_INVALID


@pytest.mark.asyncio
async def test_click_captcha_invalid_click_data_fails(fake_redis: FakeRedis) -> None:
    response = await login_endpoints.get_captcha()

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.complete_captcha_click(
            CaptchaClickRequest(
                captcha_id=response["data"].captcha_id,
                challenge=response["data"].challenge,
                click_nonce="wrong-nonce",
                elapsed_ms=captcha_core.MIN_CLICK_ELAPSED_MS,
            )
        )

    assert exc_info.value.code == ResponseCode.CAPTCHA_INVALID


@pytest.mark.asyncio
async def test_click_captcha_expired_challenge_fails(fake_redis: FakeRedis) -> None:
    response = await login_endpoints.get_captcha()
    captcha_id = response["data"].captcha_id
    challenge = response["data"].challenge
    click_nonce = fake_redis.values[f"captcha:{captcha_id}"]
    await fake_redis.delete(f"captcha:{captcha_id}")

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.complete_captcha_click(
            CaptchaClickRequest(
                captcha_id=captcha_id,
                challenge=challenge,
                click_nonce=click_nonce,
                elapsed_ms=captcha_core.MIN_CLICK_ELAPSED_MS,
            )
        )

    assert exc_info.value.code == ResponseCode.CAPTCHA_INVALID


@pytest.mark.asyncio
async def test_login_valid_proof_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, str | None]] = []

    async def fake_get_value(key: str, default: object = None) -> object:
        values = {
            "sso_enabled": False,
            "sso_allow_password_login": True,
            "enable_captcha": True,
            "email_verification": False,
            "require_totp": False,
            "single_session": False,
            "session_timeout_days": 7,
        }
        return values.get(key, default)

    async def fake_validate(captcha_id: str | None, captcha_token: str | None) -> None:
        calls.append((captcha_id, captcha_token))

    class FakeUserQuery:
        async def first(self) -> object:
            return fake_user

    class FakeUserModel:
        @staticmethod
        def filter(**kwargs: object) -> FakeUserQuery:
            return FakeUserQuery()

    class FakeUser:
        id = "user-id"
        username = "alice"
        email = "alice@example.com"
        locale = "en"
        hashed_password = "hashed"
        is_active = True
        approval_status = "approved"
        totp_enabled = False
        email_verified = True
        is_superuser = False
        force_password_change = False
        last_login = None

        async def save(self) -> None:
            return None

    fake_user = FakeUser()

    class FakeRequest:
        headers: dict[str, str] = {}
        client = None

    monkeypatch.setattr(login_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(login_endpoints, "validate_human_verification", fake_validate)
    monkeypatch.setattr(login_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(login_endpoints.security, "verify_password", lambda *_: True)
    monkeypatch.setattr(
        login_endpoints.security,
        "create_access_token",
        lambda *_args, **_kwargs: "jwt",
    )

    async def fake_none_bool(_user: object) -> bool:
        return False

    async def fake_none_value(_user: object) -> None:
        return None

    async def fake_check_account_locked(_user: object) -> tuple[bool, int]:
        return False, 0

    async def fake_none(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_check_login_anomaly(
        **_kwargs: object,
    ) -> tuple[bool, dict[str, object]]:
        return False, {}

    monkeypatch.setattr(
        login_endpoints, "check_account_locked", fake_check_account_locked
    )
    monkeypatch.setattr(login_endpoints, "reset_login_attempts", fake_none)
    monkeypatch.setattr(
        login_endpoints, "check_login_anomaly", fake_check_login_anomaly
    )
    monkeypatch.setattr(login_endpoints, "record_login", fake_none)
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "is_user_exempt",
        fake_none_bool,
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "is_password_expired",
        fake_none_bool,
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "should_warn_user",
        fake_none_bool,
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "days_until_expiration",
        fake_none_value,
    )
    monkeypatch.setattr(login_endpoints.AuditLogService, "log", fake_none)

    result = await login_endpoints.login_access_token(
        request=FakeRequest(),
        identifier="alice",
        password="password",
        captcha_id="captcha-id",
        captcha_token="proof-token",
    )

    assert calls == [("captcha-id", "proof-token")]
    assert result["data"]["access_token"] == "jwt"


@pytest.mark.asyncio
async def test_register_requires_valid_proof_for_non_first_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str | None, str | None]] = []

    async def fake_validate(captcha_id: str | None, captcha_token: str | None) -> None:
        calls.append((captcha_id, captcha_token))

    class FakeCountQuery:
        async def count(self) -> int:
            return 1

    class FakeUserModel:
        @staticmethod
        def all() -> FakeCountQuery:
            return FakeCountQuery()

    async def fake_get_value(key: str, default: object = None) -> object:
        values = {
            "allow_registration": True,
            "enable_captcha": True,
        }
        return values.get(key, default)

    user_in = type(
        "UserIn",
        (),
        {"captcha_id": "captcha-id", "captcha_token": "proof-token", "password": "bad"},
    )()

    async def fake_invalid_password(_password: str) -> tuple[bool, list[str]]:
        return False, []

    monkeypatch.setattr(login_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(login_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(login_endpoints, "validate_human_verification", fake_validate)
    monkeypatch.setattr(login_endpoints, "validate_password", fake_invalid_password)

    with pytest.raises(BusinessError):
        await login_endpoints.register(request=object(), user_in=user_in)

    assert calls == [("captcha-id", "proof-token")]


@pytest.mark.asyncio
async def test_first_user_registration_bypasses_captcha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def fake_validate(captcha_id: str | None, captcha_token: str | None) -> None:
        nonlocal called
        called = True

    class FakeCountQuery:
        async def count(self) -> int:
            return 0

    class FakeUserModel:
        @staticmethod
        def all() -> FakeCountQuery:
            return FakeCountQuery()

    user_in = type("UserIn", (), {"password": "bad"})()

    async def fake_invalid_password(_password: str) -> tuple[bool, list[str]]:
        return False, []

    monkeypatch.setattr(login_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(login_endpoints, "validate_human_verification", fake_validate)
    monkeypatch.setattr(login_endpoints, "validate_password", fake_invalid_password)

    with pytest.raises(BusinessError):
        await login_endpoints.register(request=object(), user_in=user_in)

    assert called is False
