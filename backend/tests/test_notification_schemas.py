from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.notification import (
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
    NotificationStatus,
)
from app.schemas.notification import (
    NotificationAdminCreate,
    NotificationOut,
    NotificationReadRequest,
    NotificationUnreadCount,
)


def test_notification_admin_create_defaults_and_validates_required_text():
    payload = {
        "scope": NotificationScope.GLOBAL,
        "type": "deployment.complete",
        "title": "Deployment complete",
        "content": "The deployment succeeded.",
    }

    notification = NotificationAdminCreate(**payload)
    another_notification = NotificationAdminCreate(**payload)

    assert notification.source is NotificationSource.SYSTEM
    assert notification.level is NotificationLevel.MEDIUM
    assert notification.notify_channels == []
    notification.notify_channels.append(NotificationChannel.EMAIL)
    assert another_notification.notify_channels == []

    with pytest.raises(ValidationError):
        NotificationAdminCreate(**{**payload, "title": ""})


def test_notification_out_reads_attributes_and_nested_deliveries():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    notification_id = uuid4()
    delivery = SimpleNamespace(
        channel=NotificationChannel.EMAIL,
        status=NotificationDeliveryStatus.SUCCESS,
        error_message=None,
        retry_count=1,
        sent_at=now,
        created_at=now,
        updated_at=now,
    )
    notification = SimpleNamespace(
        id=notification_id,
        scope=NotificationScope.USER,
        team_id=None,
        user_id=uuid4(),
        type="deployment.complete",
        source=NotificationSource.SYSTEM,
        title="Deployment complete",
        content="The deployment succeeded.",
        level=NotificationLevel.HIGH,
        data={"deployment_id": "deploy-1"},
        link_url="/deployments/deploy-1",
        status=NotificationStatus.ACTIVE,
        expires_at=None,
        created_at=now,
        updated_at=now,
        is_read=True,
        read_at=now,
        deliveries=[delivery],
    )

    result = NotificationOut.model_validate(notification)

    assert result.id == notification_id
    assert result.is_read is True
    assert result.deliveries[0].channel is NotificationChannel.EMAIL
    assert result.deliveries[0].status is NotificationDeliveryStatus.SUCCESS


def test_notification_read_request_and_unread_count_defaults():
    request = NotificationReadRequest()

    assert request.notification_ids is None
    assert request.mark_all is False
    assert NotificationUnreadCount(total=0).total == 0
