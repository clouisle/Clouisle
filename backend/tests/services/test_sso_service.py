from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

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
    manager = Mock()
    assign_default_team = AsyncMock(return_value=True)
    create_connection = AsyncMock()
    manager.attach_mock(assign_default_team, "assign_default_team")
    manager.attach_mock(create_connection, "create_connection")

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
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", create_connection)
    monkeypatch.setattr(team_role_sync, "assign_default_team", assign_default_team)

    provider = SimpleNamespace(name="oidc")
    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=provider,
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com", "username": "alice"},
    )

    assert user is existing_user
    assert is_new is False
    assert manager.mock_calls == [
        call.assign_default_team(existing_user),
        call.create_connection(
            user=existing_user,
            provider=provider,
            provider_user_id="provider-user-id",
            provider_username="alice",
            provider_email="alice@example.com",
            provider_data={"email": "alice@example.com", "username": "alice"},
        ),
    ]


@pytest.mark.asyncio
async def test_find_or_create_user_assigns_default_team_to_new_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_user = SimpleNamespace(id="user-id", roles=SimpleNamespace(add=AsyncMock()))
    manager = Mock()
    assign_default_team = AsyncMock(return_value=True)
    create_connection = AsyncMock()
    manager.attach_mock(assign_default_team, "assign_default_team")
    manager.attach_mock(create_connection, "create_connection")

    async def get_value(key: str, default: object = None) -> object:
        values = {
            "sso_match_by_email": True,
            "sso_auto_create_users": True,
            "sso_require_approval": False,
            "default_language": "en",
        }
        return values.get(key, default)

    class UserQuery:
        def __init__(
            self, first_value: object = None, exists_value: bool = False
        ) -> None:
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
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", create_connection)
    monkeypatch.setattr(team_role_sync, "assign_default_role", AsyncMock())
    monkeypatch.setattr(team_role_sync, "assign_default_team", assign_default_team)

    provider = SimpleNamespace(
        name="oidc",
        allow_signup=True,
        require_approval=False,
        default_role_id=None,
    )
    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=provider,
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com", "username": "alice"},
    )

    assert user is new_user
    assert is_new is True
    assert manager.mock_calls == [
        call.assign_default_team(new_user),
        call.create_connection(
            user=new_user,
            provider=provider,
            provider_user_id="provider-user-id",
            provider_username="alice",
            provider_email="alice@example.com",
            provider_data={"email": "alice@example.com", "username": "alice"},
        ),
    ]
