from fastapi import BackgroundTasks
import pytest
from starlette.requests import Request

from app.api.v1.endpoints import login as login_endpoints
from app.api.v1.endpoints import users as user_endpoints
from app.schemas.response import BusinessError, ResponseCode


class _AwaitableValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def __await__(self):
        async def _result():
            return self.value

        return _result().__await__()


class _FakeFirstQuery:
    def __init__(self, value: object = None) -> None:
        self.value = value

    async def first(self) -> object:
        return self.value


class _FakeGetQuery:
    def __init__(self, value: object) -> None:
        self.value = value

    def prefetch_related(self, *_args: object) -> _AwaitableValue:
        return _AwaitableValue(self.value)


class _FakeUser:
    id = "user-id"
    username = "alice"
    email = "alice@example.com"
    email_verified = True
    locale = "zh"
    avatar_url = None

    async def update_from_dict(self, data: dict[str, object]) -> None:
        for key, value in data.items():
            setattr(self, key, value)

    async def save(self) -> None:
        return None


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/api/v1/users/me",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


def _patch_user_model(monkeypatch: pytest.MonkeyPatch, user: _FakeUser) -> None:
    class FakeUserModel:
        @staticmethod
        def filter(**_kwargs: object) -> _FakeFirstQuery:
            return _FakeFirstQuery()

        @staticmethod
        def get(**_kwargs: object) -> _FakeGetQuery:
            return _FakeGetQuery(user)

    async def fake_log(**_kwargs: object) -> None:
        return None

    async def fake_serialize(updated_user: object) -> object:
        return {
            "email": updated_user.email,
            "email_verified": updated_user.email_verified,
        }

    monkeypatch.setattr(user_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(user_endpoints.AuditLogService, "log", fake_log)
    monkeypatch.setattr(user_endpoints, "serialize_user_with_sso", fake_serialize)


@pytest.mark.asyncio
async def test_profile_email_change_requires_code_when_verification_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _FakeUser()
    _patch_user_model(monkeypatch, user)

    async def fake_get_value(key: str, default: object = None) -> object:
        return {"email_verification": True}.get(key, default)

    monkeypatch.setattr(user_endpoints.SiteSetting, "get_value", fake_get_value)

    with pytest.raises(BusinessError) as exc_info:
        await user_endpoints.update_user_me(
            request=_request(),
            data=user_endpoints.UpdateProfileRequest(email="new@example.com"),
            current_user=user,  # type: ignore[arg-type]
        )

    assert exc_info.value.code == ResponseCode.VERIFICATION_CODE_INVALID
    assert user.email == "alice@example.com"
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_profile_email_change_rejects_invalid_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _FakeUser()
    _patch_user_model(monkeypatch, user)

    async def fake_get_value(key: str, default: object = None) -> object:
        return {"email_verification": True}.get(key, default)

    async def fake_verify_code(_email: str, _code: str, _purpose: str) -> bool:
        return False

    monkeypatch.setattr(user_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(user_endpoints, "verify_code", fake_verify_code)

    with pytest.raises(BusinessError) as exc_info:
        await user_endpoints.update_user_me(
            request=_request(),
            data=user_endpoints.UpdateProfileRequest(
                email="new@example.com",
                email_verification_code="000000",
            ),
            current_user=user,  # type: ignore[arg-type]
        )

    assert exc_info.value.code == ResponseCode.VERIFICATION_CODE_INVALID
    assert user.email == "alice@example.com"
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_profile_email_change_saves_after_valid_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _FakeUser()
    _patch_user_model(monkeypatch, user)
    verify_calls: list[tuple[str, str, str]] = []

    async def fake_get_value(key: str, default: object = None) -> object:
        return {"email_verification": True}.get(key, default)

    async def fake_verify_code(email: str, code: str, purpose: str) -> bool:
        verify_calls.append((email, code, purpose))
        return True

    monkeypatch.setattr(user_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(user_endpoints, "verify_code", fake_verify_code)

    result = await user_endpoints.update_user_me(
        request=_request(),
        data=user_endpoints.UpdateProfileRequest(
            email="new@example.com",
            email_verification_code="123456",
        ),
        current_user=user,  # type: ignore[arg-type]
    )

    assert verify_calls == [("new@example.com", "123456", "profile_email")]
    assert result["data"] == {"email": "new@example.com", "email_verified": True}


@pytest.mark.asyncio
async def test_profile_email_change_stays_verified_when_verification_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _FakeUser()
    _patch_user_model(monkeypatch, user)

    async def fake_get_value(key: str, default: object = None) -> object:
        return {"email_verification": False}.get(key, default)

    monkeypatch.setattr(user_endpoints.SiteSetting, "get_value", fake_get_value)

    result = await user_endpoints.update_user_me(
        request=_request(),
        data=user_endpoints.UpdateProfileRequest(email="new@example.com"),
        current_user=user,  # type: ignore[arg-type]
    )

    assert result["data"] == {"email": "new@example.com", "email_verified": True}


@pytest.mark.asyncio
async def test_profile_email_send_verification_respects_backend_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_value(key: str, default: object = None) -> object:
        return {"smtp_enabled": True}.get(key, default)

    async def fake_check_email_cooldown(_email: str, _purpose: str) -> tuple[bool, int]:
        return False, 42

    monkeypatch.setattr(login_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(
        login_endpoints, "check_email_cooldown", fake_check_email_cooldown
    )

    with pytest.raises(BusinessError) as exc_info:
        await login_endpoints.send_verification(
            data=login_endpoints.SendVerificationRequest(
                email="new@example.com",
                purpose="profile_email",
            ),
            background_tasks=BackgroundTasks(),
        )

    assert exc_info.value.code == ResponseCode.EMAIL_SEND_TOO_FREQUENT
    assert exc_info.value.data == {"remaining_seconds": 42}
