"""Behavioral tests for the MCP client adapter.

These tests exercise the adapter's real normalization, capability gating,
pagination, deadline and callback-policy logic against SDK protocol models and
purpose-built fake sessions. They intentionally avoid asserting source strings
or echoing unrelated mocks.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import mcp.types as types
import pytest

from app.llm.tools import mcp_client as mcp

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _context(value):
    yield value


def _caps(**overrides):
    values = {
        "protocol_version": "2025-11-25",
        "server_name": "test-server",
        "server_version": "1.0",
        "tools": True,
        "resources": True,
        "prompts": True,
        "completions": True,
    }
    values.update(overrides)
    return mcp.McpServerCapabilities(**values)


def _install_open(monkeypatch, client, session, capabilities):
    """Replace transport+handshake so protocol behavior can be tested directly."""

    @asynccontextmanager
    async def fake_open(deadline):
        yield session, capabilities

    monkeypatch.setattr(client, "_open", fake_open)


def _tool(name="search", **kwargs):
    payload = {
        "name": name,
        "description": f"{name} description",
        "input_schema": {"type": "object", "properties": {}},
    }
    payload.update(kwargs)
    return types.Tool(**payload)


# ---------------------------------------------------------------------------
# Tool result normalization
# ---------------------------------------------------------------------------


async def test_tool_result_enforces_block_and_structured_budgets():
    block_result = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="x" * 50)],
        isError=False,
        structuredContent=None,
    )
    with pytest.raises(mcp.McpContentTooLarge):
        mcp.McpClient._tool_result_from_sdk(
            block_result,
            limits=mcp.McpContentLimits(max_block_bytes=10, max_total_bytes=1000),
        )

    structured_result = SimpleNamespace(
        content=[],
        isError=False,
        structuredContent={"value": "x" * 50},
    )
    with pytest.raises(mcp.McpContentTooLarge):
        mcp.McpClient._tool_result_from_sdk(
            structured_result,
            limits=mcp.McpContentLimits(max_block_bytes=1000, max_total_bytes=10),
        )


async def test_execute_tool_reports_a_content_budget_failure(monkeypatch):
    async def call_tool(name, arguments, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="x" * 50)],
            isError=False,
            structuredContent=None,
        )

    client = mcp.McpClient(
        {},
        content_limits=mcp.McpContentLimits(max_block_bytes=10, max_total_bytes=1000),
    )
    _install_open(
        monkeypatch,
        client,
        SimpleNamespace(call_tool=call_tool),
        _caps(),
    )

    result = await client.execute_tool("search", {})

    assert result.success is False
    assert result.error
    assert result.content == []


async def test_text_tool_result_keeps_legacy_shape_and_full_content():
    result = mcp.McpClient._tool_result_from_sdk(
        types.CallToolResult(content=[types.TextContent(type="text", text="one")])
    )

    assert result.success is True
    assert result.is_error is False
    assert result.result == "one"
    assert [block.type for block in result.content] == ["text"]
    assert result.to_dict()["content"] == [{"type": "text", "text": "one"}]


async def test_empty_tool_result_has_no_legacy_payload():
    result = mcp.McpClient._tool_result_from_sdk(types.CallToolResult(content=[]))

    assert result.success is True
    assert result.result is None
    assert result.content == []
    assert result.to_dict()["result"] is None


async def test_multimodal_tool_result_preserves_every_block():
    result = mcp.McpClient._tool_result_from_sdk(
        types.CallToolResult(
            content=[
                types.TextContent(type="text", text="note"),
                types.ImageContent(type="image", data="aGk=", mime_type="image/png"),
                types.ResourceLink(
                    type="resource_link",
                    uri="file:///report",
                    name="report",
                    mime_type="text/plain",
                ),
                types.EmbeddedResource(
                    type="resource",
                    resource=types.TextResourceContents(
                        uri="file:///body", text="body", mime_type="text/plain"
                    ),
                ),
            ],
            structured_content={"count": 1},
        )
    )

    assert result.success is True
    assert result.result == [
        "note",
        "aGk=",
        {
            "type": "resource_link",
            "uri": "file:///report",
            "name": "report",
            "mimeType": "text/plain",
        },
        {
            "type": "resource",
            "resource": {
                "uri": "file:///body",
                "mimeType": "text/plain",
                "text": "body",
            },
        },
    ]
    assert [block.type for block in result.content] == [
        "text",
        "image",
        "resource_link",
        "resource",
    ]
    assert result.structured_content == {"count": 1}
    assert result.has_structured_content is True
    payload = result.to_dict()
    assert payload["structured_content"] == {"count": 1}
    assert payload["content"][1] == {
        "type": "image",
        "data": "aGk=",
        "mimeType": "image/png",
    }


async def test_structured_only_tool_result_populates_legacy_result():
    result = mcp.McpClient._tool_result_from_sdk(
        types.CallToolResult(content=[], structured_content={"ok": True})
    )

    assert result.result == {"ok": True}
    assert result.structured_content == {"ok": True}


async def test_protocol_error_result_exposes_text_and_error_flag():
    result = mcp.McpClient._tool_result_from_sdk(
        types.CallToolResult(
            content=[types.TextContent(type="text", text="bad request")],
            is_error=True,
        )
    )

    assert result.success is False
    assert result.is_error is True
    assert result.error == "bad request"
    assert result.content[0].text == "bad request"


async def test_legacy_camel_case_error_flag_is_honoured():
    result = mcp.McpClient._tool_result_from_sdk(
        SimpleNamespace(
            isError=True,
            content=[types.TextContent(type="text", text="legacy failure")],
        )
    )

    assert result.success is False
    assert result.error == "legacy failure"


async def test_content_block_metadata_and_size_are_preserved():
    block = mcp._content_block(
        types.TextContent(
            type="text",
            text="héllo",
            annotations=types.Annotations(priority=0.5),
        )
    )
    image = mcp._content_block(
        types.ImageContent(type="image", data="aGk=", mime_type="image/png")
    )

    assert block.byte_size() == len("héllo".encode("utf-8"))
    assert block.annotations == {"priority": 0.5}
    assert block.to_dict()["annotations"] == {"priority": 0.5}
    assert image.byte_size() == 3
    assert image.to_dict()["mimeType"] == "image/png"


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------


async def test_execute_tool_returns_normalized_success(monkeypatch):
    seen: dict[str, object] = {}

    async def call_tool(name, arguments, **kwargs):
        seen["name"] = name
        seen["arguments"] = arguments
        seen["kwargs"] = kwargs
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="done")]
        )

    session = SimpleNamespace(call_tool=call_tool)
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session, _caps())

    result = await client.execute_tool("search", {"query": "docs"}, timeout=3)

    assert result.success is True
    assert result.result == "done"
    assert seen["name"] == "search"
    assert seen["arguments"] == {"query": "docs"}
    if mcp._CALL_TOOL_ALLOWS_INPUT_REQUIRED:
        assert seen["kwargs"] == {"allow_input_required": True}


async def test_execute_tool_fails_closed_without_tools_capability(monkeypatch):
    session = SimpleNamespace(call_tool=AsyncMock())
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session, _caps(tools=False))

    result = await client.execute_tool("search", {})

    assert result.success is False
    assert result.error
    session.call_tool.assert_not_awaited()


async def test_execute_tool_maps_timeout_without_leaking_details(monkeypatch):
    async def call_tool(name, arguments, **kwargs):
        await asyncio.sleep(10)

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(call_tool=call_tool), _caps())

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()


async def test_execute_tool_masks_unexpected_exceptions(monkeypatch):
    async def call_tool(name, arguments, **kwargs):
        raise RuntimeError("token leaked")

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(call_tool=call_tool), _caps())

    result = await client.execute_tool("fail", {})

    assert result.success is False
    assert result.error
    assert "token leaked" not in result.error


async def test_execute_tool_surfaces_input_required_without_retrying(monkeypatch):
    required = types.InputRequiredResult(
        input_requests={"1": types.ListRootsRequest()},
        request_state="state-1",
    )
    session = SimpleNamespace(call_tool=AsyncMock(return_value=required))
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session, _caps())

    result = await client.execute_tool("needs-input", {})

    assert result.success is False
    assert result.input_required is not None
    assert result.input_required.method == "tools/call"
    assert result.input_required.request_state == "state-1"
    assert "1" in result.input_required.requests
    session.call_tool.assert_awaited_once()


# ---------------------------------------------------------------------------
# Capability negotiation
# ---------------------------------------------------------------------------


async def test_read_negotiated_uses_session_properties():
    initialize = types.InitializeResult(
        protocol_version="2025-11-25",
        capabilities=types.ServerCapabilities(
            tools=types.ToolsCapability(list_changed=True),
            resources=types.ResourcesCapability(subscribe=True, list_changed=True),
            prompts=types.PromptsCapability(list_changed=True),
            completions=types.CompletionsCapability(),
        ),
        server_info=types.Implementation(name="srv", version="2.1"),
        instructions="read the docs",
    )
    session = SimpleNamespace(
        protocol_version="2025-11-25",
        server_info=initialize.server_info,
        server_capabilities=initialize.capabilities,
        instructions=initialize.instructions,
    )

    capabilities = mcp._read_negotiated(session, None)

    assert capabilities.tools is True
    assert capabilities.tools_list_changed is True
    assert capabilities.resources is True
    assert capabilities.resources_subscribe is True
    assert capabilities.resource_templates is True
    assert capabilities.prompts is True
    assert capabilities.completions is True
    assert capabilities.server_name == "srv"
    assert capabilities.server_version == "2.1"
    assert capabilities.instructions == "read the docs"
    assert capabilities.raw["tools"] == {"listChanged": True}


async def test_read_negotiated_falls_back_to_handshake_result():
    initialize = types.InitializeResult(
        protocol_version="2025-06-18",
        capabilities=types.ServerCapabilities(tools=types.ToolsCapability()),
        server_info=types.Implementation(name="legacy", version="0.9"),
    )
    session = SimpleNamespace()  # mcp 1.x sessions expose no negotiated properties

    capabilities = mcp._read_negotiated(session, initialize)

    assert capabilities.protocol_version == "2025-06-18"
    assert capabilities.tools is True
    assert capabilities.resources is False
    assert capabilities.server_name == "legacy"


async def test_negotiate_prefers_discover_when_session_supports_it(monkeypatch):
    handshake = object()
    auto = AsyncMock()

    async def fake_auto(session):
        await auto(session)

    monkeypatch.setattr(mcp, "_negotiate_auto", fake_auto)
    session = SimpleNamespace(
        send_discover=object(),
        initialize_result=handshake,
        initialize=AsyncMock(),
    )

    result = await mcp._negotiate(session)

    assert result is handshake
    auto.assert_awaited_once_with(session)
    session.initialize.assert_not_awaited()


async def test_negotiate_falls_back_to_legacy_initialize(monkeypatch):
    monkeypatch.setattr(mcp, "_negotiate_auto", AsyncMock())
    session = SimpleNamespace(initialize=AsyncMock(return_value="handshake"))

    assert await mcp._negotiate(session) == "handshake"
    session.initialize.assert_awaited_once_with()


async def test_get_capabilities_returns_negotiated_capabilities(monkeypatch):
    client = mcp.McpClient({})
    capabilities = _caps(logging=True)
    _install_open(monkeypatch, client, SimpleNamespace(), capabilities)

    assert await client.get_capabilities(timeout=1) is capabilities


async def test_operations_reject_missing_capabilities(monkeypatch):
    client = mcp.McpClient({})

    _install_open(monkeypatch, client, SimpleNamespace(), _caps(resources=False))
    with pytest.raises(mcp.McpCapabilityUnavailable) as resource_error:
        await client.enumerate_resources()
    assert resource_error.value.capability == "resources"
    with pytest.raises(mcp.McpCapabilityUnavailable):
        await client.read_resource("file:///a")

    _install_open(monkeypatch, client, SimpleNamespace(), _caps(prompts=False))
    with pytest.raises(mcp.McpCapabilityUnavailable) as prompt_error:
        await client.enumerate_prompts()
    assert prompt_error.value.capability == "prompts"
    with pytest.raises(mcp.McpCapabilityUnavailable):
        await client.get_prompt("p")

    _install_open(monkeypatch, client, SimpleNamespace(), _caps(completions=False))
    with pytest.raises(mcp.McpCapabilityUnavailable) as completion_error:
        await client.complete(
            mcp.McpCompletionReference(kind="prompt", name="p"), "x", "y"
        )
    assert completion_error.value.capability == "completions"


# ---------------------------------------------------------------------------
# Bounded enumeration
# ---------------------------------------------------------------------------


def _two_page_tool_session():
    pages = {
        None: ([_tool("first")], "cursor-2"),
        "cursor-2": ([_tool("second")], None),
    }
    calls: list[str | None] = []

    async def list_tools(*, params=None):
        cursor = params.cursor if params is not None else None
        calls.append(cursor)
        tools, next_cursor = pages[cursor]
        return SimpleNamespace(tools=tools, next_cursor=next_cursor)

    return SimpleNamespace(list_tools=list_tools), calls


async def test_enumerate_tools_resumes_from_a_start_cursor(monkeypatch):
    calls: list[str | None] = []

    async def list_tools(*, params=None):
        calls.append(params.cursor if params is not None else None)
        return SimpleNamespace(tools=[_tool("second")], next_cursor=None)

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools(start_cursor="page-2")

    assert calls == ["page-2"]
    assert [tool.name for tool in enumerated.items] == ["second"]
    assert enumerated.pages_fetched == 1


async def test_enumerate_tools_collects_all_pages(monkeypatch):
    session, calls = _two_page_tool_session()
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session, _caps())

    enumerated = await client.enumerate_tools()

    assert [tool.name for tool in enumerated.items] == ["first", "second"]
    assert enumerated.pages_fetched == 2
    assert enumerated.truncated is False
    assert calls == [None, "cursor-2"]


async def test_enumerate_tools_maps_optional_metadata(monkeypatch):
    tool = _tool(
        "search",
        title="Search",
        output_schema={"type": "object"},
        annotations=types.ToolAnnotations(read_only_hint=True),
    )

    async def list_tools(*, params=None):
        return SimpleNamespace(tools=[tool], next_cursor=None)

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    information = (await client.enumerate_tools()).items[0]

    assert information.title == "Search"
    assert information.output_schema == {"type": "object"}
    assert information.annotations == {"readOnlyHint": True}
    assert information.parameters == {"type": "object", "properties": {}}


async def test_enumerate_tools_reports_page_limit(monkeypatch):
    counter = {"value": 0}

    async def list_tools(*, params=None):
        counter["value"] += 1
        return SimpleNamespace(
            tools=[_tool(f"t{counter['value']}")],
            next_cursor=f"cursor-{counter['value']}",
        )

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools(
        limits=mcp.McpEnumerationLimits(max_pages=2, max_items=10)
    )

    assert enumerated.truncated is True
    assert enumerated.truncation_reason == "max_pages"
    assert enumerated.pages_fetched == 2
    assert enumerated.next_cursor == "cursor-2"


async def test_enumerate_tools_detects_repeated_cursor(monkeypatch):
    async def list_tools(*, params=None):
        return SimpleNamespace(tools=[_tool()], next_cursor="same")

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools(
        limits=mcp.McpEnumerationLimits(max_pages=10, max_items=10)
    )

    assert enumerated.truncated is True
    assert enumerated.truncation_reason == "cursor_loop"
    assert enumerated.pages_fetched == 2
    assert enumerated.next_cursor is None


async def test_enumerate_tools_stops_mid_page_at_item_limit(monkeypatch):
    async def list_tools(*, params=None):
        return SimpleNamespace(
            tools=[_tool("a"), _tool("b"), _tool("c")], next_cursor="next"
        )

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools(
        limits=mcp.McpEnumerationLimits(max_pages=2, max_items=2)
    )

    assert [tool.name for tool in enumerated.items] == ["a", "b"]
    assert enumerated.truncation_reason == "max_items"
    # A partly consumed page has no MCP offset to resume from.
    assert enumerated.next_cursor is None


async def test_enumerate_tools_keeps_resume_cursor_at_page_boundary(monkeypatch):
    async def list_tools(*, params=None):
        return SimpleNamespace(tools=[_tool("a"), _tool("b")], next_cursor="page-2")

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools(
        limits=mcp.McpEnumerationLimits(max_pages=2, max_items=2)
    )

    assert enumerated.truncation_reason == "max_items"
    assert enumerated.next_cursor == "page-2"


async def test_enumerate_tools_treats_empty_cursor_as_end(monkeypatch):
    async def list_tools(*, params=None):
        return SimpleNamespace(tools=[_tool()], next_cursor="")

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools()

    assert enumerated.truncated is False
    assert enumerated.pages_fetched == 1


async def test_enumerate_tools_supports_legacy_cursor_keyword(monkeypatch):
    calls: list[str | None] = []

    async def list_tools(cursor=None):
        calls.append(cursor)
        return SimpleNamespace(tools=[_tool()], next_cursor=None)

    monkeypatch.setattr(mcp, "_LIST_TOOLS_USES_PARAMS", False)
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(list_tools=list_tools), _caps())

    enumerated = await client.enumerate_tools()

    assert len(enumerated.items) == 1
    assert calls == [None]


async def test_enumeration_raises_timeout_when_nothing_was_collected():
    async def fetch(cursor):
        raise TimeoutError

    with pytest.raises(mcp.McpTimeout):
        await mcp.McpClient({})._enumerate(
            fetch,
            limits=mcp.McpEnumerationLimits(max_pages=2, max_items=2),
            deadline=mcp._Deadline(1.0, "test"),
        )


async def test_enumeration_returns_partial_items_and_resume_cursor_on_deadline():
    calls = {"value": 0}

    async def fetch(cursor):
        calls["value"] += 1
        if calls["value"] == 1:
            return [mcp.McpToolInfo("first", None, {})], "cursor-2"
        raise TimeoutError

    enumerated = await mcp.McpClient({})._enumerate(
        fetch,
        limits=mcp.McpEnumerationLimits(max_pages=5, max_items=5),
        deadline=mcp._Deadline(1.0, "test"),
    )

    assert [item.name for item in enumerated.items] == ["first"]
    assert enumerated.truncated is True
    assert enumerated.truncation_reason == "deadline"
    assert enumerated.next_cursor == "cursor-2"


async def test_enumeration_stops_when_deadline_expires_between_pages():
    async def fetch(cursor):
        await asyncio.sleep(0.01)
        return [mcp.McpToolInfo("first", None, {})], "cursor-2"

    enumerated = await mcp.McpClient({})._enumerate(
        fetch,
        limits=mcp.McpEnumerationLimits(max_pages=5, max_items=5),
        deadline=mcp._Deadline(0.001, "test"),
    )

    assert enumerated.truncated is True
    assert enumerated.truncation_reason == "deadline"
    assert enumerated.next_cursor == "cursor-2"


# ---------------------------------------------------------------------------
# Resources and resource templates
# ---------------------------------------------------------------------------


async def test_enumerate_resources_and_templates_map_protocol_fields(monkeypatch):
    resource = types.Resource(
        uri="file:///doc",
        name="doc",
        title="Doc",
        description="A document",
        mime_type="text/plain",
        size=12,
        annotations=types.Annotations(priority=0.2),
    )
    template = types.ResourceTemplate(
        uri_template="file:///{path}",
        name="files",
        description="Any file",
        mime_type="text/plain",
    )
    session = SimpleNamespace(
        list_resources=AsyncMock(
            return_value=SimpleNamespace(resources=[resource], next_cursor=None)
        ),
        list_resource_templates=AsyncMock(
            return_value=SimpleNamespace(
                resource_templates=[template], next_cursor=None
            )
        ),
    )
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session, _caps())

    resources = await client.enumerate_resources()
    templates = await client.enumerate_resource_templates()

    assert resources.items[0].to_dict() == {
        "uri": "file:///doc",
        "name": "doc",
        "title": "Doc",
        "description": "A document",
        "mimeType": "text/plain",
        "size": 12,
        "annotations": {"priority": 0.2},
    }
    assert templates.items[0].to_dict() == {
        "uriTemplate": "file:///{path}",
        "name": "files",
        "description": "Any file",
        "mimeType": "text/plain",
    }


async def test_read_resource_preserves_text_and_blob_with_verbatim_uri(monkeypatch):
    read_resource = AsyncMock(
        return_value=types.ReadResourceResult(
            contents=[
                types.TextResourceContents(
                    uri="file:///doc", text="hello", mime_type="text/plain"
                ),
                types.BlobResourceContents(
                    uri="file:///image", blob="aGk=", mime_type="image/png"
                ),
            ]
        )
    )
    client = mcp.McpClient({})
    _install_open(
        monkeypatch, client, SimpleNamespace(read_resource=read_resource), _caps()
    )

    contents = await client.read_resource("file:///doc")

    assert read_resource.await_args.args[0] == "file:///doc"
    assert contents[0].text == "hello"
    assert contents[1].blob == "aGk="
    assert contents[1].is_binary is True
    assert contents[1].byte_size() == 3


async def test_read_resource_enforces_block_and_total_limits(monkeypatch):
    read_resource = AsyncMock(
        return_value=types.ReadResourceResult(
            contents=[
                types.TextResourceContents(uri="file:///a", text="abcd"),
                types.TextResourceContents(uri="file:///b", text="efgh"),
            ]
        )
    )
    client = mcp.McpClient({})
    _install_open(
        monkeypatch, client, SimpleNamespace(read_resource=read_resource), _caps()
    )

    with pytest.raises(mcp.McpContentTooLarge) as block_error:
        await client.read_resource(
            "file:///a",
            limits=mcp.McpContentLimits(max_block_bytes=3, max_total_bytes=99),
        )
    assert block_error.value.details["bytes_received"] == 4

    with pytest.raises(mcp.McpContentTooLarge) as total_error:
        await client.read_resource(
            "file:///a",
            limits=mcp.McpContentLimits(max_block_bytes=10, max_total_bytes=7),
        )
    assert total_error.value.details["bytes_received"] == 8


async def test_read_resource_surfaces_input_required(monkeypatch):
    read_resource = AsyncMock(
        return_value=types.InputRequiredResult(
            input_requests={
                "1": types.ElicitRequest(
                    params=types.ElicitRequestFormParams(
                        mode="form", message="need", requested_schema={}
                    )
                )
            },
            request_state="state",
        )
    )
    client = mcp.McpClient({})
    _install_open(
        monkeypatch, client, SimpleNamespace(read_resource=read_resource), _caps()
    )

    with pytest.raises(mcp.McpInputRequired) as error:
        await client.read_resource("file:///a")

    assert error.value.info.method == "resources/read"
    assert error.value.info.request_state == "state"


async def test_read_resource_requires_a_uri():
    with pytest.raises(ValueError, match="Resource URI is required"):
        await mcp.McpClient({}).read_resource("   ")


async def test_read_resource_rejects_unexpanded_template_uri():
    with pytest.raises(mcp.McpInvalidRequest) as error:
        await mcp.McpClient({}).read_resource("repo://{owner}/{repo}/contents{/path*}")

    assert error.value.reason == "resource_uri"


async def test_translate_mcp_error_unwraps_nested_task_groups():
    from mcp.shared.exceptions import MCPError as SdkMcpError

    unavailable = mcp.McpCapabilityUnavailable("resources")
    nested = ExceptionGroup(
        "outer",
        [ExceptionGroup("inner", [RuntimeError("teardown"), unavailable])],
    )

    assert mcp.translate_mcp_error(nested) is unavailable
    assert mcp.translate_mcp_error(RuntimeError("transport")) is None
    assert mcp.translate_mcp_error(ExceptionGroup("noise", [RuntimeError("x")])) is None

    rejected = ExceptionGroup("session", [SdkMcpError(-32602, "unknown resource uri")])
    typed = mcp.translate_mcp_error(rejected)

    assert isinstance(typed, mcp.McpServerError)
    assert typed.rpc_code == -32602
    assert typed.invalid_request is True

    server_fault = mcp.translate_mcp_error(SdkMcpError(-32603, "boom"))
    assert isinstance(server_fault, mcp.McpServerError)
    assert server_fault.invalid_request is False


# ---------------------------------------------------------------------------
# Prompts and completion
# ---------------------------------------------------------------------------


async def test_enumerate_prompts_maps_arguments(monkeypatch):
    prompt = types.Prompt(
        name="summarize",
        title="Summarize",
        description="Summarize text",
        arguments=[
            types.PromptArgument(name="text", description="Input", required=True)
        ],
    )
    session = SimpleNamespace(
        list_prompts=AsyncMock(
            return_value=SimpleNamespace(prompts=[prompt], next_cursor=None)
        )
    )
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session, _caps())

    enumerated = await client.enumerate_prompts()

    assert enumerated.items[0].to_dict() == {
        "name": "summarize",
        "title": "Summarize",
        "description": "Summarize text",
        "arguments": [{"name": "text", "description": "Input", "required": True}],
    }


async def test_get_prompt_returns_messages_and_enforces_limits(monkeypatch):
    get_prompt = AsyncMock(
        return_value=types.GetPromptResult(
            description="A prompt",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text="hello"),
                ),
                types.PromptMessage(
                    role="assistant",
                    content=types.ImageContent(
                        type="image", data="aGk=", mime_type="image/png"
                    ),
                ),
            ],
        )
    )
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(get_prompt=get_prompt), _caps())

    prompt = await client.get_prompt("p", {"name": "x"})

    assert get_prompt.await_args.args == ("p", {"name": "x"})
    assert prompt.description == "A prompt"
    assert [message.role for message in prompt.messages] == ["user", "assistant"]
    assert prompt.messages[1].content.type == "image"
    assert prompt.to_dict()["messages"][0] == {
        "role": "user",
        "content": {"type": "text", "text": "hello"},
    }

    with pytest.raises(mcp.McpContentTooLarge):
        await client.get_prompt(
            "p", limits=mcp.McpContentLimits(max_block_bytes=1, max_total_bytes=99)
        )


async def test_get_prompt_surfaces_input_required_and_validates_name(monkeypatch):
    get_prompt = AsyncMock(
        return_value=types.InputRequiredResult(request_state="state")
    )
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(get_prompt=get_prompt), _caps())

    with pytest.raises(mcp.McpInputRequired) as error:
        await client.get_prompt("p")
    assert error.value.info.method == "prompts/get"
    with pytest.raises(ValueError, match="Prompt name is required"):
        await client.get_prompt("  ")


async def test_complete_maps_prompt_and_template_references(monkeypatch):
    seen: dict[str, object] = {}
    complete = AsyncMock(
        return_value=types.CompleteResult(
            completion=types.Completion(values=["alpha"], total=3, has_more=True)
        )
    )

    async def fake_complete(ref, argument, context_arguments=None):
        seen["ref"] = ref
        seen["argument"] = argument
        seen["context"] = context_arguments
        return complete.return_value

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(complete=fake_complete), _caps())

    prompt_result = await client.complete(
        mcp.McpCompletionReference(kind="prompt", name="p"),
        "topic",
        "al",
        context_arguments={"other": "value"},
    )
    assert isinstance(seen["ref"], types.PromptReference)
    assert seen["ref"].name == "p"
    assert seen["argument"] == {"name": "topic", "value": "al"}
    assert seen["context"] == {"other": "value"}
    assert prompt_result.to_dict() == {
        "values": ["alpha"],
        "total": 3,
        "hasMore": True,
    }

    await client.complete(
        mcp.McpCompletionReference(kind="resource_template", uri="file:///{p}"),
        "p",
        "x",
    )
    assert isinstance(seen["ref"], types.ResourceTemplateReference)
    assert seen["ref"].uri == "file:///{p}"


async def test_completion_reference_and_argument_validation():
    with pytest.raises(ValueError, match="requires 'name'"):
        mcp.McpCompletionReference(kind="prompt")
    with pytest.raises(ValueError, match="requires 'uri'"):
        mcp.McpCompletionReference(kind="resource_template")
    with pytest.raises(ValueError, match="argument name is required"):
        await mcp.McpClient({}).complete(
            mcp.McpCompletionReference(kind="prompt", name="p"), "", "x"
        )


# ---------------------------------------------------------------------------
# Callback policy
# ---------------------------------------------------------------------------


def _sampling_params(max_tokens=100, tools=None):
    return types.CreateMessageRequestParams(
        messages=[
            types.SamplingMessage(
                role="user", content=types.TextContent(type="text", text="q")
            )
        ],
        max_tokens=max_tokens,
        tools=tools,
    )


async def test_callback_defaults_advertise_nothing_and_refuse_requests():
    callbacks = mcp.McpCallbacks()
    guard = mcp._CallbackGuard(callbacks)

    assert guard.roots_enabled is False
    sampling = await guard.sampling(None, _sampling_params())
    elicitation = await guard.elicitation(
        None,
        types.ElicitRequestFormParams(mode="form", message="m", requested_schema={}),
    )
    roots = await guard.list_roots(None)

    assert sampling.code == types.INVALID_REQUEST
    assert elicitation.code == types.INVALID_REQUEST
    # No roots capability is advertised by default, so the guard never has to
    # answer a server request; if called directly it returns an empty list.
    assert isinstance(roots, types.ListRootsResult)
    assert roots.roots == []


async def test_sampling_handler_is_capped_and_returns_result():
    seen: list[int] = []

    async def sampling(context, params):
        seen.append(params.max_tokens)
        return types.CreateMessageResult(
            role="assistant",
            content=types.TextContent(type="text", text="answer"),
            model="test",
        )

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            sampling=sampling,
            policy=mcp.McpCallbackPolicy(sampling_max_tokens=10),
        )
    )

    result = await guard.sampling(None, _sampling_params(max_tokens=500))

    assert isinstance(result, types.CreateMessageResult)
    assert seen == [10]


async def test_sampling_refuses_tools_unless_explicitly_allowed():
    async def sampling(context, params):
        return types.CreateMessageResult(
            role="assistant",
            content=types.TextContent(type="text", text="answer"),
            model="test",
        )

    tool = types.Tool(name="x", input_schema={"type": "object"})
    guard = mcp._CallbackGuard(mcp.McpCallbacks(sampling=sampling))

    refused = await guard.sampling(None, _sampling_params(tools=[tool]))
    assert refused.code == types.INVALID_REQUEST

    allowed_guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            sampling=sampling,
            policy=mcp.McpCallbackPolicy(sampling_tools=True),
        )
    )
    allowed = await allowed_guard.sampling(None, _sampling_params(tools=[tool]))
    assert isinstance(allowed, types.CreateMessageResult)


async def test_sampling_failures_and_limits_are_masked():
    async def failing(context, params):
        raise RuntimeError("provider secret")

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            sampling=failing,
            policy=mcp.McpCallbackPolicy(
                max_sampling_requests=1, max_callback_seconds=0.01
            ),
        )
    )
    failed = await guard.sampling(None, _sampling_params())
    limited = await guard.sampling(None, _sampling_params())

    assert failed.code == types.INTERNAL_ERROR
    assert "provider secret" not in (failed.message or "")
    assert limited.code == types.INVALID_REQUEST

    async def slow(context, params):
        await asyncio.sleep(5)

    timeout_guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            sampling=slow,
            policy=mcp.McpCallbackPolicy(max_callback_seconds=0.01),
        )
    )
    timed_out = await timeout_guard.sampling(None, _sampling_params())
    assert timed_out.code == types.INTERNAL_ERROR


async def test_elicitation_declines_secret_fields_and_unsupported_modes():
    async def elicitation(context, params):
        return types.ElicitResult(action="accept", content={"name": "ok"})

    guard = mcp._CallbackGuard(mcp.McpCallbacks(elicitation=elicitation))

    secret = types.ElicitRequestFormParams(
        mode="form",
        message="login",
        requested_schema={
            "type": "object",
            "properties": {"api_token": {"type": "string"}},
        },
    )
    normal = types.ElicitRequestFormParams(
        mode="form",
        message="name",
        requested_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
    )
    url = types.ElicitRequestURLParams(
        mode="url", message="go", url="https://auth.example.com/start"
    )

    assert (await guard.elicitation(None, secret)).action == "decline"
    assert (await guard.elicitation(None, normal)).action == "accept"
    assert (await guard.elicitation(None, url)).code == types.INVALID_REQUEST


async def test_elicitation_url_allowlist_is_enforced():
    async def elicitation(context, params):
        return types.ElicitResult(action="accept")

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            elicitation=elicitation,
            policy=mcp.McpCallbackPolicy(
                elicitation_modes=frozenset({"form", "url"}),
                elicitation_url_hosts=frozenset({"auth.example.com"}),
            ),
        )
    )

    for url, action in [
        ("https://auth.example.com/start", "accept"),
        ("https://evil.example.com/start", "decline"),
        ("http://auth.example.com/start", "decline"),
        ("https://user:pass@auth.example.com/start", "decline"),
    ]:
        request = types.ElicitRequestURLParams(mode="url", message="go", url=url)
        assert (await guard.elicitation(None, request)).action == action


async def test_elicitation_timeout_and_limit_cancel():
    async def slow(context, params):
        await asyncio.sleep(5)

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            elicitation=slow,
            policy=mcp.McpCallbackPolicy(
                max_elicitation_requests=1, max_callback_seconds=0.01
            ),
        )
    )
    request = types.ElicitRequestFormParams(
        mode="form", message="m", requested_schema={}
    )

    assert (await guard.elicitation(None, request)).action == "cancel"
    assert (await guard.elicitation(None, request)).action == "cancel"


async def test_configured_roots_are_returned_without_a_handler():
    policy = mcp.McpCallbackPolicy(
        roots=(
            mcp.McpRoot(uri="file:///work", name="work"),
            mcp.McpRoot(uri="file:///other"),
        ),
        roots_allowlist=("file:///work",),
    )
    guard = mcp._CallbackGuard(mcp.McpCallbacks(policy=policy))

    result = await guard.list_roots(None)

    assert guard.roots_enabled is True
    assert [str(root.uri) for root in result.roots] == ["file:///work"]


async def test_roots_handler_output_is_filtered_and_errors_are_masked():
    async def roots(context):
        return types.ListRootsResult(
            roots=[
                types.Root(uri="file:///allowed"),
                types.Root(uri="file:///other"),
            ]
        )

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            roots=roots,
            policy=mcp.McpCallbackPolicy(roots_allowlist=("file:///allowed",)),
        )
    )
    allowed = await guard.list_roots(None)
    assert [str(root.uri) for root in allowed.roots] == ["file:///allowed"]

    async def failing(context):
        raise RuntimeError("disk path leaked")

    failing_guard = mcp._CallbackGuard(mcp.McpCallbacks(roots=failing))
    failed = await failing_guard.list_roots(None)
    assert failed.code == types.INTERNAL_ERROR
    assert "disk path leaked" not in (failed.message or "")

    async def slow(context):
        await asyncio.sleep(5)

    timeout_guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            roots=slow,
            policy=mcp.McpCallbackPolicy(max_callback_seconds=0.01),
        )
    )
    timed_out = await timeout_guard.list_roots(None)
    assert timed_out.code == types.INTERNAL_ERROR


async def test_notification_handler_errors_are_contained():
    seen: list[object] = []

    async def notification(message):
        seen.append(message)
        raise RuntimeError("consumer bug")

    guard = mcp._CallbackGuard(mcp.McpCallbacks(notification=notification))

    await guard.notification({"method": "notifications/tools/list_changed"})

    assert seen == [{"method": "notifications/tools/list_changed"}]


# ---------------------------------------------------------------------------
# Transport wiring and injected auth
# ---------------------------------------------------------------------------


async def test_http_headers_merge_runtime_over_config():
    client = mcp.McpClient(
        {"transport": "http", "headers": {"Authorization": "old", "X-Trace": "1"}},
        headers={"Authorization": "Bearer new"},
    )

    assert client._http_headers() == {
        "Authorization": "Bearer new",
        "X-Trace": "1",
    }
    assert mcp.McpClient({"transport": "http"})._http_headers() is None


async def test_stdio_transport_passes_reviewed_command_and_env(monkeypatch):
    seen: dict[str, object] = {}
    read_stream, write_stream = object(), object()

    @asynccontextmanager
    async def fake_stdio(params, errlog=None):
        seen["params"] = params
        seen["errlog"] = errlog
        yield read_stream, write_stream

    monkeypatch.setattr(mcp, "stdio_client", fake_stdio)
    client = mcp.McpClient(
        {
            "transport": "stdio",
            "command": "server",
            "args": ["--flag"],
            "env": {"TOKEN": "secret"},
        }
    )

    async with client._connect_stdio() as streams:
        assert streams == (read_stream, write_stream)

    params = seen["params"]
    assert (params.command, params.args, params.env) == (
        "server",
        ["--flag"],
        {"TOKEN": "secret"},
    )
    assert seen["errlog"] is sys.__stderr__


async def test_sse_transport_merges_headers_observer_and_auth(monkeypatch):
    seen: dict[str, object] = {}
    read_stream, write_stream = object(), object()
    auth = object()
    observed: list[str] = []

    @asynccontextmanager
    async def fake_sse(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        if "on_session_created" in kwargs:
            kwargs["on_session_created"]("session-1")
        yield read_stream, write_stream

    monkeypatch.setattr(mcp, "sse_client", fake_sse)
    client = mcp.McpClient(
        {
            "transport": "sse",
            "url": "https://mcp.example/sse",
            "headers": {"X-Config": "1"},
        },
        headers={"Authorization": "Bearer runtime"},
        auth=auth,
        on_session_created=observed.append,
    )

    async with client._connect_sse() as streams:
        assert streams == (read_stream, write_stream)

    assert seen["url"] == "https://mcp.example/sse"
    assert seen["headers"] == {
        "X-Config": "1",
        "Authorization": "Bearer runtime",
    }
    if mcp._SSE_ACCEPTS_AUTH:
        assert seen["auth"] is auth
    if mcp._SSE_ACCEPTS_SESSION_OBSERVER:
        assert client.last_session_id == "session-1"
        assert observed == ["session-1"]


async def test_session_observer_failure_does_not_break_transport(monkeypatch):
    if not mcp._SSE_ACCEPTS_SESSION_OBSERVER:
        pytest.skip("SDK does not expose on_session_created")

    @asynccontextmanager
    async def fake_sse(url, **kwargs):
        kwargs["on_session_created"]("session-2")
        yield object(), object()

    def observer(session_id):
        raise RuntimeError("observer bug")

    monkeypatch.setattr(mcp, "sse_client", fake_sse)
    client = mcp.McpClient(
        {"transport": "sse", "url": "https://mcp.example/sse"},
        on_session_created=observer,
    )

    async with client._connect_sse():
        pass

    assert client.last_session_id == "session-2"


async def test_http_transport_passes_headers_and_auth_to_sdk(monkeypatch):
    captured: dict[str, object] = {}
    read_stream, write_stream = object(), object()
    auth = object()

    def fake_factory(**kwargs):
        captured["factory"] = kwargs
        return _context(object())

    @asynccontextmanager
    async def fake_streamable(url, http_client=None):
        captured["url"] = url
        captured["http_client"] = http_client
        yield read_stream, write_stream, lambda: "http-session"

    monkeypatch.setattr(mcp, "create_mcp_http_client", fake_factory)
    monkeypatch.setattr(mcp, "streamablehttp_client", fake_streamable)
    client = mcp.McpClient(
        {"transport": "http", "url": "https://mcp.example/mcp"},
        headers={"Authorization": "Bearer runtime"},
        auth=auth,
    )

    async with client._connect_http() as streams:
        assert streams == (read_stream, write_stream)

    assert captured["factory"] == {
        "headers": {"Authorization": "Bearer runtime"},
        "auth": auth,
    }
    assert captured["url"] == "https://mcp.example/mcp"
    assert captured["http_client"] is not None
    assert client.last_session_id == "http-session"


async def test_http_transport_without_headers_uses_default_client(monkeypatch):
    seen: dict[str, object] = {}

    @asynccontextmanager
    async def fake_streamable(url, http_client=None):
        seen["http_client"] = http_client
        yield object(), object()

    monkeypatch.setattr(mcp, "streamablehttp_client", fake_streamable)
    client = mcp.McpClient({"transport": "http", "url": "https://mcp.example/mcp"})

    async with client._connect_http():
        pass

    assert seen["http_client"] is None


async def test_transports_require_targets_and_reject_unknown_transport():
    with pytest.raises(ValueError, match="Command is required"):
        async with mcp.McpClient({"transport": "stdio"})._connect_stdio():
            pass
    with pytest.raises(ValueError, match="URL is required"):
        async with mcp.McpClient({"transport": "sse"})._connect_sse():
            pass
    with pytest.raises(ValueError, match="URL is required"):
        async with mcp.McpClient({"transport": "http"})._connect_http():
            pass

    client = mcp.McpClient({"transport": "websocket"})
    with pytest.raises(ValueError, match="Unsupported transport: websocket"):
        async with client.connect():
            pass


# ---------------------------------------------------------------------------
# Enumeration and capability serialization
# ---------------------------------------------------------------------------


async def test_enumeration_to_dict_uses_item_serializers():
    tool = mcp.McpToolInfo("search", "d", {"type": "object"})
    enumerated = mcp.McpEnumeration(
        items=[tool],
        pages_fetched=1,
        truncated=True,
        truncation_reason="max_items",
        next_cursor="page-2",
    )

    payload = enumerated.to_dict()

    assert payload["items"] == [tool.to_dict()]
    assert payload["truncated"] is True
    assert payload["truncation_reason"] == "max_items"
    assert payload["next_cursor"] == "page-2"
    assert payload["total_items"] == 1

    custom = enumerated.to_dict(serializer=lambda item: item.name)
    assert custom["items"] == ["search"]


async def test_capability_dict_reports_template_and_raw_flags():
    capabilities = mcp.McpServerCapabilities(
        protocol_version="2025-11-25",
        tools=True,
        resources=True,
        resources_subscribe=True,
        prompts=True,
        completions=True,
        logging=True,
        raw={"tools": {}},
    )

    payload = capabilities.to_dict()

    assert payload["resource_templates"] is True
    assert payload["resources_subscribe"] is True
    assert payload["completions"] is True
    assert payload["raw_capabilities"] == {"tools": {}}
