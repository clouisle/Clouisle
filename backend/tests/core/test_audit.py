from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.core.audit import audit_log


def make_request() -> Request:
    return Request({"type": "http", "headers": []})


@pytest.mark.asyncio
async def test_audit_log_records_success_payload():
    resource_id = uuid4()

    @audit_log(
        action="create_widget",
        resource_type="widget",
        operation="create",
        get_resource_id=lambda kwargs, result: result["id"],
        get_resource_name=lambda kwargs, result: result["name"],
    )
    async def create_widget(*, request: Request):
        return {"id": resource_id, "name": "Quarterly report"}

    with patch("app.core.audit.AuditLogService.log", new=AsyncMock()) as log:
        result = await create_widget(request=make_request())

    assert result == {"id": resource_id, "name": "Quarterly report"}
    log.assert_awaited_once_with(
        user=None,
        action="create_widget",
        resource_type="widget",
        resource_id=resource_id,
        resource_name="Quarterly report",
        operation="create",
        status="success",
        request=ANY,
        error_message=None,
    )


@pytest.mark.asyncio
async def test_audit_log_records_failure_and_reraises():
    @audit_log(action="delete_widget", resource_type="widget", operation="delete")
    async def delete_widget(*, request: Request):
        raise RuntimeError("widget is protected")

    with patch("app.core.audit.AuditLogService.log", new=AsyncMock()) as log:
        with pytest.raises(RuntimeError, match="widget is protected"):
            await delete_widget(request=make_request())

    log.assert_awaited_once_with(
        user=None,
        action="delete_widget",
        resource_type="widget",
        resource_id=None,
        resource_name=None,
        operation="delete",
        status="failed",
        request=ANY,
        error_message="widget is protected",
    )
