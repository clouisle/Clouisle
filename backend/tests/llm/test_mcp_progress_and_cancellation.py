"""Progress reporting and explicit cancellation for MCP tool calls.

Two consumer-visible contracts, both exercised against fake sessions:

* a tool call reports throttled progress only when its runtime supplied a
  sink, and a failing sink never changes the result;
* a timeout or an interrupt tells the server to stop working (best effort)
  while the caller still sees exactly the error it saw before.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import mcp.types as types
import pytest

from app.llm.tools import mcp_client as mcp
from app.llm.tools import mcp_tasks

pytestmark = pytest.mark.asyncio


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


def _install_open(monkeypatch, client, session, capabilities=None):
    @asynccontextmanager
    async def fake_open(deadline):
        yield session, capabilities or _caps()

    monkeypatch.setattr(client, "_open", fake_open)


def _ok_result(text: str = "done"):
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


class _RecordingSession:
    """Fake ClientSession that records notifications and progress callbacks."""

    def __init__(self, *, call_tool=None, pending=None, notify=None):
        self.kwargs: dict[str, object] = {}
        self.notifications: list[object] = []
        self._call_tool = call_tool
        self._notify = notify
        if pending is not None:
            self._dispatcher = SimpleNamespace(_pending=pending)

    async def call_tool(self, name, arguments, **kwargs):
        self.kwargs = kwargs
        if self._call_tool is not None:
            return await self._call_tool(name, arguments, **kwargs)
        return _ok_result()

    async def send_notification(self, notification):
        self.notifications.append(notification)
        if self._notify is not None:
            await self._notify(notification)


# ---------------------------------------------------------------------------
# Progress sink wiring
# ---------------------------------------------------------------------------


async def test_execute_tool_without_a_sink_sends_no_progress_callback(monkeypatch):
    session = _RecordingSession()
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("search", {})

    assert result.success is True
    assert "progress_callback" not in session.kwargs


async def test_execute_tool_forwards_a_throttled_progress_callback(monkeypatch):
    updates: list[mcp.McpToolProgress] = []

    async def sink(update):
        updates.append(update)

    async def call_tool(_name, _arguments, **kwargs):
        callback = kwargs["progress_callback"]
        await callback(1.0, 4.0, "step 1")
        await callback(2.0, 4.0, "step 2")
        await callback(4.0, 4.0, "done")
        return _ok_result()

    monkeypatch.setattr(mcp, "PROGRESS_MIN_INTERVAL_SECONDS", 3600.0)
    session = _RecordingSession(call_tool=call_tool)
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("search", {}, progress=sink)

    assert result.success is True
    # The first tick leads, the second is coalesced by the interval, and the
    # completion tick always passes so the UI can settle on 100%.
    assert [(item.progress, item.total, item.message) for item in updates] == [
        (1.0, 4.0, "step 1"),
        (4.0, 4.0, "done"),
    ]


async def test_progress_survives_the_task_enabled_synchronous_path(monkeypatch):
    """The task loop's fallbacks must not swallow the caller's progress callback.

    With tasks enabled the call goes through ``mcp_tasks.call_tool_with_tasks``;
    a session it cannot drive as a task (here: no raw channel) falls back to the
    plain call, which still has to carry the progress options.
    """

    async def sink(_update):
        raise AssertionError("sink must not be called")

    monkeypatch.setattr(mcp_tasks.settings, "MCP_TASKS_ENABLED", True)
    monkeypatch.setattr(mcp_tasks, "TASKS_SDK_READY", True)
    session = _RecordingSession()
    client = mcp.McpClient({"enable_tasks": True})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("search", {}, progress=sink)

    assert result.success is True
    assert "progress_callback" in session.kwargs


async def test_progress_callback_is_skipped_when_the_sdk_cannot_take_it(
    monkeypatch,
):
    monkeypatch.setattr(mcp, "_CALL_TOOL_ACCEPTS_PROGRESS", False)
    session = _RecordingSession()
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    async def sink(_update):
        raise AssertionError("sink must not be called")

    result = await client.execute_tool("search", {}, progress=sink)

    assert result.success is True
    assert "progress_callback" not in session.kwargs


async def test_a_failing_sink_never_fails_the_tool_call(monkeypatch):
    async def call_tool(_name, _arguments, **kwargs):
        await kwargs["progress_callback"](0.5, 1.0, "half")
        return _ok_result("still fine")

    async def sink(_update):
        raise RuntimeError("renderer exploded")

    session = _RecordingSession(call_tool=call_tool)
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("search", {}, progress=sink)

    assert result.success is True
    assert result.result == "still fine"


async def test_repeated_identical_ticks_are_dropped(monkeypatch):
    updates: list[mcp.McpToolProgress] = []

    async def sink(update):
        updates.append(update)

    monkeypatch.setattr(mcp, "PROGRESS_MIN_INTERVAL_SECONDS", 0.0)
    reporter = mcp._ProgressReporter(sink)

    await reporter(1.0, None, None)
    await reporter(1.0, None, None)

    assert len(updates) == 1
    assert updates[0].total is None


async def test_progress_callback_survives_an_input_required_retry(monkeypatch):
    """An MRTR continuation is the same call, so it keeps reporting progress."""

    pushed: list[mcp.McpToolProgress] = []
    calls: list[dict[str, object]] = []
    parked = types.InputRequiredResult(
        input_requests={
            "q1": types.ElicitRequest(
                params=types.ElicitRequestFormParams(
                    message="Which environment?",
                    requestedSchema={"type": "object", "properties": {}},
                )
            )
        },
        request_state="state-1",
    )

    async def call_tool(_name, _arguments, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return parked
        return _ok_result()

    async def elicit(_context, _params):
        return types.ElicitResult(action="accept", content={"choice": "beta"})

    async def sink(update):
        pushed.append(update)

    session = _RecordingSession(call_tool=call_tool)
    client = mcp.McpClient({}, callbacks=mcp.McpCallbacks(elicitation=elicit))
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool(
        "search", {}, resolve_input_required=True, progress=sink
    )

    assert result.success is True
    assert len(calls) == 2
    # Both halves of the round trip carry the same reporter, so a server that
    # keeps working after the answer still reports progress.
    assert calls[0]["progress_callback"] is calls[1]["progress_callback"]
    await calls[1]["progress_callback"](1.0, 1.0, None)
    assert [item.progress for item in pushed] == [1.0]


async def test_execute_mcp_tool_forwards_the_sink_to_the_client(monkeypatch):
    seen: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.client_args = args

        async def execute_tool(self, *args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs
            return mcp.McpToolResult(success=True)

    monkeypatch.setattr(mcp, "_client", lambda *args, **kwargs: _FakeClient())

    async def sink(_update):
        return None

    result = await mcp.execute_mcp_tool({}, "search", {}, progress=sink)

    assert result.success is True
    assert seen["args"] == ("search", {}, 60.0)
    assert seen["kwargs"]["progress"] is sink


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def _cancel_params(notification):
    assert isinstance(notification, types.CancelledNotification)
    return notification.params


async def test_timeout_cancels_the_in_flight_request(monkeypatch):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    session = _RecordingSession(call_tool=call_tool, pending={7: object()})
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()
    params = _cancel_params(session.notifications[0])
    assert params.request_id == 7
    assert params.reason == "tool call timed out"


async def test_interrupt_cancels_the_in_flight_request_and_reraises(monkeypatch):
    started = asyncio.Event()

    async def call_tool(_name, _arguments, **_kwargs):
        started.set()
        await asyncio.sleep(30)

    session = _RecordingSession(call_tool=call_tool, pending={11: object()})
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    task = asyncio.ensure_future(client.execute_tool("slow", {}, timeout=30))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    params = _cancel_params(session.notifications[0])
    assert params.request_id == 11
    assert params.reason == "tool call interrupted"


async def test_cancellation_uses_the_older_sdk_pending_shape(monkeypatch):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    session = _RecordingSession(call_tool=call_tool)
    session._response_streams = {3: object()}
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert _cancel_params(session.notifications[0]).request_id == 3


async def test_cancellation_is_skipped_without_a_known_request_id(monkeypatch):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    session = _RecordingSession(call_tool=call_tool)
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()
    assert session.notifications == []


async def test_cancellation_is_skipped_when_pending_requests_are_ambiguous(
    monkeypatch,
):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    session = _RecordingSession(call_tool=call_tool, pending={1: object(), 2: object()})
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert session.notifications == []


async def test_cancellation_is_skipped_when_the_sdk_cannot_express_it(
    monkeypatch,
):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    monkeypatch.setattr(mcp.types, "CancelledNotification", None)
    session = _RecordingSession(call_tool=call_tool, pending={5: object()})
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert session.notifications == []


async def test_a_dead_session_still_surfaces_the_timeout_to_the_caller(
    monkeypatch,
):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    async def notify(_notification):
        raise RuntimeError("transport is gone")

    session = _RecordingSession(
        call_tool=call_tool, pending={5: object()}, notify=notify
    )
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()


async def test_a_hung_notification_write_cannot_hold_the_timeout(monkeypatch):
    async def call_tool(_name, _arguments, **_kwargs):
        await asyncio.sleep(10)

    async def notify(_notification):
        await asyncio.sleep(30)

    monkeypatch.setattr(mcp, "CANCEL_NOTIFY_TIMEOUT_SECONDS", 0.01)
    session = _RecordingSession(
        call_tool=call_tool, pending={5: object()}, notify=notify
    )
    client = mcp.McpClient({})
    _install_open(monkeypatch, client, session)

    result = await client.execute_tool("slow", {}, timeout=0.02)

    assert result.success is False
    assert "timed out" in (result.error or "").lower()


async def test_discarding_a_cancelled_task_result_does_not_raise():
    future = asyncio.get_running_loop().create_future()
    future.cancel()
    mcp._discard_task_result(future)
    assert future.cancelled() is True

    completed = asyncio.ensure_future(asyncio.sleep(0))
    await completed
    mcp._discard_task_result(completed)
    assert completed.done() is True
