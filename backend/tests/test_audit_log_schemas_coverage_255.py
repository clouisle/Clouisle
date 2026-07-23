from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.audit_log import AuditLog, AuditLogListParams


def test_audit_log_serializes_required_and_optional_fields():
    log_id = uuid4()
    user_id = uuid4()
    created_at = datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc)

    audit_log = AuditLog(
        id=log_id,
        user_id=user_id,
        action="login_success",
        resource_type="session",
        operation="create",
        status="success",
        created_at=created_at,
    )

    assert audit_log.model_dump(mode="json") == {
        "user_id": str(user_id),
        "username": None,
        "team_id": None,
        "ip_address": None,
        "user_agent": None,
        "action": "login_success",
        "resource_type": "session",
        "resource_id": None,
        "resource_name": None,
        "operation": "create",
        "status": "success",
        "error_message": None,
        "changes": None,
        "metadata": None,
        "auth_method": None,
        "api_key_id": None,
        "id": str(log_id),
        "created_at": "2026-01-02T03:04:00Z",
    }


def test_audit_log_list_params_uses_pagination_defaults():
    assert AuditLogListParams().model_dump() == {
        "user_id": None,
        "team_id": None,
        "action": None,
        "resource_type": None,
        "resource_id": None,
        "status": None,
        "start_date": None,
        "end_date": None,
        "search": None,
        "page": 1,
        "page_size": 20,
    }


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 101}])
def test_audit_log_list_params_rejects_pagination_outside_bounds(params):
    with pytest.raises(ValidationError):
        AuditLogListParams(**params)
