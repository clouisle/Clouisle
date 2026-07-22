from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.api.v1.endpoints import conversations, login
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.verification import (
    ResendVerificationRequest,
    ResetPasswordRequest,
    SendVerificationRequest,
    VerifyCodeRequest,
)


class Query:
    def __init__(self, value=None, *, count=0, values=None, deleted=0):
        self.value = value
        self.count_value = count
        self.values_value = [] if values is None else values
        self.deleted = deleted
        self.update = AsyncMock()

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()

    def filter(self, *_args, **_kwargs):
        return self

    def select_related(self, *_args):
        return self

    def prefetch_related(self, *_args):
        return self

    def annotate(self, **_kwargs):
        return self

    def group_by(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, *_args):
        return self

    def limit(self, *_args):
        return self

    async def first(self):
        return self.value

    async def count(self):
        return self.count_value

    async def values(self, *_args):
        return self.values_value

    async def values_list(self, *_args, **_kwargs):
        return self.values_value

    async def delete(self):
        return self.deleted


class User:
    def __init__(self, **overrides):
        values = {
            "id": uuid4(),
            "username": "alice",
            "email": "alice@example.com",
            "locale": "en",
            "hashed_password": "hashed",
            "is_active": True,
            "approval_status": "approved",
            "totp_enabled": False,
            "email_verified": True,
            "is_superuser": False,
            "force_password_change": False,
            "roles": [],
            "last_login": None,
        }
        values.update(overrides)
        self.__dict__.update(values)
        self.save = AsyncMock()


def patch_user(monkeypatch, user):
    model = SimpleNamespace(
        filter=Mock(return_value=Query(user)),
        get_or_none=AsyncMock(return_value=user),
    )
    monkeypatch.setattr(login, "User", model)


def patch_settings(monkeypatch, **overrides):
    values = {
        "sso_enabled": False,
        "sso_allow_password_login": True,
        "enable_captcha": False,
        "require_totp": False,
        "email_verification": False,
        "session_timeout_days": 7,
        "single_session": False,
        "smtp_enabled": True,
    }
    values.update(overrides)
    monkeypatch.setattr(
        login.SiteSetting,
        "get_value",
        AsyncMock(side_effect=lambda key, default=None: values.get(key, default)),
    )


@pytest.mark.anyio
async def test_captcha_success_and_failure_arcs(monkeypatch):
    payload = SimpleNamespace(
        captcha_id="captcha",
        challenge="challenge",
        clicked_option=1,
        elapsed_ms=500,
        pointer=[],
    )
    monkeypatch.setattr(login, "create_captcha_proof", AsyncMock(return_value=None))
    with pytest.raises(BusinessError) as error:
        await login.complete_captcha_click(payload)
    assert error.value.code == ResponseCode.CAPTCHA_INVALID

    login.create_captcha_proof.return_value = "proof"
    result = await login.complete_captcha_click(payload)
    assert result["data"].captcha_token == "proof"

    with pytest.raises(BusinessError) as error:
        await login.validate_human_verification(None, None)
    assert error.value.code == ResponseCode.CAPTCHA_REQUIRED

    monkeypatch.setattr(login, "verify_captcha", AsyncMock(return_value=False))
    with pytest.raises(BusinessError) as error:
        await login.validate_human_verification("captcha", "proof")
    assert error.value.code == ResponseCode.CAPTCHA_INVALID

    login.verify_captcha.return_value = True
    await login.validate_human_verification("captcha", "proof")


@pytest.mark.anyio
async def test_login_enabled_captcha_reaches_plain_success(monkeypatch):
    user = User()
    patch_user(monkeypatch, user)
    patch_settings(monkeypatch, enable_captcha=True)
    monkeypatch.setattr(login, "validate_human_verification", AsyncMock())
    monkeypatch.setattr(
        login, "check_account_locked", AsyncMock(return_value=(False, 0))
    )
    monkeypatch.setattr(login.security, "verify_password", Mock(return_value=True))
    monkeypatch.setattr(login, "reset_login_attempts", AsyncMock())
    monkeypatch.setattr(
        login, "check_login_anomaly", AsyncMock(return_value=(False, {}))
    )
    monkeypatch.setattr(login, "record_login", AsyncMock())
    monkeypatch.setattr(login.security, "create_access_token", Mock(return_value="jwt"))
    monkeypatch.setattr(login.AuditLogService, "get_client_ip", Mock(return_value="ip"))
    monkeypatch.setattr(login.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        login.PasswordExpirationService, "is_user_exempt", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "is_password_expired",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "should_warn_user",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        login.PasswordExpirationService,
        "days_until_expiration",
        AsyncMock(return_value=None),
    )
    request = SimpleNamespace(headers={})

    result = await login.login_access_token(
        request, "alice", "password", "captcha", "proof"
    )

    assert result["data"]["access_token"] == "jwt"
    login.validate_human_verification.assert_awaited_once_with("captcha", "proof")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (None, ResponseCode.NOT_FOUND),
        (User(email_verified=True), ResponseCode.VALIDATION_ERROR),
    ],
)
async def test_send_verification_register_errors(monkeypatch, user, expected):
    patch_settings(monkeypatch)
    patch_user(monkeypatch, user)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )

    with pytest.raises(BusinessError) as error:
        await login.send_verification(
            data=SendVerificationRequest(email="alice@example.com"),
            background_tasks=BackgroundTasks(),
        )
    assert error.value.code == expected


@pytest.mark.anyio
async def test_email_verification_invalid_and_nonregistration_arcs(monkeypatch):
    user = User(email_verified=False)
    patch_user(monkeypatch, user)
    monkeypatch.setattr(login, "verify_code", AsyncMock(return_value=False))
    with pytest.raises(BusinessError) as error:
        await login.verify_email_by_code(
            data=VerifyCodeRequest(email=user.email, code="123456")
        )
    assert error.value.code == ResponseCode.VERIFICATION_CODE_INVALID

    monkeypatch.setattr(login, "verify_token", AsyncMock(return_value=None))
    with pytest.raises(BusinessError) as error:
        await login.verify_email_by_token("expired")
    assert error.value.code == ResponseCode.VERIFICATION_CODE_EXPIRED

    login.verify_token.return_value = (user.email, "reset_password")
    result = await login.verify_email_by_token("valid")
    assert result["data"].verified is True
    user.save.assert_not_awaited()


@pytest.mark.anyio
async def test_resend_verification_remaining_arcs(monkeypatch):
    data = ResendVerificationRequest(email="alice@example.com")
    patch_settings(monkeypatch, smtp_enabled=False)
    with pytest.raises(BusinessError) as error:
        await login.resend_verification(data=data, background_tasks=BackgroundTasks())
    assert error.value.code == ResponseCode.EMAIL_SEND_FAILED

    patch_settings(monkeypatch)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )
    patch_user(monkeypatch, None)
    result = await login.resend_verification(
        data=data, background_tasks=BackgroundTasks()
    )
    assert result["code"] == ResponseCode.SUCCESS

    verified = User(email_verified=True)
    patch_user(monkeypatch, verified)
    with pytest.raises(BusinessError) as error:
        await login.resend_verification(data=data, background_tasks=BackgroundTasks())
    assert error.value.code == ResponseCode.VALIDATION_ERROR

    unverified = User(email_verified=False)
    patch_user(monkeypatch, unverified)
    monkeypatch.setattr(
        login,
        "generate_verification_code",
        AsyncMock(return_value=("123456", "token")),
    )
    monkeypatch.setattr(login, "set_email_cooldown", AsyncMock())
    tasks = BackgroundTasks()
    result = await login.resend_verification(data=data, background_tasks=tasks)
    assert result["code"] == ResponseCode.SUCCESS
    assert tasks.tasks[0].args[-1] == "register"


@pytest.mark.anyio
async def test_forgot_password_cooldown_and_existing_user(monkeypatch):
    data = ResetPasswordRequest(email="alice@example.com")
    patch_settings(monkeypatch)
    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(False, 9))
    )
    with pytest.raises(BusinessError) as error:
        await login.forgot_password(data=data, background_tasks=BackgroundTasks())
    assert error.value.code == ResponseCode.EMAIL_SEND_TOO_FREQUENT

    monkeypatch.setattr(
        login, "check_email_cooldown", AsyncMock(return_value=(True, 0))
    )
    patch_user(monkeypatch, User())
    monkeypatch.setattr(
        login,
        "generate_verification_code",
        AsyncMock(return_value=("123456", "token")),
    )
    monkeypatch.setattr(login, "set_email_cooldown", AsyncMock())
    tasks = BackgroundTasks()
    result = await login.forgot_password(data=data, background_tasks=tasks)
    assert result["code"] == ResponseCode.SUCCESS
    assert tasks.tasks[0].args[-1] == "reset_password"


@pytest.mark.anyio
async def test_conversation_admin_fallthrough_and_stats_arcs(monkeypatch):
    actor = User(is_superuser=True)
    assert conversations._has_global_dashboard_access(actor)

    agent_id = uuid4()
    list_query = Query([], count=0)
    monkeypatch.setattr(
        conversations,
        "has_conversation_team_admin_access",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[agent_id])
    )
    monkeypatch.setattr(
        conversations.Conversation, "filter", Mock(return_value=list_query)
    )
    result = await conversations.list_all_conversations(
        team_id=None,
        agent_id=None,
        user_id=None,
        search=None,
        untitled_only=False,
        page=1,
        page_size=20,
        current_user=actor,
    )
    assert result["data"]["total"] == 0

    conversation_query = Query(count=2, values=[uuid4()])
    stats_query = Query(values=[{"agent_id": agent_id, "count": 2}])
    agent_query = Query(values=[{"id": agent_id, "name": "Agent", "icon": None}])
    monkeypatch.setattr(
        conversations.Conversation,
        "filter",
        Mock(side_effect=[conversation_query, stats_query]),
    )
    monkeypatch.setattr(
        conversations.Message, "filter", Mock(return_value=Query(count=3))
    )
    monkeypatch.setattr(conversations.Agent, "filter", Mock(return_value=agent_query))
    result = await conversations.get_conversation_stats(None, actor)
    assert result["data"]["total_conversations"] == 2
    assert result["data"]["total_messages"] == 3


@pytest.mark.anyio
async def test_conversation_admin_none_agent_skips_scope_checks(monkeypatch):
    actor = User(is_superuser=False)
    actor.roles = [
        SimpleNamespace(permissions=[SimpleNamespace(code="admin:dashboard:access")])
    ]
    item = SimpleNamespace(
        id=uuid4(),
        agent_id=None,
        user_id=uuid4(),
        message_count=0,
        title="Title",
        delete=AsyncMock(),
    )
    scope = AsyncMock(return_value=[])
    monkeypatch.setattr(conversations, "get_user_team_agent_ids", scope)
    monkeypatch.setattr(
        conversations.Conversation, "filter", Mock(return_value=Query(item))
    )
    monkeypatch.setattr(conversations.Agent, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(conversations.AuditLogService, "log", AsyncMock())

    result = await conversations.delete_conversation_admin(
        item.id, SimpleNamespace(), actor
    )

    assert result["data"]["id"] == str(item.id)
    scope.assert_not_awaited()


@pytest.mark.anyio
async def test_batch_admin_none_agent_continues_and_deletes(monkeypatch):
    actor = User(is_superuser=False)
    actor.roles = [SimpleNamespace(permissions=[SimpleNamespace(code="*")])]
    items = [
        SimpleNamespace(id=uuid4(), agent_id=None, user_id=uuid4(), message_count=0),
        SimpleNamespace(id=uuid4(), agent_id=None, user_id=uuid4(), message_count=0),
    ]
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        conversations.Conversation,
        "filter",
        Mock(side_effect=[Query(items), Query(deleted=2)]),
    )
    monkeypatch.setattr(conversations.Agent, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(conversations.AuditLogService, "log", AsyncMock())

    result = await conversations.batch_delete_conversations(
        ids=[item.id for item in items],
        request=SimpleNamespace(),
        current_user=actor,
    )

    assert result["data"]["deleted_count"] == 2
