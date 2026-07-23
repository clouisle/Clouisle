from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.tool_config import ToolConfigCreate, ToolConfigOut, ToolConfigUpdate


def test_create_and_update_accept_empty_or_populated_credentials():
    assert ToolConfigCreate(tool_name="web_search", credentials={}).model_dump() == {
        "tool_name": "web_search",
        "credentials": {},
    }
    assert ToolConfigUpdate(credentials={"api_key": "secret"}).model_dump() == {
        "credentials": {"api_key": "secret"}
    }


def test_output_serializes_attributes_uuid_datetime_and_optional_team_id():
    output = ToolConfigOut.model_validate(
        SimpleNamespace(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            tool_name="web_search",
            team_id=None,
            credentials={"api_key": "secret"},
            created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 2, 3, 4, 6, tzinfo=timezone.utc),
        )
    )

    assert output.model_dump(mode="json") == {
        "id": "00000000-0000-0000-0000-000000000001",
        "tool_name": "web_search",
        "team_id": None,
        "credentials": {"api_key": "secret"},
        "created_at": "2026-01-02T03:04:05Z",
        "updated_at": "2026-01-02T03:04:06Z",
    }


@pytest.mark.parametrize(
    ("schema", "payload", "location", "error_type"),
    [
        (ToolConfigCreate, {}, ("tool_name",), "missing"),
        (ToolConfigCreate, {"tool_name": "web_search"}, ("credentials",), "missing"),
        (
            ToolConfigCreate,
            {"tool_name": "web_search", "credentials": ["api_key"]},
            ("credentials",),
            "dict_type",
        ),
        (ToolConfigUpdate, {}, ("credentials",), "missing"),
        (
            ToolConfigUpdate,
            {"credentials": {"api_key": 1}},
            ("credentials", "api_key"),
            "string_type",
        ),
    ],
)
def test_config_schemas_reject_missing_or_invalid_credentials(
    schema, payload, location, error_type
):
    with pytest.raises(ValidationError) as exc_info:
        schema.model_validate(payload)

    assert any(
        error["loc"] == location and error["type"] == error_type
        for error in exc_info.value.errors()
    )
