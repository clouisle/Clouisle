from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import jwt
import pytest

from app.api.v1.endpoints import conversations, login
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, value=None):
        self.value = value

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()

    async def first(self):
        return self.value

    async def values_list(self, *_args, **_kwargs):
        return self.value


@pytest.mark.asyncio
async def test_conversation_scope_helpers_cover_denied_and_role_paths():
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    team = SimpleNamespace(id=uuid4())

    with patch.object(conversations.Team, "filter", return_value=Query()):
        with pytest.raises(BusinessError) as exc_info:
            await conversations.check_team_access(team.id, user)
    assert exc_info.value.code == ResponseCode.TEAM_NOT_FOUND

    with (
        patch.object(conversations.Team, "filter", return_value=Query(team)),
        patch.object(conversations.TeamMember, "filter", return_value=Query()),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await conversations.check_team_access(team.id, user)
    assert exc_info.value.code == ResponseCode.NOT_TEAM_MEMBER

    membership = SimpleNamespace(role="admin")
    with patch.object(
        conversations.TeamMember, "filter", return_value=Query(membership)
    ):
        assert await conversations.has_conversation_team_admin_access(user, team.id)

    assert not await conversations.has_conversation_team_admin_access(user, None)
    user.roles = [
        SimpleNamespace(permissions=[SimpleNamespace(code="admin:dashboard:access")])
    ]
    assert conversations._has_global_dashboard_access(user)
    assert await conversations.has_conversation_team_admin_access(user, None)


@pytest.mark.asyncio
async def test_conversation_agent_scope_flattens_each_database_shape():
    user = SimpleNamespace(id=uuid4(), is_superuser=False, roles=[])
    team_id = uuid4()
    first_id, second_id = uuid4(), uuid4()

    with (
        patch.object(conversations, "check_team_access", AsyncMock()) as check_access,
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query([(first_id,), second_id]),
        ),
    ):
        assert await conversations.get_user_team_agent_ids(user, team_id) == [
            first_id,
            second_id,
        ]
    check_access.assert_awaited_once_with(team_id, user)

    user.is_superuser = True
    with patch.object(
        conversations.Agent, "all", return_value=Query([(first_id,), second_id])
    ):
        assert await conversations.get_user_team_agent_ids(user) == [
            first_id,
            second_id,
        ]

    user.is_superuser = False
    with (
        patch.object(
            conversations.TeamMember,
            "filter",
            return_value=Query([(team_id,), uuid4()]),
        ),
        patch.object(
            conversations.Agent,
            "filter",
            return_value=Query([first_id, second_id]),
        ),
    ):
        assert await conversations.get_user_team_agent_ids(user) == [
            first_id,
            second_id,
        ]


@pytest.mark.asyncio
async def test_login_rejects_disabled_password_and_locked_accounts():
    request = SimpleNamespace(headers={})

    async def disabled_setting(key, default=None):
        return {
            "sso_enabled": True,
            "sso_allow_password_login": False,
        }.get(key, default)

    with patch.object(login.SiteSetting, "get_value", disabled_setting):
        with pytest.raises(BusinessError) as exc_info:
            await login.login_access_token(request, "alice", "password")
    assert exc_info.value.code == ResponseCode.PASSWORD_LOGIN_DISABLED

    user = SimpleNamespace(id=uuid4())

    async def enabled_setting(key, default=None):
        return {
            "sso_enabled": False,
            "sso_allow_password_login": True,
            "enable_captcha": False,
        }.get(key, default)

    with (
        patch.object(login.SiteSetting, "get_value", enabled_setting),
        patch.object(login.User, "filter", return_value=Query(user)),
        patch.object(login, "check_account_locked", AsyncMock(return_value=(True, 9))),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await login.login_access_token(request, "alice@example.com", "password")
    assert exc_info.value.code == ResponseCode.ACCOUNT_LOCKED
    assert exc_info.value.data == {"remaining_seconds": 9}


@pytest.mark.asyncio
async def test_login_email_flows_preserve_enumeration_and_update_only_registration():
    background_tasks = SimpleNamespace(add_task=Mock())
    data = SimpleNamespace(
        email="alice@example.com", purpose="reset_password", code="123456"
    )
    user = SimpleNamespace(email_verified=False, save=AsyncMock())

    with (
        patch.object(login.SiteSetting, "get_value", AsyncMock(return_value=True)),
        patch.object(login, "check_email_cooldown", AsyncMock(return_value=(True, 0))),
        patch.object(login.User, "filter", return_value=Query()),
        patch.object(
            login,
            "generate_verification_code",
            AsyncMock(return_value=("123456", "token")),
        ) as generate,
        patch.object(login, "set_email_cooldown", AsyncMock()) as cooldown,
    ):
        result = await login.send_verification(
            data=data, background_tasks=background_tasks
        )
    assert result["code"] == ResponseCode.SUCCESS
    generate.assert_awaited_once_with(data.email, data.purpose)
    cooldown.assert_awaited_once_with(data.email, data.purpose, 60)
    background_tasks.add_task.assert_called_once()

    with (
        patch.object(login, "verify_code", AsyncMock(return_value=True)),
        patch.object(login.User, "filter", return_value=Query(user)),
    ):
        await login.verify_email_by_code(data=data)
    user.save.assert_not_awaited()

    token_user = SimpleNamespace(email_verified=False, save=AsyncMock())
    with (
        patch.object(
            login, "verify_token", AsyncMock(return_value=(data.email, "register"))
        ),
        patch.object(login.User, "filter", return_value=Query(token_user)),
    ):
        await login.verify_email_by_token("token")
    assert token_user.email_verified is True
    token_user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_reset_and_logout_reject_invalid_auth_without_database_leaks():
    reset_data = SimpleNamespace(
        token="bad-token", email=None, code=None, new_password="StrongPass123!"
    )
    with patch.object(login, "verify_token", AsyncMock(return_value=None)):
        with pytest.raises(BusinessError) as exc_info:
            await login.reset_password(request=object(), data=reset_data)
    assert exc_info.value.code == ResponseCode.VERIFICATION_CODE_INVALID

    reset_data.token = "wrong-purpose"
    with patch.object(
        login, "verify_token", AsyncMock(return_value=("alice@example.com", "register"))
    ):
        with pytest.raises(BusinessError) as exc_info:
            await login.reset_password(request=object(), data=reset_data)
    assert exc_info.value.code == ResponseCode.VERIFICATION_CODE_INVALID

    with (
        patch.object(login.jwt, "decode", side_effect=jwt.InvalidTokenError),
        patch.object(login.User, "get_or_none", AsyncMock()) as get_user,
    ):
        result = await login.logout(request=object(), token="invalid")
    assert result["code"] == ResponseCode.SUCCESS
    get_user.assert_not_awaited()
