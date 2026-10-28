from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.tool_connection import ToolConnectionCreate, ToolConnectionUpdate


def make_payload(**overrides):
    return {
        "team_id": uuid4(),
        "scope": "user",
        "name": "Account",
        "tool_id": uuid4(),
        **overrides,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "   "},
        {"scope": "user", "team_id": None},
        {"scope": "site"},
        {"tool_id": None},
        {"builtin_tool_key": "invalid/key"},
        {"builtin_tool_key": "valid_key"},
        {"config": {"bad field": "secret"}},
        {"config": {"token": ""}},
        {"config": {"token": "x" * 8193}},
        {"config": {f"field_{i}": "x" for i in range(51)}},
    ],
)
def test_connection_creation_rejects_invalid_scope_identity_or_credentials(overrides):
    with pytest.raises(ValidationError):
        ToolConnectionCreate(**make_payload(**overrides))


def test_connection_creation_normalizes_labels_and_accepts_site_scope():
    payload = ToolConnectionCreate(
        **make_payload(
            team_id=None, scope="site", name="  Shared  ", account_label="  "
        )
    )
    assert payload.name == "Shared"
    assert payload.account_label is None


@pytest.mark.parametrize(
    "update",
    [
        {"name": "  "},
        {"status": "revoked"},
        {"config_remove": ["token", "token"]},
        {"config_remove": ["invalid name"]},
        {"config_set": {"token": "new"}, "config_remove": ["token"]},
        {"config_set": {"token": ""}},
        {"expected_secret_version": 0},
    ],
)
def test_connection_update_rejects_unsafe_mutations(update):
    with pytest.raises(ValidationError):
        ToolConnectionUpdate(**update)


def test_connection_update_supports_distinct_set_and_remove():
    update = ToolConnectionUpdate(
        name=None,
        account_label="  primary  ",
        config_set={"new": "value"},
        config_remove=["old"],
    )
    assert update.account_label == "primary"
    assert update.config_set == {"new": "value"}
    assert update.config_remove == ["old"]
