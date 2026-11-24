"""Behavioral tests for the hand-rolled MCP client task loop.

The installed SDK has no client task API, so these tests pin the behavior of
the module that stands in for it: the create -> poll -> result sequence,
cancellation, and every way the loop must stay bounded.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import mcp.types as types
import pytest
from mcp.shared.exceptions import MCPError

from app.llm.tools import mcp_client, mcp_tasks
from app.llm.tools.mcp_client import McpServerError, McpTimeout

pytestmark = pytest.mark.asyncio

TASK_ID = "task-1"
CREATED_AT = "2025-05-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fakes: the parts of a live session the task loop actually uses
# ---------------------------------------------------------------------------


def _task(status: str = "working", *, message: str | None = None) -> types.Task:
    return types.Task(
        task_id=TASK_ID,
        status=status,
        status_message=message,
        created_at=CREATED_AT,
        last_updated_at=CREATED_AT,
        ttl=None,
    )


def _task_payload(**overrides) -> dict:
    """The wire shape of ``CreateTaskResult.task`` (``ttl`` is a required key)."""
    return _task(**overrides).model_dump(by_alias=True, mode="json")


def _call_result(text: str = "done") -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


def _policy(**overrides) -> mcp_tasks.McpTaskPolicy:
    values: dict = {
        "enabled": True,
        "poll_interval": 0.01,
        "timeout": 2.0,
        "max_polls": 10,
    }
    values.update(overrides)
    return mcp_tasks.McpTaskPolicy(**values)


class _FakeDispatcher:
    """Stands in for the session's raw JSON-RPC channel."""

    def __init__(self, *, response=None, error: BaseException | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict, dict]] = []

    async def send_raw_request(self, method, params, opts=None):
        self.calls.append((method, params, dict(opts or {})))
        if self.error is not None:
            raise self.error
        return self.response


class _FakeSession:
    """A ``ClientSession`` look-alike driven by scripted task statuses."""

    protocol_version = "2025-11-25"

    def __init__(
        self,
        *,
        dispatcher=None,
        statuses: tuple[str, ...] = (),
        result: types.CallToolResult | None = None,
        cancel_error: BaseException | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._statuses = list(statuses)
        self._result = result or _call_result()
        self._cancel_error = cancel_error
        self.methods: list[str] = []
        self.sync_calls: list[tuple[str, dict | None, dict]] = []
        # Failures a scripted poll can raise instead of answering.
        self.fail_get_task: BaseException | None = None
        self.hang_get_task = False

    async def send_request(
        self, request, result_type, request_read_timeout_seconds=None
    ):
        self.methods.append(type(request).__name__)
        if isinstance(request, types.CancelTaskRequest):
            if self._cancel_error is not None:
                raise self._cancel_error
            return types.CancelTaskResult(
                task_id=request.params.task_id,
                status="cancelled",
                created_at=CREATED_AT,
                last_updated_at=CREATED_AT,
                ttl=None,
            )
        if isinstance(request, types.GetTaskRequest):
            if self.hang_get_task:
                await asyncio.sleep(3600)
            if self.fail_get_task is not None:
                raise self.fail_get_task
            status = (
                self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
            )
            return types.GetTaskResult(
                task_id=request.params.task_id,
                status=status,
                created_at=CREATED_AT,
                last_updated_at=CREATED_AT,
                ttl=None,
            )
        if isinstance(request, types.GetTaskPayloadRequest):
            return self._result
        raise AssertionError(f"unexpected request {type(request).__name__}")

    async def call_tool(self, name, arguments=None, **kwargs):
        self.sync_calls.append((name, arguments, dict(kwargs)))
        return self._result


def _session(**kwargs) -> _FakeSession:
    kwargs.setdefault("dispatcher", _FakeDispatcher(response={"task": _task_payload()}))
    return _FakeSession(**kwargs)


# ---------------------------------------------------------------------------
# Happy path: create -> poll -> result
# ---------------------------------------------------------------------------


async def test_task_is_created_polled_and_its_result_returned():
    dispatcher = _FakeDispatcher(response={"task": _task_payload()})
    session = _FakeSession(dispatcher=dispatcher, statuses=("working", "completed"))

    result = await mcp_tasks.call_tool_with_tasks(
        session, "index_video", {"url": "https://example.com/v"}, _policy()
    )

    assert isinstance(result, types.CallToolResult)
    assert result.content[0].text == "done"
    assert session.methods == [
        "GetTaskRequest",
        "GetTaskRequest",
        "GetTaskPayloadRequest",
    ]
    assert session.sync_calls == []

    method, params, opts = dispatcher.calls[0]
    assert method == "tools/call"
    assert params["name"] == "index_video"
    assert params["arguments"] == {"url": "https://example.com/v"}
    assert params["task"] == {}
    assert opts["headers"] == {"MCP-Protocol-Version": "2025-11-25"}
    assert opts["timeout"] == 2.0


async def test_a_session_without_a_negotiated_version_stays_synchronous():
    """``tasks/*`` exists on one revision only; anything else never asks."""
    dispatcher = _FakeDispatcher(response={"task": _task_payload(status="completed")})
    session = _FakeSession(dispatcher=dispatcher)
    session.protocol_version = None

    await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert dispatcher.calls == []
    assert [call[0] for call in session.sync_calls] == ["index"]


async def test_a_modern_session_stays_synchronous():
    """2026-07-28 defines no task capability: no raw request is attempted."""
    dispatcher = _FakeDispatcher(response={"task": _task_payload(status="completed")})
    session = _FakeSession(dispatcher=dispatcher)
    session.protocol_version = "2026-07-28"

    await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert dispatcher.calls == []
    assert [call[0] for call in session.sync_calls] == ["index"]


async def test_a_task_that_is_already_complete_is_not_polled():
    dispatcher = _FakeDispatcher(response={"task": _task_payload(status="completed")})
    session = _FakeSession(dispatcher=dispatcher)

    result = await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert result.content[0].text == "done"
    assert session.methods == ["GetTaskPayloadRequest"]


# ---------------------------------------------------------------------------
# Bounds: deadline, poll cap, cancel
# ---------------------------------------------------------------------------


async def test_deadline_exhaustion_cancels_the_task_and_times_out():
    session = _session(statuses=("working",))

    with pytest.raises(McpTimeout) as excinfo:
        await mcp_tasks.call_tool_with_tasks(
            session,
            "index",
            {},
            _policy(poll_interval=0.02, timeout=0.05, max_polls=99),
        )

    assert "did not complete" in str(excinfo.value)
    assert excinfo.value.details["timeout_seconds"] == 0.05
    assert "CancelTaskRequest" in session.methods


async def test_poll_cap_exhaustion_cancels_the_task_and_times_out():
    session = _session(statuses=("working",))

    with pytest.raises(McpTimeout):
        await mcp_tasks.call_tool_with_tasks(
            session, "index", {}, _policy(poll_interval=0.001, timeout=60, max_polls=2)
        )

    assert session.methods.count("GetTaskRequest") == 2
    assert session.methods[-1] == "CancelTaskRequest"


async def test_cancel_failure_does_not_mask_the_timeout():
    session = _session(
        statuses=("working",),
        cancel_error=MCPError(code=types.METHOD_NOT_FOUND, message="nope"),
    )

    with pytest.raises(McpTimeout):
        await mcp_tasks.call_tool_with_tasks(
            session,
            "index",
            {},
            _policy(poll_interval=0.001, timeout=0.02, max_polls=99),
        )

    assert "CancelTaskRequest" in session.methods


async def test_caller_budget_caps_the_task_deadline():
    """A deadline longer than the caller's budget would leave the task running."""
    policy = _policy(poll_interval=0.001, timeout=600, max_polls=999)
    session = _session(statuses=("working",))

    with pytest.raises(McpTimeout) as excinfo:
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, policy, budget=2.5)

    assert excinfo.value.details["timeout_seconds"] == pytest.approx(0.5)
    assert "CancelTaskRequest" in session.methods


async def test_a_budget_below_the_cancel_reserve_still_terminates():
    policy = _policy(poll_interval=0.001, timeout=600, max_polls=999)
    session = _session(statuses=("working",))

    with pytest.raises(McpTimeout) as excinfo:
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, policy, budget=0.05)

    assert excinfo.value.details["timeout_seconds"] == 0.001


async def test_input_required_task_is_cancelled_and_reported():
    session = _session(statuses=("input_required",))

    with pytest.raises(McpServerError) as excinfo:
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert "requires client input" in str(excinfo.value)
    assert "CancelTaskRequest" in session.methods


async def test_failed_task_is_reported_with_the_server_reason():
    session = _session(statuses=("failed",))

    with pytest.raises(McpServerError) as excinfo:
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert "ended as failed" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Failure safety: the synchronous path keeps working
# ---------------------------------------------------------------------------


async def test_refused_task_request_falls_back_to_the_synchronous_call():
    dispatcher = _FakeDispatcher(
        error=MCPError(code=types.METHOD_NOT_FOUND, message="Method not found")
    )
    session = _FakeSession(dispatcher=dispatcher)

    result = await mcp_tasks.call_tool_with_tasks(session, "index", {"a": 1}, _policy())

    assert result.content[0].text == "done"
    assert dispatcher.calls[0][0] == "tools/call"
    assert session.sync_calls == [("index", {"a": 1}, {})]


async def test_fallback_keeps_the_callers_progress_callback():
    """Progress rides the same kwargs, so a fallback must not drop it.

    ``McpClient.execute_tool`` merges its progress callback into the options it
    hands ``call_tool_with_tasks``; the synchronous paths pass those options
    straight to ``session.call_tool``, which is what makes a server progress
    notification reach the run event stream even with tasks enabled.
    """
    callback = object()
    dispatcher = _FakeDispatcher(
        error=MCPError(code=types.METHOD_NOT_FOUND, message="Method not found")
    )
    session = _FakeSession(dispatcher=dispatcher)

    await mcp_tasks.call_tool_with_tasks(
        session, "index", {}, _policy(), progress_callback=callback
    )

    assert session.sync_calls == [("index", {}, {"progress_callback": callback})]


async def test_inline_answer_also_keeps_the_progress_callback():
    dispatcher = _FakeDispatcher(
        response={"content": [{"type": "text", "text": "inline"}], "isError": False}
    )
    session = _FakeSession(dispatcher=dispatcher)

    result = await mcp_tasks.call_tool_with_tasks(
        session, "index", {}, _policy(), progress_callback="cb"
    )

    # The augmented request already carried the options, so no second call.
    assert result.content[0].text == "inline"
    assert session.sync_calls == []
    assert dispatcher.calls[0][1]["name"] == "index"


async def test_transport_failure_of_the_augmented_call_propagates():
    """A timeout may follow real work, so it must never be retried inline."""
    dispatcher = _FakeDispatcher(error=TimeoutError())
    session = _FakeSession(dispatcher=dispatcher)

    with pytest.raises(TimeoutError):
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert session.sync_calls == []


async def test_server_that_answers_inline_keeps_its_result():
    dispatcher = _FakeDispatcher(
        response={"content": [{"type": "text", "text": "inline"}], "isError": False}
    )
    session = _FakeSession(dispatcher=dispatcher)

    result = await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert result.content[0].text == "inline"
    assert session.sync_calls == []


@pytest.mark.parametrize("dispatcher", [None, object()])
async def test_session_without_a_raw_channel_falls_back(dispatcher):
    session = _FakeSession(dispatcher=dispatcher)

    result = await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert result.content[0].text == "done"
    assert len(session.sync_calls) == 1
    assert session.methods == []


async def test_disabled_policy_never_touches_the_task_machinery():
    dispatcher = _FakeDispatcher(response={"task": _task_payload()})
    session = _FakeSession(dispatcher=dispatcher)

    await mcp_tasks.call_tool_with_tasks(
        session, "index", {}, mcp_tasks.DEFAULT_TASK_POLICY
    )

    assert dispatcher.calls == []
    assert len(session.sync_calls) == 1


async def test_sdk_without_task_support_never_touches_the_task_machinery(monkeypatch):
    monkeypatch.setattr(mcp_tasks, "TASKS_SDK_READY", False)
    dispatcher = _FakeDispatcher(response={"task": _task_payload()})
    session = _FakeSession(dispatcher=dispatcher)

    await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert dispatcher.calls == []
    assert len(session.sync_calls) == 1


# ---------------------------------------------------------------------------
# McpClient wiring
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _fake_transport():
    yield object(), object()


async def test_open_uses_the_task_capable_session_only_when_enabled(monkeypatch):
    """A live session needs real streams, so the chosen class is what we assert."""
    opened: list[type] = []

    class _StubSession:
        protocol_version = "2025-11-25"
        server_info = {"name": "stub", "version": "1.0"}
        server_capabilities = {"tools": {}}
        instructions = None

        def __init__(self, *args, **kwargs) -> None:
            opened.append(type(self))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def initialize(self):
            return None

    monkeypatch.setattr(mcp_client, "task_session_class", lambda policy: _StubSession)
    client = mcp_client.McpClient({"enable_tasks": True})
    monkeypatch.setattr(client, "_transport", _fake_transport)

    await client.get_capabilities(timeout=1)

    assert opened == [_StubSession]


async def test_an_sdk_request_timeout_never_replays_the_call():
    """A delivered request whose answer timed out may already have run."""
    dispatcher = _FakeDispatcher(
        error=MCPError(code=types.REQUEST_TIMEOUT, message="Request timed out")
    )
    session = _FakeSession(dispatcher=dispatcher)

    with pytest.raises(MCPError):
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert session.sync_calls == []


async def test_the_augmented_request_forwards_the_progress_callback():
    """The raw path must translate ``progress_callback`` into ``on_progress``."""
    callback = object()
    dispatcher = _FakeDispatcher(
        response={"content": [{"type": "text", "text": "inline"}], "isError": False}
    )
    session = _FakeSession(dispatcher=dispatcher)

    await mcp_tasks.call_tool_with_tasks(
        session, "index", {}, _policy(), progress_callback=callback
    )

    assert dispatcher.calls[0][2]["on_progress"] is callback


async def test_a_failing_poll_cancels_the_accepted_task():
    """Every exceptional exit releases the server task; a durable one persists."""
    dispatcher = _FakeDispatcher(response={"task": _task_payload()})
    session = _FakeSession(dispatcher=dispatcher, statuses=("working",))
    session.fail_get_task = RuntimeError("poll transport died")

    with pytest.raises(RuntimeError):
        await mcp_tasks.call_tool_with_tasks(session, "index", {}, _policy())

    assert "CancelTaskRequest" in session.methods


async def test_caller_cancellation_cancels_the_accepted_task():
    dispatcher = _FakeDispatcher(response={"task": _task_payload()})
    session = _FakeSession(dispatcher=dispatcher, statuses=("working",))
    session.hang_get_task = True

    task = asyncio.create_task(
        mcp_tasks.call_tool_with_tasks(
            session, "index", {}, _policy(poll_interval=0.01, timeout=30.0)
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "CancelTaskRequest" in session.methods


async def test_a_non_string_version_sends_no_protocol_header():
    """A malformed version must never be stamped onto the wire."""
    dispatcher = _FakeDispatcher(response={"task": _task_payload(status="completed")})
    session = _FakeSession(dispatcher=dispatcher)
    session.protocol_version = 20251125

    await mcp_tasks._start_task(session, "index", {}, 5.0, {})

    assert "headers" not in dispatcher.calls[0][2]
