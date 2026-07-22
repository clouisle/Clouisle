from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import users
from app.schemas.response import BusinessError, ResponseCode


class AwaitableQuery:
    def __init__(self, value):
        self.value = value
        self.prefetch_calls = []

    def prefetch_related(self, *relations):
        self.prefetch_calls.append(relations)
        return self

    def __await__(self):
        async def result():
            return self.value

        return result().__await__()


class FirstQuery:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/users/me",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )


def user(**overrides):
    values = {
        "id": "user-id",
        "username": "alice",
        "email": "alice@example.com",
        "is_active": True,
        "is_superuser": False,
        "email_verified": True,
        "avatar_url": None,
        "locale": "en",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "last_login": None,
        "auth_source": "local",
        "external_id": None,
        "hashed_password": "hashed",
        "force_password_change": False,
        "password_changed_at": None,
    }
    values.update(overrides)
    value = SimpleNamespace(**values)
    value.save = AsyncMock()
    value.delete = AsyncMock()
    value.update_from_dict = AsyncMock()
    return value


def assert_error(exc_info, code):
    assert exc_info.value.code == code


@pytest.mark.asyncio
async def test_serialize_user_uses_prefetched_roles_and_sso_connections(monkeypatch):
    permission = SimpleNamespace(
        id="permission-id", scope="user", code="read", description="Read"
    )
    role = SimpleNamespace(
        id="role-id",
        name="member",
        description="Member",
        is_system_role=True,
        permissions=[permission],
    )
    current_user = user()
    current_user._fetched_relations = {"roles"}
    current_user.roles = [role]
    provider = SimpleNamespace(
        id=uuid4(),
        name="oidc",
        display_name="OIDC",
        icon_url=None,
    )
    connection = SimpleNamespace(
        id=uuid4(),
        provider=provider,
        provider_user_id="external-user",
        provider_username="external-alice",
        provider_email="external@example.com",
        first_login=current_user.created_at,
        last_login=current_user.created_at,
    )
    connection_query = AwaitableQuery([connection])
    connection_model = Mock()
    connection_model.filter.return_value = connection_query
    monkeypatch.setattr(
        "app.models.user_sso_connection.UserSSOConnection", connection_model
    )

    result = await users.serialize_user_with_sso(current_user)

    assert result["roles"] == [
        {
            "id": "role-id",
            "name": "member",
            "description": "Member",
            "is_system_role": True,
            "permissions": [
                {
                    "id": "permission-id",
                    "scope": "user",
                    "code": "read",
                    "description": "Read",
                }
            ],
        }
    ]
    assert result["sso_connections"][0]["provider_name"] == "oidc"
    connection_model.filter.assert_called_once_with(user=current_user)
    assert connection_query.prefetch_calls == [("provider",)]


@pytest.mark.asyncio
async def test_serialize_user_fetches_roles_and_defaults_locale(monkeypatch):
    current_user = user()
    del current_user.locale
    role_query = AwaitableQuery([])
    current_user.roles = SimpleNamespace(all=Mock(return_value=role_query))
    connection_model = Mock()
    connection_model.filter.return_value = AwaitableQuery([])
    monkeypatch.setattr(
        "app.models.user_sso_connection.UserSSOConnection", connection_model
    )

    result = await users.serialize_user_with_sso(current_user)

    assert result["locale"] == "en"
    assert result["roles"] == []
    assert role_query.prefetch_calls == [("permissions",)]


@pytest.mark.asyncio
async def test_read_user_me_prefetches_and_serializes(monkeypatch):
    current_user = user()
    loaded_user = user(username="loaded")
    query = AwaitableQuery(loaded_user)
    model = Mock()
    model.get.return_value = query
    serialize = AsyncMock(return_value={"username": "loaded"})
    monkeypatch.setattr(users, "User", model)
    monkeypatch.setattr(users, "serialize_user_with_sso", serialize)

    result = await users.read_user_me(current_user=current_user)

    assert result["data"] == {"username": "loaded"}
    model.get.assert_called_once_with(id="user-id")
    assert query.prefetch_calls == [("roles__permissions", "sso_connections__provider")]
    serialize.assert_awaited_once_with(loaded_user)


@pytest.mark.parametrize(
    ("data", "existing", "expected_code"),
    [
        (
            users.UpdateProfileRequest(username="taken"),
            object(),
            ResponseCode.USERNAME_EXISTS,
        ),
        (
            users.UpdateProfileRequest(email="taken@example.com"),
            object(),
            ResponseCode.EMAIL_EXISTS,
        ),
    ],
)
@pytest.mark.asyncio
async def test_update_user_me_rejects_duplicate_identity(
    monkeypatch, data, existing, expected_code
):
    current_user = user()
    model = Mock()
    model.filter.return_value = FirstQuery(existing)
    monkeypatch.setattr(users, "User", model)

    with pytest.raises(BusinessError) as exc_info:
        await users.update_user_me(
            request=request(), data=data, current_user=current_user
        )

    assert_error(exc_info, expected_code)
    current_user.update_from_dict.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_me_updates_profile_and_audits_fields(monkeypatch):
    current_user = user()
    loaded_user = user(username="bob")
    query = AwaitableQuery(loaded_user)
    model = Mock()
    model.filter.return_value = FirstQuery(None)
    model.get.return_value = query
    audit = AsyncMock()
    serialize = AsyncMock(return_value={"username": "bob"})
    monkeypatch.setattr(users, "User", model)
    monkeypatch.setattr(users.AuditLogService, "log", audit)
    monkeypatch.setattr(users, "serialize_user_with_sso", serialize)

    result = await users.update_user_me(
        request=request(),
        data=users.UpdateProfileRequest(username="bob", locale="zh"),
        current_user=current_user,
    )

    current_user.update_from_dict.assert_awaited_once_with(
        {"username": "bob", "locale": "zh"}
    )
    current_user.save.assert_awaited_once()
    assert query.prefetch_calls == [("roles__permissions",)]
    assert audit.await_args.kwargs["metadata"] == {
        "fields_updated": ["username", "locale"]
    }
    assert result["data"] == {"username": "bob"}


@pytest.mark.parametrize(
    ("verified", "can_change", "valid", "expected_code"),
    [
        (False, True, True, ResponseCode.INVALID_CREDENTIALS),
        (True, False, True, ResponseCode.PASSWORD_MIN_AGE_NOT_MET),
        (True, True, False, ResponseCode.VALIDATION_ERROR),
    ],
)
@pytest.mark.asyncio
async def test_change_password_rejects_invalid_inputs(
    monkeypatch, verified, can_change, valid, expected_code
):
    current_user = user()
    monkeypatch.setattr(users.security, "verify_password", Mock(return_value=verified))
    can_change_password = AsyncMock(return_value=(can_change, 3))
    monkeypatch.setattr(
        users.PasswordExpirationService, "can_change_password", can_change_password
    )
    validate = AsyncMock(return_value=(valid, ["password_too_short"]))
    monkeypatch.setattr(users, "validate_password", validate)
    monkeypatch.setattr(
        users,
        "translate_password_validation_errors",
        Mock(return_value=["Too short"]),
    )

    with pytest.raises(BusinessError) as exc_info:
        await users.change_password(
            request=request(),
            data=users.ChangePasswordRequest(
                current_password="old-password", new_password="new-password"
            ),
            current_user=current_user,
        )

    assert_error(exc_info, expected_code)
    if expected_code == ResponseCode.PASSWORD_MIN_AGE_NOT_MET:
        assert exc_info.value.kwargs == {"days": 3}
    if expected_code == ResponseCode.VALIDATION_ERROR:
        assert exc_info.value.data == {"errors": {"new_password": ["Too short"]}}


@pytest.mark.parametrize("force_password_change", [False, True])
@pytest.mark.asyncio
async def test_change_password_updates_expiration_audit_and_notification(
    monkeypatch, force_password_change
):
    current_user = user(force_password_change=force_password_change, locale="zh")
    monkeypatch.setattr(users.security, "verify_password", Mock(return_value=True))
    monkeypatch.setattr(
        users.PasswordExpirationService,
        "can_change_password",
        AsyncMock(return_value=(True, 0)),
    )
    monkeypatch.setattr(users, "validate_password", AsyncMock(return_value=(True, [])))
    monkeypatch.setattr(
        users.security, "get_password_hash", Mock(return_value="new-hash")
    )
    update_password = AsyncMock()
    monkeypatch.setattr(
        users.PasswordExpirationService,
        "update_password_with_expiration",
        update_password,
    )
    audit = AsyncMock()
    notify = AsyncMock()
    translate = Mock(side_effect=lambda key, lang: f"{key}:{lang}")
    monkeypatch.setattr(users.AuditLogService, "log", audit)
    monkeypatch.setattr(users.AutoNotificationService, "send_to_user", notify)
    monkeypatch.setattr(users, "t", translate)

    result = await users.change_password(
        request=request(),
        data=users.ChangePasswordRequest(
            current_password="old-password", new_password="new-password"
        ),
        current_user=current_user,
    )

    update_password.assert_awaited_once_with(current_user, "new-hash")
    assert current_user.force_password_change is False
    assert current_user.save.await_count == int(force_password_change)
    audit.assert_awaited_once()
    notify.assert_awaited_once_with(
        notification_type=users.AutoNotificationType.SECURITY_PASSWORD_CHANGED,
        user_id="user-id",
        title="notify_password_changed_title:zh",
        content="notify_password_changed_content:zh",
        level=users.NotificationLevel.HIGH,
    )
    assert result["code"] == ResponseCode.SUCCESS


@pytest.mark.parametrize("with_dates", [False, True])
@pytest.mark.asyncio
async def test_get_password_status_serializes_optional_dates(monkeypatch, with_dates):
    changed_at = datetime(2026, 1, 2, tzinfo=timezone.utc) if with_dates else None
    expires_at = datetime(2026, 2, 2, tzinfo=timezone.utc) if with_dates else None
    current_user = user(
        password_changed_at=changed_at, force_password_change=with_dates
    )
    monkeypatch.setattr(
        users.PasswordExpirationService, "is_user_exempt", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        users.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=with_dates),
    )
    monkeypatch.setattr(
        users.PasswordExpirationService,
        "days_until_expiration",
        AsyncMock(return_value=10 if with_dates else None),
    )
    monkeypatch.setattr(
        users.PasswordExpirationService,
        "calculate_expiration_date",
        AsyncMock(return_value=expires_at),
    )

    result = await users.get_password_status(current_user=current_user)
    status = result["data"]

    assert status.password_changed_at == (
        changed_at.isoformat() if changed_at else None
    )
    assert status.password_expires_at == (
        expires_at.isoformat() if expires_at else None
    )
    assert status.is_expired is with_dates
    assert status.force_change_required is with_dates


@pytest.mark.parametrize(
    ("allow_deletion", "is_superuser", "password_valid", "expected_code"),
    [
        (False, False, True, ResponseCode.PERMISSION_DENIED),
        (True, True, True, ResponseCode.PERMISSION_DENIED),
        (True, False, False, ResponseCode.INVALID_CREDENTIALS),
    ],
)
@pytest.mark.asyncio
async def test_delete_account_rejects_unauthorized_requests(
    monkeypatch, allow_deletion, is_superuser, password_valid, expected_code
):
    current_user = user(is_superuser=is_superuser)
    monkeypatch.setattr(
        users.SiteSetting, "get_value", AsyncMock(return_value=allow_deletion)
    )
    verify = Mock(return_value=password_valid)
    monkeypatch.setattr(users.security, "verify_password", verify)

    with pytest.raises(BusinessError) as exc_info:
        await users.delete_account(
            request=request(),
            data=users.DeleteAccountRequest(password="password"),
            current_user=current_user,
        )

    assert_error(exc_info, expected_code)
    current_user.delete.assert_not_awaited()
    if not allow_deletion or is_superuser:
        verify.assert_not_called()


@pytest.mark.asyncio
async def test_delete_account_audits_before_deleting(monkeypatch):
    current_user = user()
    monkeypatch.setattr(users.SiteSetting, "get_value", AsyncMock(return_value=True))
    monkeypatch.setattr(users.security, "verify_password", Mock(return_value=True))
    events = []
    audit = AsyncMock(side_effect=lambda **_kwargs: events.append("audit"))
    current_user.delete = AsyncMock(side_effect=lambda: events.append("delete"))
    monkeypatch.setattr(users.AuditLogService, "log", audit)

    result = await users.delete_account(
        request=request(),
        data=users.DeleteAccountRequest(password="password"),
        current_user=current_user,
    )

    assert events == ["audit", "delete"]
    assert audit.await_args.kwargs["metadata"] == {"self_deletion": True}
    assert result["code"] == ResponseCode.SUCCESS
