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


@pytest.mark.parametrize(
    ("protocol", "provider_cls"),
    [
        ("oidc", sso_service.OIDCProvider),
        ("oauth2", sso_service.OIDCProvider),
        ("saml2", sso_service.SAMLProvider),
        ("cas", sso_service.CASProvider),
    ],
)
def test_get_provider_instance_dispatches_supported_protocols(
    protocol: str,
    provider_cls: type,
) -> None:
    provider = SimpleNamespace(protocol=protocol, config={})

    result = sso_service.SSOService.get_provider_instance(provider)  # type: ignore[arg-type]

    assert isinstance(result, provider_cls)


def test_get_provider_instance_rejects_unsupported_protocol() -> None:
    provider = SimpleNamespace(protocol="ldap")

    with pytest.raises(ValueError, match="Unsupported protocol: ldap"):
        sso_service.SSOService.get_provider_instance(provider)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_find_or_create_user_updates_existing_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_user = SimpleNamespace(id="user-id")
    connection = SimpleNamespace(
        user=existing_user,
        save=AsyncMock(),
        last_login=None,
        provider_data=None,
    )

    class ConnectionQuery:
        def prefetch_related(self, *_args: object) -> "ConnectionQuery":
            return self

        async def first(self) -> object:
            return connection

    monkeypatch.setattr(
        sso_service.UserSSOConnection,
        "filter",
        lambda **_kwargs: ConnectionQuery(),
    )

    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=SimpleNamespace(name="oidc"),
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com"},
    )

    assert user is existing_user
    assert is_new is False
    assert connection.provider_data == {"email": "alice@example.com"}
    assert connection.last_login is not None
    connection.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_or_create_user_rejects_disabled_signup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object = None) -> object:
        return False if key == "sso_auto_create_users" else default

    class UserQuery:
        async def first(self) -> object:
            return None

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.User, "filter", lambda **_kwargs: UserQuery())

    with pytest.raises(sso_service.BusinessError) as exc_info:
        await sso_service.SSOService.find_or_create_user(
            provider=SimpleNamespace(name="oidc", allow_signup=False),
            provider_user_id="provider-user-id",
            user_info={"email": "alice@example.com"},
        )

    assert exc_info.value.code == sso_service.ResponseCode.SSO_REGISTRATION_DISABLED
    assert exc_info.value.msg_key == "sso_registration_disabled"


@pytest.mark.asyncio
async def test_find_or_create_user_requires_email_before_creating_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_value(key: str, default: object = None) -> object:
        return default

    class UserQuery:
        async def exists(self) -> bool:
            return False

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.User, "filter", lambda **_kwargs: UserQuery())

    with pytest.raises(sso_service.BusinessError) as exc_info:
        await sso_service.SSOService.find_or_create_user(
            provider=SimpleNamespace(
                name="oidc",
                allow_signup=True,
                require_approval=False,
            ),
            provider_user_id="provider-user-id",
            user_info={},
        )

    assert exc_info.value.code == sso_service.ResponseCode.VALIDATION_ERROR
    assert exc_info.value.msg_key == "email_required"


@pytest.mark.asyncio
async def test_find_or_create_user_makes_username_unique_and_applies_provider_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_user = SimpleNamespace(id="user-id", roles=SimpleNamespace(add=AsyncMock()))
    role = SimpleNamespace(id="role-id")
    manager = Mock()
    user_create = AsyncMock(return_value=new_user)
    assign_default_team = AsyncMock()
    create_connection = AsyncMock()
    manager.attach_mock(user_create, "user_create")
    manager.attach_mock(new_user.roles.add, "add_role")
    manager.attach_mock(assign_default_team, "assign_default_team")
    manager.attach_mock(create_connection, "create_connection")

    async def get_value(key: str, default: object = None) -> object:
        values = {
            "sso_match_by_email": False,
            "sso_auto_create_users": True,
            "sso_require_approval": True,
            "default_language": "zh",
        }
        return values.get(key, default)

    class UserQuery:
        def __init__(self, username: str | None) -> None:
            self.username = username

        async def exists(self) -> bool:
            return self.username == "alice"

    class UserModel:
        @staticmethod
        def filter(**kwargs: object) -> UserQuery:
            return UserQuery(kwargs.get("username"))

        create = user_create

    monkeypatch.setattr(sso_service.SiteSetting, "get_value", get_value)
    monkeypatch.setattr(sso_service.User, "filter", UserModel.filter)
    monkeypatch.setattr(sso_service.User, "create", UserModel.create)
    monkeypatch.setattr(sso_service.Role, "get_or_none", AsyncMock(return_value=role))
    monkeypatch.setattr(
        sso_service.UserSSOConnection, "filter", lambda **_kwargs: _ConnectionQuery()
    )
    monkeypatch.setattr(sso_service.UserSSOConnection, "create", create_connection)
    monkeypatch.setattr(team_role_sync, "assign_default_team", assign_default_team)

    user, is_new = await sso_service.SSOService.find_or_create_user(
        provider=SimpleNamespace(
            name="oidc",
            allow_signup=True,
            require_approval=True,
            default_role_id="role-id",
        ),
        provider_user_id="provider-user-id",
        user_info={"email": "alice@example.com"},
    )

    assert user is new_user
    assert is_new is True
    user_create.assert_awaited_once_with(
        username="alice1",
        email="alice@example.com",
        hashed_password="",
        auth_source="oidc",
        is_active=False,
        approval_status="pending",
        email_verified=True,
        avatar_url=None,
        locale="zh",
    )
    assert manager.mock_calls == [
        call.user_create(
            username="alice1",
            email="alice@example.com",
            hashed_password="",
            auth_source="oidc",
            is_active=False,
            approval_status="pending",
            email_verified=True,
            avatar_url=None,
            locale="zh",
        ),
        call.add_role(role),
        call.assign_default_team(new_user),
        call.create_connection(
            user=new_user,
            provider=SimpleNamespace(
                name="oidc",
                allow_signup=True,
                require_approval=True,
                default_role_id="role-id",
            ),
            provider_user_id="provider-user-id",
            provider_username=None,
            provider_email="alice@example.com",
            provider_data={"email": "alice@example.com"},
        ),
    ]
