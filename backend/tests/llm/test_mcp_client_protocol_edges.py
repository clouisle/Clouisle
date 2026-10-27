"""Protocol-edge behavior tests for the MCP client adapter.

Only observable behavior is asserted: timeout failures reported to callers,
security decisions for server-initiated elicitation, and conversion of
malformed/unknown MCP payloads into usable tool results.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import mcp.types as types
import pytest

from app.llm.tools import mcp_client as mcp

pytestmark = pytest.mark.asyncio


def _caps(**overrides):
    values = {
        "protocol_version": "2025-11-25",
        "tools": True,
        "resources": True,
        "prompts": True,
        "completions": True,
    }
    values.update(overrides)
    return mcp.McpServerCapabilities(**values)


def _install_open(monkeypatch, client, session, capabilities=None):
    @asynccontextmanager
    async def fake_open(deadline):
        yield session, capabilities or _caps()

    monkeypatch.setattr(client, "_open", fake_open)


# ---------------------------------------------------------------------------
# Timeout failures
# ---------------------------------------------------------------------------


async def test_connect_uses_the_operation_deadline_over_the_configured_budget(
    monkeypatch,
):
    @asynccontextmanager
    async def slow_transport():
        await asyncio.sleep(5)
        yield object(), object()

    client = mcp.McpClient(
        {}, timeouts=mcp.McpTimeouts(connect=30, request=30, enumeration=30)
    )
    monkeypatch.setattr(client, "_transport", slow_transport)

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(mcp.McpTimeout) as error:
        async with client.connect(timeout=0.05):
            pass

    assert error.value.details["timeout_seconds"] <= 0.05
    assert loop.time() - started < 1


async def test_tool_request_budget_is_clamped_to_the_operation_deadline(monkeypatch):
    async def slow_call(name, arguments, **kwargs):
        await asyncio.sleep(5)

    client = mcp.McpClient(
        {}, timeouts=mcp.McpTimeouts(connect=1, request=30, enumeration=1)
    )
    _install_open(monkeypatch, client, SimpleNamespace(call_tool=slow_call))

    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await client.execute_tool("slow-tool", {}, timeout=0.05)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()
    assert loop.time() - started < 1


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------


async def test_elicitation_declines_secrets_beside_boolean_subschemas():
    invoked: list[object] = []

    async def elicitation(context, params):
        invoked.append(params)
        return types.ElicitResult(action="accept")

    guard = mcp._CallbackGuard(mcp.McpCallbacks(elicitation=elicitation))

    harmless = types.ElicitRequestFormParams(
        mode="form",
        message="Pick a theme",
        requested_schema={"type": "object", "properties": {"theme": True}},
    )
    accepted = await guard.elicitation(None, harmless)
    assert accepted.action == "accept"
    assert len(invoked) == 1

    secret = types.ElicitRequestFormParams(
        mode="form",
        message="Pick a theme",
        requested_schema={
            "type": "object",
            "properties": {"theme": True, "access_token": True},
        },
    )
    declined = await guard.elicitation(None, secret)
    assert declined.action == "decline"
    # The handler must never see a request that would expose a secret.
    assert len(invoked) == 1


# ---------------------------------------------------------------------------
# Protocol payload conversion
# ---------------------------------------------------------------------------


async def test_tool_result_normalizes_malformed_and_unknown_protocol_blocks(
    monkeypatch,
):
    async def call_tool(name, arguments, **kwargs):
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="resource", resource="not-a-mapping"),
                SimpleNamespace(type="widget", payload={"id": 1}),
                SimpleNamespace(type="text", text="ok"),
            ],
            isError=False,
            structuredContent=None,
        )

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(call_tool=call_tool))

    result = await client.execute_tool("tool", {})

    assert result.success is True
    assert [block.type for block in result.content] == [
        "resource",
        "widget",
        "text",
    ]
    # A resource block without a mapping body becomes an empty, non-binary
    # resource instead of raising or leaking the raw malformed value.
    assert result.content[0].resource == {}
    assert result.content[0].uri is None
    # An unknown block type is preserved rather than dropped.
    assert result.content[1].raw is not None
    assert result.result == [
        {"type": "resource", "resource": {}},
        {"type": "widget", "value": result.content[1].raw["value"]},
        "ok",
    ]
