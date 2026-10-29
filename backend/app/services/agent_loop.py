"""Shared event-driven Agent Loop state machine.

Centralizes the four duplicated chat tool loops (non-stream, stream, edit,
regenerate) into a single loop. The loop owns:

- per-iteration provider context building (compression events included),
- one model turn (streaming with idle timeout + fallback, or non-stream),
- usage aggregation and recording,
- heartbeat / disconnect handling (stream paths only),
- tool-call execution with per-call lifecycle events,
- intermediate assistant-step / tool-result persistence (via ``agent_round``),
- iteration-cap handling and terminal result assembly.

Transport stays with the caller: the loop is an async generator of formatted
SSE strings via a route-supplied formatter (stream paths) or a silent
side-effecting run with ``formatter=None`` (non-stream path). Error handling
and branch/version finalization stay with the caller so every path keeps its
existing terminal persistence, error events, branch activation and stats
updates; the loop lets model errors propagate — except an unambiguously
classified provider input-context overflow that arrives before the streaming
request yielded any chunk, which the loop retries against a strictly smaller
provider view (bounded, with an explicit omission notice and existing
compression events).

The loop does NOT own: access checks, RAG retrieval, asset resolution, user
message creation, placeholder assistant creation, branch/version selection,
branch activation, stats updates. Those remain route-level concerns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.api.v1.endpoints.chat_helpers import (
    iter_with_idle_timeout,
)
from app.api.v1.endpoints.chat_sse import (
    build_media_result_sse_event,
    build_tool_call_sse_event,
    build_tool_result_sse_event,
)
from app.api.v1.endpoints.chat_tools import AssetViewResult, execute_tool_call
from app.llm.errors import ContextLengthError
from app.llm.tools.interaction import ToolInteractionRequest
from app.services.tool_context import (
    RuntimeToolIdentity,
    entrypoint_is_interactive,
    tool_identity_scope,
)
from app.utils.tool_output import (
    KNOWN_OUTPUT_TOOLS,
    ToolExecutionResult,
    get_tool_execution_payloads,
    persistable_model_result,
)
from app.llm.types import ChatStreamChunk, FinishReason, StopReason
from app.services import agent_round
from app.services.sandbox.recovery import (
    capture_workspace_resets,
    sandbox_execution_scope,
)

logger = logging.getLogger(__name__)

# Event names (public SSE names, aligned with ``SSEEventType``).
HEARTBEAT = "heartbeat"
CONTENT_DELTA = "content_delta"
REASONING_START = "reasoning_start"
REASONING_DELTA = "reasoning_delta"
REASONING_END = "reasoning_end"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
MEDIA_RESULT = "media_result"
COMPRESSION_START = "compression_start"
COMPRESSION_END = "compression_end"
OUTPUT_TRUNCATED = "output_truncated"
ITERATION_CAP_REACHED = "iteration_cap_reached"

MAX_DEPENDENCY_METRICS_PER_PASS = 64

# Provider-side context-overflow recovery. The preflight budget is an
# estimate; a provider can still reject the request. Recovery is bounded and
# only retries a request that produced no output yet, always with a strictly
# smaller provider view.
CONTEXT_OVERFLOW_MAX_RETRIES = 2
CONTEXT_OVERFLOW_OMISSION_PREFIX = (
    "Earlier conversation history was omitted to fit the model's context window."
)
CONTEXT_OVERFLOW_OMISSION_NOTICE = (
    f"{CONTEXT_OVERFLOW_OMISSION_PREFIX} Do not assume its contents."
)


@dataclass(slots=True)
class AgentLoopContext:
    """Everything the loop needs to run one round.

    Model metadata is resolved by the route exactly once (same values the
    route would pass to its old loop) so context budgeting stays identical.
    """

    agent: Any
    conversation: Any
    user: Any
    # model metadata
    model_id: str | None
    tokenizer_model_id: str | None
    model_provider: str | None
    model_context_limit: int | None
    model_max_output_tokens: int | None
    model_used: str | None
    # final user message text (with image inventory appended)
    user_message: str = ""
    input_capabilities: Any = None
    model_config: Any = None
    tools: list[Any] | None = None
    #: Optional authorized tool discovery state
    #: (``app.services.tool_discovery.ToolDiscoveryState``). ``ctx.tools`` stays
    #: the full authorized list; when discovery is active the loop sends
    #: ``tool_discovery.tools_for_turn()`` instead, so a large catalog does not
    #: occupy every provider request.
    tool_discovery: Any = None
    #: Tool schemas declared for the model response owning pending calls.
    resume_tool_visible_names: set[str] | None = None
    active_resume_tool_visible_names: set[str] | None = None
    resume_tool_call_ids: set[str] = field(default_factory=set)
    replay_tool_call_ids: set[str] = field(default_factory=set)
    resume_tool_calls: list[Any] | None = None
    tool_display_names: dict[str, str] = field(default_factory=dict)
    tool_timeouts: dict[str, Any] = field(default_factory=dict)
    # streaming config
    global_timeout: float = 1800.0
    idle_timeout: float = 300.0
    heartbeat_interval: float = 300.0
    # primary guard: hard wall-clock deadline for the whole round (worker
    # path); when set, the loop stops at it instead of the iteration cap.
    deadline_seconds: float | None = None
    # request prep outputs
    sandbox_session_id: str | None = None
    current_images: list[Any] | None = None
    working_history_override: list[dict[str, Any]] | None = None
    image_pool: list[Any] = field(default_factory=list)
    image_inventory: list[dict[str, str]] = field(default_factory=list)
    append_generated_images: Callable[..., Any] | None = None
    current_user_message_id: UUID | None = None
    exclude_message_ids: list[UUID] | None = None
    include_current_user_message: bool = True
    history_before_message_created_at: Any = None
    round_id: UUID | None = None
    protected_round_id: UUID | str | None = None
    user_locale: str | None = None
    max_iterations: int | None = None
    iteration_offset: int = 0
    # Trusted entrypoint origin persisted by the run submitter. Missing origin
    # on legacy runs is treated as non-interactive by the tool identity.
    tool_entrypoint: str | None = None
    tool_entrypoint_id: str | None = None
    # Authenticated API key that submitted the run (api_key entrypoint only).
    tool_api_key_id: UUID | None = None
    # Durable AgentRun callback used by model-callable interaction tools.
    pause_for_user: Callable[..., Any] | None = None
    # how one model turn is produced
    streaming: bool = True
    # context building (route-supplied): builds + finalizes provider context
    build_turn: Callable[..., Any] | None = None
    count_tool_definition_tokens: Callable[..., int] | None = None
    # tool execution (route-bound so tests can mock the endpoint binding)
    execute_tool_call: Callable[..., Any] | None = None
    # (name) -> "shared" | "exclusive"; absent means exclusive (conservative)
    tool_concurrency: Callable[[str], str] | None = None
    # model calls bound to model_manager by the route
    team_chat_stream: Callable[..., AsyncIterator[ChatStreamChunk]] | None = None
    team_chat: Callable[..., Any] | None = None
    record_stream_usage: Callable[..., Any] | None = None
    calculate_usage: Callable[..., tuple[int, int, int, int, int]] | None = None
    # heartbeat / disconnect (stream paths)
    send_heartbeat_if_needed: Callable[..., Any] | None = None
    is_disconnected: Callable[[], Any] | None = None
    request: Any = None
    initial_last_event_time: float | None = None
    # durable-run steering/stop (worker paths; called at safe boundaries)
    consume_inputs: Callable[[], Any] | None = None
    stop_requested: Callable[[], Any] | None = None
    input_consumed: Callable[[Any], Any] | None = None
    # formatter: (event_name, payload) -> SSE string or None to drop
    formatter: Callable[[str, dict[str, Any]], str | None] | None = None
    # persistence granularity
    persist_step_per_tool: bool = False
    collect_dependency_metrics: bool = False
    # Observability run id, used only to key on-demand tool payload drill-down.
    observability_run_id: UUID | None = None
    step_branch_parent_id: UUID | None = None
    first_round_index: int = 1
    created_message_count: int = 2
    # terminal content helpers
    cap_content: Callable[[], str] | None = None


@dataclass(slots=True)
class AgentLoopResult:
    """Terminal or durable-pause state produced by the loop."""

    full_content: str = ""
    full_reasoning: str = ""
    max_iterations_reached: bool = False
    deadline_exceeded: bool = False
    manually_stopped: bool = False
    waiting_for_user: bool = False
    aggregate_input_tokens: int = 0
    aggregate_output_tokens: int = 0
    aggregate_cache_read_tokens: int = 0
    aggregate_cache_creation_tokens: int = 0
    aggregate_total_input_tokens: int = 0
    duration_ms: int = 0
    first_token_ms: int | None = None
    dependency_metrics: list[dict[str, Any]] = field(default_factory=list)
    dependency_metrics_truncated: bool = False
    created_message_count: int = 2
    final_round_index: int = 1


def _safe_arguments(arguments: str | dict | None) -> dict[str, Any]:
    if not arguments:
        return {}
    if isinstance(arguments, dict):
        return arguments
    try:
        return json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return {}


def _tool_call_arguments(arguments: str | dict | None) -> dict[str, Any]:
    """Return a detached copy of the model-supplied tool call arguments.

    Pausing for approval must not replace the call's business arguments with
    interaction metadata, and a tool runner may mutate the dict it receives.
    Re-parsing the original payload keeps display, persistence and provider
    history on exactly what the model asked for.
    """
    parsed = _safe_arguments(arguments)
    try:
        detached = json.loads(json.dumps(parsed))
    except (TypeError, ValueError):
        return dict(parsed)
    return detached if isinstance(detached, dict) else {}


def _include_workspace_reset_result(result: str, notices: list[dict[str, Any]]) -> str:
    """Append recovery control data without discarding the tool's own output."""
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        payload = {"result": result}
    if not isinstance(payload, dict):
        payload = {"result": payload}
    payload["workspace_reset"] = notices[-1]
    return json.dumps(payload, ensure_ascii=False)


def _tool_call_changed(previous: Any, current: Any) -> bool:
    """Return whether a streamed call update changes visible metadata."""
    previous_name = getattr(previous.function, "name", None) or ""
    current_name = getattr(current.function, "name", None) or ""
    return previous_name != current_name or (
        _safe_arguments(getattr(previous.function, "arguments", None))
        != _safe_arguments(getattr(current.function, "arguments", None))
    )


def _tool_schema_names(tools: list[Any] | None) -> set[str]:
    """Return the names from the exact schema list passed to a model call."""
    names: set[str] = set()
    for tool in tools or []:
        function = (
            tool.get("function", {})
            if isinstance(tool, dict)
            else getattr(tool, "function", None)
        )
        name = (
            function.get("name")
            if isinstance(function, dict)
            else getattr(function, "name", None)
        )
        if isinstance(name, str) and name:
            names.add(name)
    return names


def _message_role(message: dict[str, Any]) -> str:
    """Return a provider-view message's role as a plain string."""
    role = message.get("role")
    return str(getattr(role, "value", role) or "")


def _reducible_history_units(
    messages: list[dict[str, Any]],
    protected_indexes: set[int] | None = None,
) -> tuple[int, int, list[tuple[int, int]]]:
    """Split the provider view into system prefix, current instruction, units.

    Only history strictly between the system prompt and the last user message
    is reducible. Each unit is either one message or an assistant tool-call
    message plus its immediately following tool results, so a retry can never
    orphan half of a provider tool exchange.

    Fail closed:
    - With no protection mask there is no evidence of which user messages are
      current instructions, so nothing is reducible.
    - Units touching a protected index (current user input and active-round
      protocol) are never offered.
    - Only plain assistant text without tool calls is droppable. User
      messages (including context summaries and instructions), tool calls and
      tool results are never dropped: the provider view has no round
      identifiers, so nothing else is provably recoverable or discardable.
    """
    protected = protected_indexes or set()
    prefix_end = 1 if messages and _message_role(messages[0]) == "system" else 0
    anchor = len(messages)
    for index in range(len(messages) - 1, prefix_end - 1, -1):
        if _message_role(messages[index]) == "user":
            anchor = index
            break
    if not protected:
        return prefix_end, anchor, []

    units: list[tuple[int, int]] = []
    index = prefix_end
    while index < anchor:
        message = messages[index]
        end = index + 1
        if _message_role(message) == "assistant" and message.get("tool_calls"):
            while end < anchor and _message_role(messages[end]) == "tool":
                end += 1
        droppable = _message_role(message) == "assistant" and not message.get(
            "tool_calls"
        )
        if droppable and not any(
            index <= protected_index < end for protected_index in protected
        ):
            units.append((index, end))
        index = end
    return prefix_end, anchor, units


def _reduce_history_messages(
    messages: list[dict[str, Any]],
    *,
    drop_all: bool,
    protected_indexes: set[int] | None = None,
    notice_index: int | None = None,
) -> tuple[list[dict[str, Any]], int, set[int], int | None]:
    """Drop removable assistant history and disclose the omission explicitly.

    ``notice_index`` is the internally tracked position of the omission notice
    this loop inserted earlier, or ``None``. It is removed by index and
    replaced by one fresh notice; content is never matched, so a user message
    that happens to share the notice wording is preserved.

    Returns the candidate provider view, the number of source messages
    removed, the protected indexes remapped onto the candidate view, and the
    new notice index. The system prompt, all user messages (including context
    summaries and instructions), and all tool-call/tool-result history are
    preserved verbatim.
    """
    protected = set(protected_indexes or ())
    prefix_end, _anchor, units = _reducible_history_units(messages, protected)
    if not units:
        return messages, 0, protected, notice_index
    drop_count = len(units) if drop_all else max(1, len(units) // 2)
    dropped: set[int] = set()
    for start, end in units[:drop_count]:
        dropped.update(range(start, end))
    if not dropped:
        return messages, 0, protected, notice_index
    kept_pairs = [
        (index, message)
        for index, message in enumerate(messages)
        if index not in dropped and index != notice_index
    ]
    insert_at = 1 if prefix_end else 0
    remapped: set[int] = set()
    for new_position, (old_index, _message) in enumerate(kept_pairs):
        if old_index in protected:
            remapped.add(new_position + (1 if new_position >= insert_at else 0))
    kept = [message for _old_index, message in kept_pairs]
    kept.insert(
        insert_at, {"role": "user", "content": CONTEXT_OVERFLOW_OMISSION_NOTICE}
    )
    return kept, len(dropped), remapped, insert_at


def _is_provider_context_overflow(exc: BaseException) -> bool:
    """Whether an error is unambiguously a provider *input* context overflow.

    ``ModelManager`` classifies provider errors loosely (message containing
    ``token`` + ``max``), which also catches output-parameter errors such as
    ``max_tokens`` being too large. Retrying those with a smaller history
    cannot help, so only explicit context-window/prompt-too-long wording is
    accepted. Local preflight guards mark themselves ``retryable=False`` and
    are never retried here.
    """
    if not isinstance(exc, ContextLengthError):
        return False
    details = exc.details or {}
    if details.get("retryable") is False:
        return False
    reason = str(details.get("reason") or "")
    if reason.startswith(("protected_payload", "context_summary")):
        return False
    if str(getattr(exc, "code", "") or "") != "context_length_error":
        return False
    message = str(getattr(exc, "message", "") or str(exc)).lower()
    return any(
        marker in message
        for marker in (
            "context_length_exceeded",
            "context length",
            "context window",
            "maximum context",
            "max context",
            "prompt is too long",
            "prompt too long",
            "input is too long",
            "input too long",
            "input token count",
            "reduce the length of the messages",
            "exceeds the maximum number of tokens",
        )
    )


@dataclass(slots=True)
class _OverflowRetryResult:
    """Successful value of a request after bounded retries."""

    value: Any
    notice_index: int | None = None
    retry_count: int = 0


@dataclass(slots=True)
class ContextTurn:
    """Prepared provider context plus the summary decision for one turn.

    Exactly one of ``prepared`` / ``plan`` should be set:

    - ``prepared``: the context is already finalized (non-stream path uses
      ``prepare_model_context`` and wants no compression events).
    - ``plan``: an unfinalized ``ContextPlan``; the loop finalizes it and
      emits compression_start/compression_end around the model summarization
      call (streaming paths).
    """

    prepared: Any = None
    plan: Any = None
    will_summarize: bool = False
    compression: Any = None


class _IncompleteToolCall:
    """Synthetic tool call for a started-but-truncated provider call.

    Carries only the id; the execution block pairs it with an explicit error
    result so no orphan tool call enters provider history.
    """

    __slots__ = ("id",)

    def __init__(self, call_id: str) -> None:
        self.id = call_id

    class function:
        name = ""
        arguments = "{}"

    compression: Any = None


class AgentLoop:
    """One round of model turns + tool execution.

    ``run()`` is an async generator. Streaming paths yield formatted SSE
    strings through the route-supplied formatter; the non-stream path passes
    ``formatter=None`` and the generator produces no output while still
    persisting intermediate steps. Read ``self.result`` after ``run()``.
    """

    PAUSE_TURN_LIMIT = 8

    def __init__(self, context: AgentLoopContext) -> None:
        self.context = context
        self._mcp_tool_names = {
            name
            for tool in context.tools or []
            if (
                name := (
                    tool.get("function", {}).get("name", "")
                    if isinstance(tool, dict)
                    else tool.function.name
                )
            ).startswith("mcp_")
        }
        self.result = AgentLoopResult()
        self._round_index = context.first_round_index
        self._consecutive_pause_turns = 0
        self._deadline_at: float | None = None
        # Current model trajectory entry id; tool entries link to it.
        self._current_model_entry_id: UUID | None = None
        # Finalizer for the in-flight model turn (cancellation safety).
        self._active_model_finalizer: Any = None
        self._last_event_time = (
            context.initial_last_event_time
            if context.initial_last_event_time is not None
            else time.time()
        )

    def _emit(self, event_name: str, payload: dict[str, Any]) -> str | None:
        if self.context.formatter is None:
            return None
        return self.context.formatter(event_name, payload)

    def _next_round_index(self) -> int:
        index = self._round_index
        self._round_index += 1
        return index

    def _append_history(
        self,
        *,
        role: str,
        content: str,
        reasoning_content: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        round_index: int,
        iteration: int,
    ) -> None:
        from app.api.v1.endpoints.chat import append_round_history_entry

        if self.context.working_history_override is None:
            self.context.working_history_override = []
        assert self.context.round_id is not None
        append_round_history_entry(
            self.context.working_history_override,
            role=role,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            round_id=self.context.round_id,
            round_index=round_index,
            round_role="assistant_step" if role == "assistant" else "tool_result",
            is_round_canonical=False,
            iteration_index=iteration,
        )

    def _tool_concurrency_of(self, tool_name: str) -> str:
        """Resolve a tool's concurrency policy (conservative exclusive)."""
        if self.context.tool_concurrency is not None:
            policy = self.context.tool_concurrency(tool_name)
            if policy == "shared":
                return "shared"
        return "exclusive"

    def _partition_tool_batch(self, calls: list[Any]) -> list[list[Any]]:
        """Split calls into consecutive shared runs + exclusive barriers.

        A run is either a maximal consecutive sequence of shared calls (all
        run concurrently) or a single exclusive call (waits for earlier calls
        and blocks later ones).
        """
        groups: list[list[Any]] = []
        current: list[Any] = []
        current_shared = False
        for tc in calls:
            tool_name = getattr(tc.function, "name", None) or ""
            shared = self._tool_concurrency_of(tool_name) == "shared"
            if current and shared != current_shared:
                groups.append(current)
                current = []
            if not current:
                current_shared = shared
            current.append(tc)
        if current:
            groups.append(current)
        return groups

    def _build_tool_call_sse(self, tc: Any) -> str:
        """Build the call event before the tool starts executing."""
        tool_name = getattr(tc.function, "name", None) or ""
        if not tool_name:
            return ""
        return build_tool_call_sse_event(
            tool_call_id=tc.id,
            tool_name=tool_name,
            tool_display_name=self.context.tool_display_names.get(tool_name, tool_name),
            arguments=_safe_arguments(getattr(tc.function, "arguments", None)),
        )

    async def _execute_one_tool(
        self,
        *,
        tc: Any,
        image_pool: list[Any],
        image_inventory: list[dict[str, Any]],
    ) -> tuple[str, str, str | None, dict[str, Any]]:
        """Execute one tool and return its protocol record.

        The call event is built before execution and emitted by the caller so
        the client can render the tool and its arguments while it is running.
        Execution may overlap for shared tools, but persistence and result
        emission happen in the caller's original tool-call order. A tool
        failure is represented as an error result so sibling calls and the
        provider protocol remain intact.
        """
        ctx = self.context
        tool_name = getattr(tc.function, "name", None) or ""
        arguments = _safe_arguments(getattr(tc.function, "arguments", None))
        if not tool_name:
            error_result = json.dumps(
                {"error": "tool_call_truncated"}, ensure_ascii=False
            )
            return (
                "",
                "",
                None,
                {
                    "id": tc.id,
                    "name": "",
                    "arguments": arguments,
                    "display_result": error_result,
                    "llm_result": error_result,
                    "display_name": "",
                },
            )
        display_name = ctx.tool_display_names.get(tool_name, tool_name)

        if str(tc.id) in ctx.replay_tool_call_ids and ctx.tool_discovery is not None:
            visible_names = ctx.active_resume_tool_visible_names
            catalog = getattr(ctx.tool_discovery, "catalog", {})
            currently_authorized = tool_name in catalog or ctx.tool_discovery.handles(
                tool_name
            )
            legacy_core_fallback = (
                visible_names is None
                and tool_name in getattr(ctx.tool_discovery, "core_names", ())
                and tool_name in catalog
                and ctx.tool_discovery.is_visible(tool_name)
            )
            visible = currently_authorized and (
                legacy_core_fallback
                or (
                    visible_names is not None
                    and tool_name in visible_names
                    and ctx.tool_discovery.is_visible(tool_name)
                )
            )
            if not visible:
                error = ctx.tool_discovery.undiscovered_error(tool_name)
                return (
                    self._build_tool_call_sse(tc),
                    build_tool_result_sse_event(
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        tool_display_name=ctx.tool_display_names.get(
                            tool_name, tool_name
                        ),
                        display_result=error,
                    ),
                    None,
                    {
                        "id": tc.id,
                        "name": tool_name,
                        "arguments": arguments,
                        "display_result": error,
                        "llm_result": error,
                        "display_name": ctx.tool_display_names.get(
                            tool_name, tool_name
                        ),
                    },
                )
        tool_runner = ctx.execute_tool_call or execute_tool_call
        reset_notices: list[dict[str, Any]] = []
        trajectory_arguments = arguments
        trajectory_started_at: float | None = None
        trajectory_started_clock = 0.0
        if ctx.observability_run_id is not None:
            trajectory_started_at = time.time()
            trajectory_started_clock = time.monotonic()
            # Preserve the exact request arguments before the tool mutates them.
            try:
                trajectory_arguments = json.loads(json.dumps(arguments))
            except (TypeError, ValueError):
                pass
        collect_dependency_metric = (
            ctx.collect_dependency_metrics and tool_name != "ask_user"
        )
        tool_started_at = time.time() if collect_dependency_metric else None
        tool_started_clock = time.monotonic() if collect_dependency_metric else 0.0
        metric_status = "in_progress"
        metric_error_category: str | None = None
        persist_result: str | None = None
        tool_result: Any = None
        try:
            with (
                tool_identity_scope(
                    RuntimeToolIdentity(
                        run_id=UUID(str(ctx.observability_run_id))
                        if ctx.observability_run_id
                        else None,
                        tool_call_id=str(tc.id),
                        entrypoint=ctx.tool_entrypoint or "agent_run",
                        entrypoint_id=ctx.tool_entrypoint_id or str(ctx.agent.id),
                        api_key_id=ctx.tool_api_key_id,
                        interactive=entrypoint_is_interactive(ctx.tool_entrypoint),
                    )
                ),
                capture_workspace_resets() as reset_notices,
                sandbox_execution_scope(
                    deadline_at=self._deadline_at, stop_requested=ctx.stop_requested
                ),
            ):
                tool_result = await tool_runner(
                    tool_name,
                    arguments,
                    agent=ctx.agent,
                    tool_timeouts=ctx.tool_timeouts,
                    user=ctx.user,
                    session_id=ctx.sandbox_session_id,
                    current_images=image_pool,
                    conversation_id=ctx.conversation.id,
                )
            if isinstance(tool_result, ToolInteractionRequest):
                if tool_result.tool_name != tool_name:
                    raise ValueError("tool interaction name mismatch")
                is_approval = (
                    tool_result.arguments.get("interaction_kind") == "tool_approval"
                )
                if is_approval:
                    for tool in ctx.tools or []:
                        function = (
                            tool.get("function", {})
                            if isinstance(tool, dict)
                            else getattr(tool, "function", None)
                        )
                        name = (
                            function.get("name")
                            if isinstance(function, dict)
                            else getattr(function, "name", None)
                        )
                        if name != tool_name:
                            continue
                        description = (
                            function.get("description")
                            if isinstance(function, dict)
                            else getattr(function, "description", None)
                        )
                        if isinstance(description, str) and description.strip():
                            tool_result = ToolInteractionRequest(
                                tool_name=tool_name,
                                arguments={
                                    **tool_result.arguments,
                                    "tool_description": description.strip(),
                                },
                            )
                        break
                metric_status = "waiting"
                # Approval is a pause of the model's call, not a different
                # call. Keep the original business arguments in the visible
                # and persisted tool call; ``execution_id`` and
                # ``interaction_kind`` belong to the durable pause marker.
                call_arguments = (
                    _tool_call_arguments(tc.function.arguments)
                    if is_approval
                    else tool_result.arguments
                )
                call_sse = build_tool_call_sse_event(
                    tool_call_id=tc.id,
                    tool_name=tool_name,
                    tool_display_name=display_name,
                    arguments=call_arguments,
                )
                return (
                    call_sse,
                    "",
                    None,
                    {
                        "id": tc.id,
                        "name": tool_name,
                        "arguments": call_arguments,
                        "display_result": "",
                        "llm_result": "",
                        "display_name": display_name,
                        "interaction": tool_result,
                    },
                )

            if isinstance(tool_result, AssetViewResult):
                llm_result = tool_result.llm_result
                record = {
                    "id": tc.id,
                    "name": tool_name,
                    "arguments": arguments,
                    "persist_result": json.dumps(
                        {
                            "kind": "asset.view.persisted",
                            "version": 1,
                            "display": tool_result.display_result,
                            "marker": tool_result.llm_result,
                        },
                        ensure_ascii=False,
                    ),
                    "llm_result": llm_result,
                    "display_result": json.dumps(
                        tool_result.display_result, ensure_ascii=False
                    ),
                    "display_name": display_name,
                }
                metric_status = "completed"
                return (
                    self._build_tool_call_sse(tc),
                    build_tool_result_sse_event(
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        tool_display_name=display_name,
                        display_result=json.dumps(
                            tool_result.display_result, ensure_ascii=False
                        ),
                    ),
                    None,
                    record,
                )
            display_result, llm_result = get_tool_execution_payloads(
                tool_result, tool_name
            )
            metric_status = "completed"
            # Error detection also matters for trajectory capture when
            # dependency metrics are disabled.
            if tool_started_at is not None or ctx.observability_run_id is not None:
                try:
                    parsed_result = json.loads(display_result)
                except (TypeError, ValueError):
                    parsed_result = None
                if (
                    isinstance(parsed_result, dict)
                    and parsed_result.get("error") is not None
                ):
                    metric_status = "failed"
                    metric_error_category = "tool_error"
            if ctx.append_generated_images is not None:
                ctx.append_generated_images(image_pool, image_inventory, display_result)
        except Exception as exc:
            metric_error_category = type(exc).__name__[:32]
            metric_status = "failed"
            logger.warning(
                "Tool %s failed in AgentLoop: %s",
                tool_name,
                str(exc) or type(exc).__name__,
                exc_info=True,
            )
            display_result = json.dumps(
                {"error": str(exc) or type(exc).__name__}, ensure_ascii=False
            )
            llm_result = display_result
        finally:
            if tool_started_at is not None:
                if (
                    len(self.result.dependency_metrics)
                    >= MAX_DEPENDENCY_METRICS_PER_PASS
                ):
                    self.result.dependency_metrics_truncated = True
                else:
                    finished_at = time.time()
                    self.result.dependency_metrics.append(
                        {
                            "span_id": str(uuid4()),
                            "kind": "retrieval"
                            if tool_name == "knowledge_search"
                            else "tool",
                            "name": tool_name[:100],
                            "tool_call_id": tc.id[:100],
                            "status": metric_status,
                            "started_at": datetime.fromtimestamp(
                                tool_started_at, timezone.utc
                            ).isoformat(),
                            "finished_at": datetime.fromtimestamp(
                                finished_at, timezone.utc
                            ).isoformat(),
                            "duration_ms": max(
                                0, int((time.monotonic() - tool_started_clock) * 1000)
                            ),
                            "error_category": metric_error_category,
                        }
                    )
            if ctx.observability_run_id is not None and trajectory_started_at:
                try:
                    from app.services.observability_trajectory import (
                        record_tool_call,
                    )

                    finished_clock = time.monotonic()
                    await record_tool_call(
                        run_id=ctx.observability_run_id,
                        conversation_id=ctx.conversation.id,
                        parent_id=self._current_model_entry_id,
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        arguments=trajectory_arguments,
                        status=(
                            metric_status
                            if metric_status != "in_progress"
                            else "interrupted"
                        ),
                        started_at=trajectory_started_at,
                        finished_at=trajectory_started_at
                        + (finished_clock - trajectory_started_clock),
                        duration_ms=max(
                            0,
                            int((finished_clock - trajectory_started_clock) * 1000),
                        ),
                        kind="retrieval" if tool_name == "knowledge_search" else "tool",
                    )
                except Exception:
                    # Telemetry must never override the tool's own result or
                    # exception in this finally block.
                    logger.debug("Tool trajectory dropped", exc_info=True)

        if reset_notices:
            display_result = _include_workspace_reset_result(
                display_result, reset_notices
            )
            # Recovery control data must remain machine-readable for replanning,
            # so this rare event keeps the structured payload instead of the
            # compact prose used for ordinary results.
            llm_result = display_result

        persist_result = persistable_model_result(
            tool_name,
            display_result,
            llm_result,
            explicit=isinstance(tool_result, ToolExecutionResult),
        )
        if ctx.observability_run_id is not None:
            from app.services.observability_payload import record_tool_payload

            await record_tool_payload(
                run_id=ctx.observability_run_id,
                tool_call_id=tc.id,
                tool_name=tool_name,
                display_result=display_result,
                model_result=llm_result,
                renderer=tool_name if tool_name in KNOWN_OUTPUT_TOOLS else None,
                conversation_id=ctx.conversation.id,
                error=metric_error_category if metric_status == "failed" else None,
            )

        return (
            self._build_tool_call_sse(tc),
            build_tool_result_sse_event(
                tool_call_id=tc.id,
                tool_name=tool_name,
                tool_display_name=display_name,
                display_result=display_result,
            ),
            build_media_result_sse_event(display_result),
            {
                "id": tc.id,
                "name": tool_name,
                "arguments": arguments,
                "persist_result": persist_result,
                "display_result": display_result,
                "llm_result": llm_result,
                "display_name": display_name,
            },
        )

    def _skipped_tool(
        self, tc: Any, *, reason: str
    ) -> tuple[str, str, str | None, dict[str, Any]]:
        """Build a protocol-complete result without executing a tool."""
        tool_name = getattr(tc.function, "name", None) or ""
        arguments = _safe_arguments(getattr(tc.function, "arguments", None))
        display_name = self.context.tool_display_names.get(tool_name, tool_name)
        error_result = json.dumps({"error": reason}, ensure_ascii=False)
        if not tool_name:
            return (
                "",
                "",
                None,
                {
                    "id": tc.id,
                    "name": "",
                    "arguments": arguments,
                    "display_result": error_result,
                    "llm_result": error_result,
                    "display_name": "",
                },
            )
        return (
            build_tool_call_sse_event(
                tool_call_id=tc.id,
                tool_name=tool_name,
                tool_display_name=display_name,
                arguments=arguments,
            ),
            build_tool_result_sse_event(
                tool_call_id=tc.id,
                tool_name=tool_name,
                tool_display_name=display_name,
                display_result=error_result,
            ),
            None,
            {
                "id": tc.id,
                "name": tool_name,
                "arguments": arguments,
                "display_result": error_result,
                "llm_result": error_result,
                "display_name": display_name,
            },
        )

    async def _persist_tool_record(
        self,
        record: dict[str, Any],
        *,
        iteration: int,
        content: str,
        reasoning: str,
    ) -> None:
        """Persist one tool protocol pair in stable round order."""
        ctx = self.context
        assert ctx.round_id is not None
        if record["name"]:
            step_index = self._next_round_index()
            await agent_round.persist_assistant_step(
                conversation=ctx.conversation,
                content=content,
                reasoning_content=reasoning or None,
                tool_calls=[
                    {
                        "id": record["id"],
                        "name": record["name"],
                        "display_name": record["display_name"],
                        "arguments": record["arguments"],
                    }
                ],
                model_used=ctx.model_used,
                round_id=ctx.round_id,
                round_index=step_index,
                iteration_index=iteration,
                branch_parent_id=ctx.step_branch_parent_id,
            )
            self._append_history(
                role="assistant",
                content=content,
                reasoning_content=reasoning or None,
                tool_calls=[
                    {
                        "id": record["id"],
                        "name": record["name"],
                        "display_name": record["display_name"],
                        "arguments": record["arguments"],
                    }
                ],
                round_index=step_index,
                iteration=iteration,
            )
            ctx.created_message_count += 1

        tool_index = self._next_round_index()
        await agent_round.persist_tool_result(
            conversation=ctx.conversation,
            content=record.get("persist_result") or record["display_result"],
            tool_call_id=record["id"],
            tool_name=record["name"],
            round_id=ctx.round_id,
            round_index=tool_index,
            iteration_index=iteration,
            branch_parent_id=ctx.step_branch_parent_id,
        )
        self._append_history(
            role="tool",
            content=record["llm_result"],
            tool_call_id=record["id"],
            tool_name=record["name"],
            round_index=tool_index,
            iteration=iteration,
        )
        ctx.created_message_count += 1

    def _context_kwargs(self, tool_definition_tokens: int) -> dict[str, Any]:
        ctx = self.context
        return dict(
            agent=ctx.agent,
            conversation=ctx.conversation,
            user_message=ctx.user_message,
            current_user_message_id=ctx.current_user_message_id,
            user_locale=ctx.user_locale,
            history_override=ctx.working_history_override,
            input_capabilities=ctx.input_capabilities,
            model_config=self.context.model_config,
            include_current_user_message=ctx.include_current_user_message,
            exclude_message_ids=ctx.exclude_message_ids,
            history_before_message_created_at=ctx.history_before_message_created_at,
            tool_timeouts=ctx.tool_timeouts,
            user=ctx.user,
            protected_round_id=ctx.protected_round_id,
            tool_definition_tokens=tool_definition_tokens,
            model_id=ctx.model_id,
            tokenizer_model_id=ctx.tokenizer_model_id,
            model_context_limit=ctx.model_context_limit,
            model_max_output_tokens=ctx.model_max_output_tokens,
            current_images=ctx.current_images,
        )

    async def _begin_model_trajectory(
        self,
        messages_for_llm: list[dict[str, Any]],
        *,
        fallback: bool = False,
        tools: list[Any] | None = None,
    ) -> Any:
        """Snapshot the request at the boundary, before history can mutate."""
        ctx = self.context
        if ctx.observability_run_id is None:
            self._current_model_entry_id = None
            return None
        try:
            from app.services.observability_trajectory import (
                record_model_request,
                safe_model_options,
            )

            handle = await record_model_request(
                run_id=ctx.observability_run_id,
                conversation_id=ctx.conversation.id if ctx.conversation else None,
                model=ctx.tokenizer_model_id or ctx.model_used or ctx.model_id,
                provider=ctx.model_provider,
                model_id=ctx.model_id,
                streaming=bool(
                    ctx.streaming and ctx.team_chat_stream is not None and not fallback
                ),
                messages=messages_for_llm,
                tools=tools if tools is not None else ctx.tools,
                options=safe_model_options(ctx.model_config),
                # Configured budgets, not verified effective provider values.
                limits={
                    "context_limit": ctx.model_context_limit,
                    "configured_max_output_tokens": ctx.model_max_output_tokens,
                },
                fallback=fallback,
            )
        except Exception:
            logger.debug("Model request trajectory dropped", exc_info=True)
            handle = None
        self._current_model_entry_id = handle.entry_id if handle else None
        return handle

    async def _finish_model_trajectory(
        self,
        handle: Any,
        *,
        status: str,
        content: str,
        reasoning: str,
        tool_calls: list[Any],
        finish_reason: str | None,
        usage: Any,
        error: str | None = None,
    ) -> None:
        """Persist the actual response without affecting the model turn."""
        if handle is None:
            return
        try:
            from app.services.observability_trajectory import finish_model_call

            token_usage: dict[str, int] | None = None
            if usage is not None:
                token_usage = {
                    "prompt": int(getattr(usage, "prompt_tokens", 0) or 0),
                    "completion": int(getattr(usage, "completion_tokens", 0) or 0),
                    "total": int(getattr(usage, "total_tokens", 0) or 0),
                }
                for key, attribute in (
                    ("cache_read", "cache_read_tokens"),
                    ("cache_creation", "cache_creation_tokens"),
                ):
                    value = int(getattr(usage, attribute, 0) or 0)
                    if value:
                        token_usage[key] = value
            await finish_model_call(
                handle,
                status=status,
                content=content,
                reasoning=reasoning,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                token_usage=token_usage,
                error=error,
            )
        except Exception:
            # Telemetry must never alter model-turn outcomes.
            logger.debug("Model response trajectory dropped", exc_info=True)

    async def _finalize_active_model(self, status: str, error: str | None) -> None:
        finalizer = self._active_model_finalizer
        if finalizer is None:
            return
        self._active_model_finalizer = None
        try:
            await finalizer(status, error)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Model trajectory finalization dropped", exc_info=True)

    def _compression_enabled(self) -> bool:
        """Whether the agent allows automatic context reduction at all."""
        from app.services.chat_context import get_context_compression_config

        try:
            config = get_context_compression_config(self.context.agent)
        except Exception:
            logger.debug("Context compression config unavailable", exc_info=True)
            return True
        return bool(config.get("enabled", True))

    def _estimate_request_tokens(
        self, messages: list[dict[str, Any]], tools: list[Any] | None
    ) -> int:
        """Estimate provider input tokens for a candidate request view."""
        from app.llm.token_counter import count_message_tokens

        ctx = self.context
        try:
            total = count_message_tokens(
                messages,
                model_id=ctx.tokenizer_model_id,
                provider=ctx.model_provider,
                include_tool_calls=True,
            )
        except Exception:
            total = (
                sum(len(str(message.get("content") or "")) for message in messages) // 4
            )
        if tools and ctx.count_tool_definition_tokens is not None:
            try:
                total += int(
                    ctx.count_tool_definition_tokens(
                        tools, ctx.tokenizer_model_id, ctx.model_provider
                    )
                    or 0
                )
            except Exception:
                logger.debug("Tool schema token estimation failed", exc_info=True)
        return total

    async def _shed_optional_tools(self) -> list[str]:
        """Drop optional loaded tool schemas; empty means no reduction."""
        discovery = self.context.tool_discovery
        if discovery is None:
            return []
        reducer = getattr(discovery, "reduce_for_retry", None)
        if not callable(reducer):
            return []
        try:
            removed = await reducer()
        except Exception:
            logger.warning("Optional tool schema reduction failed", exc_info=True)
            return []
        return [str(name) for name in removed or [] if name]

    async def _apply_context_overflow_retry(
        self,
        *,
        attempt: int,
        messages: list[dict[str, Any]],
        tools: list[Any] | None,
        protected_indexes: set[int] | None = None,
        notice_index: int | None = None,
    ) -> (
        tuple[
            list[dict[str, Any]],
            list[Any] | None,
            list[str],
            int,
            set[int],
            int | None,
        ]
        | None
    ):
        """Build a strictly smaller request view for one overflow retry.

        Attempt 0 sheds optional loaded tool schemas and removes the oldest
        half of removable (unprotected plain-assistant) history units;
        attempt 1 removes all remaining reducible history. History reduction
        fails closed without a protection mask and never drops user messages,
        context summaries, tool calls or tool results. ``notice_index`` is the
        loop-owned omission notice position, replaced by index rather than by
        matching message text. Returns ``(messages, tools, removed_tool_names,
        removed_message_count, protected_indexes, notice_index)`` or ``None``
        when nothing would actually shrink.
        """
        if attempt >= CONTEXT_OVERFLOW_MAX_RETRIES:
            return None
        if not self._compression_enabled():
            return None

        protected = set(protected_indexes or ())
        removed_tools: list[str] = []
        if attempt == 0:
            removed_tools = await self._shed_optional_tools()
        new_tools = tools
        if removed_tools and self.context.tool_discovery is not None:
            # The pre-shed list is stale; resolve the surviving authorized set.
            new_tools = self.context.tool_discovery.tools_for_turn()
            if new_tools == tools:
                # No actual schema change: never claim or retry on it.
                removed_tools = []

        before_tokens = self._estimate_request_tokens(messages, tools)
        candidate = messages
        candidate_protected = protected
        candidate_notice = notice_index
        removed_messages = 0
        for drop_all in (attempt > 0, True):
            reduced, dropped, remapped, new_notice = _reduce_history_messages(
                messages,
                drop_all=drop_all,
                protected_indexes=protected,
                notice_index=notice_index,
            )
            if not dropped:
                continue
            if self._estimate_request_tokens(reduced, new_tools) < before_tokens:
                candidate = reduced
                candidate_protected = remapped
                candidate_notice = new_notice
                removed_messages = dropped
                break

        if candidate is messages and not removed_tools:
            return None
        return (
            candidate,
            new_tools,
            removed_tools,
            removed_messages,
            candidate_protected,
            candidate_notice,
        )

    def _overflow_compression_events(
        self,
        *,
        before_tokens: int,
        after_tokens: int,
        input_budget: int,
        removed_tools: list[str],
        removed_messages: int,
    ) -> list[str]:
        """Emit the existing compression events describing the retry reduction."""
        from app.services.chat_context import CompressionMeta

        actions = ["provider_overflow_retry"]
        if removed_messages:
            actions.append("provider_overflow_history_omitted")
        if removed_tools:
            actions.append("provider_overflow_tool_schemas_shed")
        limit = int(self.context.model_context_limit or 0)
        meta = CompressionMeta(
            stage="fallback",
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            input_budget=input_budget or max(before_tokens, 1),
            trigger_ratio=0.9,
            utilization_before=before_tokens / limit if limit else 0.0,
            utilization_after=after_tokens / limit if limit else 0.0,
            policy_used="provider_overflow_retry",
            actions=actions,
            context_limit=limit,
            context_limit_source="configured" if limit else "default",
        )
        start = self._emit(
            COMPRESSION_START, {"stage": "fallback", "trigger": "provider_overflow"}
        )
        end = self._emit(
            COMPRESSION_END, {"compression": meta, "trigger": "provider_overflow"}
        )
        logger.warning(
            "Provider context overflow; retrying with a reduced request "
            "(messages_removed=%d, tools_shed=%d)",
            removed_messages,
            len(removed_tools),
        )
        return [event for event in (start, end) if event]

    async def _prepare_overflow_retry(
        self,
        *,
        exc: BaseException,
        attempt: int,
        messages: list[dict[str, Any]],
        tools: list[Any] | None,
        protected_indexes: set[int],
        notice_index: int | None,
        input_budget: int,
    ) -> (
        tuple[list[dict[str, Any]], list[Any] | None, set[int], list[str], int | None]
        | None
    ):
        """Reduce a request view after a classified provider overflow."""
        if not _is_provider_context_overflow(exc):
            return None
        before_tokens = self._estimate_request_tokens(messages, tools)
        retry = await self._apply_context_overflow_retry(
            attempt=attempt,
            messages=messages,
            tools=tools,
            protected_indexes=protected_indexes,
            notice_index=notice_index,
        )
        if retry is None:
            return None
        (
            messages,
            tools,
            removed_tools,
            removed_messages,
            protected,
            notice_index,
        ) = retry
        return (
            messages,
            tools,
            protected,
            self._overflow_compression_events(
                before_tokens=before_tokens,
                after_tokens=self._estimate_request_tokens(messages, tools),
                input_budget=input_budget,
                removed_tools=removed_tools,
                removed_messages=removed_messages,
            ),
            notice_index,
        )

    async def _iter_overflow_retried_request(
        self,
        *,
        request: Callable[[list[dict[str, Any]], list[Any] | None], Any],
        messages: list[dict[str, Any]],
        tools: list[Any] | None,
        protected_indexes: set[int],
        input_budget: int,
        finalize: Callable[[str, str | None], Any],
        on_retry: Callable[[list[dict[str, Any]], list[Any] | None, set[int]], Any],
        notice_index: int | None = None,
        initial_retries: int = 0,
    ) -> AsyncIterator[Any]:
        """Run one request with bounded overflow retries before any output.

        Used for non-streaming calls and for the first chunk of a streaming
        call. Yields compression-event lists between attempts, then exactly
        one ``_OverflowRetryResult``. ``finalize`` closes a failed attempt and
        ``on_retry`` re-arms per-attempt accounting before the next one.
        """
        attempt = initial_retries
        while True:
            try:
                value = await request(messages, tools)
            except asyncio.CancelledError:
                await finalize("cancelled", "cancelled")
                raise
            except ContextLengthError as exc:
                prepared = await self._prepare_overflow_retry(
                    exc=exc,
                    attempt=attempt,
                    messages=messages,
                    tools=tools,
                    protected_indexes=protected_indexes,
                    notice_index=notice_index,
                    input_budget=input_budget,
                )
                await finalize("failed", f"{type(exc).__name__}: {exc}")
                if prepared is None:
                    raise
                (
                    messages,
                    tools,
                    protected_indexes,
                    events,
                    notice_index,
                ) = prepared
                attempt += 1
                await on_retry(messages, tools, protected_indexes)
                if events:
                    yield events
                continue
            yield _OverflowRetryResult(value, notice_index, attempt)
            return

    async def run(self) -> AsyncIterator[str | None]:
        start_time = time.time()
        if self.context.deadline_seconds is not None:
            self._deadline_at = start_time + self.context.deadline_seconds
        try:
            async for output in self._run(start_time):
                yield output
        except asyncio.CancelledError:
            await self._finalize_active_model("cancelled", "cancelled")
            raise
        except GeneratorExit:
            await self._finalize_active_model("cancelled", "closed")
            raise
        except Exception as exc:
            await self._finalize_active_model("failed", f"{type(exc).__name__}: {exc}")
            # Capture partial state so the caller's error handlers can persist
            # reasoning/content produced before the failure.
            if self.result.duration_ms == 0:
                self.result.duration_ms = int((time.time() - start_time) * 1000)
            raise

    async def _run(self, start_time: float) -> AsyncIterator[str | None]:
        ctx = self.context
        first_token_time: float | None = None
        aggregate_input_tokens = 0
        aggregate_output_tokens = 0
        aggregate_cache_read_tokens = 0
        aggregate_cache_creation_tokens = 0
        aggregate_total_input_tokens = 0
        max_iterations_reached = False
        full_content = ""
        full_reasoning = ""

        if ctx.max_iterations is None and ctx.deadline_seconds is None:
            raise ValueError(
                "AgentLoopContext must specify at least one bound: max_iterations or deadline_seconds"
            )

        iteration = ctx.iteration_offset
        while True:
            if (
                ctx.max_iterations is not None
                and iteration >= ctx.max_iterations
                and not ctx.resume_tool_calls
            ):
                break
            iteration += 1
            # ---- deadline guard (primary normal guard) ------------------------
            if ctx.deadline_seconds is not None and (
                time.time() - start_time > ctx.deadline_seconds
            ):
                self.result.deadline_exceeded = True
                self.result.full_content = full_content
                self.result.full_reasoning = full_reasoning
                self.result.duration_ms = int((time.time() - start_time) * 1000)
                self.result.first_token_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time is not None
                    else None
                )
                return

            # ---- heartbeat / disconnect (stream paths only) ------------------
            if ctx.send_heartbeat_if_needed is not None:
                (
                    should_continue,
                    new_last_event_time,
                ) = await ctx.send_heartbeat_if_needed(
                    self._last_event_time, ctx.heartbeat_interval, ctx.request
                )
                if not should_continue:
                    self.result.manually_stopped = True
                    self.result.full_content = full_content
                    self.result.full_reasoning = full_reasoning
                    self.result.duration_ms = int((time.time() - start_time) * 1000)
                    self.result.first_token_ms = (
                        int((first_token_time - start_time) * 1000)
                        if first_token_time is not None
                        else None
                    )
                    return

                if new_last_event_time > self._last_event_time:
                    heartbeat_event = self._emit(HEARTBEAT, {})
                    if heartbeat_event:
                        yield heartbeat_event
                    self._last_event_time = new_last_event_time

            # ---- durable-run steering/stop (worker paths) --------------------
            # Consume queued inputs at a safe boundary before building the next
            # provider context. Steering/follow-up are injected into the
            # working history; a stop flips a flag the loop honors between
            # model turns (already-running tool calls are not force-killed).
            if ctx.consume_inputs is not None:
                consumed = await ctx.consume_inputs()
                for item in consumed or []:
                    if ctx.input_consumed is not None:
                        await ctx.input_consumed(item)
            if ctx.stop_requested is not None and await ctx.stop_requested():
                self.result.manually_stopped = True
                self.result.full_content = full_content
                self.result.full_reasoning = full_reasoning
                self.result.duration_ms = int((time.time() - start_time) * 1000)
                self.result.first_token_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time is not None
                    else None
                )
                return

            # ---- provider context -------------------------------------------
            # Tool discovery may change the visible schemas after each turn
            # (``load_tools``), so the list is resolved once per iteration.
            turn_tools = (
                ctx.tool_discovery.tools_for_turn()
                if ctx.tool_discovery is not None and not ctx.resume_tool_calls
                else ctx.tools
            )
            if not ctx.resume_tool_calls:
                ctx.active_resume_tool_visible_names = _tool_schema_names(turn_tools)
            messages_for_llm: list[dict[str, Any]] = []
            prepared: Any = None
            if not ctx.resume_tool_calls:
                tool_definition_tokens = (
                    ctx.count_tool_definition_tokens(
                        turn_tools, ctx.tokenizer_model_id, ctx.model_provider
                    )
                    if ctx.count_tool_definition_tokens and turn_tools
                    else 0
                )
                kwargs = self._context_kwargs(tool_definition_tokens)
                assert ctx.build_turn is not None
                turn = await ctx.build_turn(**kwargs)
                if turn.plan is not None:
                    if turn.will_summarize:
                        start_event = self._emit(
                            COMPRESSION_START,
                            {"compression": turn.plan.compression, "stage": "macro"},
                        )
                        if start_event:
                            yield start_event
                    prepared = await turn.plan.finalize()
                    end_event = self._emit(
                        COMPRESSION_END, {"compression": prepared.compression}
                    )
                    if end_event:
                        yield end_event
                else:
                    prepared = turn.prepared
                messages_for_llm = [
                    m.model_dump(exclude_none=True) for m in prepared.messages
                ]

            # Per-iteration accumulators reset exactly like the original
            # per-path loops (content from a tool turn is not carried into the
            # terminal message; only the last non-tool turn's content is).
            reasoning_started = False
            iteration_content = ""
            iteration_reasoning = ""
            full_content = ""
            full_reasoning = ""
            collected_tool_calls: list[Any] = []
            started_tool_call_ids: set[str] = set()
            streamed_tool_calls: dict[str, Any] = {}
            emitted_any = False
            stream_usage = None
            used_fallback = False
            client_disconnected = False
            pause_turn_pending = False
            resuming_calls = bool(ctx.resume_tool_calls)
            if resuming_calls:
                replay_visible_names = (
                    set(ctx.resume_tool_visible_names)
                    if ctx.resume_tool_visible_names is not None
                    else None
                )
                if ctx.tool_discovery is not None and replay_visible_names is not None:
                    ctx.tool_discovery.turn_visible_names = set(replay_visible_names)
            else:
                replay_visible_names = ctx.active_resume_tool_visible_names
            ctx.active_resume_tool_visible_names = replay_visible_names
            ctx.replay_tool_call_ids = (
                set(ctx.resume_tool_call_ids) if resuming_calls else set()
            )

            model_state: dict[str, Any] = {
                "handle": await self._begin_model_trajectory(
                    messages_for_llm, tools=turn_tools
                )
                if not resuming_calls
                else None,
                "finalized": False,
                "finish_reason": None,
            }

            async def finalize_model(status: str, error: str | None = None) -> None:
                if model_state["finalized"]:
                    return
                model_state["finalized"] = True
                self._active_model_finalizer = None
                await self._finish_model_trajectory(
                    model_state["handle"],
                    status=status,
                    content=iteration_content,
                    reasoning=iteration_reasoning,
                    tool_calls=collected_tool_calls,
                    finish_reason=model_state["finish_reason"],
                    usage=stream_usage,
                    error=error,
                )

            self._active_model_finalizer = finalize_model

            # ---- one model turn ---------------------------------------------
            if ctx.resume_tool_calls:
                collected_tool_calls = ctx.resume_tool_calls
                ctx.resume_tool_calls = None
                iteration -= 1
            elif ctx.streaming and ctx.team_chat_stream is not None:
                # Retry only before the stream yields anything. The request
                # helper finalizes rejected attempts over a smaller view.
                async def _stream_request(
                    msgs: list[dict[str, Any]], tools: list[Any] | None
                ) -> tuple[Any, AsyncIterator[Any]]:
                    stream = ctx.team_chat_stream(
                        team_id=str(ctx.agent.team_id),
                        messages=msgs,
                        model_id=ctx.model_id,
                        tools=tools,
                    )
                    timed = iter_with_idle_timeout(
                        stream,
                        timeout_seconds=ctx.idle_timeout,
                        activity_predicate=None,
                    )
                    try:
                        return await timed.__anext__(), timed
                    except StopAsyncIteration:
                        return None, timed
                    except ContextLengthError:
                        close = getattr(stream, "aclose", None)
                        if callable(close):
                            try:
                                await close()
                            except Exception:
                                logger.debug(
                                    "Provider stream close failed", exc_info=True
                                )
                        raise

                stream_protected = set(
                    getattr(prepared, "protected_indexes", None) or ()
                )
                input_budget = int(
                    getattr(getattr(prepared, "token_budget", None), "input_budget", 0)
                    or 0
                )
                first_chunk: Any = None
                timed_stream: AsyncIterator[Any] | None = None
                stream_notice_index: int | None = None
                stream_retry_count = 0

                async def _on_stream_retry(
                    retry_messages: list[dict[str, Any]],
                    retry_tools: list[Any] | None,
                    retry_protected: set[int],
                ) -> None:
                    nonlocal \
                        messages_for_llm, \
                        turn_tools, \
                        stream_usage, \
                        stream_protected
                    messages_for_llm = retry_messages
                    turn_tools = retry_tools
                    stream_protected = retry_protected
                    ctx.active_resume_tool_visible_names = _tool_schema_names(
                        retry_tools
                    )
                    stream_usage = None
                    model_state.update(
                        handle=await self._begin_model_trajectory(
                            messages_for_llm, tools=turn_tools
                        ),
                        finalized=False,
                        finish_reason=None,
                    )
                    self._active_model_finalizer = finalize_model

                async for item in self._iter_overflow_retried_request(
                    request=_stream_request,
                    messages=messages_for_llm,
                    tools=turn_tools,
                    protected_indexes=stream_protected,
                    input_budget=input_budget,
                    finalize=finalize_model,
                    on_retry=_on_stream_retry,
                ):
                    if isinstance(item, _OverflowRetryResult):
                        first_chunk, timed_stream = item.value
                        stream_notice_index = item.notice_index
                        stream_retry_count = item.retry_count
                    else:
                        for event in item:
                            yield event
                assert timed_stream is not None

                async def _with_first(
                    first: Any, rest: AsyncIterator[Any]
                ) -> AsyncIterator[Any]:
                    if first is not None:
                        yield first
                    async for item in rest:
                        yield item

                async def guarded_stream(iterator: Any) -> AsyncIterator[Any]:
                    try:
                        async for item in iterator:
                            yield item
                    except asyncio.CancelledError:
                        await finalize_model("cancelled", "cancelled")
                        raise
                    except Exception as exc:
                        await finalize_model("failed", f"{type(exc).__name__}: {exc}")
                        raise

                async for chunk in guarded_stream(
                    _with_first(first_chunk, timed_stream)
                ):
                    if chunk.usage:
                        stream_usage = chunk.usage
                    if ctx.is_disconnected and await ctx.is_disconnected():
                        client_disconnected = True
                        break
                    if chunk.delta.reasoning_content:
                        emitted_any = True
                        if not reasoning_started:
                            reasoning_started = True
                            event = self._emit(REASONING_START, {})
                            if event:
                                yield event
                        full_reasoning += chunk.delta.reasoning_content
                        iteration_reasoning += chunk.delta.reasoning_content
                        self.result.full_reasoning = full_reasoning
                        if first_token_time is None:
                            first_token_time = time.time()
                            self.result.first_token_ms = 0
                        event = self._emit(
                            REASONING_DELTA, {"delta": chunk.delta.reasoning_content}
                        )
                        if event:
                            yield event
                    if chunk.delta.content:
                        if reasoning_started and not full_content:
                            event = self._emit(REASONING_END, {})
                            if event:
                                yield event
                        full_content += chunk.delta.content
                        iteration_content += chunk.delta.content
                        self.result.full_content = full_content
                        if first_token_time is None:
                            first_token_time = time.time()
                        event = self._emit(
                            CONTENT_DELTA, {"delta": chunk.delta.content}
                        )
                        if event:
                            yield event
                    if chunk.delta.tool_calls:
                        emitted_any = True
                        collected_tool_calls = chunk.delta.tool_calls
                    if chunk.delta.tool_call_starts:
                        emitted_any = True
                        for tool_call in chunk.delta.tool_call_starts:
                            call_id = getattr(tool_call, "id", None)
                            if not call_id:
                                continue
                            tool_name = getattr(tool_call.function, "name", None) or ""
                            if tool_name not in self._mcp_tool_names and (
                                tool_name.startswith("mcp_")
                                or (
                                    tool_name
                                    and any(
                                        name.startswith(tool_name)
                                        for name in self._mcp_tool_names
                                    )
                                )
                            ):
                                continue
                            previous_call = streamed_tool_calls.get(call_id)
                            if previous_call is not None and not _tool_call_changed(
                                previous_call, tool_call
                            ):
                                continue
                            streamed_tool_calls[call_id] = tool_call
                            started_tool_call_ids.add(call_id)
                            call_sse = self._build_tool_call_sse(tool_call)
                            if call_sse and tool_name != "ask_user":
                                event = self._emit(TOOL_CALL, {"sse": call_sse})
                                if event:
                                    yield event
                    if (
                        chunk.stop_details
                        and chunk.stop_details.reason == StopReason.PAUSE_TURN
                    ):
                        pause_turn_pending = True
                    if chunk.finish_reason:
                        model_state["finish_reason"] = str(
                            getattr(chunk.finish_reason, "value", chunk.finish_reason)
                        )
                        if reasoning_started and not full_content:
                            event = self._emit(REASONING_END, {})
                            if event:
                                yield event
                        if chunk.finish_reason == FinishReason.LENGTH:
                            event = self._emit(OUTPUT_TRUNCATED, {})
                            if event:
                                yield event
                        if stream_usage is None:
                            continue
                        break
                if (
                    not emitted_any
                    and not full_content
                    and not collected_tool_calls
                    and not client_disconnected
                ):
                    assert ctx.team_chat is not None
                    # The fallback is a distinct provider invocation; finalize
                    # the empty stream separately instead of conflating it.
                    await finalize_model("empty")
                    model_state.update(
                        handle=await self._begin_model_trajectory(
                            messages_for_llm, fallback=True, tools=turn_tools
                        ),
                        finalized=False,
                        finish_reason=None,
                    )
                    self._active_model_finalizer = finalize_model

                    async def _fallback_request(
                        msgs: list[dict[str, Any]], tools: list[Any] | None
                    ) -> Any:
                        return await ctx.team_chat(
                            team_id=str(ctx.agent.team_id),
                            messages=msgs,
                            model_id=ctx.model_id,
                            tools=tools,
                        )

                    async def _on_fallback_retry(
                        retry_messages: list[dict[str, Any]],
                        retry_tools: list[Any] | None,
                        retry_protected: set[int],
                    ) -> None:
                        nonlocal messages_for_llm, turn_tools, stream_usage
                        nonlocal stream_protected
                        messages_for_llm = retry_messages
                        turn_tools = retry_tools
                        stream_protected = retry_protected
                        ctx.active_resume_tool_visible_names = _tool_schema_names(
                            retry_tools
                        )
                        stream_usage = None
                        model_state.update(
                            handle=await self._begin_model_trajectory(
                                retry_messages, fallback=True, tools=retry_tools
                            ),
                            finalized=False,
                            finish_reason=None,
                        )
                        self._active_model_finalizer = finalize_model

                    # No provider output exists here (the stream produced no
                    # chunk), so overflow retries are safe.
                    fallback_response: Any = None
                    async for item in self._iter_overflow_retried_request(
                        request=_fallback_request,
                        messages=messages_for_llm,
                        tools=turn_tools,
                        protected_indexes=stream_protected,
                        input_budget=input_budget,
                        finalize=finalize_model,
                        on_retry=_on_fallback_retry,
                        notice_index=stream_notice_index,
                        initial_retries=stream_retry_count,
                    ):
                        if isinstance(item, _OverflowRetryResult):
                            fallback_response = item.value
                        else:
                            for event in item:
                                yield event
                    used_fallback = True
                    fallback_finish = getattr(fallback_response, "finish_reason", None)
                    model_state["finish_reason"] = (
                        str(getattr(fallback_finish, "value", fallback_finish))
                        if fallback_finish is not None
                        else None
                    )
                    stream_usage = getattr(fallback_response, "usage", None)
                    collected_tool_calls = (
                        getattr(fallback_response, "tool_calls", None) or []
                    )
                    reasoning = getattr(fallback_response, "reasoning_content", None)
                    if reasoning:
                        event = self._emit(REASONING_START, {})
                        if event:
                            yield event
                        full_reasoning += reasoning
                        iteration_reasoning += reasoning
                        event = self._emit(REASONING_DELTA, {"delta": reasoning})
                        if event:
                            yield event
                        event = self._emit(REASONING_END, {})
                        if event:
                            yield event
                    content = getattr(fallback_response, "content", None)
                    if content:
                        full_content += content
                        iteration_content += content
                        event = self._emit(CONTENT_DELTA, {"delta": content})
                        if event:
                            yield event
            elif ctx.team_chat is not None:

                async def _request(
                    msgs: list[dict[str, Any]], tools: list[Any] | None
                ) -> Any:
                    return await ctx.team_chat(
                        team_id=str(ctx.agent.team_id),
                        messages=msgs,
                        model_id=ctx.model_id,
                        tools=tools,
                    )

                response: Any = None

                async def _on_retry(
                    retry_messages: list[dict[str, Any]],
                    retry_tools: list[Any] | None,
                    _retry_protected: set[int],
                ) -> None:
                    nonlocal messages_for_llm, turn_tools, stream_usage
                    messages_for_llm = retry_messages
                    turn_tools = retry_tools
                    ctx.active_resume_tool_visible_names = _tool_schema_names(
                        retry_tools
                    )
                    stream_usage = None
                    model_state.update(
                        handle=await self._begin_model_trajectory(
                            retry_messages, tools=retry_tools
                        ),
                        finalized=False,
                        finish_reason=None,
                    )
                    self._active_model_finalizer = finalize_model

                async for item in self._iter_overflow_retried_request(
                    request=_request,
                    messages=messages_for_llm,
                    tools=turn_tools,
                    protected_indexes=set(
                        getattr(prepared, "protected_indexes", None) or ()
                    ),
                    input_budget=int(
                        getattr(
                            getattr(prepared, "token_budget", None),
                            "input_budget",
                            0,
                        )
                        or 0
                    ),
                    finalize=finalize_model,
                    on_retry=_on_retry,
                ):
                    if isinstance(item, _OverflowRetryResult):
                        response = item.value
                    else:
                        for event in item:
                            yield event
                response_finish = getattr(response, "finish_reason", None)
                model_state["finish_reason"] = (
                    str(getattr(response_finish, "value", response_finish))
                    if response_finish is not None
                    else None
                )
                stream_usage = getattr(response, "usage", None)
                if (
                    getattr(response, "stop_details", None)
                    and response.stop_details.reason == StopReason.PAUSE_TURN
                ):
                    pause_turn_pending = True
                collected_tool_calls = getattr(response, "tool_calls", None) or []
                iteration_content = getattr(response, "content", "") or ""
                iteration_reasoning = getattr(response, "reasoning_content", "") or ""
                full_content += iteration_content
                full_reasoning += iteration_reasoning

            await finalize_model(
                "cancelled"
                if client_disconnected
                else "paused"
                if pause_turn_pending
                else "completed"
            )

            # ---- deadline guard after the turn ------------------------------
            if ctx.deadline_seconds is not None and (
                time.time() - start_time > ctx.deadline_seconds
            ):
                self.result.deadline_exceeded = True
                self.result.full_content = full_content
                self.result.full_reasoning = full_reasoning
                self.result.duration_ms = int((time.time() - start_time) * 1000)
                self.result.first_token_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time is not None
                    else None
                )
                return

            # ---- truncated tool-call pairing --------------------------------
            # When the provider truncates (finish == LENGTH) after announcing
            # tool calls, every started-but-uncompleted call must still get a
            # protocol result (skipped/error) so no orphan tool call enters
            # provider history or a later compaction cut.
            if started_tool_call_ids:
                missing_ids = started_tool_call_ids - {
                    tc.id for tc in collected_tool_calls if tc.id
                }
                # Append synthetic incomplete calls so the tool-execution block
                # below pairs them with error results.
                for call_id in missing_ids:
                    collected_tool_calls.append(_IncompleteToolCall(call_id))

            # ---- usage aggregation -------------------------------------------
            if ctx.calculate_usage is not None and not resuming_calls:
                (
                    iteration_input_tokens,
                    iteration_output_tokens,
                    iteration_cache_read_tokens,
                    iteration_cache_creation_tokens,
                    iteration_total_input_tokens,
                ) = ctx.calculate_usage(
                    tools=turn_tools,
                    messages=messages_for_llm,
                    content=iteration_content,
                    reasoning_content=iteration_reasoning,
                    tool_calls=collected_tool_calls,
                    usage=stream_usage,
                    model_id=ctx.tokenizer_model_id,
                    provider=ctx.model_provider,
                )
                aggregate_input_tokens += iteration_input_tokens
                aggregate_output_tokens += iteration_output_tokens
                aggregate_cache_read_tokens += iteration_cache_read_tokens
                aggregate_cache_creation_tokens += iteration_cache_creation_tokens
                aggregate_total_input_tokens += iteration_total_input_tokens
                if ctx.record_stream_usage is not None and not used_fallback:
                    await ctx.record_stream_usage(
                        team_id=str(ctx.agent.team_id),
                        model_id=ctx.model_id,
                        input_tokens=iteration_input_tokens,
                        output_tokens=iteration_output_tokens,
                    )

            # ---- disconnect stop ----------------------------------------------
            if client_disconnected:
                self.result.manually_stopped = True
                self.result.full_content = full_content
                self.result.full_reasoning = full_reasoning
                self.result.duration_ms = int((time.time() - start_time) * 1000)
                self.result.first_token_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time is not None
                    else None
                )
                return

            # ---- tool execution ---------------------------------------------
            if collected_tool_calls:
                self._consecutive_pause_turns = 0
                assert ctx.round_id is not None
                pending_tool_calls: list[dict[str, Any]] = []
                pause_record: dict[str, Any] | None = None
                processed_call_count = 0
                for group in self._partition_tool_batch(collected_tool_calls):
                    if ctx.is_disconnected and await ctx.is_disconnected():
                        self.result.manually_stopped = True
                        self.result.full_content = full_content
                        self.result.full_reasoning = full_reasoning
                        self.result.duration_ms = int((time.time() - start_time) * 1000)
                        self.result.first_token_ms = (
                            int((first_token_time - start_time) * 1000)
                            if first_token_time is not None
                            else None
                        )
                        return
                    if ctx.stop_requested is not None and await ctx.stop_requested():
                        # Cooperative stop between barriers: unstarted calls
                        # get explicit protocol-complete skipped results.
                        for tc in group:
                            result = self._skipped_tool(
                                tc, reason="tool_call_skipped_due_to_stop"
                            )
                            call_sse, result_sse, media_sse, record = result
                            event = self._emit(TOOL_CALL, {"sse": call_sse})
                            if event:
                                yield event
                            event = self._emit(TOOL_RESULT, {"sse": result_sse})
                            if event:
                                yield event
                            if media_sse:
                                event = self._emit(MEDIA_RESULT, {"sse": media_sse})
                                if event:
                                    yield event
                            if ctx.persist_step_per_tool:
                                await self._persist_tool_record(
                                    record,
                                    iteration=iteration,
                                    content=iteration_content,
                                    reasoning=iteration_reasoning,
                                )
                            else:
                                pending_tool_calls.append(record)
                        break

                    # Shared group runs concurrently; exclusive group runs alone.
                    if (
                        len(group) > 1
                        and self._tool_concurrency_of(
                            getattr(group[0].function, "name", None) or ""
                        )
                        == "shared"
                    ):
                        import asyncio as _asyncio

                        # The initial status was emitted while the provider
                        # generated the call. Send a complete-input update only
                        # when the final call adds visible metadata.
                        for tc in group:
                            previous_call = streamed_tool_calls.get(
                                getattr(tc, "id", None)
                            )
                            if previous_call is not None and not _tool_call_changed(
                                previous_call, tc
                            ):
                                continue
                            call_sse = self._build_tool_call_sse(tc)
                            if call_sse:
                                event = self._emit(TOOL_CALL, {"sse": call_sse})
                                if event:
                                    yield event

                        async def _run_shared(tc):
                            return await self._execute_one_tool(
                                tc=tc,
                                image_pool=ctx.image_pool,
                                image_inventory=ctx.image_inventory,
                            )

                        results = await _asyncio.gather(
                            *[_run_shared(tc) for tc in group],
                            return_exceptions=True,
                        )
                        for tc, result in zip(group, results):
                            if isinstance(result, BaseException):
                                if isinstance(result, _asyncio.CancelledError):
                                    raise result
                                result = self._skipped_tool(
                                    tc,
                                    reason=(
                                        "tool_execution_failed: "
                                        f"{type(result).__name__}"
                                    ),
                                )
                            _call_sse, result_sse, media_sse, record = result
                            event = self._emit(TOOL_RESULT, {"sse": result_sse})
                            if event:
                                yield event
                            if media_sse:
                                event = self._emit(MEDIA_RESULT, {"sse": media_sse})
                                if event:
                                    yield event
                            if ctx.persist_step_per_tool:
                                await self._persist_tool_record(
                                    record,
                                    iteration=iteration,
                                    content=iteration_content,
                                    reasoning=iteration_reasoning,
                                )
                            else:
                                pending_tool_calls.append(record)
                        processed_call_count += len(group)
                    else:
                        for tc in group:
                            tool_name = getattr(tc.function, "name", None) or ""
                            previous_call = streamed_tool_calls.get(
                                getattr(tc, "id", None)
                            )
                            if tool_name != "ask_user" and (
                                previous_call is None
                                or _tool_call_changed(previous_call, tc)
                            ):
                                call_sse = self._build_tool_call_sse(tc)
                                if call_sse:
                                    event = self._emit(TOOL_CALL, {"sse": call_sse})
                                    if event:
                                        yield event
                            (
                                _call_sse,
                                result_sse,
                                media_sse,
                                record,
                            ) = await self._execute_one_tool(
                                tc=tc,
                                image_pool=ctx.image_pool,
                                image_inventory=ctx.image_inventory,
                            )
                            processed_call_count += 1
                            ctx.resume_tool_call_ids.discard(str(tc.id))
                            if record.get("interaction") is not None:
                                pause_record = record
                                pending_tool_calls.append(record)
                                break
                            event = self._emit(TOOL_RESULT, {"sse": result_sse})
                            if event:
                                yield event
                            if media_sse:
                                event = self._emit(MEDIA_RESULT, {"sse": media_sse})
                                if event:
                                    yield event
                            if ctx.persist_step_per_tool:
                                await self._persist_tool_record(
                                    record,
                                    iteration=iteration,
                                    content=iteration_content,
                                    reasoning=iteration_reasoning,
                                )
                            else:
                                pending_tool_calls.append(record)
                        if pause_record is not None:
                            break

                if not ctx.persist_step_per_tool and pending_tool_calls:
                    valid_tool_calls = [p for p in pending_tool_calls if p["name"]]
                    if valid_tool_calls:
                        step_index = self._next_round_index()
                        tool_call_payload = [
                            {
                                "id": p["id"],
                                "name": p["name"],
                                "display_name": p["display_name"],
                                "arguments": p["arguments"],
                            }
                            for p in valid_tool_calls
                        ]
                        await agent_round.persist_assistant_step(
                            conversation=ctx.conversation,
                            content=iteration_content,
                            reasoning_content=iteration_reasoning or None,
                            tool_calls=tool_call_payload,
                            model_used=ctx.model_used,
                            round_id=ctx.round_id,
                            round_index=step_index,
                            iteration_index=iteration,
                            branch_parent_id=ctx.step_branch_parent_id,
                        )
                        self._append_history(
                            role="assistant",
                            content=iteration_content,
                            reasoning_content=iteration_reasoning or None,
                            tool_calls=tool_call_payload,
                            round_index=step_index,
                            iteration=iteration,
                        )
                        ctx.created_message_count += 1

                    pause_tool_index: int | None = None
                    for p_data in pending_tool_calls:
                        tool_index = self._next_round_index()
                        if p_data.get("interaction") is not None:
                            pause_tool_index = tool_index
                            continue
                        await agent_round.persist_tool_result(
                            conversation=ctx.conversation,
                            content=p_data.get("persist_result")
                            or p_data["display_result"],
                            tool_call_id=p_data["id"],
                            tool_name=p_data["name"],
                            round_id=ctx.round_id,
                            round_index=tool_index,
                            iteration_index=iteration,
                            branch_parent_id=ctx.step_branch_parent_id,
                        )
                        self._append_history(
                            role="tool",
                            content=p_data["llm_result"],
                            tool_call_id=p_data["id"],
                            tool_name=p_data["name"],
                            round_index=tool_index,
                            iteration=iteration,
                        )
                        ctx.created_message_count += 1
                elif ctx.persist_step_per_tool and pause_record is not None:
                    step_index = self._next_round_index()
                    tool_call_payload = [
                        {
                            "id": pause_record["id"],
                            "name": pause_record["name"],
                            "display_name": pause_record["display_name"],
                            "arguments": pause_record["arguments"],
                        }
                    ]
                    await agent_round.persist_assistant_step(
                        conversation=ctx.conversation,
                        content=iteration_content,
                        reasoning_content=iteration_reasoning or None,
                        tool_calls=tool_call_payload,
                        model_used=ctx.model_used,
                        round_id=ctx.round_id,
                        round_index=step_index,
                        iteration_index=iteration,
                        branch_parent_id=ctx.step_branch_parent_id,
                    )
                    self._append_history(
                        role="assistant",
                        content=iteration_content,
                        reasoning_content=iteration_reasoning or None,
                        tool_calls=tool_call_payload,
                        round_index=step_index,
                        iteration=iteration,
                    )
                    ctx.created_message_count += 1
                    pause_tool_index = self._next_round_index()
                else:
                    pause_tool_index = None

                if pause_record is not None:
                    if ctx.pause_for_user is None or pause_tool_index is None:
                        raise RuntimeError("ask_user requires a durable pause callback")
                    interaction = pause_record["interaction"]
                    remaining_calls = collected_tool_calls[processed_call_count:]
                    if resuming_calls and remaining_calls:
                        ctx.resume_tool_calls = list(remaining_calls)
                        ctx.resume_tool_call_ids = {
                            str(call.id) for call in remaining_calls
                        }
                        ctx.replay_tool_call_ids = {
                            str(call.id) for call in remaining_calls
                        }
                        ctx.resume_tool_visible_names = (
                            set(ctx.active_resume_tool_visible_names)
                            if ctx.active_resume_tool_visible_names is not None
                            else None
                        )
                    else:
                        ctx.resume_tool_calls = None
                        ctx.resume_tool_call_ids.clear()
                        ctx.resume_tool_visible_names = None
                    await ctx.pause_for_user(
                        tool_call_id=pause_record["id"],
                        tool_name=pause_record["name"],
                        arguments=interaction.arguments,
                        round_id=ctx.round_id,
                        round_index=pause_tool_index,
                        iteration_index=iteration,
                        display_name=pause_record["display_name"],
                        resume_tool_visible_names=(
                            sorted(ctx.active_resume_tool_visible_names)
                            if ctx.active_resume_tool_visible_names is not None
                            else None
                        ),
                        remaining_tool_calls=remaining_calls,
                    )
                    call_sse = build_tool_call_sse_event(
                        tool_call_id=pause_record["id"],
                        tool_name=pause_record["name"],
                        tool_display_name=pause_record["display_name"],
                        arguments=pause_record["arguments"],
                    )
                    event = self._emit(TOOL_CALL, {"sse": call_sse})
                    if event:
                        yield event
                    self.result.waiting_for_user = True
                    self.result.full_content = full_content
                    self.result.full_reasoning = full_reasoning
                    self.result.aggregate_input_tokens = aggregate_input_tokens
                    self.result.aggregate_output_tokens = aggregate_output_tokens
                    self.result.aggregate_cache_read_tokens = (
                        aggregate_cache_read_tokens
                    )
                    self.result.aggregate_cache_creation_tokens = (
                        aggregate_cache_creation_tokens
                    )
                    self.result.aggregate_total_input_tokens = (
                        aggregate_total_input_tokens
                    )
                    self.result.created_message_count = ctx.created_message_count
                    self.result.final_round_index = self._round_index
                    self.result.duration_ms = int((time.time() - start_time) * 1000)
                    self.result.first_token_ms = (
                        int((first_token_time - start_time) * 1000)
                        if first_token_time is not None
                        else None
                    )
                    return

                if ctx.max_iterations is not None and iteration >= ctx.max_iterations:
                    max_iterations_reached = True
                    cap_text = ctx.cap_content() if ctx.cap_content else ""
                    event = self._emit(ITERATION_CAP_REACHED, {"content": cap_text})
                    if event:
                        yield event
                    full_content = ""
                    full_reasoning = ""
                    break
                continue

            # Pause-turn continuation: a provider-requested pause (e.g. cache
            # warm-up) with no tool calls is non-terminal. Replay the partial
            # assistant turn into history and resample, capped at 8 consecutive
            # continuations; a fresh tool-call turn resets the counter.
            if pause_turn_pending and not collected_tool_calls:
                if self._consecutive_pause_turns < self.PAUSE_TURN_LIMIT:
                    self._consecutive_pause_turns += 1
                    if full_content:
                        if ctx.working_history_override is None:
                            ctx.working_history_override = []
                        self._append_history(
                            role="assistant",
                            content=full_content,
                            reasoning_content=full_reasoning or None,
                            round_index=self._next_round_index(),
                            iteration=iteration,
                        )
                    full_content = ""
                    full_reasoning = ""
                    continue
            if ctx.stop_requested is not None and await ctx.stop_requested():
                self.result.manually_stopped = True
                self.result.full_content = full_content
                self.result.full_reasoning = full_reasoning
                self.result.duration_ms = int((time.time() - start_time) * 1000)
                self.result.first_token_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time is not None
                    else None
                )
                return
            if ctx.consume_inputs is not None:
                consumed_end = await ctx.consume_inputs()
                if consumed_end:
                    for item in consumed_end:
                        if ctx.input_consumed is not None:
                            await ctx.input_consumed(item)
                    if full_content:
                        if ctx.working_history_override is None:
                            ctx.working_history_override = []
                        self._append_history(
                            role="assistant",
                            content=full_content,
                            reasoning_content=full_reasoning or None,
                            round_index=self._next_round_index(),
                            iteration=iteration,
                        )
                    full_content = ""
                    full_reasoning = ""
                    continue

            if ctx.stop_requested is not None and await ctx.stop_requested():
                self.result.manually_stopped = True
                self.result.full_content = full_content
                self.result.full_reasoning = full_reasoning
                self.result.duration_ms = int((time.time() - start_time) * 1000)
                self.result.first_token_ms = (
                    int((first_token_time - start_time) * 1000)
                    if first_token_time is not None
                    else None
                )
                return
            break  # no tool calls and no queued inputs: round done
        self.result.full_content = full_content
        self.result.full_reasoning = full_reasoning
        self.result.max_iterations_reached = max_iterations_reached
        self.result.aggregate_input_tokens = aggregate_input_tokens
        self.result.aggregate_output_tokens = aggregate_output_tokens
        self.result.aggregate_cache_read_tokens = aggregate_cache_read_tokens
        self.result.aggregate_cache_creation_tokens = aggregate_cache_creation_tokens
        self.result.aggregate_total_input_tokens = aggregate_total_input_tokens
        self.result.duration_ms = int((time.time() - start_time) * 1000)
        self.result.first_token_ms = (
            int((first_token_time - start_time) * 1000)
            if first_token_time is not None
            else None
        )
        self.result.created_message_count = ctx.created_message_count
        self.result.final_round_index = self._round_index
