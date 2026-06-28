from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import login as login_endpoints
from app.models import user as user_models
from app.schemas.user import UserCreate


class _AwaitableValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def __await__(self):
        async def _result():
            return self.value

        return _result().__await__()


class _FakeRoles:
    async def add(self, role: object) -> None:
        return None


class _FakeUser:
    id = "user-id"
    username = "alice"
    email = "alice@example.com"
    roles = _FakeRoles()

    async def save(self) -> None:
        return None


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


class _FakeAllQuery:
    async def count(self) -> int:
        return 0


@pytest.mark.asyncio
async def test_register_persists_submitted_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_kwargs: dict[str, object] = {}
    created_user = _FakeUser()

    async def fake_get_value(key: str, default: object = None) -> object:
        values = {
            "require_approval": False,
            "email_verification": False,
            "default_language": "en",
            "force_password_change_first_login": False,
        }
        return values.get(key, default)

    class FakeUserModel:
        @staticmethod
        def all() -> _FakeAllQuery:
            return _FakeAllQuery()

        @staticmethod
        def filter(**_kwargs: object) -> _FakeFirstQuery:
            return _FakeFirstQuery()

        @staticmethod
        async def create(**kwargs: object) -> _FakeUser:
            created_kwargs.update(kwargs)
            return created_user

        @staticmethod
        def get(**_kwargs: object) -> _FakeGetQuery:
            return _FakeGetQuery(created_user)

    class FakeRoleModel:
        @staticmethod
        def filter(**_kwargs: object) -> _FakeFirstQuery:
            return _FakeFirstQuery(SimpleNamespace())

    async def fake_log(**_kwargs: object) -> None:
        return None

    async def fake_serialize(user: object) -> object:
        return user

    async def fake_validate_password(_password: str) -> tuple[bool, list[str]]:
        return True, []

    monkeypatch.setattr(login_endpoints.SiteSetting, "get_value", fake_get_value)
    monkeypatch.setattr(login_endpoints, "User", FakeUserModel)
    monkeypatch.setattr(user_models, "Role", FakeRoleModel)
    monkeypatch.setattr(login_endpoints, "validate_password", fake_validate_password)
    monkeypatch.setattr(
        login_endpoints.security, "get_password_hash", lambda _password: "hash"
    )
    monkeypatch.setattr(
        login_endpoints.PasswordExpirationService,
        "calculate_expiration_date",
        lambda _user: _AwaitableValue(None),
    )
    monkeypatch.setattr(login_endpoints.AuditLogService, "log", fake_log)
    monkeypatch.setattr(login_endpoints, "serialize_user_with_sso", fake_serialize)

    await login_endpoints.register(
        request=Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/register",
                "headers": [],
                "query_string": b"",
                "server": ("testserver", 80),
                "scheme": "http",
                "client": ("testclient", 50000),
            }
        ),
        user_in=UserCreate(
            username="alice",
            email="alice@example.com",
            password="StrongPass123!",
            locale="zh-CN",
        ),
    )

    assert created_kwargs["locale"] == "zh"
