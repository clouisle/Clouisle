"""``x-mcp-header`` parameter mirroring for the MCP adapter.

On a 2026-07-28 connection the SDK mirrors arguments annotated ``x-mcp-header``
into ``Mcp-Param-*`` request headers, but only for tools it has seen in a
``tools/list`` on the same session. ``execute_tool`` therefore lists the tools
first on modern protocols — and only there: older protocols emit no such headers
and must not pay an extra round trip. A listing that never reaches the called
tool leaves the annotations unknown, so the call fails closed instead of being
sent with the wrong (absent) headers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import mcp.types as types
import pytest

from app.llm.tools import mcp_client as mcp

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _caps(**overrides):
    values = {
        "protocol_version": "2026-07-28",
        "tools": True,
    }
    values.update(overrides)
    return mcp.McpServerCapabilities(**values)


def _install(monkeypatch, client, session, capabilities=None):
    caps = capabilities or _caps()

    @asynccontextmanager
    async def fake_open(deadline):
        yield session, caps

    monkeypatch.setattr(client, "_open", fake_open)


def _listing(*names, cursor=None):
    return SimpleNamespace(
        tools=[
            SimpleNamespace(name=name, input_schema={"type": "object"})
            for name in names
        ],
        next_cursor=cursor,
    )


class _Session:
    """One session serving both requests, recording them in call order."""

    def __init__(self, *pages):
        self.pages = list(pages)
        self.order: list[str] = []
        self.cursors: list[str | None] = []

    async def list_tools(self, *, params=None):
        self.order.append("list_tools")
        cursor = params.cursor if params is not None else None
        self.cursors.append(cursor)
        return self.pages.pop(0)

    async def call_tool(self, name, arguments, **kwargs):
        self.order.append("call_tool")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="done")]
        )


# ---------------------------------------------------------------------------
# Negotiated version decides whether the listing happens
# ---------------------------------------------------------------------------


async def test_new_protocol_lists_tools_on_the_same_session_before_calling(
    monkeypatch,
):
    session = _Session(_listing("search"))
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {"q": "docs"})

    assert result.success is True
    # Same session object served both requests, listing first: that listing is
    # what arms the SDK's header emission for the call that follows it.
    assert session.order == ["list_tools", "call_tool"]


async def test_older_protocol_never_lists_tools(monkeypatch):
    class OldSession(_Session):
        async def list_tools(self, *, params=None):
            pytest.fail("a pre-2026-07-28 call must not list tools")

    session = OldSession()
    client = mcp.McpClient({})
    _install(monkeypatch, client, session, _caps(protocol_version="2025-11-25"))

    result = await client.execute_tool("search", {})

    assert result.success is True
    assert session.order == ["call_tool"]


async def test_unknown_protocol_never_lists_tools(monkeypatch):
    """An unnegotiated version is not proof of the modern behaviour."""

    class OldSession(_Session):
        async def list_tools(self, *, params=None):
            pytest.fail("an unknown protocol must not list tools")

    session = OldSession()
    client = mcp.McpClient({})
    _install(monkeypatch, client, session, _caps(protocol_version=None))

    result = await client.execute_tool("search", {})

    assert result.success is True
    assert session.order == ["call_tool"]


async def test_missing_tools_capability_fails_before_listing(monkeypatch):
    """A server without the ``tools`` capability keeps failing closed."""

    class NoTools(_Session):
        async def list_tools(self, *, params=None):
            pytest.fail("a server without tools must not be listed")

    session = NoTools()
    client = mcp.McpClient({})
    _install(monkeypatch, client, session, _caps(tools=False))

    result = await client.execute_tool("search", {})

    assert result.success is False
    assert session.order == []


# ---------------------------------------------------------------------------
# Pagination reuses the adapter's own enumeration bounds
# ---------------------------------------------------------------------------


async def test_a_tool_after_the_first_page_is_still_reached(monkeypatch):
    session = _Session(_listing("other", cursor="page-2"), _listing("search"))
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {})

    assert result.success is True
    assert session.cursors == [None, "page-2"]
    assert session.order == ["list_tools", "list_tools", "call_tool"]


# ---------------------------------------------------------------------------
# Incomplete annotations fail closed
# ---------------------------------------------------------------------------


async def test_truncated_listing_without_the_tool_fails_closed(monkeypatch):
    """The target tool may sit on an unfetched page: its headers are unknown."""
    session = _Session(_listing("other", cursor="page-2"))
    client = mcp.McpClient(
        {},
        enumeration_limits=mcp.McpEnumerationLimits(max_items=1),
    )
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {})

    assert result.success is False
    assert result.error
    assert session.order == ["list_tools"]


async def test_truncated_listing_that_still_reached_the_tool_calls_it(monkeypatch):
    """Truncation only matters when it hides the annotated tool itself."""
    session = _Session(_listing("search", cursor="page-2"), _listing("other"))
    client = mcp.McpClient(
        {},
        enumeration_limits=mcp.McpEnumerationLimits(max_pages=1),
    )
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {})

    assert result.success is True
    # One page was enough to reach the tool; the page it could not fetch is
    # irrelevant to the annotations of the tool actually being called.
    assert session.cursors == [None]
    assert session.order == ["list_tools", "call_tool"]


async def test_listing_page_without_tools_still_calls_the_tool(monkeypatch):
    """A complete, empty listing means the tool genuinely has no headers."""
    session = _Session(SimpleNamespace())
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {})

    assert result.success is True
    assert session.order == ["list_tools", "call_tool"]


async def test_failing_listing_fails_closed_without_calling(monkeypatch):
    """A listing error must not turn into an unannotated tool call."""

    class BrokenListing(_Session):
        async def list_tools(self, *, params=None):
            self.order.append("list_tools")
            raise RuntimeError("listing exploded with token abc")

    session = BrokenListing()
    client = mcp.McpClient({})
    _install(monkeypatch, client, session)

    result = await client.execute_tool("search", {})

    assert result.success is False
    assert "token abc" not in (result.error or "")
    assert session.order == ["list_tools"]
