from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.llm.tools import mcp_client


@asynccontextmanager
async def _context(value):
    yield value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transport", "method"),
    [("stdio", "_connect_stdio"), ("sse", "_connect_sse"), ("http", "_connect_http")],
)
async def test_connect_dispatches_to_configured_transport(
    monkeypatch, transport, method
):
    client = mcp_client.McpClient({"transport": transport})
    session = object()
    monkeypatch.setattr(client, method, lambda: _context(session))

    async with client.connect() as connected:
        assert connected is session


@pytest.mark.asyncio
async def test_connect_rejects_unknown_transport():
    client = mcp_client.McpClient({"transport": "websocket"})

    with pytest.raises(ValueError, match="Unsupported transport: websocket"):
        async with client.connect():
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "method", "message"),
    [
        ({"transport": "stdio"}, "_connect_stdio", "Command is required"),
        ({"transport": "sse"}, "_connect_sse", "URL is required"),
        ({"transport": "http"}, "_connect_http", "URL is required"),
    ],
)
async def test_transport_requires_connection_target(config, method, message):
    client = mcp_client.McpClient(config)

    with pytest.raises(ValueError, match=message):
        async with getattr(client, method)():
            pass


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "sse", "http"])
async def test_transport_initializes_session_without_real_io(monkeypatch, transport):
    read_stream, write_stream = object(), object()
    transport_call = AsyncMock()
    http_client = _context(object())
    http_client_factory = MagicMock(return_value=http_client)
    monkeypatch.setattr(mcp_client, "create_mcp_http_client", http_client_factory)

    @asynccontextmanager
    async def fake_transport(*args, **kwargs):
        await transport_call(*args, **kwargs)
        yield (read_stream, write_stream)

    session = SimpleNamespace(initialize=AsyncMock())
    monkeypatch.setattr(
        mcp_client,
        "ClientSession",
        lambda read, write: _context(session),
    )
    config = {
        "transport": transport,
        "command": "server",
        "args": ["--flag"],
        "env": {"TOKEN": "secret"},
        "url": "https://mcp.example.test",
        "headers": {"Authorization": "Bearer token"},
    }
    factory_name = {
        "stdio": "stdio_client",
        "sse": "sse_client",
        "http": "streamablehttp_client",
    }[transport]
    monkeypatch.setattr(mcp_client, factory_name, fake_transport)

    async with mcp_client.McpClient(config).connect() as connected:
        assert connected is session

    session.initialize.assert_awaited_once_with()
    if transport == "stdio":
        params = transport_call.await_args.args[0]
        assert (params.command, params.args, params.env) == (
            "server",
            ["--flag"],
            {"TOKEN": "secret"},
        )
    elif transport == "sse":
        transport_call.assert_awaited_once_with(
            "https://mcp.example.test",
            headers={"Authorization": "Bearer token"},
        )
    else:
        http_client_factory.assert_called_once_with(
            headers={"Authorization": "Bearer token"}
        )
        transport_call.assert_awaited_once_with(
            "https://mcp.example.test",
            http_client=http_client,
        )


@pytest.mark.asyncio
async def test_list_tools_returns_structured_tool_info(monkeypatch):
    tools = [
        SimpleNamespace(
            name="search", description="Search", inputSchema={"type": "object"}
        ),
        SimpleNamespace(name="ping", description=None),
    ]
    session = SimpleNamespace(
        list_tools=AsyncMock(return_value=SimpleNamespace(tools=tools))
    )
    client = mcp_client.McpClient({})
    monkeypatch.setattr(client, "connect", lambda: _context(session))

    assert await client.list_tools() == [
        mcp_client.McpToolInfo("search", "Search", {"type": "object"}),
        mcp_client.McpToolInfo("ping", None, {}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ([SimpleNamespace(text="one")], "one"),
        ([], None),
        ([SimpleNamespace(text="one"), SimpleNamespace(data=b"two")], ["one", b"two"]),
    ],
)
async def test_execute_tool_returns_structured_success(monkeypatch, content, expected):
    session = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=SimpleNamespace(isError=False, content=content)
        )
    )
    client = mcp_client.McpClient({})
    monkeypatch.setattr(client, "connect", lambda: _context(session))

    result = await client.execute_tool("search", {"query": "docs"}, timeout=3)

    assert result == mcp_client.McpToolResult(success=True, result=expected)
    session.call_tool.assert_awaited_once_with("search", {"query": "docs"})


@pytest.mark.asyncio
async def test_execute_tool_maps_server_timeout_and_connection_errors(monkeypatch):
    resolve_error = MagicMock(side_effect=lambda message, **kwargs: f"safe:{message}")
    mask_error = MagicMock(return_value="masked:offline")
    monkeypatch.setattr(mcp_client, "resolve_user_visible_error", resolve_error)
    monkeypatch.setattr(mcp_client, "exception_to_user_message", mask_error)
    client = mcp_client.McpClient({})

    error_session = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=SimpleNamespace(
                isError=True,
                content=[SimpleNamespace(text="bad "), SimpleNamespace(text="request")],
            )
        )
    )
    monkeypatch.setattr(client, "connect", lambda: _context(error_session))
    assert await client.execute_tool("fail", {}) == mcp_client.McpToolResult(
        success=False, error="safe:bad request"
    )

    @asynccontextmanager
    async def timeout_context():
        raise TimeoutError
        yield

    monkeypatch.setattr(client, "connect", timeout_context)
    assert await client.execute_tool("slow", {}, timeout=2) == mcp_client.McpToolResult(
        success=False, error="safe:Tool execution timed out after 2 seconds"
    )

    @asynccontextmanager
    async def failing_context():
        raise RuntimeError("offline")
        yield

    monkeypatch.setattr(client, "connect", failing_context)
    assert await client.execute_tool("fail", {}) == mcp_client.McpToolResult(
        success=False, error="masked:offline"
    )

    assert resolve_error.call_args_list[1].kwargs == {"fallback_key": "request_timeout"}
    mask_error.assert_called_once()
    assert isinstance(mask_error.call_args.args[0], RuntimeError)
    assert mask_error.call_args.kwargs == {"fallback_key": "mcp_tool_execution_failed"}


@pytest.mark.asyncio
async def test_convenience_functions_delegate_to_client(monkeypatch):
    execute = AsyncMock(
        return_value=mcp_client.McpToolResult(success=True, result="ok")
    )
    list_tools = AsyncMock(return_value=[mcp_client.McpToolInfo("ping", None, {})])
    client = SimpleNamespace(execute_tool=execute, list_tools=list_tools)
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(mcp_client, "McpClient", constructor)
    config = {"transport": "http", "url": "https://mcp.example.test"}

    assert await mcp_client.execute_mcp_tool(config, "ping", {"value": 1}, 4) == (
        mcp_client.McpToolResult(success=True, result="ok")
    )
    assert await mcp_client.list_mcp_tools(config) == [
        mcp_client.McpToolInfo("ping", None, {})
    ]
    assert constructor.call_args_list == [call(config), call(config)]
    execute.assert_awaited_once_with("ping", {"value": 1}, 4)
    list_tools.assert_awaited_once_with()
