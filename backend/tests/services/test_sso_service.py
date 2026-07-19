from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.schemas.response import BusinessError, ResponseCode
from app.services import sso as sso_service
from app.services import team_role_sync
from app.sso.providers.cas import CASProvider
from app.sso.providers.oidc import OIDCProvider
from app.sso.providers.saml import SAMLProvider


class _ConnectionQuery:
    def __init__(self, connection: object = None) -> None:
        self.connection = connection

    def prefetch_related(self, *_args: object) -> "_ConnectionQuery":
        return self

    async def first(self) -> object:
        return self.connection


class _UserQuery:
    def __init__(self, *, first: object = None, exists: bool = False) -> None:
        self.first_value = first
        self.exists_value = exists

    async def first(self) -> object:
        return self.first_value

    async def exists(self) -> bool:
        return self.exists_value


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


@pytest.mark.parametrize(
    ("protocol", "expected_type"),
    [
        ("OIDC", OIDCProvider),
        ("oauth2", OIDCProvider),
        ("SAML2", SAMLProvider),
        ("CAS", CASProvider),
    ],
)
def test_get_provider_instance_supports_protocols(
    protocol: str, expected_type: type
) -> None:
    provider = SimpleNamespace(protocol=protocol, config={}, attribute_mapping={})

    assert isinstance(
        sso_service.SSOService.get_provider_instance(provider), expected_type
    )


def test_get_provider_instance_rejects_unsupported_protocol() -> None:
    provider = SimpleNamespace(protocol="ldap")

    with pytest.raises(ValueError, match="Unsupported protocol: ldap"):
        sso_service.SSOService.get_provider_instance(provider)


@pytest.mark.asyncio
async def test_find_or_create_user_updates_existing_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id="user-id")
    connection = SimpleNamespace(user=user, save=AsyncMock())
    timestamp = object()
    monkeypatch.setattr(
        sso_service.UserSSOConnection,
        "filter",
        lambda **_kwargs: _ConnectionQuery(connection),
    )
    monkeypatch.setattr(sso_service, "now_utc", lambda: timestamp)

    result = await sso_service.SSOService.find_or_create_user(
        SimpleNamespace(), "provider-user-id", {"email": "new@example.com"}
    )

    assert result == (user, False)
    assert connection.last_login is timestamp
    assert connection.provider_data == {"email": "new@example.com"}
    connection.save.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_find_or_create_user_rejects_disabled_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object = None) -> object:
        return (
            False if key in {"sso_match_by_email", "sso_auto_create_users"} else default
        )

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )

    with pytest.raises(BusinessError) as exc_info:
        await sso_service.SSOService.find_or_create_user(
            SimpleNamespace(allow_signup=False),
            "provider-user-id",
            {"email": "alice@example.com"},
        )

    assert exc_info.value.code == ResponseCode.SSO_REGISTRATION_DISABLED
    assert exc_info.value.msg_key == "sso_registration_disabled"


@pytest.mark.asyncio
async def test_find_or_create_user_requires_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object = None) -> object:
        return {
            "sso_match_by_email": False,
            "sso_auto_create_users": True,
            "sso_require_approval": False,
        }.get(key, default)

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(
        sso_service.User, "filter", lambda **_kwargs: _UserQuery(exists=False)
    )

    with pytest.raises(BusinessError) as exc_info:
        await sso_service.SSOService.find_or_create_user(
            SimpleNamespace(allow_signup=True, require_approval=False),
            "provider-user-id",
            {},
        )

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    assert exc_info.value.msg_key == "email_required"


@pytest.mark.asyncio
async def test_find_or_create_user_creates_pending_user_with_unique_username_and_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filters: list[str] = []
    role = object()
    new_user = SimpleNamespace(roles=SimpleNamespace(add=AsyncMock()))
    create_user = AsyncMock(return_value=new_user)
    create_connection = AsyncMock()

    async def get_value(key: str, default: object = None) -> object:
        return {
            "sso_match_by_email": False,
            "sso_auto_create_users": True,
            "sso_require_approval": False,
            "default_language": "zh",
        }.get(key, default)

    def user_filter(**kwargs: object) -> _UserQuery:
        username = str(kwargs["username"])
        filters.append(username)
        return _UserQuery(exists=username == "alice")

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", create_connection)
    monkeypatch.setattr(sso_service.User, "filter", user_filter)
    monkeypatch.setattr(sso_service.User, "create", create_user)
    monkeypatch.setattr(sso_service.Role, "get_or_none", AsyncMock(return_value=role))
    monkeypatch.setattr(team_role_sync, "assign_default_team", AsyncMock())
    provider = SimpleNamespace(
        name="company",
        allow_signup=True,
        require_approval=True,
        default_role_id="role-id",
    )

    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider,
        "provider-user-id",
        {"email": "alice@example.com", "picture": "avatar.png"},
    )

    assert (user, is_new) == (new_user, True)
    assert filters == ["alice", "alice1"]
    create_user.assert_awaited_once_with(
        username="alice1",
        email="alice@example.com",
        hashed_password="",
        auth_source="company",
        is_active=False,
        approval_status="pending",
        email_verified=True,
        avatar_url="avatar.png",
        locale="zh",
    )
    new_user.roles.add.assert_awaited_once_with(role)
    create_connection.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_deletes_matching_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = object()
    expired_sessions = SimpleNamespace(delete=AsyncMock())
    filter_sessions = AsyncMock(return_value=expired_sessions)
    from app.models.sso_session import SSOSession

    monkeypatch.setattr(sso_service, "now_utc", lambda: timestamp)
    monkeypatch.setattr(SSOSession, "filter", filter_sessions)

    await sso_service.SSOService.cleanup_expired_sessions()

    filter_sessions.assert_awaited_once_with(expires_at__lt=timestamp)
    expired_sessions.delete.assert_awaited_once_with()
