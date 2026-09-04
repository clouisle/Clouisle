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
updates; the loop lets model errors propagate.

The loop does NOT own: access checks, RAG retrieval, asset resolution, user
message creation, placeholder assistant creation, branch/version selection,
branch activation, stats updates. Those remain route-level concerns.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.api.v1.endpoints.chat_helpers import (
    get_tool_execution_payloads,
    iter_with_idle_timeout,
)
from app.api.v1.endpoints.chat_sse import (
    build_media_result_sse_event,
    build_tool_call_sse_event,
    build_tool_result_sse_event,
)
from app.api.v1.endpoints.chat_tools import execute_tool_call
from app.llm.tools.interaction import ToolInteractionRequest
from app.llm.types import ChatStreamChunk, FinishReason, StopReason
from app.services import agent_round

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
    model_supports_vision: bool = False
    # tools
    tools: list[Any] | None = None
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
    file_content: str | None = None
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
    max_iterations: int = 5
    iteration_offset: int = 0
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


def _tool_call_changed(previous: Any, current: Any) -> bool:
    """Return whether a streamed call update changes visible metadata."""
    previous_name = getattr(previous.function, "name", None) or ""
    current_name = getattr(current.function, "name", None) or ""
    return previous_name != current_name or (
        _safe_arguments(getattr(previous.function, "arguments", None))
        != _safe_arguments(getattr(current.function, "arguments", None))
    )


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
        self.result = AgentLoopResult()
        self._round_index = context.first_round_index
        self._consecutive_pause_turns = 0
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
        tool_runner = ctx.execute_tool_call or execute_tool_call
        try:
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
                call_sse = build_tool_call_sse_event(
                    tool_call_id=tc.id,
                    tool_name=tool_name,
                    tool_display_name=display_name,
                    arguments=tool_result.arguments,
                )
                return (
                    call_sse,
                    "",
                    None,
                    {
                        "id": tc.id,
                        "name": tool_name,
                        "arguments": tool_result.arguments,
                        "display_result": "",
                        "llm_result": "",
                        "display_name": display_name,
                        "interaction": tool_result,
                    },
                )

            display_result, llm_result = get_tool_execution_payloads(tool_result)
            if ctx.append_generated_images is not None:
                ctx.append_generated_images(image_pool, image_inventory, display_result)
        except Exception as exc:
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
            content=record["display_result"],
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
            file_content=ctx.file_content,
            user_locale=ctx.user_locale,
            history_override=ctx.working_history_override,
            current_images=ctx.current_images,
            model_supports_vision=ctx.model_supports_vision,
            current_user_message_id=ctx.current_user_message_id,
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
            provider=ctx.model_provider,
        )

    async def run(self) -> AsyncIterator[str | None]:
        start_time = time.time()
        try:
            async for output in self._run(start_time):
                yield output
        except Exception:
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

        for iteration in range(ctx.iteration_offset + 1, ctx.max_iterations + 1):
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
            tool_definition_tokens = (
                ctx.count_tool_definition_tokens(
                    ctx.tools, ctx.tokenizer_model_id, ctx.model_provider
                )
                if ctx.count_tool_definition_tokens and ctx.tools
                else 0
            )
            kwargs = self._context_kwargs(tool_definition_tokens)
            assert ctx.build_turn is not None
            turn = await ctx.build_turn(**kwargs)
            if turn.plan is not None:
                if turn.will_summarize:
                    start_event = self._emit(
                        COMPRESSION_START,
                        {
                            "compression": turn.plan.compression,
                            "stage": "macro",
                        },
                    )
                    if start_event:
                        yield start_event
                prepared = await turn.plan.finalize()
                end_event = self._emit(
                    COMPRESSION_END,
                    {
                        "compression": prepared.compression,
                    },
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

            # ---- one model turn ---------------------------------------------
            if ctx.streaming and ctx.team_chat_stream is not None:
                stream = ctx.team_chat_stream(
                    team_id=str(ctx.agent.team_id),
                    messages=messages_for_llm,
                    model_id=ctx.model_id,
                    tools=ctx.tools,
                )
                async for chunk in iter_with_idle_timeout(
                    stream,
                    timeout_seconds=ctx.idle_timeout,
                    activity_predicate=None,
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
                            previous_call = streamed_tool_calls.get(call_id)
                            if previous_call is not None and not _tool_call_changed(
                                previous_call, tool_call
                            ):
                                continue
                            streamed_tool_calls[call_id] = tool_call
                            started_tool_call_ids.add(call_id)
                            tool_name = getattr(tool_call.function, "name", None) or ""
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
                    fallback_response = await ctx.team_chat(
                        team_id=str(ctx.agent.team_id),
                        messages=messages_for_llm,
                        model_id=ctx.model_id,
                        tools=ctx.tools,
                    )
                    used_fallback = True
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
                response = await ctx.team_chat(
                    team_id=str(ctx.agent.team_id),
                    messages=messages_for_llm,
                    model_id=ctx.model_id,
                    tools=ctx.tools,
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
            if ctx.calculate_usage is not None:
                (
                    iteration_input_tokens,
                    iteration_output_tokens,
                    iteration_cache_read_tokens,
                    iteration_cache_creation_tokens,
                    iteration_total_input_tokens,
                ) = ctx.calculate_usage(
                    tools=ctx.tools,
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
                            content=p_data["display_result"],
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
                    await ctx.pause_for_user(
                        tool_call_id=pause_record["id"],
                        tool_name=pause_record["name"],
                        arguments=interaction.arguments,
                        round_id=ctx.round_id,
                        round_index=pause_tool_index,
                        iteration_index=iteration,
                        display_name=pause_record["display_name"],
                    )
                    call_sse = build_tool_call_sse_event(
                        tool_call_id=pause_record["id"],
                        tool_name=pause_record["name"],
                        tool_display_name=pause_record["display_name"],
                        arguments=interaction.arguments,
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

                if iteration >= ctx.max_iterations:
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
                # cap reached: terminate normally with the current content
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
            break  # no tool calls: round done

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
