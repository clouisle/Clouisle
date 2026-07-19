from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.api_key import APIKeyCreate, APIKeyUpdate


def test_api_key_create_defaults_and_access_ids():
    agent_id, workflow_id = uuid4(), uuid4()

    api_key = APIKeyCreate(
        name="deployment", agent_ids=[agent_id], workflow_ids=[workflow_id]
    )

    assert api_key.scopes == ["chat"]
    assert api_key.rate_limit == 1000
    assert api_key.agent_ids == [agent_id]
    assert api_key.workflow_ids == [workflow_id]


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"name": "valid", "rate_limit": -1}, "rate_limit"),
    ],
)
def test_api_key_create_rejects_invalid_bounds(payload, field):
    with pytest.raises(ValidationError) as exc_info:
        APIKeyCreate(**payload)

    assert field in str(exc_info.value)


def test_api_key_update_keeps_unspecified_fields_unset():
    update = APIKeyUpdate(is_active=False)

    assert update.is_active is False
    assert update.model_dump(exclude_unset=True) == {"is_active": False}
