from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.notification import NotificationAuditAction
from app.models.notification import NotificationAudit
from app.services.notification import create_notification, create_notification_audit


@pytest.mark.asyncio
async def test_create_notification_saves_notification_before_audit():
    notification = SimpleNamespace(id="notification-id", save=AsyncMock())

    with patch(
        "app.services.notification.create_notification_audit",
        new=AsyncMock(),
    ) as create_audit:
        result = await create_notification(notification)  # type: ignore[arg-type]

    notification.save.assert_awaited_once()
    create_audit.assert_awaited_once_with(
        notification_id="notification-id",
        action=NotificationAuditAction.CREATE,
        user=None,
        meta=None,
    )
    assert result is notification


@pytest.mark.asyncio
async def test_create_notification_forwards_actor_and_meta():
    actor = SimpleNamespace(id="actor-id")
    notification = SimpleNamespace(id="notification-id", save=AsyncMock())

    with patch(
        "app.services.notification.create_notification_audit",
        new=AsyncMock(),
    ) as create_audit:
        await create_notification(
            notification,
            actor=actor,
            meta={"source": "admin"},  # type: ignore[arg-type]
        )

    create_audit.assert_awaited_once_with(
        notification_id="notification-id",
        action=NotificationAuditAction.CREATE,
        user=actor,
        meta={"source": "admin"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("actor", "expected_user_id"),
    [(SimpleNamespace(id="actor-id"), "actor-id"), (None, None)],
)
async def test_create_notification_audit_creates_expected_row(actor, expected_user_id):
    with patch.object(
        NotificationAudit, "create", new=AsyncMock(return_value="audit")
    ) as create:
        result = await create_notification_audit(
            notification_id="notification-id",  # type: ignore[arg-type]
            action=NotificationAuditAction.READ,
            user=actor,
            meta={"source": "in_app"},
        )

    assert result == "audit"
    create.assert_awaited_once()
    kwargs = create.await_args.kwargs
    assert kwargs["notification_id"] == "notification-id"
    assert kwargs["user_id"] == expected_user_id
    assert kwargs["action"] is NotificationAuditAction.READ
    assert kwargs["meta"] == {"source": "in_app"}
    assert kwargs["created_at"] is not None


@pytest.mark.asyncio
async def test_create_notification_does_not_audit_when_save_fails():
    notification = SimpleNamespace(
        id="notification-id", save=AsyncMock(side_effect=RuntimeError("database down"))
    )

    with patch(
        "app.services.notification.create_notification_audit", new=AsyncMock()
    ) as create_audit:
        with pytest.raises(RuntimeError, match="database down"):
            await create_notification(notification)  # type: ignore[arg-type]

    create_audit.assert_not_awaited()
