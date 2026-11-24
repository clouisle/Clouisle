"""Client-side MCP tasks (``tasks/*``) for long-running server tools.

Why this module exists
----------------------
``mcp`` 2.3.0 ships the task *models* (``Task``, ``CreateTaskResult``,
``GetTaskRequest``, ``CancelTaskRequest`` ...) but no client-side API:
``ClientSession`` has no task method, never declares the ``tasks`` client
capability, and its ``tools/call`` result surface rejects a task-shaped reply.
A server therefore creates a task only when the client hand-rolls the JSON-RPC
sequence, which is what this module does:

1. advertise ``capabilities.tasks`` by overriding the SDK's capability hook;
2. send a task-augmented ``tools/call`` (``params.task``) and, when the answer
   is a ``CreateTaskResult``, poll ``tasks/get`` until the task is terminal;
3. fetch the payload with ``tasks/result``, or ``tasks/cancel`` when the poll
   bounds are exhausted.

Only ``tasks/cancel`` is declared in the capability: this adapter sends it and
never ``tasks/list``, and it never augments its own sampling/elicitation
requests. ``tasks/*`` is defined by protocol revision 2025-11-25 only, so a
session negotiated on any other revision advertises nothing.

Opt-in and fail closed
----------------------
Declaring the capability changes what the server does with *every* call of that
tool, so it takes two switches: ``MCP_TASKS_ENABLED`` (platform-wide, default
off) and ``enable_tasks`` in the server's ``mcp_config``. Every step also
degrades safely: when the SDK lacks the task models or the capability hook, or
the server refuses the task-augmented request, the caller keeps the existing
synchronous path. A task that *was* created is never re-executed; it is polled,
cancelled or reported as failed, because replaying a tool call can duplicate
side effects.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import mcp.types as types
from mcp import ClientSession

from app.core.config import settings

if TYPE_CHECKING:
    from mcp.shared.dispatcher import CallOptions

try:  # mcp >= 2.x: JSON-RPC errors reported by the server.
    from mcp.shared.exceptions import MCPError as _SdkMcpError
except ImportError:  # pragma: no cover - the SDK always ships this module
    _SdkMcpError = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_TASK_POLICY",
    "McpTaskPolicy",
    "TASKS_PROTOCOL_VERSION",
    "TASKS_SDK_READY",
    "call_tool_with_tasks",
    "capability_for",
    "resolve_task_policy",
    "task_session_class",
]

TASKS_PROTOCOL_VERSION = "2025-11-25"
"""The only protocol revision that defines ``tasks/*``."""

DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_TASK_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_POLLS = 60
"""Defaults for an enabled server that does not tune the bounds."""

MIN_POLL_INTERVAL_SECONDS = 0.1
MAX_POLL_INTERVAL_SECONDS = 30.0
MIN_TASK_TIMEOUT_SECONDS = 1.0
MAX_TASK_TIMEOUT_SECONDS = 3600.0
MAX_TASK_POLLS = 600
"""Hard bounds applied at runtime, whatever a persisted config claims."""

_TASK_AUGMENTED_CALL = "tools/call"
_WORKING = "working"
_COMPLETED = "completed"
_INPUT_REQUIRED = "input_required"
_PROTOCOL_VERSION_HEADER = "MCP-Protocol-Version"
# Headroom kept when the caller's own budget is the tighter bound, so one
# ``tasks/cancel`` still fits before that budget cancels this coroutine.
_CANCEL_RESERVE_SECONDS = 2.0
_CANCEL_REQUEST_TIMEOUT_SECONDS = 2.0
"""Hard bound on the cleanup ``tasks/cancel`` request itself."""

# Everything the hand-rolled loop touches. Probed once at import so a missing
# model is a documented degradation instead of an AttributeError mid-call.
_REQUIRED_TASK_MODELS = (
    "CallToolRequestParams",
    "CallToolResult",
    "CancelTaskRequest",
    "CancelTaskRequestParams",
    "CancelTaskResult",
    "ClientTasksCapability",
    "CreateTaskResult",
    "GetTaskPayloadRequest",
    "GetTaskPayloadRequestParams",
    "GetTaskRequest",
    "GetTaskRequestParams",
    "GetTaskResult",
    "Task",
    "TaskMetadata",
    "TasksCancelCapability",
)

TASKS_SDK_READY = hasattr(ClientSession, "_build_capabilities") and all(
    hasattr(types, name) for name in _REQUIRED_TASK_MODELS
)
"""Whether this SDK can run the hand-rolled loop at all.

False for an SDK without the task models (``mcp`` 2.2 and earlier) and false if
``ClientSession`` ever stops exposing the capability hook this module overrides.
Both cases keep every MCP call on the synchronous path.

Note that ``_build_capabilities`` is private SDK surface: a session class is
the only supported way to add a capability, because ``ClientSession`` computes
its capability ad internally with no hook. It is probed, not assumed, exactly
for that reason.
"""


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class McpTaskPolicy:
    """Bounds for one task execution.

    ``poll_interval`` is the delay between ``tasks/get`` polls,
    ``timeout`` the overall deadline and ``max_polls`` a cap that holds even
    when the deadline is generous. Whichever bound trips first cancels the
    server task and fails the call, so a task that never completes can never
    hang the caller. The server's own ``pollInterval`` hint is deliberately
    ignored: it is unvalidated remote input.
    """

    enabled: bool = False
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS
    timeout: float = DEFAULT_TASK_TIMEOUT_SECONDS
    max_polls: int = DEFAULT_MAX_POLLS


DEFAULT_TASK_POLICY = McpTaskPolicy()
"""The disabled policy: synchronous execution, nothing advertised."""


def _bounded_float(value: Any, *, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def resolve_task_policy(
    config: Mapping[str, Any] | None = None, *, global_enabled: bool | None = None
) -> McpTaskPolicy:
    """Build one server's policy from the platform flag and its own settings.

    Both switches must be on. Persisted configs are validated by
    ``McpConfigSchema``, but a row can predate the field or be edited directly,
    so every value is parsed and clamped again here.
    """
    platform_on = (
        settings.MCP_TASKS_ENABLED if global_enabled is None else global_enabled
    )
    server = config if isinstance(config, Mapping) else {}
    if not platform_on or server.get("enable_tasks") is not True:
        return DEFAULT_TASK_POLICY
    if not TASKS_SDK_READY:
        logger.warning(
            "MCP tasks are enabled for this server but the installed MCP SDK has "
            "no task models or no capability hook; staying on the synchronous path"
        )
        return DEFAULT_TASK_POLICY
    return McpTaskPolicy(
        enabled=True,
        poll_interval=_bounded_float(
            server.get("tasks_poll_interval_seconds"),
            default=DEFAULT_POLL_INTERVAL_SECONDS,
            low=MIN_POLL_INTERVAL_SECONDS,
            high=MAX_POLL_INTERVAL_SECONDS,
        ),
        timeout=_bounded_float(
            server.get("tasks_timeout_seconds"),
            default=DEFAULT_TASK_TIMEOUT_SECONDS,
            low=MIN_TASK_TIMEOUT_SECONDS,
            high=MAX_TASK_TIMEOUT_SECONDS,
        ),
        max_polls=_bounded_int(
            server.get("tasks_max_polls"),
            default=DEFAULT_MAX_POLLS,
            low=1,
            high=MAX_TASK_POLLS,
        ),
    )


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------


def capability_for(protocol_version: str | None) -> types.ClientTasksCapability | None:
    """The client tasks capability to advertise on ``protocol_version``.

    ``None`` on every other revision (and on an unknown one), so the ad never
    claims a feature the negotiated session does not define.
    """
    if protocol_version != TASKS_PROTOCOL_VERSION:
        return None
    return types.ClientTasksCapability(cancel=types.TasksCancelCapability())


class _TaskCapableSession(ClientSession):
    """``ClientSession`` that also advertises the ``tasks`` capability.

    The SDK builds the client's capability ad in the private
    ``_build_capabilities`` hook and offers no way to extend it, so declaring
    ``tasks`` means overriding that one method. :func:`task_session_class`
    returns ``None`` instead of this class when the hook is unavailable, and
    ``TASKS_SDK_READY`` is probed at import, so an SDK change turns task support
    off rather than breaking MCP calls.
    """

    def _build_capabilities(self, version: str) -> types.ClientCapabilities:
        capabilities = super()._build_capabilities(version)
        task_capability = capability_for(version)
        if task_capability is None:
            return capabilities
        return capabilities.model_copy(update={"tasks": task_capability})


def task_session_class(policy: McpTaskPolicy) -> type[ClientSession] | None:
    """Session type to open for ``policy``, or ``None`` for the plain SDK one."""
    if not policy.enabled or not TASKS_SDK_READY:
        return None
    return _TaskCapableSession


# ---------------------------------------------------------------------------
# Call flow
# ---------------------------------------------------------------------------


def _timeout_error(message: str, seconds: float) -> Exception:
    """Build the adapter's timeout error.

    ``mcp_client`` imports this module at module scope, so its error types are
    imported lazily here to keep the import graph acyclic.
    """
    from app.llm.tools.mcp_client import McpTimeout

    return McpTimeout(message, timeout_seconds=seconds)


def _server_error(code: int, message: str) -> Exception:
    """Build the adapter's server-error (lazy import; see ``_timeout_error``)."""
    from app.llm.tools.mcp_client import McpServerError

    return McpServerError(code, message)


async def call_tool_with_tasks(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any] | None,
    policy: McpTaskPolicy,
    *,
    budget: float | None = None,
    **kwargs: Any,
) -> Any:
    """Call a tool, running the server's task machinery when one is created.

    ``budget`` is the caller's own remaining time for the whole call; the task
    deadline is capped by it (see :func:`_effective_deadline`). ``kwargs`` are
    the per-request options ``McpClient`` already computes (MRTR answers); they
    go to ``session.call_tool`` unchanged on the synchronous path and, on the
    task path, into the task-augmented request.

    Falls back to ``session.call_tool`` when tasks are off, when the server
    answered the augmented request synchronously, or when it refused that
    request outright: in the last case no work has started, so the plain call
    cannot duplicate side effects.
    """
    if not policy.enabled or not TASKS_SDK_READY:
        return await session.call_tool(tool_name, arguments, **kwargs)
    if getattr(session, "protocol_version", None) != TASKS_PROTOCOL_VERSION:
        # ``tasks/*`` exists only on this revision. Another revision defines no
        # task capability, and the raw request also skips the SDK's modern
        # stamping (``_meta`` protocol fields, ``Mcp-Method`` / ``Mcp-Name`` /
        # ``Mcp-Param-*``), so sending it would at best earn a refusal.
        return await session.call_tool(tool_name, arguments, **kwargs)
    deadline = _effective_deadline(policy, budget)
    # One absolute expiry for the whole call: task creation time comes out of
    # the same budget the poll loop is bounded by, so a slow ``tools/call``
    # cannot push the poll window past the caller's deadline.
    expires_at = asyncio.get_running_loop().time() + deadline
    start = await _start_task(session, tool_name, arguments, deadline, kwargs)
    if start is None:  # refused before any work started
        return await session.call_tool(tool_name, arguments, **kwargs)
    if isinstance(start, types.CallToolResult):  # server ran it inline
        return start
    return await _await_task(
        session, start.task, policy, deadline=deadline, expires_at=expires_at
    )


def _effective_deadline(policy: McpTaskPolicy, budget: float | None) -> float:
    """The bound the loop actually honours: the policy's, capped by ``budget``.

    A task deadline longer than the caller's own budget would let that budget
    kill the loop mid-poll, leaving the server's task running with nobody left
    to cancel it. The cap keeps ``_CANCEL_RESERVE_SECONDS`` free for the cancel
    request itself.
    """
    if budget is None:
        return policy.timeout
    return max(min(policy.timeout, budget - _CANCEL_RESERVE_SECONDS), 0.001)


async def _start_task(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any] | None,
    deadline: float,
    kwargs: Mapping[str, Any],
) -> types.CreateTaskResult | types.CallToolResult | None:
    """Send the task-augmented ``tools/call`` and classify the answer.

    The request goes through the session's raw dispatcher: ``send_request``
    validates every ``tools/call`` result against ``CallToolResult``, which
    rejects a ``CreateTaskResult`` body before it can be read.
    """
    dispatcher = getattr(session, "_dispatcher", None)
    if dispatcher is None or not hasattr(dispatcher, "send_raw_request"):
        logger.warning(
            "MCP session cannot send a raw task-augmented request; staying on "
            "the synchronous path"
        )
        return None

    params = types.CallToolRequestParams(
        name=tool_name,
        arguments=arguments,
        task=types.TaskMetadata(),
        input_responses=kwargs.get("input_responses"),
        request_state=kwargs.get("request_state"),
    )
    opts: CallOptions = {"timeout": max(deadline, 0.001)}
    progress_callback = kwargs.get("progress_callback")
    if progress_callback is not None:
        # ``session.call_tool`` is where the SDK would turn this into the
        # dispatcher's ``on_progress`` option; the raw path has to do it here
        # or an inline answer can never report progress.
        opts["on_progress"] = progress_callback
    version = getattr(session, "protocol_version", None)
    if isinstance(version, str) and version:
        # The raw path skips the SDK's stamping; keep the negotiated version on
        # the wire so an HTTP server routes the request the same way.
        opts["headers"] = {_PROTOCOL_VERSION_HEADER: version}

    try:
        raw = await dispatcher.send_raw_request(
            _TASK_AUGMENTED_CALL,
            params.model_dump(by_alias=True, mode="json", exclude_none=True),
            opts,
        )
    except Exception as exc:
        # Only a JSON-RPC error means "this request shape is unusable". A
        # timeout or transport failure may follow real work, so it propagates.
        if _SdkMcpError is None or not isinstance(exc, _SdkMcpError):
            raise
        if getattr(exc, "code", None) == types.REQUEST_TIMEOUT:
            # The request was delivered and its answer never came: the server
            # may have run the call. Replaying it synchronously could repeat a
            # committed write, so this is not a pre-execution rejection.
            raise
        logger.warning(
            "MCP server rejected the task-augmented tools/call for %s (%s); "
            "falling back to synchronous execution",
            tool_name,
            exc,
        )
        return None

    if "task" in raw:
        return types.CreateTaskResult.model_validate(raw)
    return types.CallToolResult.model_validate(raw)


async def _await_task(
    session: ClientSession,
    task: types.Task,
    policy: McpTaskPolicy,
    *,
    deadline: float,
    expires_at: float,
) -> types.CallToolResult:
    """Poll ``tasks/get`` until the task is terminal, then fetch its payload.

    ``expires_at`` is the absolute expiry fixed before the task was created;
    ``deadline`` is the same bound in seconds, kept for the timeout message.
    """
    polls = 0
    current = task
    try:
        while current.status == _WORKING:
            remaining = expires_at - asyncio.get_running_loop().time()
            if polls >= policy.max_polls or remaining <= 0:
                raise _timeout_error(
                    f"MCP task {current.task_id} did not complete within "
                    f"{deadline:g}s / {policy.max_polls} polls",
                    deadline,
                )
            await asyncio.sleep(min(policy.poll_interval, remaining))
            polls += 1
            current = await _get_task(session, current.task_id, expires_at)
    except BaseException:
        # Every way out of the loop — timeout, caller cancellation, a failing
        # ``tasks/get`` — abandons an accepted server task. MCP tasks are
        # durable operations: without this the task keeps running with no
        # poller left to read it. A normally completed task is never cancelled.
        await _cancel(session, current, expires_at=expires_at)
        raise

    if current.status == _COMPLETED:
        return await _task_result(session, current.task_id, expires_at)
    if current.status == _INPUT_REQUIRED:
        # The task is parked on a server-initiated request this adapter cannot
        # answer inside the task loop, so release the server's resources.
        await _cancel(session, current)
        raise _server_error(
            types.INTERNAL_ERROR,
            f"MCP task {current.task_id} requires client input",
        )
    raise _server_error(
        types.INTERNAL_ERROR,
        f"MCP task {current.task_id} ended as {current.status}: "
        f"{current.status_message or 'no reason given'}",
    )


def _request_budget(expires_at: float) -> float:
    """Seconds left before the task deadline, floored so the SDK accepts it."""
    return max(expires_at - asyncio.get_running_loop().time(), 0.001)


async def _get_task(
    session: ClientSession, task_id: str, expires_at: float
) -> types.Task:
    return await session.send_request(
        types.GetTaskRequest(params=types.GetTaskRequestParams(task_id=task_id)),
        types.GetTaskResult,
        request_read_timeout_seconds=_request_budget(expires_at),
    )


async def _task_result(
    session: ClientSession, task_id: str, expires_at: float
) -> types.CallToolResult:
    """Fetch the payload: ``tasks/result`` returns the original result shape."""
    return await session.send_request(
        types.GetTaskPayloadRequest(
            params=types.GetTaskPayloadRequestParams(task_id=task_id)
        ),
        types.CallToolResult,
        request_read_timeout_seconds=_request_budget(expires_at),
    )


async def _cancel(
    session: ClientSession, task: types.Task, *, expires_at: float | None = None
) -> None:
    """Best-effort ``tasks/cancel``: cleanup never masks the real failure.

    The request carries its own short read timeout. Without one it inherits the
    session timeout, which is far longer than the reserve left for cleanup, so
    a server that never answers ``tasks/cancel`` would hold the caller past its
    own budget instead of failing here.
    """
    budget = _CANCEL_REQUEST_TIMEOUT_SECONDS
    if expires_at is not None:
        budget = min(budget, max(_request_budget(expires_at), 0.001))
    try:
        async with asyncio.timeout(budget):
            await session.send_request(
                types.CancelTaskRequest(
                    params=types.CancelTaskRequestParams(task_id=task.task_id)
                ),
                types.CancelTaskResult,
                request_read_timeout_seconds=budget,
            )
    except BaseException:  # noqa: BLE001 - cleanup must not mask the real error
        logger.warning("Unable to cancel MCP task %s", task.task_id, exc_info=True)
