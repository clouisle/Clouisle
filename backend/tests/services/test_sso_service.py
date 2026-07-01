from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import sso as sso_service
from app.services import team_role_sync


class _ConnectionQuery:
    def prefetch_related(self, *_args: object) -> "_ConnectionQuery":
        return self

    async def first(self) -> object:
        return None


@pytest.mark.asyncio
async def test_find_or_create_user_assigns_default_team_to_email_matched_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_user = SimpleNamespace(id="user-id", email="alice@example.com")
    assign_default_team = AsyncMock(return_value=True)

    async def get_value(key: str, default: object = None) -> object:
        return True if key == "sso_match_by_email" else default

    class UserQuery:
        async def first(self) -> object:
            return existing_user

    class UserModel:
        @staticmethod
        def filter(**_kwargs: object) -> UserQuery:
            return UserQuery()

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(sso_service.User, "filter", UserModel.filter)
    monkeypatch.setattr(sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery())
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", AsyncMock())
    monkeypatch.setattr(team_role_sync, "assign_default_team", assign_default_team)

    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=SimpleNamespace(name="oidc"),
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com", "username": "alice"},
    )

    assert user is existing_user
    assert is_new is False
    assign_default_team.assert_awaited_once_with(existing_user)


@pytest.mark.asyncio
async def test_find_or_create_user_assigns_default_team_to_new_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_user = SimpleNamespace(id="user-id", roles=SimpleNamespace(add=AsyncMock()))
    assign_default_team = AsyncMock(return_value=True)

    async def get_value(key: str, default: object = None) -> object:
        values = {
            "sso_match_by_email": True,
            "sso_auto_create_users": True,
            "sso_require_approval": False,
            "default_language": "en",
        }
        return values.get(key, default)

    class UserQuery:
        def __init__(self, first_value: object = None, exists_value: bool = False) -> None:
            self.first_value = first_value
            self.exists_value = exists_value

        async def first(self) -> object:
            return self.first_value

        async def exists(self) -> bool:
            return self.exists_value

    class UserModel:
        @staticmethod
        def filter(**_kwargs: object) -> UserQuery:
            return UserQuery()

        @staticmethod
        async def create(**_kwargs: object) -> object:
            return new_user

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(sso_service.User, "filter", UserModel.filter)
    monkeypatch.setattr(sso_service.User, "create", UserModel.create)
    monkeypatch.setattr(sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery())
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", AsyncMock())
    monkeypatch.setattr(team_role_sync, "assign_default_role", AsyncMock())
    monkeypatch.setattr(team_role_sync, "assign_default_team", assign_default_team)

    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=SimpleNamespace(
            name="oidc",
            allow_signup=True,
            require_approval=False,
            default_role_id=None,
        ),
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com", "username": "alice"},
    )

    assert user is new_user
    assert is_new is True
    assign_default_team.assert_awaited_once_with(new_user)
