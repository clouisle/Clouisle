from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import login as login_endpoints
from app.api.v1.endpoints import users as user_endpoints


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


class _FakeBackgroundTasks:
    def __init__(self) -> None:
        self.tasks: list[tuple[object, tuple[object, ...]]] = []

    def add_task(self, func: object, *args: object) -> None:
        self.tasks.append((func, args))


class _FakeRequest:
    headers: dict[str, str] = {}
    client = None


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


@pytest.mark.asyncio
async def test_profile_email_change_sends_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _FakeUser()
    background_tasks = _FakeBackgroundTasks()
    cooldown_calls: list[tuple[str, str, int]] = []

    class FakeUserModel:
        @staticmethod
        def filter(**_kwargs: object) -> _FakeFirstQuery:
            return _FakeFirstQuery()

        @staticmethod
        def get(**_kwargs: object) -> _FakeGetQuery:
            return _FakeGetQuery(user)

    async def fake_get_value(key: str, default: object = None) -> object:
        return {"email_verification": True, "smtp_enabled": True}.get(key, default)

    async def fake_cooldown(_email: str, _purpose: str) -> tuple[bool, int]:
        return True, 0

    async def fake_generate(email: str, purpose: str) -> tuple[str, str]:
        assert (email, purpose) == ("new@example.com", "profile_email")
        return "123456", "token"

    async def fake_set_cooldown(email: str, purpose: str, seconds: int) -> None:
        cooldown_calls.append((email, purpose, seconds))

    async def fake_log(**_kwargs: object) -> None:
        return None

    async def fake_serialize(updated_user: object) -> object:
        return {
            "email": updated_user.email,
            "email_verified": updated_user.email_verified,
        }

    monkeypatch.setattr(user_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(user_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(user_endpoints, "check_email_cooldown", fake_cooldown)
    monkeypatch.setattr(user_endpoints, "generate_verification_code", fake_generate)
    monkeypatch.setattr(user_endpoints, "set_email_cooldown", fake_set_cooldown)
    monkeypatch.setattr(user_endpoints.AuditLogService, "log", fake_log)
    monkeypatch.setattr(user_endpoints, "serialize_user_with_sso", fake_serialize)

    result = await user_endpoints.update_user_me(
        request=_request(),
        background_tasks=background_tasks,  # type: ignore[arg-type]
        data=user_endpoints.UpdateProfileRequest(email="new@example.com"),
        current_user=user,  # type: ignore[arg-type]
    )

    assert result["data"] == {"email": "new@example.com", "email_verified": False}
    assert cooldown_calls == [("new@example.com", "profile_email", 60)]
    assert background_tasks.tasks == [
        (
            user_endpoints.send_verification_email,
            ("new@example.com", "123456", "token", "profile_email", "zh"),
        )
    ]


@pytest.mark.asyncio
async def test_profile_email_change_stays_verified_when_verification_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _FakeUser()
    background_tasks = _FakeBackgroundTasks()

    class FakeUserModel:
        @staticmethod
        def filter(**_kwargs: object) -> _FakeFirstQuery:
            return _FakeFirstQuery()

        @staticmethod
        def get(**_kwargs: object) -> _FakeGetQuery:
            return _FakeGetQuery(user)

    async def fake_get_value(key: str, default: object = None) -> object:
        return {"email_verification": False}.get(key, default)

    async def fake_log(**_kwargs: object) -> None:
        return None

    async def fake_serialize(updated_user: object) -> object:
        return {
            "email": updated_user.email,
            "email_verified": updated_user.email_verified,
        }

    monkeypatch.setattr(user_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(user_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(user_endpoints.AuditLogService, "log", fake_log)
    monkeypatch.setattr(user_endpoints, "serialize_user_with_sso", fake_serialize)

    result = await user_endpoints.update_user_me(
        request=_request(),
        background_tasks=background_tasks,  # type: ignore[arg-type]
        data=user_endpoints.UpdateProfileRequest(email="new@example.com"),
        current_user=user,  # type: ignore[arg-type]
    )

    assert result["data"] == {"email": "new@example.com", "email_verified": True}
    assert background_tasks.tasks == []


@pytest.mark.asyncio
async def test_profile_email_purpose_marks_user_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(email="new@example.com", email_verified=False)

    async def fake_save() -> None:
        return None

    user.save = fake_save

    class FakeUserModel:
        @staticmethod
        def filter(**_kwargs: object) -> _FakeFirstQuery:
            return _FakeFirstQuery(user)

    async def fake_verify_code(email: str, code: str, purpose: str) -> bool:
        assert (email, code, purpose) == (
            "new@example.com",
            "123456",
            "profile_email",
        )
        return True

    monkeypatch.setattr(login_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(login_endpoints, "verify_code", fake_verify_code)

    result = await login_endpoints.verify_email_by_code(
        data=login_endpoints.VerifyCodeRequest(
            email="new@example.com",
            code="123456",
            purpose="profile_email",
        )
    )

    assert result["data"].verified is True
    assert user.email_verified is True
