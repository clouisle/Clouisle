"""Asset tool handlers: scope resolution and error reporting.

These handlers are how an Agent reads files out of its own conversation or run
history. They must reject an unbound call and report access failures as tool
errors instead of raising into the model loop.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat_tools
from app.core.i18n import t
from app.schemas.response import BusinessError, ResponseCode


def _agent(team_id=None):
    return SimpleNamespace(id=uuid4(), team_id=team_id)


@pytest.mark.anyio
async def test_asset_tool_needs_a_scope_and_a_string_ref():
    agent = _agent()

    # No Agent at all: the tool cannot run outside a chat/run context.
    assert "error" in json.loads(
        await chat_tools._execute_asset_tool(
            "list_assets", {}, agent=None, user=None, conversation_id=None
        )
    )
    # A read without a ref is a validation error, not a crash.
    assert "error" in json.loads(
        await chat_tools._execute_asset_tool(
            "read_asset", {}, agent=agent, user=object(), conversation_id=uuid4()
        )
    )
    # Scope ids must parse; both workflow-run and conversation ids do.
    for scope in ({"workflow_run_id": "not-a-uuid"}, {"conversation_id": None}):
        result = json.loads(
            await chat_tools._execute_asset_tool(
                "read_asset",
                {"ref": "asset-1"},
                agent=agent,
                user=object(),
                conversation_id=scope.get("conversation_id"),
                workflow_run_id=scope.get("workflow_run_id"),
            )
        )
        assert "error" in result


@pytest.mark.anyio
@pytest.mark.parametrize(
    "raised, expected_key",
    [
        (ValueError("invalid_cursor"), "validation_error"),
        (
            BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="access_denied",
                status_code=403,
            ),
            "access_denied",
        ),
    ],
)
async def test_list_assets_reports_scope_errors_as_tool_errors(raised, expected_key):
    """A denied or malformed listing is reported to the model, never raised."""
    user, team_id, conversation_id = object(), uuid4(), uuid4()
    listing = AsyncMock(side_effect=raised)

    with patch("app.services.asset_access.list_authorized_assets", listing):
        result = json.loads(
            await chat_tools._execute_asset_tool(
                "list_assets",
                {"query": "report"},
                agent=_agent(team_id=team_id),
                user=user,
                conversation_id=conversation_id,
            )
        )

    assert result["error"] == t(expected_key)
    assert listing.await_args.kwargs["expected_team_id"] == team_id
    assert listing.await_args.kwargs["scope_id"] == conversation_id
