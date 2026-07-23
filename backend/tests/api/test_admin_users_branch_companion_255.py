from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import users as endpoint
from app.schemas.response import BusinessError


def _query(*, first=None, all_rows=None):
    query = SimpleNamespace()
    query.first = AsyncMock(return_value=first)
    query.all = AsyncMock(return_value=all_rows)
    return query


def _patch_user_filter(monkeypatch, query):
    monkeypatch.setattr(endpoint.User, "filter", lambda **_kwargs: query)


@pytest.mark.parametrize(
    ("active", "approval", "expected"),
    [
        (False, "pending", "pending"),
        (True, "pending", "active"),
        (False, "approved", "inactive"),
    ],
)
def test_issue255_get_user_status_branches(active, approval, expected):
    assert (
        endpoint.get_user_status(
            SimpleNamespace(is_active=active, approval_status=approval)
        )
        == expected
    )


@pytest.mark.asyncio
async def test_issue255_send_email_requires_smtp(monkeypatch):
    monkeypatch.setattr(
        endpoint.SiteSetting, "get_value", AsyncMock(return_value=False)
    )

    with pytest.raises(BusinessError) as caught:
        await endpoint.send_email_to_users(
            data=endpoint.SendEmailRequest(
                subject="s", content="c", user_ids=[uuid4()]
            ),
            background_tasks=SimpleNamespace(add_task=lambda *_args, **_kwargs: None),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert caught.value.msg_key == "smtp_not_configured"


@pytest.mark.asyncio
async def test_issue255_send_email_rate_and_recipient_branches(monkeypatch):
    monkeypatch.setattr(endpoint.SiteSetting, "get_value", AsyncMock(return_value=True))
    monkeypatch.setattr(
        endpoint, "check_bulk_email_rate", AsyncMock(return_value=(True, 0, 3))
    )
    monkeypatch.setattr(
        endpoint,
        "check_recipient_email_rate",
        AsyncMock(side_effect=[(False, 5), (True, 0)]),
    )
    increment_recipient = AsyncMock()
    increment_bulk = AsyncMock()
    monkeypatch.setattr(
        endpoint, "increment_recipient_email_count", increment_recipient
    )
    monkeypatch.setattr(endpoint, "increment_bulk_email_count", increment_bulk)
    users = [
        SimpleNamespace(email=None, username="none"),
        SimpleNamespace(email="limited@example.com", username="limited"),
        SimpleNamespace(email="sent@example.com", username="sent"),
    ]
    _patch_user_filter(monkeypatch, _query(all_rows=users))
    tasks = SimpleNamespace(
        calls=[], add_task=lambda *args, **kwargs: tasks.calls.append((args, kwargs))
    )
    current = SimpleNamespace(id=uuid4())

    result = await endpoint.send_email_to_users(
        data=endpoint.SendEmailRequest(
            subject="subject", content="content", user_ids=[uuid4(), uuid4(), uuid4()]
        ),
        background_tasks=tasks,
        current_user=current,
    )

    assert result["data"] == {"sent_count": 1, "skipped_count": 1, "total": 3}
    assert len(tasks.calls) == 1
    increment_recipient.assert_awaited_once_with("sent@example.com")
    increment_bulk.assert_awaited_once_with(str(current.id), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("can_send", "remaining", "rows", "message"),
    [
        (False, 0, [], "email_rate_limit_exceeded"),
        (True, 2, [], "user_not_found"),
        (True, 0, [SimpleNamespace(email="a@example.com")], "email_quota_insufficient"),
    ],
)
async def test_issue255_send_email_failure_branches(
    monkeypatch, can_send, remaining, rows, message
):
    monkeypatch.setattr(endpoint.SiteSetting, "get_value", AsyncMock(return_value=True))
    monkeypatch.setattr(
        endpoint,
        "check_bulk_email_rate",
        AsyncMock(return_value=(can_send, 0, remaining)),
    )
    _patch_user_filter(monkeypatch, _query(all_rows=rows))

    with pytest.raises(BusinessError) as caught:
        await endpoint.send_email_to_users(
            data=endpoint.SendEmailRequest(
                subject="s", content="c", user_ids=[uuid4()]
            ),
            background_tasks=SimpleNamespace(add_task=lambda *_args, **_kwargs: None),
            current_user=SimpleNamespace(id=uuid4()),
        )

    assert caught.value.msg_key == message


@pytest.mark.asyncio
async def test_issue255_exemption_clears_forced_change(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        username="user",
        force_password_change=True,
        password_expiration_exempt=False,
        save=AsyncMock(),
    )
    _patch_user_filter(monkeypatch, _query(first=user))
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.exempt_password_expiration(
        request=SimpleNamespace(),
        user_id=user.id,
        data=endpoint.ExemptPasswordExpirationRequest(exempt=True),
        current_user=SimpleNamespace(id=uuid4()),
    )

    assert user.password_expiration_exempt is True
    assert user.force_password_change is False
    user.save.assert_awaited_once_with()
