from unittest.mock import AsyncMock

import pytest

from app.core import audit


class RequestBoundary:
    pass


class UserBoundary:
    pass


@pytest.mark.asyncio
async def test_audit_log_skips_logging_without_request(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(audit.AuditLogService, "log", log)

    @audit.audit_log("read_widget", "widget", "read")
    async def read_widget(value):
        return value

    assert await read_widget("result") == "result"
    log.assert_not_awaited()


@pytest.mark.asyncio
async def test_audit_log_records_success_from_positional_context(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(audit.AuditLogService, "log", log)
    monkeypatch.setattr(audit, "Request", RequestBoundary)
    request = RequestBoundary()
    monkeypatch.setattr(audit, "User", UserBoundary)
    user = UserBoundary()

    @audit.audit_log(
        "update_widget",
        "widget",
        "update",
        get_resource_id=lambda kwargs, result: kwargs["widget_id"],
        get_resource_name=lambda kwargs, result: result["name"],
        capture_changes=True,
    )
    async def update_widget(request, current_user, **kwargs):
        return {"name": "renamed"}

    result = await update_widget(request, user, widget_id="widget-1")

    assert result == {"name": "renamed"}
    log.assert_awaited_once_with(
        user=user,
        action="update_widget",
        resource_type="widget",
        resource_id="widget-1",
        resource_name="renamed",
        operation="update",
        status="success",
        request=request,
        error_message=None,
    )


@pytest.mark.asyncio
async def test_audit_log_records_failure_from_keyword_context(monkeypatch):
    log = AsyncMock()
    monkeypatch.setattr(audit.AuditLogService, "log", log)
    monkeypatch.setattr(audit, "Request", RequestBoundary)
    request = RequestBoundary()
    monkeypatch.setattr(audit, "User", UserBoundary)
    user = UserBoundary()

    @audit.audit_log("delete_widget", "widget", "delete")
    async def delete_widget(**kwargs):
        raise ValueError("cannot delete")

    with pytest.raises(ValueError, match="cannot delete"):
        await delete_widget(request=request, current_user=user)

    log.assert_awaited_once_with(
        user=user,
        action="delete_widget",
        resource_type="widget",
        resource_id=None,
        resource_name=None,
        operation="delete",
        status="failed",
        request=request,
        error_message="cannot delete",
    )


@pytest.mark.asyncio
async def test_audit_log_ignores_callback_and_persistence_failures(monkeypatch):
    log = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(audit.AuditLogService, "log", log)
    monkeypatch.setattr(audit, "Request", RequestBoundary)
    request = RequestBoundary()

    def fail(*args):
        raise RuntimeError("callback failed")

    @audit.audit_log(
        "create_widget",
        "widget",
        "create",
        get_resource_id=fail,
        get_resource_name=fail,
        capture_changes=True,
    )
    async def create_widget(**kwargs):
        return "created"

    assert await create_widget(request=request) == "created"
    log.assert_awaited_once()
