"""The Agent tool boundary carries its runtime's progress sink.

``execute_agent_stored_tool`` is the only place that turns the runtime identity
into the call context handed to ``ToolExecutor``, so this is where an Agent
run's progress reporter has to survive the hop.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.agent_tool_execution import execute_agent_stored_tool
from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope


async def _sink(_update):
    return None


@pytest.mark.asyncio
async def test_agent_tool_context_receives_the_runtime_progress_sink():
    team_id = uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=team_id)
    user = SimpleNamespace(id=uuid4())
    tool = SimpleNamespace(id=uuid4(), name="server", display_name="Docs")
    captured: dict[str, object] = {}

    async def fake_execute(_self, _tool, _arguments, *, context, operation):
        captured["context"] = context
        return {"ok": True}

    identity = RuntimeToolIdentity(
        run_id=uuid4(),
        tool_call_id="call-1",
        entrypoint="agent_run",
        progress=_sink,
    )
    with (
        patch(
            "app.services.agent_tool_execution.User.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(id=user.id)),
        ),
        patch(
            "app.services.agent_tool_execution.Tool.get_or_none",
            new=AsyncMock(return_value=tool),
        ),
        patch(
            "app.services.agent_tool_execution.ToolExecutor.execute",
            new=fake_execute,
        ),
        tool_identity_scope(identity),
    ):
        result = await execute_agent_stored_tool(
            SimpleNamespace(
                id=agent.id,
                team_id=team_id,
                tools_config=[{"type": "mcp", "server_id": str(tool.id)}],
            ),
            f"mcp_{tool.name}_search",
            {"q": "docs"},
            user,
        )

    assert result == {"ok": True}
    context = captured["context"]
    assert context.progress is _sink
    assert context.run_id is identity.run_id


@pytest.mark.asyncio
async def test_agent_tool_context_has_no_sink_without_a_runtime_reporter():
    team_id = uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=team_id)
    user = SimpleNamespace(id=uuid4())
    tool = SimpleNamespace(id=uuid4(), name="server", display_name="Docs")
    captured: dict[str, object] = {}

    async def fake_execute(_self, _tool, _arguments, *, context, operation):
        captured["context"] = context
        return {"ok": True}

    with (
        patch(
            "app.services.agent_tool_execution.User.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(id=user.id)),
        ),
        patch(
            "app.services.agent_tool_execution.Tool.get_or_none",
            new=AsyncMock(return_value=tool),
        ),
        patch(
            "app.services.agent_tool_execution.ToolExecutor.execute",
            new=fake_execute,
        ),
        tool_identity_scope(RuntimeToolIdentity(entrypoint="agent_run")),
    ):
        await execute_agent_stored_tool(
            SimpleNamespace(
                id=agent.id,
                team_id=team_id,
                tools_config=[{"type": "mcp", "server_id": str(tool.id)}],
            ),
            f"mcp_{tool.name}_search",
            {},
            user,
        )

    assert captured["context"].progress is None
