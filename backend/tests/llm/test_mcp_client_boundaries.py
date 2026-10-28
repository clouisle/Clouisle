"""Boundary tests for the MCP client adapter.

These exercise the real adapter against purpose-built fake protocol sessions:
capability negotiation robustness, callback containment and filtering, the
connect/negotiate lifecycle with its deadlines, request-boundary error
mapping, and pagination cursor interaction. Wire-shape serialization and
helper-forwarding tests live in the primary behavior suite; this module only
covers behavior a consumer can observe.
"""

from __future__ import annotations

import asyncio
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


def _install_open(monkeypatch, client, session, capabilities=None):
    """Replace transport+handshake so request behavior is testable directly."""

    caps = capabilities or _caps()

    @asynccontextmanager
    async def fake_open(deadline):
        yield session, caps

    monkeypatch.setattr(client, "_open", fake_open)


def _install_class_open(monkeypatch, session, capabilities=None):
    """Patch the class so module-level helpers use the fake protocol session."""

    caps = capabilities or _caps()

    @asynccontextmanager
    async def fake_open(self, deadline):
        yield session, caps

    monkeypatch.setattr(mcp.McpClient, "_open", fake_open)


def _tool(name="search"):
    return types.Tool(
        name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}},
    )


def _sampling_params():
    return types.CreateMessageRequestParams(
        messages=[
            types.SamplingMessage(
                role="user", content=types.TextContent(type="text", text="q")
            )
        ],
        max_tokens=10,
    )


def _elicitation_form():
    return types.ElicitRequestFormParams(mode="form", message="m", requested_schema={})


# ---------------------------------------------------------------------------
# Negotiation robustness
# ---------------------------------------------------------------------------


async def test_read_negotiated_tolerates_unexpected_handshake_shapes():
    session = SimpleNamespace(
        protocol_version=None,
        server_info="not-a-mapping",
        server_capabilities=["not", "a", "mapping"],
        instructions=None,
    )

    capabilities = mcp._read_negotiated(session, None)

    assert capabilities.protocol_version is None
    assert capabilities.server_name is None
    assert capabilities.server_version is None
    assert capabilities.instructions is None
    assert capabilities.raw == {}
    assert capabilities.tools is False
    assert capabilities.resources is False
    assert capabilities.prompts is False
    assert capabilities.completions is False


# ---------------------------------------------------------------------------
# Callback containment and filtering
# ---------------------------------------------------------------------------


async def test_sampling_accepts_sync_results_and_explicit_errors():
    def sync_handler(context, params):
        return types.CreateMessageResult(
            role="assistant",
            content=types.TextContent(type="text", text="ok"),
            model="test",
        )

    guard = mcp._CallbackGuard(mcp.McpCallbacks(sampling=sync_handler))
    result = await guard.sampling(None, _sampling_params())
    assert isinstance(result, types.CreateMessageResult)

    error = types.ErrorData(code=types.INVALID_REQUEST, message="declined")
    guard = mcp._CallbackGuard(mcp.McpCallbacks(sampling=lambda c, p: error))
    assert await guard.sampling(None, _sampling_params()) is error


async def test_sampling_rejects_unexpected_handler_output():
    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(sampling=lambda c, p: SimpleNamespace(answer="x"))
    )

    result = await guard.sampling(None, _sampling_params())

    assert isinstance(result, types.ErrorData)
    assert result.code == types.INTERNAL_ERROR
    assert "Invalid sampling response" in (result.message or "")


async def test_elicitation_masks_handler_errors_and_validates_output():
    async def failing(context, params):
        raise RuntimeError("provider secret")

    guard = mcp._CallbackGuard(mcp.McpCallbacks(elicitation=failing))
    assert (await guard.elicitation(None, _elicitation_form())).action == "cancel"

    error = types.ErrorData(code=types.INTERNAL_ERROR, message="declined")
    guard = mcp._CallbackGuard(mcp.McpCallbacks(elicitation=lambda c, p: error))
    assert await guard.elicitation(None, _elicitation_form()) is error

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(elicitation=lambda c, p: SimpleNamespace(action="accept"))
    )
    invalid = await guard.elicitation(None, _elicitation_form())
    assert isinstance(invalid, types.ErrorData)
    assert invalid.code == types.INTERNAL_ERROR
    assert "Invalid elicitation response" in (invalid.message or "")


async def test_roots_masks_errors_and_rejects_corrupt_output():
    async def failing(context):
        raise RuntimeError("disk path leaked")

    guard = mcp._CallbackGuard(mcp.McpCallbacks(roots=failing))
    failed = await guard.list_roots(None)
    assert failed.code == types.INTERNAL_ERROR
    assert "disk path leaked" not in (failed.message or "")

    error = types.ErrorData(code=types.INTERNAL_ERROR, message="declined")
    guard = mcp._CallbackGuard(mcp.McpCallbacks(roots=lambda c: error))
    assert await guard.list_roots(None) is error

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(roots=lambda c: SimpleNamespace(roots="not-a-list"))
    )
    invalid = await guard.list_roots(None)
    assert invalid.code == types.INTERNAL_ERROR
    assert "Invalid roots response" in (invalid.message or "")


async def test_configured_roots_outside_scope_or_unserializable_are_dropped():
    class _Root:
        def __init__(self, uri):
            self.uri = uri

        def to_sdk(self):
            raise RuntimeError("bad root")

    roots = (
        _Root(uri=None),
        _Root(uri="https://example.com/work"),
        _Root(uri="file:///broken"),
        mcp.McpRoot(uri="file:///ok", name="ok"),
    )
    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(policy=mcp.McpCallbackPolicy(roots=roots))
    )

    result = await guard.list_roots(None)

    assert [str(root.uri) for root in result.roots] == ["file:///ok"]


async def test_notification_sync_handler_runs_and_slow_handler_is_cut_off():
    seen: list[object] = []

    def sync_handler(message):
        seen.append(message)

    guard = mcp._CallbackGuard(mcp.McpCallbacks(notification=sync_handler))
    assert (
        await guard.notification({"method": "notifications/tools/list_changed"}) is None
    )
    assert seen == [{"method": "notifications/tools/list_changed"}]

    async def slow(message):
        await asyncio.sleep(5)

    guard = mcp._CallbackGuard(
        mcp.McpCallbacks(
            notification=slow,
            policy=mcp.McpCallbackPolicy(max_callback_seconds=0.01),
        )
    )
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await asyncio.wait_for(guard.notification({"method": "x"}), timeout=1)
    assert result is None
    assert loop.time() - started < 0.5


async def test_secret_detection_scans_names_titles_and_descriptions():
    # The sensitive-field regex targets identifier-style forms
    # (api_key / api-key / apikey, bare token/secret/...), not prose.
    # Non-mapping schemas or properties carry no fields to inspect.
    assert mcp._schema_requests_secrets("not-a-schema") is False
    assert mcp._schema_requests_secrets({"properties": []}) is False

    assert mcp._schema_requests_secrets({"properties": {"api_key": {}}}) is True
    assert (
        mcp._schema_requests_secrets(
            {"properties": {"x": {"description": "private_key"}}}
        )
        is True
    )
    assert (
        mcp._schema_requests_secrets({"properties": {"x": {"title": "Bearer"}}}) is True
    )

    # Harmless metadata and non-string values are ignored.
    assert (
        mcp._schema_requests_secrets({"properties": {"nick": {"title": "Nickname"}}})
        is False
    )
    assert (
        mcp._schema_requests_secrets({"properties": {"x": {"description": 5}}}) is False
    )


async def test_url_and_root_gates_reject_malformed_values():
    hosts = frozenset({"auth.example.com"})

    assert mcp._url_host_allowed(None, hosts) is False
    assert mcp._url_host_allowed("", hosts) is False
    assert mcp._url_host_allowed("https://[bad", hosts) is False
    assert mcp._url_host_allowed("https://auth.example.com/start", hosts) is True

    assert mcp._root_allowed(None, ()) is False
    assert mcp._root_allowed("https://example.com/work", ()) is False
    assert mcp._root_allowed("file:///work", ()) is True


# ---------------------------------------------------------------------------
# Real connect / negotiate lifecycle
# ---------------------------------------------------------------------------


class _FakeClientSession:
    def __init__(self, *, enter_delay: float = 0.0) -> None:
        self.enter_delay = enter_delay
        self.entered = False
        self.exited = False
        self.protocol_version = "2025-11-25"
        self.server_info = {"name": "fake-server", "version": "9.9"}
        self.server_capabilities = {
            "tools": {"listChanged": True},
            "resources": {"subscribe": True},
            "prompts": {},
            "completions": {},
        }
        self.instructions = "Read the docs"

    async def __aenter__(self):
        if self.enter_delay:
            await asyncio.sleep(self.enter_delay)
        self.entered = True
        return self

    async def __aexit__(self, *exc_info):
        self.exited = True
        return False

    async def initialize(self):
        return None


def _install_fake_session(monkeypatch, *, enter_delay: float = 0.0):
    def factory(read_stream, write_stream, **kwargs):
        return _FakeClientSession(enter_delay=enter_delay)

    monkeypatch.setattr(mcp, "ClientSession", factory)


@asynccontextmanager
async def _fake_transport():
    yield object(), object()


async def test_connect_negotiates_a_real_session_and_reports_capabilities(monkeypatch):
    _install_fake_session(monkeypatch)

    client = mcp.McpClient(
        {}, timeouts=mcp.McpTimeouts(connect=1, request=1, enumeration=1)
    )
    monkeypatch.setattr(client, "_transport", _fake_transport)

    async with client.connect(timeout=1) as session:
        assert isinstance(session, _FakeClientSession)
        assert session.entered is True
        assert session.exited is False
    assert session.exited is True

    capabilities = await client.get_capabilities(timeout=1)
    assert capabilities.protocol_version == "2025-11-25"
    assert capabilities.server_name == "fake-server"
    assert capabilities.server_version == "9.9"
    assert capabilities.instructions == "Read the docs"
    assert capabilities.tools is True
    assert capabilities.tools_list_changed is True
    assert capabilities.resources_subscribe is True
    assert capabilities.completions is True


async def test_connect_maps_transport_timeout_to_mcp_timeout(monkeypatch):
    @asynccontextmanager
    async def slow_transport():
        await asyncio.sleep(0.5)
        yield object(), object()

    client = mcp.McpClient(
        {}, timeouts=mcp.McpTimeouts(connect=0.02, request=1, enumeration=1)
    )
    monkeypatch.setattr(client, "_transport", slow_transport)

    with pytest.raises(mcp.McpTimeout) as error:
        async with client.connect(timeout=0.05):
            pass

    assert "Timed out connecting" in str(error.value)
    assert error.value.details["timeout_seconds"] == pytest.approx(0.02)


async def test_connect_maps_initialization_timeout_to_mcp_timeout(monkeypatch):
    _install_fake_session(monkeypatch, enter_delay=0.5)

    client = mcp.McpClient(
        {}, timeouts=mcp.McpTimeouts(connect=0.02, request=1, enumeration=1)
    )
    monkeypatch.setattr(client, "_transport", _fake_transport)

    with pytest.raises(mcp.McpTimeout) as error:
        async with client.connect(timeout=0.05):
            pass

    assert "initialization" in str(error.value)
    assert error.value.details["timeout_seconds"] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# Request-boundary error mapping
# ---------------------------------------------------------------------------


async def test_read_resource_prompt_and_completion_map_request_timeouts(monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(5)

    timeouts = mcp.McpTimeouts(connect=1, request=0.02, enumeration=1)

    client = mcp.McpClient({}, timeouts=timeouts)
    _install_open(monkeypatch, client, SimpleNamespace(read_resource=slow))
    with pytest.raises(mcp.McpTimeout) as read_error:
        await client.read_resource("file:///a", timeout=0.02)
    assert "reading MCP resource" in str(read_error.value)
    assert 0 < read_error.value.details["timeout_seconds"] <= 0.02

    client = mcp.McpClient({}, timeouts=timeouts)
    _install_open(monkeypatch, client, SimpleNamespace(get_prompt=slow))
    with pytest.raises(mcp.McpTimeout) as prompt_error:
        await client.get_prompt("p", timeout=0.02)
    assert "fetching MCP prompt" in str(prompt_error.value)

    client = mcp.McpClient({}, timeouts=timeouts)
    _install_open(monkeypatch, client, SimpleNamespace(complete=slow))
    with pytest.raises(mcp.McpTimeout) as complete_error:
        await client.complete(
            mcp.McpCompletionReference(kind="prompt", name="p"),
            "topic",
            "a",
            timeout=0.02,
        )
    assert "completing MCP argument" in str(complete_error.value)


async def test_complete_accepts_legacy_camelcase_has_more(monkeypatch):
    async def complete(**kwargs):
        return SimpleNamespace(
            completion=SimpleNamespace(values=["a"], total="3", hasMore=True)
        )

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(complete=complete))

    result = await client.complete(
        mcp.McpCompletionReference(kind="prompt", name="p"), "topic", "a"
    )

    # A non-integer total is dropped rather than leaked into the payload.
    assert result.total is None
    assert result.has_more is True
    assert result.to_dict() == {"values": ["a"], "hasMore": True}


async def test_tool_input_required_is_detected_from_result_type_alone(monkeypatch):
    async def call_tool(name, arguments, **kwargs):
        return SimpleNamespace(
            result_type="input_required",
            input_requests=["not", "a", "mapping"],
            request_state=123,
        )

    client = mcp.McpClient({})
    _install_open(monkeypatch, client, SimpleNamespace(call_tool=call_tool))

    result = await client.execute_tool("needs-input", {})

    assert result.success is False
    info = result.input_required
    assert info is not None
    assert info.method == "tools/call"
    assert info.requests == {}
    assert info.request_state is None


async def test_execute_tool_maps_an_escaping_client_timeout(monkeypatch):
    @asynccontextmanager
    async def timing_out(deadline):
        raise TimeoutError
        yield  # pragma: no cover - unreachable, keeps the CM a generator

    client = mcp.McpClient({})
    monkeypatch.setattr(client, "_open", timing_out)

    result = await client.execute_tool("slow", {}, timeout=2)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Pagination interaction
# ---------------------------------------------------------------------------


async def test_enumerate_mcp_tools_starts_from_a_cursor(monkeypatch):
    seen: list[str | None] = []

    async def list_tools(*, params=None):
        seen.append(params.cursor if params is not None else None)
        return SimpleNamespace(tools=[_tool("second")], next_cursor=None)

    _install_class_open(monkeypatch, SimpleNamespace(list_tools=list_tools))

    enumerated = await mcp.enumerate_mcp_tools(
        {"transport": "stdio", "command": "server"},
        start_cursor="page-2",
    )

    assert [tool.name for tool in enumerated.items] == ["second"]
    assert enumerated.pages_fetched == 1
    assert seen == ["page-2"]
