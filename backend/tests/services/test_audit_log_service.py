from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services import audit_log


def test_get_client_ip_uses_proxy_headers_then_direct_client() -> None:
    request = SimpleNamespace(
        headers={"x-forwarded-for": " 203.0.113.1, 10.0.0.1 ", "x-real-ip": "10.0.0.2"},
        client=SimpleNamespace(host="10.0.0.3"),
    )
    assert audit_log.AuditLogService.get_client_ip(request) == "203.0.113.1"

    request.headers = {"x-real-ip": " 10.0.0.2 "}
    assert audit_log.AuditLogService.get_client_ip(request) == "10.0.0.2"

    request.headers = {}
    assert audit_log.AuditLogService.get_client_ip(request) == "10.0.0.3"

    request.client = None
    assert audit_log.AuditLogService.get_client_ip(request) == "unknown"


def test_sanitize_changes_masks_nested_secrets_and_emails() -> None:
    changes = {
        "before": {
            "password": "short",
            "api_key_value": "1234567890",
            "profile": {"email": "alice@example.com", "token": 123, "name": "Alice"},
        },
        "after": "not-a-dict",
        "reason": "rotation",
    }

    assert audit_log.AuditLogService.sanitize_changes(changes) == {
        "before": {
            "password": "***",
            "api_key_value": "12345678***",
            "profile": {
                "email": "a***e@example.com",
                "token": "***",
                "name": "Alice",
            },
        },
        "after": "not-a-dict",
        "reason": "rotation",
    }
    assert audit_log.AuditLogService._mask_email("ab@example.com") == "a***@example.com"
    assert audit_log.AuditLogService._mask_email("invalid") == "invalid"


@pytest.mark.asyncio
async def test_log_sanitizes_request_context_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(audit_log.AuditLog, "create", create)
    user = SimpleNamespace(id=uuid4(), username="alice", current_team_id=uuid4())
    api_key = SimpleNamespace(id=uuid4())
    resource_id = uuid4()
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.4", "user-agent": "pytest"},
        client=None,
    )

    result = await audit_log.AuditLogService.log(
        user=user,
        action="update_user",
        resource_type="user",
        resource_id=resource_id,
        resource_name="alice",
        operation="update",
        status="success",
        request=request,
        changes={"after": {"secret": "long-secret-value"}},
        metadata={"source": "test"},
        api_key=api_key,
    )

    assert result is created
    create.assert_awaited_once_with(
        user_id=user.id,
        username="alice",
        team_id=user.current_team_id,
        ip_address="203.0.113.4",
        user_agent="pytest",
        action="update_user",
        resource_type="user",
        resource_id=resource_id,
        resource_name="alice",
        operation="update",
        status="success",
        error_message=None,
        changes={"after": {"secret": "long-sec***"}},
        metadata={"source": "test"},
        auth_method="api_key",
        api_key_id=api_key.id,
    )


@pytest.mark.asyncio
async def test_log_supports_system_actor_and_propagates_create_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(audit_log.AuditLog, "create", create)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await audit_log.AuditLogService.log(
            user=None,
            action="archive",
            resource_type="audit_log",
            resource_id=None,
            resource_name=None,
            operation="delete",
            status="failed",
            error_message="archive failed",
        )

    create.assert_awaited_once_with(
        user_id=None,
        username=None,
        team_id=None,
        ip_address="system",
        user_agent="system",
        action="archive",
        resource_type="audit_log",
        resource_id=None,
        resource_name=None,
        operation="delete",
        status="failed",
        error_message="archive failed",
        changes=None,
        metadata=None,
        auth_method="jwt",
        api_key_id=None,
    )
