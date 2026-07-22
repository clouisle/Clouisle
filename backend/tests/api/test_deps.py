from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import jwt
import pytest

from app.api import deps
from app.schemas.response import BusinessError


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def user(**overrides):
    values = {
        "id": uuid4(),
        "is_active": True,
        "is_superuser": False,
        "approval_status": "approved",
        "locale": None,
        "roles": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_auth_selection_and_optional_auth(monkeypatch):
    current_user = user(locale="zh")
    api_key = SimpleNamespace()
    authenticate_jwt = AsyncMock(return_value=current_user)
    authenticate_api_key = AsyncMock(return_value=(current_user, api_key))
    set_language = Mock()
    monkeypatch.setattr(deps, "_authenticate_jwt", authenticate_jwt)
    monkeypatch.setattr(deps, "_authenticate_api_key", authenticate_api_key)
    monkeypatch.setattr(deps, "set_language", set_language)

    assert await deps.get_current_user("jwt") is current_user
    authenticate_jwt.assert_awaited_with("jwt")

    assert await deps.get_current_user_or_api_key(None, "Bearer clou_key") == (
        current_user,
        api_key,
    )
    authenticate_api_key.assert_awaited_once_with("clou_key")
    set_language.assert_called_once_with("zh")

    authenticate_jwt.reset_mock()
    current_user.locale = None
    assert await deps.get_current_user_or_api_key("jwt", None) == (current_user, None)
    authenticate_jwt.assert_awaited_once_with("jwt")

    with pytest.raises(BusinessError) as exc:
        await deps.get_current_user_or_api_key(None, "Basic ignored")
    assert exc.value.msg_key == "not_authenticated"

    assert await deps.get_current_user_or_api_key_optional(None, None) is None
    assert (
        await deps.get_current_user_or_api_key_optional(None, "Basic ignored") is None
    )
    authenticate_api_key.side_effect = BusinessError()
    assert (
        await deps.get_current_user_or_api_key_optional(None, "Bearer clou_bad") is None
    )
    authenticate_jwt.side_effect = BusinessError()
    assert await deps.get_current_user_or_api_key_optional("bad-jwt", None) is None

    authenticate_jwt.side_effect = None
    authenticate_jwt.return_value = current_user
    assert await deps.get_current_user_optional("jwt", None) is current_user
    authenticate_jwt.side_effect = BusinessError()
    assert await deps.get_current_user_optional("bad-jwt", None) is None


@pytest.mark.asyncio
async def test_authenticate_api_key_errors_and_success(monkeypatch):
    now = deps.now_utc()
    active_user = user()
    key = SimpleNamespace(
        key_hash="hash",
        expires_at=None,
        user=active_user,
        user_id=active_user.id,
        last_used_at=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(deps.APIKey, "filter", Mock(return_value=Query([key])))
    verify_key = Mock(return_value=False)
    monkeypatch.setattr(deps.APIKey, "verify_key", verify_key)

    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_api_key("clou_invalid")
    assert exc.value.msg_key == "invalid_api_key"

    verify_key.return_value = True
    key.expires_at = now - timedelta(seconds=1)
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_api_key("clou_expired")
    assert exc.value.msg_key == "api_key_expired"

    key.expires_at = None
    key.user = None
    pending_user = user(is_active=False, approval_status="pending")
    monkeypatch.setattr(deps.User, "filter", Mock(return_value=Query(pending_user)))
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_api_key("clou_pending")
    assert exc.value.msg_key == "pending_approval_user"

    monkeypatch.setattr(deps.User, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_api_key("clou_missing_user")
    assert exc.value.msg_key == "inactive_user"

    key.user = active_user
    result_user, result_key = await deps._authenticate_api_key("clou_valid")
    assert (result_user, result_key) == (active_user, key)
    assert key.last_used_at >= now
    key.save.assert_awaited_once_with(update_fields=["last_used_at"])


@pytest.mark.asyncio
async def test_authenticate_jwt_errors_and_sessions(monkeypatch):
    monkeypatch.setattr(deps, "is_token_blacklisted", AsyncMock(return_value=True))
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_jwt("revoked")
    assert exc.value.msg_key == "token_revoked"

    monkeypatch.setattr(deps, "is_token_blacklisted", AsyncMock(return_value=False))
    monkeypatch.setattr(deps.jwt, "decode", Mock(side_effect=jwt.PyJWTError()))
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_jwt("invalid")
    assert exc.value.msg_key == "could_not_validate_credentials"

    decode = Mock(return_value={"sub": None})
    monkeypatch.setattr(deps.jwt, "decode", decode)
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_jwt("no-sub")
    assert exc.value.msg_key == "user_not_found"

    decode.return_value = {"sub": str(uuid4())}
    monkeypatch.setattr(deps.User, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_jwt("missing-user")
    assert exc.value.msg_key == "user_not_found"

    current_user = user()
    monkeypatch.setattr(deps.User, "filter", Mock(return_value=Query(current_user)))
    from app.core import redis
    from app.models.site_setting import SiteSetting

    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=True))
    get_session = AsyncMock(return_value="new-token")
    monkeypatch.setattr(redis, "get_user_session", get_session)
    with pytest.raises(BusinessError) as exc:
        await deps._authenticate_jwt("old-token")
    assert exc.value.msg_key == "session_expired_new_login"

    get_session.return_value = "current-token"
    assert await deps._authenticate_jwt("current-token") is current_user
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=False))
    assert await deps._authenticate_jwt("any-token") is current_user


@pytest.mark.asyncio
async def test_active_user_and_permission_checks(monkeypatch):
    set_language = Mock()
    monkeypatch.setattr(deps, "set_language", set_language)
    pending = user(is_active=False, approval_status="pending")
    with pytest.raises(BusinessError) as exc:
        await deps.get_current_active_user(pending)
    assert exc.value.msg_key == "pending_approval_user"

    inactive = user(is_active=False)
    with pytest.raises(BusinessError) as exc:
        await deps.get_current_active_user(inactive)
    assert exc.value.msg_key == "inactive_user"

    active = user(locale="en")
    assert await deps.get_current_active_user(active) is active
    set_language.assert_called_once_with("en")
    assert await deps.get_current_active_user(user())

    with pytest.raises(BusinessError) as exc:
        await deps.get_current_active_superuser(active)
    assert exc.value.msg_key == "insufficient_privileges"
    admin = user(is_superuser=True)
    assert await deps.get_current_active_superuser(admin) is admin

    permission = SimpleNamespace(code="admin:read")
    wildcard = SimpleNamespace(code="*")

    def role(permissions):
        return SimpleNamespace(permissions=permissions)

    assert deps.user_has_global_permission(
        user(roles=[role([permission])]), "admin:read"
    )
    assert deps.user_has_global_permission(user(roles=[role([wildcard])]), "anything")
    assert not deps.user_has_global_permission(
        user(roles=[role([SimpleNamespace(code="other"), permission])]), "missing"
    )
    assert not deps.user_has_global_permission(user(roles=[role([])]), "missing")

    assignment = SimpleNamespace(role=role([permission]))
    monkeypatch.setattr(
        deps.ScopedRoleAssignment, "filter", Mock(return_value=Query([assignment]))
    )
    scope_id = uuid4()
    assert await deps.user_has_scoped_permission(active, "admin:read", "team", scope_id)
    assert not await deps.user_has_scoped_permission(
        active, "missing", "team", scope_id
    )

    await deps.check_scoped_permission(admin, "anything", "team", scope_id)
    global_user = user(roles=[role([permission])])
    await deps.check_scoped_permission(global_user, "admin:read", "team", scope_id)
    monkeypatch.setattr(
        deps, "user_has_scoped_permission", AsyncMock(return_value=True)
    )
    await deps.check_scoped_permission(active, "team:read", "team", scope_id)
    with pytest.raises(BusinessError) as exc:
        await deps.check_scoped_permission(active, "admin:write", "team", scope_id)
    assert exc.value.kwargs["permission"] == "admin:write"

    checker = deps.PermissionChecker("admin:read")
    assert await checker(admin) is admin
    assert await checker(global_user) is global_user
    with pytest.raises(BusinessError):
        await checker(active)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("resource", "checker", "error_key"),
    [
        ("agents", deps.check_api_key_agent_access, "api_key_no_agent_access"),
        ("workflows", deps.check_api_key_workflow_access, "api_key_no_workflow_access"),
    ],
)
async def test_api_key_resource_access(resource, checker, error_key):
    allowed_id = uuid4()
    relation = SimpleNamespace(all=AsyncMock(return_value=[]))
    api_key = SimpleNamespace(**{resource: relation})

    await checker(None, allowed_id)
    await checker(api_key, allowed_id)

    relation.all.return_value = [SimpleNamespace(id=allowed_id)]
    await checker(api_key, allowed_id)

    with pytest.raises(BusinessError) as exc:
        await checker(api_key, uuid4())
    assert exc.value.msg_key == error_key
