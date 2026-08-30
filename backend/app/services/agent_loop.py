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
from app.llm.types import ChatStreamChunk, FinishReason
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
    enable_user_input_request: bool = False
    # how one model turn is produced
    streaming: bool = True
    # context building (route-supplied): builds + finalizes provider context
    build_turn: Callable[..., Any] | None = None
    count_tool_definition_tokens: Callable[..., int] | None = None
    trigger_for_compression: Callable[..., str | None] | None = None
    # tool execution (route-bound so tests can mock the endpoint binding)
    execute_tool_call: Callable[..., Any] | None = None
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
    """Terminal state produced by the loop for route finalization."""

    full_content: str = ""
    full_reasoning: str = ""
    max_iterations_reached: bool = False
    manually_stopped: bool = False
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


class AgentLoop:
    """One round of model turns + tool execution.

    ``run()`` is an async generator. Streaming paths yield formatted SSE
    strings through the route-supplied formatter; the non-stream path passes
    ``formatter=None`` and the generator produces no output while still
    persisting intermediate steps. Read ``self.result`` after ``run()``.
    """

    def __init__(self, context: AgentLoopContext) -> None:
        self.context = context
        self.result = AgentLoopResult()
        self._round_index = context.first_round_index
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

        for iteration in range(1, ctx.max_iterations + 1):
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
                            "trigger": self._trigger(turn.plan.compression),
                        },
                    )
                    if start_event:
                        yield start_event
                prepared = await turn.plan.finalize()
                end_event = self._emit(
                    COMPRESSION_END,
                    {
                        "compression": prepared.compression,
                        "trigger": self._trigger(prepared.compression),
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
            stream_usage = None
            used_fallback = False
            client_disconnected = False

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
                        collected_tool_calls = chunk.delta.tool_calls
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
                    not reasoning_started
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
                collected_tool_calls = getattr(response, "tool_calls", None) or []
                iteration_content = getattr(response, "content", "") or ""
                iteration_reasoning = getattr(response, "reasoning_content", "") or ""
                full_content += iteration_content
                full_reasoning += iteration_reasoning

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
                assert ctx.round_id is not None
                pending_tool_calls = []
                for tc in collected_tool_calls:
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
                    tool_name = getattr(tc.function, "name", None)
                    if not tool_name:
                        continue
                    arguments = _safe_arguments(tc.function.arguments)
                    display_name = ctx.tool_display_names.get(tool_name, tool_name)
                    tool_call_event = build_tool_call_sse_event(
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        tool_display_name=display_name,
                        arguments=arguments,
                    )
                    event = self._emit(TOOL_CALL, {"sse": tool_call_event})
                    if event:
                        yield event
                    tool_runner = ctx.execute_tool_call or execute_tool_call
                    tool_result = await tool_runner(
                        tool_name,
                        arguments,
                        agent=ctx.agent,
                        tool_timeouts=ctx.tool_timeouts,
                        user=ctx.user,
                        session_id=ctx.sandbox_session_id,
                        current_images=ctx.image_pool,
                        conversation_id=ctx.conversation.id,
                    )
                    display_result, llm_result = get_tool_execution_payloads(
                        tool_result
                    )
                    if ctx.append_generated_images is not None:
                        ctx.append_generated_images(
                            ctx.image_pool, ctx.image_inventory, display_result
                        )
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
                    tool_result_event = build_tool_result_sse_event(
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        tool_display_name=display_name,
                        display_result=display_result,
                    )
                    event = self._emit(TOOL_RESULT, {"sse": tool_result_event})
                    if event:
                        yield event
                    media_event = self._emit(
                        MEDIA_RESULT,
                        {"sse": build_media_result_sse_event(display_result)},
                    )
                    if media_event:
                        yield media_event
                    pending_tool_calls.append(
                        {
                            "id": tc.id,
                            "name": tool_name,
                            "arguments": arguments,
                            "display_result": display_result,
                            "llm_result": llm_result,
                            "display_name": display_name,
                        }
                    )

                    if ctx.persist_step_per_tool:
                        step_index = self._next_round_index()
                        await agent_round.persist_assistant_step(
                            conversation=ctx.conversation,
                            content=full_content,
                            reasoning_content=full_reasoning or None,
                            tool_calls=[
                                {
                                    "id": tc.id,
                                    "name": tool_name,
                                    "display_name": display_name,
                                    "arguments": arguments,
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
                            content=full_content,
                            reasoning_content=full_reasoning or None,
                            tool_calls=[
                                {
                                    "id": tc.id,
                                    "name": tool_name,
                                    "display_name": display_name,
                                    "arguments": arguments,
                                }
                            ],
                            round_index=step_index,
                            iteration=iteration,
                        )
                        tool_index = self._next_round_index()
                        await agent_round.persist_tool_result(
                            conversation=ctx.conversation,
                            content=display_result,
                            tool_call_id=tc.id,
                            tool_name=tool_name,
                            round_id=ctx.round_id,
                            round_index=tool_index,
                            iteration_index=iteration,
                            branch_parent_id=ctx.step_branch_parent_id,
                        )
                        self._append_history(
                            role="tool",
                            content=llm_result,
                            tool_call_id=tc.id,
                            tool_name=tool_name,
                            round_index=tool_index,
                            iteration=iteration,
                        )
                        ctx.created_message_count += 2
                        full_content = ""
                        full_reasoning = ""

                if not ctx.persist_step_per_tool and pending_tool_calls:
                    step_index = self._next_round_index()
                    await agent_round.persist_assistant_step(
                        conversation=ctx.conversation,
                        content=iteration_content,
                        reasoning_content=iteration_reasoning or None,
                        tool_calls=[
                            {
                                "id": p["id"],
                                "name": p["name"],
                                "display_name": p["display_name"],
                                "arguments": p["arguments"],
                            }
                            for p in pending_tool_calls
                        ],
                        model_used=ctx.model_used,
                        round_id=ctx.round_id,
                        round_index=step_index,
                        iteration_index=iteration,
                    )
                    self._append_history(
                        role="assistant",
                        content=iteration_content,
                        reasoning_content=iteration_reasoning or None,
                        tool_calls=[
                            {
                                "id": p["id"],
                                "name": p["name"],
                                "display_name": p["display_name"],
                                "arguments": p["arguments"],
                            }
                            for p in pending_tool_calls
                        ],
                        round_index=step_index,
                        iteration=iteration,
                    )
                    for p_data in pending_tool_calls:
                        tool_index = self._next_round_index()
                        await agent_round.persist_tool_result(
                            conversation=ctx.conversation,
                            content=p_data["display_result"],
                            tool_call_id=p_data["id"],
                            tool_name=p_data["name"],
                            round_id=ctx.round_id,
                            round_index=tool_index,
                            iteration_index=iteration,
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
                    ctx.created_message_count += 1  # assistant step

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

    def _trigger(self, compression: Any) -> str | None:
        if self.context.trigger_for_compression is not None:
            return self.context.trigger_for_compression(compression)
        return None
