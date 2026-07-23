from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import conversations, login
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.verification import (
    ResetPasswordConfirmRequest,
    SendVerificationRequest,
)


class Query:
    def __init__(self, *, first=None, rows=None, count=0, values=None):
        self.first_value = first
        self.rows = rows or []
        self.count_value = count
        self.values_value = values or []
        self.filters = []

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def prefetch_related(self, *_args):
        return self

    def annotate(self, **_kwargs):
        return self

    def group_by(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.count_value

    async def values(self, *_args):
        return self.values_value

    async def values_list(self, *_args, **_kwargs):
        return self.values_value

    async def all(self):
        return self.rows


class BackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, *args):
        self.tasks.append(args)


def user(**overrides):
    values = {
        "id": uuid4(),
        "username": "alice",
        "email": "alice@example.com",
        "locale": "en",
        "is_superuser": False,
        "is_active": True,
        "approval_status": "approved",
        "hashed_password": "hash",
        "totp_enabled": False,
        "email_verified": True,
        "force_password_change": False,
        "last_login": None,
        "save": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def request():
    return SimpleNamespace(headers={"user-agent": "pytest"})


@pytest.mark.anyio
async def test_conversation_stats_and_trends_cover_empty_and_admin_user_breakdowns():
    current_user = user()
    agent_id = uuid4()

    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=False),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
        ),
    ):
        stats = await conversations.get_conversation_stats(None, current_user)
        trends = await conversations.get_conversation_trends(
            None, "bad-period", current_user
        )

    assert stats["data"] == {
        "total_conversations": 0,
        "total_messages": 0,
        "conversations_by_agent": [],
    }
    assert trends["data"]["period"] == "bad-period"
    assert len(trends["data"]["data"]) == 7
    assert {point["messages"] for point in trends["data"]["data"]} == {0}

    conversation_id = uuid4()
    conv_query = Query(
        rows=[SimpleNamespace(id=conversation_id, user_id=current_user.id)],
        values=[conversation_id],
    )
    message_query = Query(
        rows=[
            SimpleNamespace(
                conversation=SimpleNamespace(user_id=current_user.id),
                token_usage={"prompt": 2, "completion": 3},
            )
        ],
        values=[{"token_usage": {"prompt": 2, "completion": 3}}],
    )
    team_member = SimpleNamespace(
        user=SimpleNamespace(id=current_user.id, username="alice")
    )

    with (
        patch.object(
            conversations,
            "has_conversation_team_admin_access",
            AsyncMock(return_value=True),
        ),
        patch.object(
            conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
        ),
        patch.object(
            conversations.TeamMember, "filter", return_value=Query(rows=[team_member])
        ),
        patch.object(conversations.Conversation, "filter", return_value=conv_query),
        patch.object(conversations.Message, "filter", return_value=message_query),
    ):
        trends = await conversations.get_conversation_trends(
            uuid4(), "30d", current_user
        )

    user_buckets = [
        point["users"][str(current_user.id)] for point in trends["data"]["data"]
    ]
    assert len(trends["data"]["data"]) == 30
    assert any(bucket["conversations"] == 1 for bucket in user_buckets)
    assert any(bucket["tokens"] == 5 for bucket in user_buckets)


@pytest.mark.anyio
async def test_login_access_token_blocks_sso_only_and_returns_totp_setup():
    with patch.object(
        login.SiteSetting, "get_value", AsyncMock(side_effect=[True, False])
    ):
        with pytest.raises(BusinessError) as exc:
            await login.login_access_token(request(), "alice", "secret")
    assert exc.value.code == ResponseCode.PASSWORD_LOGIN_DISABLED

    current_user = user(totp_enabled=False)
    settings = AsyncMock(side_effect=[False, True, False, True])
    with (
        patch.object(login.SiteSetting, "get_value", settings),
        patch.object(login.User, "filter", return_value=Query(first=current_user)),
        patch.object(login, "check_account_locked", AsyncMock(return_value=(False, 0))),
        patch.object(login.security, "verify_password", Mock(return_value=True)),
        patch.object(
            login.security, "create_access_token", Mock(return_value="setup-token")
        ),
    ):
        response = await login.login_access_token(request(), "alice", "secret")

    assert response["data"] == {
        "requires_totp_setup": True,
        "temp_token": "setup-token",
    }
    assert response["code"] == ResponseCode.SUCCESS


@pytest.mark.anyio
async def test_login_edges_for_disabled_captcha_logout_email_and_reset_token():
    with patch.object(login, "verify_captcha", AsyncMock(return_value=False)):
        with pytest.raises(BusinessError) as exc:
            await login.validate_human_verification("captcha", "token")
    assert exc.value.code == ResponseCode.CAPTCHA_INVALID

    with patch.object(login.jwt, "decode", Mock(side_effect=login.jwt.PyJWTError)):
        response = await login.logout(request(), token="bad-token")
    assert response["code"] == ResponseCode.SUCCESS

    with patch.object(login.SiteSetting, "get_value", AsyncMock(return_value=False)):
        with pytest.raises(BusinessError) as exc:
            await login.send_verification(
                data=SendVerificationRequest(email="a@example.com", purpose="register"),
                background_tasks=BackgroundTasks(),
            )
    assert exc.value.code == ResponseCode.EMAIL_SEND_FAILED

    data = ResetPasswordConfirmRequest(token="token", new_password="Newpass123!")
    with patch.object(
        login, "verify_token", AsyncMock(return_value=("a@example.com", "register"))
    ):
        with pytest.raises(BusinessError) as exc:
            await login.reset_password(request=request(), data=data)
    assert exc.value.code == ResponseCode.VERIFICATION_CODE_INVALID
