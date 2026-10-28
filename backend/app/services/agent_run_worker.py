"""Worker-side execution of one AgentRun.

The Celery ``agent`` task runs a complete round (context preparation, model
turns, tool execution, canonical finalization, branch activation and stats)
from a serialized ``AgentRunPayload``. The route keeps request preparation
(access, RAG, assets, branch/version selection, user message creation) and
enqueues the payload; the worker reloads ORM objects and drives the shared
``AgentLoop``, publishing typed events through ``AgentRunStream`` so SSE
subscribers replay/live-stream the run independently of the execution
connection.

Lifecycle:

1. worker marks run ``running`` and acquires the conversation lock,
2. rebuilds the ``AgentLoopContext`` from the payload,
3. marks its sandbox round active and runs the loop with a run-stream
   formatter (events persisted then broadcast),
4. checkpoints the sandbox before pause/terminal publication and finalizes
   the canonical assistant + branch + stats exactly like the
   pre-extraction route paths,
5. transitions to a terminal state and releases the lock.

Failures propagate as typed error events; the run becomes ``failed`` with the
partial content preserved. Worker loss is detected later as ``interrupted``
(never auto-replayed).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from app.core.config import settings
from app.core.timezone import now_utc
from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.llm.types import ToolCall
from app.models.agent import (
    Agent,
    Conversation,
    Message,
    MessageRole,
    MessageRoundRole,
    MessageRoundStatus,
    RAGMode,
)
from app.models.agent_run import (
    AgentRun,
    AgentRunInputKind,
    AgentRunMode,
    AgentRunStatus,
)
from app.services import agent_run_store
from app.services.observability_v2 import record_dependency_metrics
from app.services.agent_loop import (
    AgentLoop,
    AgentLoopContext,
    AgentLoopResult,
    ContextTurn,
)
from app.services.agent_run_stream import AgentRunStream
from app.services.sandbox.gateway import sandbox_gateway

logger = logging.getLogger(__name__)


def _payload_api_key_id(payload: dict[str, Any]) -> UUID | None:
    """Lenient api-key id from a worker payload (legacy payloads lack it)."""
    value = payload.get("api_key_id")
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def build_payload(
    *,
    agent_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
    mode: AgentRunMode,
    user_message_id: UUID,
    round_id: UUID,
    run_id: UUID,
    message: str,
    images: list[dict[str, Any]] | None = None,
    file_urls: list[dict[str, Any]] | None = None,
    legacy_files: list[dict[str, Any]] | None = None,
    history_override: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    source_message_id: UUID | None = None,
    edited_user_message_id: UUID | None = None,
    canonical_message_id: UUID | None = None,
    in_place_retry: bool = False,
    branch_parent_id: UUID | None = None,
    locale: str | None = None,
    include_current_user_message: bool = True,
    history_before_message_created_at: Any = None,
    exclude_message_ids: list[UUID] | None = None,
    created_message_count: int = 2,
    first_round_index: int = 1,
    rag_contexts: list[dict[str, Any]] | None = None,
    message_start: dict[str, Any] | None = None,
    tool_entrypoint: str | None = None,
    tool_entrypoint_id: str | None = None,
    api_key_id: UUID | None = None,
) -> dict[str, Any]:
    """Serializable run payload: primitives + reloadable ids only."""
    return {
        "run_id": str(run_id),
        "agent_id": str(agent_id),
        "conversation_id": str(conversation_id),
        "user_id": str(user_id),
        "mode": mode.value,
        "user_message_id": str(user_message_id),
        "round_id": str(round_id),
        "message": message,
        "images": images or [],
        "file_urls": file_urls or [],
        "legacy_files": legacy_files or [],
        "history_override": history_override,
        "variables": variables or {},
        "source_message_id": str(source_message_id) if source_message_id else None,
        "edited_user_message_id": str(edited_user_message_id)
        if edited_user_message_id
        else None,
        "canonical_message_id": str(canonical_message_id)
        if canonical_message_id
        else None,
        "in_place_retry": in_place_retry,
        "branch_parent_id": str(branch_parent_id) if branch_parent_id else None,
        "locale": locale,
        "include_current_user_message": include_current_user_message,
        "history_before_message_created_at": (
            history_before_message_created_at.isoformat()
            if history_before_message_created_at is not None
            else None
        ),
        "exclude_message_ids": [
            str(message_id) for message_id in (exclude_message_ids or [])
        ],
        "created_message_count": created_message_count,
        "message_start": message_start or {},
        "rag_contexts": rag_contexts,
        "first_round_index": first_round_index,
        "tool_entrypoint": tool_entrypoint,
        "tool_entrypoint_id": tool_entrypoint_id,
        "api_key_id": str(api_key_id) if api_key_id else None,
    }


class _RunFormatter:
    """Queue loop events for ordered persistence and live replay."""

    def __init__(
        self,
        event_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None],
        *,
        agent: Agent,
    ) -> None:
        self.event_queue = event_queue
        self.agent = agent

    def __call__(self, event_name: str, payload: dict[str, Any]) -> str | None:
        normalized = self._normalize(event_name, payload)
        if normalized is not None:
            self.event_queue.put_nowait((event_name, normalized))
        return None

    def _normalize(
        self, event_name: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        if event_name == "compression_start":
            from app.api.v1.endpoints.chat_sse import build_compression_start_event

            raw = build_compression_start_event(
                agent=self.agent,
                stage=str(payload.get("stage", "macro")),
                trigger=str(payload.get("trigger", "context_limit")),
            )
            return _decode_sse_payload(raw)
        if event_name == "compression_end":
            from app.api.v1.endpoints.chat_sse import build_compression_events

            _, raw = build_compression_events(
                agent=self.agent,
                compression=payload.get("compression"),
                trigger=str(payload.get("trigger", "context_limit")),
            )
            return _decode_sse_payload(raw)
        raw = payload.get("sse")
        if isinstance(raw, str):
            return _decode_sse_payload(raw)
        return _json_safe(payload)


def _decode_sse_payload(event: str | None) -> dict[str, Any] | None:
    if not event:
        return None
    data = next(
        (line[5:].strip() for line in event.splitlines() if line.startswith("data:")),
        None,
    )
    if data is None:
        return None
    try:
        value = json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    return value


def _format_sse(event_name: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event_name}\ndata: {data}\n\n"


class MicroBatchingCollector:
    """Batches consecutive streaming deltas within a time window or size limit.

    Measures deadline from the first received delta to guarantee latency bounds.
    Flushes immediately upon receiving non-delta events, delta type changes,
    or termination sentinels.
    """

    BATCH_DELTA_TYPES = {"content_delta", "reasoning_delta"}
    BATCH_WINDOW_SECONDS = 0.02
    BATCH_MAX_DELTA_COUNT = 6

    def __init__(
        self,
        *,
        event_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None],
        stream: Any,
        run: Any = None,
        canonical_message_id: UUID | None = None,
    ) -> None:
        self.event_queue = event_queue
        self.stream = stream
        self.run_obj = run
        self.canonical_message_id = canonical_message_id
        self.batch_type: str | None = None
        self.batch_deltas: list[str] = []
        self.batch_deadline: float | None = None

    async def flush(self) -> None:
        """Flush currently buffered delta tokens to the event stream."""
        if not self.batch_type or not self.batch_deltas:
            self.batch_type = None
            self.batch_deltas = []
            self.batch_deadline = None
            return
        merged = "".join(self.batch_deltas)
        current_type = self.batch_type
        self.batch_type = None
        self.batch_deltas = []
        self.batch_deadline = None
        round_id = (
            getattr(self.run_obj, "active_round_id", None) if self.run_obj else None
        )
        await self.stream.publish(
            current_type,
            {"delta": merged},
            round_id=round_id,
            message_id=self.canonical_message_id,
        )

    async def run_loop(self) -> None:
        """Continuously process queued events and flush batches within the time window."""
        loop = asyncio.get_running_loop()
        while True:
            timeout: float | None = None
            if self.batch_deadline is not None:
                timeout = max(0.0, self.batch_deadline - loop.time())

            try:
                if timeout is not None:
                    item = await asyncio.wait_for(
                        self.event_queue.get(), timeout=timeout
                    )
                else:
                    item = await self.event_queue.get()
            except TimeoutError:
                await self.flush()
                continue

            try:
                if item is None:
                    await self.flush()
                    return
                event_type, event_payload = item
                if (
                    event_type in self.BATCH_DELTA_TYPES
                    and isinstance(event_payload, dict)
                    and "delta" in event_payload
                ):
                    delta_val = str(event_payload.get("delta") or "")
                    if self.batch_type is not None and self.batch_type != event_type:
                        await self.flush()
                    if self.batch_type is None:
                        self.batch_type = event_type
                        self.batch_deadline = loop.time() + self.BATCH_WINDOW_SECONDS
                    self.batch_deltas.append(delta_val)
                    if len(self.batch_deltas) >= self.BATCH_MAX_DELTA_COUNT:
                        await self.flush()
                else:
                    await self.flush()
                    round_id = (
                        getattr(self.run_obj, "active_round_id", None)
                        if self.run_obj
                        else None
                    )
                    await self.stream.publish(
                        event_type,
                        event_payload,
                        round_id=round_id,
                        message_id=self.canonical_message_id,
                    )
            except Exception:
                run_id = (
                    getattr(self.run_obj, "id", "unknown")
                    if self.run_obj
                    else "unknown"
                )
                logger.warning(
                    "Failed to publish AgentRun %s event", run_id, exc_info=True
                )
            finally:
                self.event_queue.task_done()


async def _rebuild_context(
    payload: dict[str, Any],
    *,
    agent: Agent,
    conversation: Conversation,
    event_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None],
) -> tuple[AgentLoopContext, Message, AgentLoop]:
    """Rebuild the loop context and the user message from the payload."""
    from app.models.asset import AssetScopeType, MessageAsset
    from app.api.v1.endpoints.chat import (
        _calculate_model_usage,
        build_max_iterations_terminal_content,
    )
    from app.api.v1.endpoints.chat_helpers import (
        resolve_agent_chat_model,
        get_streaming_config,
        append_generated_images,
        collect_conversation_images,
    )
    from app.llm import model_manager
    from app.llm.token_counter import count_tool_definition_tokens
    from app.services.sandbox.gateway import sandbox_gateway

    user_msg = await Message.get_or_none(id=UUID(payload["user_message_id"]))
    if not user_msg:
        raise LookupError("user message not found")

    streaming_config = get_streaming_config(agent)
    sandbox_session_id = await sandbox_gateway.create_session(
        agent_id=str(agent.id),
        team_id=str(agent.team_id) if agent.team_id else None,
        user_id=str(conversation.user_id),
        conversation_id=str(conversation.id),
    )
    chat_model = await resolve_agent_chat_model(agent)
    from app.services.tool_context import (
        RuntimeToolIdentity,
        entrypoint_is_interactive,
        tool_identity_scope,
    )

    origin = payload.get("tool_entrypoint")
    with tool_identity_scope(
        RuntimeToolIdentity(
            run_id=UUID(payload["run_id"]),
            entrypoint=origin or "agent_run",
            entrypoint_id=payload.get("tool_entrypoint_id"),
            api_key_id=_payload_api_key_id(payload),
            interactive=entrypoint_is_interactive(origin),
        )
    ):
        tools_openai = await _load_tools(agent, user_id=conversation.user_id)
    from app.core.i18n import resolve_language, set_language

    effective_locale = await resolve_language(payload.get("locale"))
    set_language(effective_locale)
    tool_display_names = await _load_tool_display_names(agent, effective_locale)
    from app.models.asset import AssetScopeRef

    message_asset_links = (
        await MessageAsset.filter(message_id=user_msg.id)
        .prefetch_related("asset")
        .order_by("position")
    )
    current_assets = []
    for link in message_asset_links:
        binding = await AssetScopeRef.get_or_none(
            scope_type=AssetScopeType.CONVERSATION,
            scope_id=conversation.id,
            asset_id=link.asset_id,
        )
        if binding is not None:
            current_assets.append(
                {
                    "asset_id": str(link.asset_id),
                    "checksum": link.asset.checksum,
                    "asset_ref": binding.ref,
                    "mime_type": link.asset.content_type,
                    "filename": link.asset.display_filename,
                }
            )
    image_pool, image_inventory = collect_conversation_images(
        await _visible_messages(conversation.id),
        current_message_id=user_msg.id,
    )

    mode = AgentRunMode(payload["mode"])
    if mode == AgentRunMode.NON_STREAM and tools_openai:
        # ask_user pauses the run for an interactive answer; a non-stream API
        # caller has no UI to answer, so the model must never see the tool.
        tools_openai = [
            tool
            for tool in tools_openai
            if tool.get("function", {}).get("name") != "ask_user"
        ]
    tools = _tools_definitions(tools_openai)
    is_streaming = mode != AgentRunMode.NON_STREAM

    from app.llm.tools import tool_registry

    from app.services.tool_context import get_agent_tool_require_approval

    def tool_concurrency(name: str) -> str:
        if get_agent_tool_require_approval(agent, name):
            return "exclusive"
        tool_info = tool_registry.get_tool(name)
        return tool_info.concurrency.value if tool_info else "exclusive"

    user_message_text = payload["message"]
    history_before_raw = payload.get("history_before_message_created_at")
    history_before = (
        datetime.fromisoformat(history_before_raw) if history_before_raw else None
    )
    history_override = payload.get("history_override")
    exclude_message_ids = [
        UUID(str(message_id)) for message_id in payload.get("exclude_message_ids") or []
    ]

    # RAG is prepared at route level and stored on the user message or payload.
    rag_contexts = payload.get("rag_contexts")
    if rag_contexts is None:
        rag_contexts = user_msg.rag_context
    if agent.rag_mode == RAGMode.AUTO and rag_contexts:
        from app.api.v1.endpoints.chat_rag import build_rag_prompt

        user_message_text = build_rag_prompt(
            rag_contexts,
            user_message_text,
            enable_citations=getattr(agent, "enable_citations", False),
        )
    image_inventory_text = user_message_text

    stream = AgentRunStream(UUID(payload["run_id"]))
    await stream.seed_sequence()

    loop_context = AgentLoopContext(
        agent=agent,
        conversation=conversation,
        user=SimpleNamespace(
            id=conversation.user_id,
            locale=effective_locale,
        ),
        user_message=image_inventory_text,
        model_id=chat_model.model_id,
        tokenizer_model_id=chat_model.tokenizer_model_id,
        model_provider=chat_model.provider,
        model_context_limit=chat_model.context_length,
        model_max_output_tokens=chat_model.max_output_tokens,
        model_used=chat_model.model_id,
        input_capabilities=chat_model.input_capabilities,
        model_config=chat_model.model,
        current_images=current_assets or None,
        resume_tool_calls=[
            ToolCall.model_validate(item)
            for item in json.loads(
                decrypt_tool_secret(payload["pending_tool_calls_cipher"])
            )
        ]
        if payload.get("pending_tool_calls_cipher")
        else None,
        tools=tools,
        tool_display_names=tool_display_names,
        tool_timeouts=streaming_config["tool_timeouts"],
        global_timeout=streaming_config["global_timeout"],
        deadline_seconds=streaming_config["global_timeout"],
        idle_timeout=streaming_config["idle_timeout"],
        heartbeat_interval=streaming_config["heartbeat_interval"],
        sandbox_session_id=sandbox_session_id,
        working_history_override=history_override,
        exclude_message_ids=exclude_message_ids or None,
        image_pool=image_pool,
        image_inventory=image_inventory,
        append_generated_images=append_generated_images,
        current_user_message_id=user_msg.id,
        include_current_user_message=bool(
            payload.get("include_current_user_message", True)
        ),
        history_before_message_created_at=history_before,
        round_id=UUID(payload["round_id"]),
        protected_round_id=UUID(payload["round_id"]),
        user_locale=effective_locale,
        tool_entrypoint=payload.get("tool_entrypoint"),
        tool_entrypoint_id=payload.get("tool_entrypoint_id"),
        tool_api_key_id=_payload_api_key_id(payload),
        max_iterations=None,
        iteration_offset=int(payload.get("iteration_offset", 0)),
        streaming=is_streaming,
        collect_dependency_metrics=True,
        observability_run_id=UUID(payload["run_id"]),
        execute_tool_call=__import__(
            "app.api.v1.endpoints.chat_tools", fromlist=["execute_tool_call"]
        ).execute_tool_call,
        team_chat_stream=model_manager.team_chat_stream,
        team_chat=model_manager.team_chat,
        record_stream_usage=None,
        calculate_usage=_calculate_model_usage,
        count_tool_definition_tokens=count_tool_definition_tokens,
        tool_concurrency=tool_concurrency,
        formatter=_RunFormatter(event_queue, agent=agent),
        first_round_index=int(payload.get("first_round_index", 1)),
        created_message_count=int(payload.get("created_message_count", 2)),
        cap_content=lambda: build_max_iterations_terminal_content(effective_locale),
    )

    async def build_turn(**kwargs):
        from app.services.chat_context import build_context_plan

        plan = await build_context_plan(**kwargs)
        return ContextTurn(
            prepared=None,
            will_summarize=plan.will_summarize,
            compression=plan.compression,
            plan=plan,
        )

    loop_context.build_turn = build_turn
    loop = AgentLoop(loop_context)
    return loop_context, user_msg, loop


async def _visible_messages(conversation_id: UUID):
    from app.services.message_branching import get_visible_conversation_messages

    return await get_visible_conversation_messages(conversation_id)


async def _load_tools(agent: Agent, user_id: UUID | str | None = None):
    from app.api.v1.endpoints.chat import get_agent_tools

    return await get_agent_tools(agent, user_id=user_id)


async def _load_tool_display_names(agent: Agent, locale: str = "en"):
    from app.api.v1.endpoints.chat import get_tool_display_names

    return await get_tool_display_names(agent, locale, enumerate_mcp_tools=False)


def _tools_definitions(tools_openai: list[dict] | None):
    from app.llm.types import ToolDefinition, FunctionDefinition

    if not tools_openai:
        return None
    return [
        ToolDefinition(
            type="function",
            function=FunctionDefinition(
                name=t["function"]["name"],
                description=t["function"]["description"],
                parameters=t["function"]["parameters"],
            ),
        )
        for t in tools_openai
    ]


async def _transition_active_run(
    run: AgentRun,
    status: AgentRunStatus,
    *,
    allowed_statuses: tuple[AgentRunStatus, ...],
    error_code: str | None = None,
    error_message: str | None = None,
) -> tuple[AgentRun | None, bool]:
    """Apply a terminal/intermediate transition without overwriting a winner."""
    current = run
    for _ in range(len(allowed_statuses) + 1):
        if current.status not in allowed_statuses:
            return current, False
        transitioned = await agent_run_store.transition_run_if_status(
            current,
            current.status,
            status,
            error_code=error_code,
            error_message=error_message,
        )
        if transitioned is not None:
            return transitioned, True
        current = await agent_run_store.get_run(current.id)
        if current is None:
            return None, False
    return current, False


def _marker_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} is invalid")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is invalid") from exc


def _marker_uuid(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("approval resume round_id is invalid") from exc


async def _execute_approved_pending_tool(
    payload: dict[str, Any],
    *,
    run: AgentRun,
    agent: Agent,
    conversation: Conversation,
) -> dict[str, Any] | None:
    """Execute the original deferred tool call, then persist its tool result.

    Approval is not a tool result: this runs the bound original operation with
    the approved parameters (loaded by the execution boundary), persists the
    real result for the same tool_call_id, and only then lets the model resume.
    """
    marker = payload.pop("resume_tool_approval", None)
    if not isinstance(marker, dict):
        return payload
    tool_call_id = str(marker.get("tool_call_id") or "")
    tool_name = str(marker.get("tool_name") or "")
    tool_display_name = str(marker.get("tool_display_name") or tool_name)
    if not tool_call_id or not tool_name:
        raise RuntimeError("approval resume marker is invalid")
    execution_id = UUID(str(marker["execution_id"]))
    round_id = _marker_uuid(marker.get("round_id")) or run.active_round_id
    round_index = _marker_int(marker.get("round_index"), "round_index")
    iteration_index = _marker_int(marker.get("iteration_index"), "iteration_index")

    started_at = time.time()
    started_clock = time.monotonic()
    trajectory_arguments: dict[str, Any] = {}
    metric_status = "completed"
    metric_error_category: str | None = None
    is_error = False
    try:
        from app.api.v1.endpoints.chat_tools import execute_tool_call
        from app.llm.tools.interaction import ToolInteractionRequest
        from app.models.tool_approval import ToolExecutionStatus
        from app.models.user import User
        from app.services import tool_approvals
        from app.services.sandbox.gateway import sandbox_gateway
        from app.services.tool_context import (
            RuntimeToolIdentity,
            entrypoint_is_interactive,
            tool_identity_scope,
        )
        from app.utils.tool_output import get_tool_execution_payloads

        # Session-scoped sandbox tools must resume in the same conversation
        # workspace they were approved from; create_session is idempotent. A
        # gateway failure must not turn an approved call into an error result.
        sandbox_session_id: str | None = None
        try:
            sandbox_session_id = await sandbox_gateway.create_session(
                agent_id=str(getattr(agent, "id", "")),
                team_id=str(getattr(agent, "team_id", "")) or None,
                user_id=str(conversation.user_id),
                conversation_id=str(conversation.id),
            )
        except Exception:
            logger.warning(
                "Sandbox session unavailable for approved resume of run %s",
                run.id,
                exc_info=True,
            )

        execution = await tool_approvals.get_execution(execution_id)
        trajectory_arguments = dict(execution.parameters_preview or {})
        if (
            execution.run_id != run.id
            or getattr(execution.run_kind, "value", execution.run_kind) != "agent"
            or execution.tool_call_id != tool_call_id
            or execution.status != ToolExecutionStatus.READY
        ):
            raise RuntimeError("approved tool execution is no longer ready")

        entrypoint = getattr(execution.entrypoint, "value", "agent_run")
        entrypoint_id = execution.entrypoint_id or str(agent.id)
        actor = await User.get_or_none(id=conversation.user_id)
        if actor is None:
            raise RuntimeError("run user is missing")
        with tool_identity_scope(
            RuntimeToolIdentity(
                run_id=run.id,
                run_kind=getattr(execution.run_kind, "value", "agent"),
                tool_call_id=tool_call_id,
                entrypoint=entrypoint,
                entrypoint_id=entrypoint_id,
                api_key_id=tool_approvals.stored_api_key_id(execution),
                # Reuse the origin stored on the execution; never re-derive
                # interactivity from the resume route.
                interactive=entrypoint_is_interactive(entrypoint),
            )
        ):
            # Route through the same dispatcher AgentLoop uses so builtin,
            # asset, stored custom/MCP and skill tools share one execution
            # semantics. Stored/builtin boundaries find the existing execution
            # by run/tool_call, claim it once and load the approved parameters;
            # the approval itself is never reused as a tool result.
            raw_result = await execute_tool_call(
                tool_name,
                {},
                agent=agent,
                user=actor,
                conversation_id=conversation.id,
                session_id=sandbox_session_id,
            )
        if isinstance(raw_result, ToolInteractionRequest):
            raise RuntimeError("approved tool execution did not resume")
        display_result, llm_result = get_tool_execution_payloads(raw_result, tool_name)
    except Exception as exc:
        logger.warning(
            "Approved tool resume failed for run %s execution %s: %s",
            run.id,
            execution_id,
            exc,
            exc_info=True,
        )
        is_error = True
        metric_status = "failed"
        metric_error_category = type(exc).__name__[:32]
        display_result = llm_result = json.dumps(
            {"error": str(exc) or type(exc).__name__}, ensure_ascii=False
        )

    if not is_error:
        try:
            parsed_result = json.loads(display_result)
        except (TypeError, ValueError):
            parsed_result = None
        if isinstance(parsed_result, dict) and parsed_result.get("error") is not None:
            metric_status = "failed"
            metric_error_category = "tool_error"

    finished_clock = time.monotonic()
    duration_ms = max(0, int((finished_clock - started_clock) * 1000))
    finished_at = started_at + (finished_clock - started_clock)
    dependency_metric = {
        "span_id": str(uuid4()),
        "kind": "retrieval" if tool_name == "knowledge_search" else "tool",
        "name": tool_name[:100],
        "tool_call_id": tool_call_id[:100],
        "status": metric_status,
        "started_at": datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
        "finished_at": datetime.fromtimestamp(finished_at, timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "error_category": metric_error_category,
    }
    try:
        from app.models.observability_payload import ObservabilityTrajectoryEntry
        from app.services.observability_trajectory import record_tool_call

        parent = (
            await ObservabilityTrajectoryEntry.filter(run_id=run.id, kind="model")
            .order_by("-sequence")
            .first()
        )
        await record_tool_call(
            run_id=run.id,
            conversation_id=conversation.id,
            parent_id=parent.id if parent is not None else None,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=trajectory_arguments,
            status=metric_status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            kind=dependency_metric["kind"],
        )
    except Exception:
        logger.debug("Resumed tool trajectory dropped", exc_info=True)

    updated = await agent_run_store.record_resumed_tool_result(
        run.id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_display_name=tool_display_name,
        display_result=display_result,
        llm_result=llm_result,
        is_error=is_error,
        round_id=round_id,
        round_index=round_index,
        iteration_index=iteration_index,
    )
    if updated is not None:
        updated["resume_dependency_metrics"] = [dependency_metric]
    return updated


async def run_agent_round(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one run payload to terminal and persist the canonical round."""
    payload = dict(payload)
    from app.core.i18n import resolve_language, set_language

    worker_locale = await resolve_language(payload.get("locale"))
    set_language(worker_locale)
    resume_tool_result = payload.pop("resume_tool_result", None)
    run = await agent_run_store.get_run(UUID(payload["run_id"]))
    if not run:
        raise LookupError("run not found")
    if run.status in (
        AgentRunStatus.STOPPED,
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    ):
        return {"status": run.status.value}
    if run.status in (AgentRunStatus.WAITING, AgentRunStatus.COMPLETING):
        return {"status": run.status.value}
    if run.status == AgentRunStatus.QUEUED:
        run = await agent_run_store.claim_queued_run(run.id)
        if run is None:
            current = await agent_run_store.get_run(UUID(payload["run_id"]))
            if current is None:
                raise LookupError("run not found")
            return {"status": current.status.value}
    if (
        run.status == AgentRunStatus.STOPPING
        or await agent_run_store.has_pending_inputs(run.id, kind=AgentRunInputKind.STOP)
    ):
        approval_marker = payload.get("resume_tool_approval")
        if isinstance(approval_marker, dict):
            from app.models.tool_approval import ToolExecutionCancelReason
            from app.services import tool_approvals

            try:
                await tool_approvals.cancel_execution(
                    UUID(str(approval_marker["execution_id"])),
                    reason=ToolExecutionCancelReason.RUN_STOPPED,
                )
            except Exception:
                logger.warning(
                    "Failed to cancel approved execution for stopped run %s",
                    run.id,
                    exc_info=True,
                )
        stopped, transitioned = await _transition_active_run(
            run,
            AgentRunStatus.STOPPED,
            allowed_statuses=(AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
        )
        if stopped is None:
            raise LookupError("run not found")
        if transitioned and stopped.status == AgentRunStatus.STOPPED:
            stream = AgentRunStream(run.id)
            await stream.seed_sequence()
            await stream.publish("run_end", {"status": "stopped"})
        return {"status": stopped.status.value}
    agent = await Agent.get_or_none(id=UUID(payload["agent_id"]))
    conversation = await Conversation.get_or_none(id=UUID(payload["conversation_id"]))
    if not agent or not conversation:
        failed, _ = await _transition_active_run(
            run,
            AgentRunStatus.FAILED,
            allowed_statuses=(AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
            error_code="context_lost",
            error_message="Agent or conversation missing",
        )
        if failed is None:
            raise LookupError("run not found")
        return {"status": failed.status.value}
    stream = AgentRunStream(run.id)
    await stream.seed_sequence()
    owned = await agent_run_store.acquire_run_lock(run.id, conversation.id)
    if not owned:
        current = await agent_run_store.get_run(run.id)
        if current is None:
            raise LookupError("run not found")
        stop_requested = (
            current.status == AgentRunStatus.STOPPING
            or await agent_run_store.has_pending_inputs(
                run.id, kind=AgentRunInputKind.STOP
            )
        )
        if stop_requested:
            current, transitioned = await _transition_active_run(
                current,
                AgentRunStatus.STOPPED,
                allowed_statuses=(AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
            )
            if current is None:
                raise LookupError("run not found")
            if current.status != AgentRunStatus.STOPPED:
                return {"status": current.status.value}
            if transitioned:
                await stream.publish("run_end", {"status": "stopped"})
            return {"status": AgentRunStatus.STOPPED.value}
        failed, transitioned = await _transition_active_run(
            current,
            AgentRunStatus.FAILED,
            allowed_statuses=(AgentRunStatus.RUNNING,),
            error_code="lock_busy",
            error_message="Another run is active for this conversation",
        )
        if failed is None:
            raise LookupError("run not found")
        if not transitioned:
            return {"status": failed.status.value}
        await stream.publish(
            "error",
            {"code": "lock_busy", "msg": "Another run is active for this conversation"},
        )
        await stream.publish("run_end", {"status": "failed"})
        return {"status": AgentRunStatus.FAILED.value}
    lease_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        agent_run_store.heartbeat_run_lock(run.id, conversation.id, lease_stop)
    )

    event_queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()
    publisher_task: asyncio.Task[None] | None = None
    canonical_message_id: UUID | None = None
    deferred_resume_run: AgentRun | None = None
    sandbox_session_id: str | None = None
    sandbox_round_id: str | None = None
    checkpoint_attempted = False

    collector = MicroBatchingCollector(
        event_queue=event_queue,
        stream=stream,
        run=run,
        canonical_message_id=canonical_message_id,
    )

    async def publish_queued_events() -> None:
        await collector.run_loop()

    async def flush_queued_events() -> None:
        if publisher_task is not None:
            await event_queue.join()
            await collector.flush()

    async def finish_sandbox_round() -> None:
        nonlocal checkpoint_attempted
        if sandbox_session_id and sandbox_round_id and not checkpoint_attempted:
            # A failed save is not retried by the failure handler: it must not
            # turn a checkpoint error into a successful terminal outcome.
            checkpoint_attempted = True
            await sandbox_gateway.finish_round(sandbox_session_id, sandbox_round_id)

    loop: AgentLoop | None = None
    persisted_dependency_metrics = 0

    async def _persist_dependency_metrics() -> None:
        nonlocal persisted_dependency_metrics
        if loop is None:
            return
        metrics = loop.result.dependency_metrics
        pending = metrics[persisted_dependency_metrics:]
        await record_dependency_metrics(
            run.id,
            pending,
            truncated=loop.result.dependency_metrics_truncated,
        )
        persisted_dependency_metrics = len(metrics)

    try:
        # The queued claim above owns RUNNING before publication. Keep this
        # inside the protected lifecycle so stream errors still release locks.
        await stream.publish("run_start", {"status": "running", "run_id": str(run.id)})
        approval_marker = payload.get("resume_tool_approval")
        if isinstance(approval_marker, dict):
            stop_requested = (
                run.status == AgentRunStatus.STOPPING
                or await agent_run_store.has_pending_inputs(
                    run.id, kind=AgentRunInputKind.STOP
                )
            )
            if stop_requested:
                from app.models.tool_approval import ToolExecutionCancelReason
                from app.services import tool_approvals

                try:
                    execution_id = UUID(str(approval_marker["execution_id"]))
                    await tool_approvals.cancel_execution(
                        execution_id,
                        reason=ToolExecutionCancelReason.RUN_STOPPED,
                    )
                except Exception:
                    logger.warning(
                        "Failed to cancel approved execution for stopped run %s",
                        run.id,
                        exc_info=True,
                    )
                await agent_run_store.drop_pending_inputs(run.id)
                stopped, transitioned = await _transition_active_run(
                    run,
                    AgentRunStatus.STOPPED,
                    allowed_statuses=(
                        AgentRunStatus.RUNNING,
                        AgentRunStatus.STOPPING,
                    ),
                )
                if stopped is None:
                    raise LookupError("run not found")
                if transitioned:
                    await stream.publish(
                        "run_end",
                        {
                            "status": "stopped",
                            "message_id": str(
                                stopped.canonical_message_id
                                or run.canonical_message_id
                                or ""
                            ),
                        },
                    )
                return {"status": stopped.status.value}

            updated_payload = await _execute_approved_pending_tool(
                payload,
                run=run,
                agent=agent,
                conversation=conversation,
            )
            if updated_payload is None:
                current = await agent_run_store.get_run(run.id)
                if current is None:
                    raise LookupError("run not found")
                if current.status == AgentRunStatus.STOPPING:
                    await agent_run_store.drop_pending_inputs(run.id)
                    current, transitioned = await _transition_active_run(
                        current,
                        AgentRunStatus.STOPPED,
                        allowed_statuses=(
                            AgentRunStatus.RUNNING,
                            AgentRunStatus.STOPPING,
                        ),
                    )
                    if current is not None and transitioned:
                        await stream.publish("run_end", {"status": "stopped"})
                return {"status": current.status.value}
            payload = updated_payload
            resume_tool_result = payload.pop("resume_tool_result", None)
        loop_context, user_msg, loop = await _rebuild_context(
            payload,
            agent=agent,
            conversation=conversation,
            event_queue=event_queue,
        )
        resumed_metrics = payload.pop("resume_dependency_metrics", None)
        if isinstance(resumed_metrics, list):
            loop.result.dependency_metrics.extend(
                metric for metric in resumed_metrics if isinstance(metric, dict)
            )
        sandbox_session_id = getattr(loop_context, "sandbox_session_id", None)
        if sandbox_session_id:
            sandbox_round_id = (
                f"{run.id}:{run.active_round_id or loop_context.round_id}:{uuid4()}"
            )
            deadline_seconds = loop_context.deadline_seconds
            if deadline_seconds is None:
                deadline_seconds = loop_context.global_timeout
            await sandbox_gateway.begin_round(
                sandbox_session_id,
                sandbox_round_id,
                ttl_seconds=deadline_seconds
                + settings.SANDBOX_CHECKPOINT_TIMEOUT_SECONDS,
            )
        if run.canonical_message_id:
            canonical = await Message.get_or_none(id=run.canonical_message_id)
        else:
            canonical = None
        if canonical is None:
            canonical = await _create_placeholder(conversation, user_msg, run)
            run.canonical_message_id = canonical.id
            await run.save(update_fields=["canonical_message_id"])
        canonical_message_id = canonical.id
        publisher_task = asyncio.create_task(publish_queued_events())
        if isinstance(resume_tool_result, dict):
            await stream.publish(
                "tool_result",
                resume_tool_result,
                round_id=run.active_round_id,
                message_id=canonical.id,
            )
        rag_contexts = payload.get("rag_contexts")
        if rag_contexts is None:
            rag_contexts = user_msg.rag_context
        if agent.rag_mode == RAGMode.AUTO and rag_contexts is not None:
            await stream.publish("rag_start", {})
            await stream.publish(
                "rag_context",
                {"contexts": rag_contexts, "query": user_msg.content},
            )
        if run.message_started_at is None:
            run.message_started_at = now_utc()
            await run.save(update_fields=["message_started_at"])
        agent_run_store.record_observability_progress(
            run.id,
            message_started_at=run.message_started_at,
        )
        await stream.publish(
            "message_start",
            {
                "conversation_id": str(conversation.id),
                "message_id": str(canonical.id),
                "user_message_id": str(user_msg.id),
                **(payload.get("message_start") or {}),
            },
            round_id=run.active_round_id,
            message_id=canonical.id,
        )

        # Close the terminal race: consume inputs accepted before we flip to
        # ``completing``; inputs enqueued after terminal start a new run.
        async def _consume_inputs():

            collected = []
            while run.status in (
                AgentRunStatus.RUNNING,
                AgentRunStatus.STOPPING,
                AgentRunStatus.COMPLETING,
            ):
                item = await agent_run_store.consume_next_input(run.id)
                if item is None:
                    break
                collected.append(item)
            return collected

        async def _input_consumed(item) -> None:
            from app.models.agent_run import AgentRunInputKind

            payload = {
                "kind": item.kind.value
                if hasattr(item.kind, "value")
                else str(item.kind),
                "content": item.content,
                "sequence": item.sequence,
            }
            event_queue.put_nowait(("input_accepted", payload))
            if item.kind in (AgentRunInputKind.STEER, AgentRunInputKind.FOLLOW_UP):
                # 形态 B：作为当前轮次的内部 step 消息持久化（is_round_canonical=False）
                # 随同当前 Assistant 消息保存在 steps 数组中，刷新时还原到 CoT 时间线
                try:
                    step_msg = await Message.create(
                        conversation=conversation,
                        role=MessageRole.USER,
                        content=item.content or "",
                        round_id=run.active_round_id or user_msg.round_id,
                        round_index=10_000 + item.sequence,
                        round_role=MessageRoundRole.USER_INPUT,
                        is_round_canonical=False,
                        is_active=True,
                    )
                    from app.models.user import User
                    from app.services.audit_log import AuditLogService

                    run_user = await User.get_or_none(id=conversation.user_id)
                    after_snapshot = AuditLogService.snapshot(step_msg, "message")
                    changes = AuditLogService.build_changes({}, after_snapshot)
                    await AuditLogService.log(
                        user=run_user,
                        action="create_message",
                        resource_type="message",
                        resource_id=step_msg.id,
                        resource_name=str(step_msg.id),
                        operation="create",
                        status="success",
                        changes=changes,
                        metadata={
                            "run_id": str(run.id),
                            "conversation_id": str(conversation.id),
                            "sequence": item.sequence,
                        },
                    )
                except Exception as persist_err:
                    logger.error(
                        "Failed to persist consumed input step message for run %s: %s",
                        run.id,
                        persist_err,
                        exc_info=True,
                    )
                    raise

                if loop_context.working_history_override is None:
                    loop_context.working_history_override = []

                loop_context.working_history_override.append(
                    {
                        "role": "user",
                        "content": item.content or "",
                        "round_id": str(run.active_round_id or user_msg.round_id),
                        "round_index": 10_000 + item.sequence,
                        "round_role": "user_input",
                        "is_round_canonical": True,
                        "round_status": "completed",
                    }
                )

        async def _stop_requested() -> bool:
            if run.status == AgentRunStatus.STOPPING:
                return True
            from app.models.agent_run import AgentRunInputKind

            return await agent_run_store.has_pending_inputs(
                run.id, kind=AgentRunInputKind.STOP
            )

        loop_context.consume_inputs = _consume_inputs
        loop_context.input_consumed = _input_consumed
        loop_context.stop_requested = _stop_requested
        loop_context.is_disconnected = _stop_requested
        pending_interaction: dict[str, Any] | None = None

        async def _pause_for_user(**interaction: Any) -> None:
            nonlocal pending_interaction
            resume_payload = dict(payload)
            remaining_calls = interaction.get("remaining_tool_calls") or []
            if remaining_calls:
                resume_payload["pending_tool_calls_cipher"] = encrypt_tool_secret(
                    json.dumps(
                        [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.function.name,
                                    "arguments": call.function.arguments
                                    if isinstance(call.function.arguments, str)
                                    else json.dumps(call.function.arguments),
                                },
                            }
                            for call in remaining_calls
                        ]
                    )
                )
            else:
                resume_payload.pop("pending_tool_calls_cipher", None)
            # The current round's protocol entries are held in the in-memory
            # history override until the model turn completes. Carry them
            # across the durable pause so the resumed provider sees the
            # original ask_user call before its answer result.
            resume_payload["history_override"] = list(
                loop_context.working_history_override or []
            )
            resume_payload["first_round_index"] = int(interaction["round_index"]) + 1
            resume_payload["created_message_count"] = loop_context.created_message_count
            resume_payload["iteration_offset"] = int(interaction["iteration_index"])
            resume_payload["pending_tool_display_name"] = str(
                interaction.get("display_name") or interaction["tool_name"]
            )
            # Park only once the stable workspace has been checkpointed. The
            # pause hook runs before AgentLoop has returned to this boundary.
            pending_interaction = {
                "tool_call_id": str(interaction["tool_call_id"]),
                "tool_name": str(interaction["tool_name"]),
                "tool_input": interaction["arguments"],
                "round_id": interaction["round_id"],
                "round_index": int(interaction["round_index"]),
                "iteration_index": int(interaction["iteration_index"]),
                "worker_payload": resume_payload,
            }

        loop_context.pause_for_user = _pause_for_user

        async for _chunk in loop.run():
            pass
        await finish_sandbox_round()
        result = loop.result
        await _persist_dependency_metrics()
        if run.first_token_ms is None and result.first_token_ms is not None:
            run.first_token_ms = result.first_token_ms
            await run.save(update_fields=["first_token_ms"])
        agent_run_store.record_observability_progress(
            run.id,
            first_token_ms=run.first_token_ms,
        )
        if result.waiting_for_user:
            if pending_interaction is None:
                raise RuntimeError("AgentRun is waiting without a pending tool call")
            await agent_run_store.park_run_waiting(run, **pending_interaction)
            # The tool-call event is queued by AgentLoop after the pause hook;
            # drain it before publishing the waiting status so replay order is
            # tool_call -> run_status.
            await flush_queued_events()
            pending_tool_call_id = run.pending_tool_call_id
            # Close the approval/park race: a decision may already have been
            # recorded while this run was still RUNNING, so the decision
            # scheduler saw no WAITING row. Re-check now that the pending call
            # is durable and queue the correct resume before returning.
            deferred_resume_run = (
                await agent_run_store.queue_agent_run_resume_if_approval_terminal(
                    run.id
                )
            )
            current = await agent_run_store.get_run(run.id)
            if deferred_resume_run is None and (
                current is not None and current.status != AgentRunStatus.WAITING
            ):
                # The decision scheduler won the race and already queued the
                # run. Do not emit a false WAITING status; the resumed worker
                # publishes run_start.
                return {
                    "status": current.status.value,
                    "tool_call_id": pending_tool_call_id,
                }
            if deferred_resume_run is not None:
                # Dispatch after the per-conversation lock is released in the
                # finally block; dispatching while this worker still owns the
                # lock would make the resumed task fail as lock_busy.
                return {
                    "status": AgentRunStatus.QUEUED.value,
                    "tool_call_id": pending_tool_call_id,
                }
            await stream.publish(
                "run_status",
                {
                    "status": AgentRunStatus.WAITING.value,
                    "pending_tool_call_id": pending_tool_call_id,
                    "pending_tool_name": run.pending_tool_name,
                    "pending_tool_input": run.pending_tool_input,
                },
                round_id=run.active_round_id,
                message_id=run.canonical_message_id,
            )
            return {
                "status": AgentRunStatus.WAITING.value,
                "tool_call_id": pending_tool_call_id,
            }

        if result.deadline_exceeded:
            await agent_run_store.drop_pending_inputs(run.id)
            await flush_queued_events()
            await _finalize_stopped(canonical, result, stream)
            stopped, transitioned = await _transition_active_run(
                run,
                AgentRunStatus.STOPPED,
                allowed_statuses=(AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
            )
            if stopped is None:
                raise LookupError("run not found")
            if stopped.status == AgentRunStatus.STOPPED and transitioned:
                await stream.publish(
                    "run_end", {"status": "stopped", "reason": "deadline_exceeded"}
                )
            return {
                "status": stopped.status.value,
                "reason": "deadline_exceeded",
            }

        if result.manually_stopped:
            await agent_run_store.drop_pending_inputs(run.id)
            await flush_queued_events()
            await _finalize_stopped(canonical, result, stream)
            stopped, transitioned = await _transition_active_run(
                run,
                AgentRunStatus.STOPPED,
                allowed_statuses=(AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
            )
            if stopped is None:
                raise LookupError("run not found")
            if stopped.status == AgentRunStatus.STOPPED and transitioned:
                await stream.publish(
                    "run_end", {"status": "stopped", "message_id": str(canonical.id)}
                )
            return {
                "status": stopped.status.value,
                "message_id": str(canonical.id),
            }

        # Atomically claim completion so a concurrent stop cannot be
        # overwritten by the finalization path.
        completing, claimed = await _transition_active_run(
            run,
            AgentRunStatus.COMPLETING,
            allowed_statuses=(AgentRunStatus.RUNNING,),
        )
        if not claimed:
            current = completing
            if current is None:
                raise LookupError("run not found")
            if current.status == AgentRunStatus.STOPPING:
                await agent_run_store.drop_pending_inputs(run.id)
                await flush_queued_events()
                await _finalize_stopped(canonical, result, stream)
                stopped, stopped_claimed = await _transition_active_run(
                    current,
                    AgentRunStatus.STOPPED,
                    allowed_statuses=(AgentRunStatus.RUNNING, AgentRunStatus.STOPPING),
                )
                if stopped is None:
                    raise LookupError("run not found")
                if stopped.status == AgentRunStatus.STOPPED and stopped_claimed:
                    await stream.publish(
                        "run_end",
                        {"status": "stopped", "message_id": str(canonical.id)},
                    )
                return {
                    "status": stopped.status.value,
                    "message_id": str(canonical.id),
                }
            return {"status": current.status.value}

        await agent_run_store.drop_pending_inputs(run.id)
        await flush_queued_events()
        await _finalize_completed(
            canonical,
            result,
            conversation,
            agent,
            stream,
            user_message=user_msg,
            model_used=loop_context.model_used,
            locale=payload.get("locale"),
        )
        completed, completed_claimed = await _transition_active_run(
            run,
            AgentRunStatus.COMPLETED,
            allowed_statuses=(AgentRunStatus.COMPLETING,),
        )
        if completed is None:
            raise LookupError("run not found")
        if not completed_claimed:
            return {
                "status": completed.status.value,
                "message_id": str(canonical.id),
            }
        await stream.publish(
            "run_end", {"status": "completed", "message_id": str(canonical.id)}
        )
        try:
            from app.tasks.memory import schedule_background_memory_extraction

            await schedule_background_memory_extraction(
                conversation_id=conversation.id,
                agent_id=agent.id,
                user_id=run.user_id,
            )
        except Exception:
            logger.warning(
                "Failed to schedule background memory extraction for conversation %s",
                conversation.id,
                exc_info=True,
            )
        return {
            "status": AgentRunStatus.COMPLETED.value,
            "message_id": str(canonical.id),
        }
    except Exception as exc:
        await _persist_dependency_metrics()
        try:
            await finish_sandbox_round()
        except Exception:
            # Preserve the execution error when both execution and saving fail.
            logger.exception("Failed to checkpoint sandbox for agent run %s", run.id)
        await flush_queued_events()
        logger.exception("Agent run %s failed", run.id)
        from app.core.i18n import t
        from app.schemas.response import BusinessError

        error_message = (
            t(exc.msg_key, lang=payload.get("locale"), **exc.kwargs)
            if isinstance(exc, BusinessError) and exc.msg_key
            else str(exc)
        )
        failed, transitioned = await _transition_active_run(
            run,
            AgentRunStatus.FAILED,
            allowed_statuses=(
                AgentRunStatus.RUNNING,
                AgentRunStatus.STOPPING,
                AgentRunStatus.COMPLETING,
            ),
            error_code=type(exc).__name__,
            error_message=error_message,
        )
        if failed is None:
            raise LookupError("run not found") from exc
        if not transitioned:
            return {"status": failed.status.value, "error": error_message}
        await stream.publish(
            "error",
            {"code": "run_failed", "msg": error_message},
        )
        await stream.publish(
            "run_end",
            {"status": "failed", "message_id": str(run.canonical_message_id or "")},
        )
        return {"status": AgentRunStatus.FAILED.value, "error": error_message}
    finally:
        lease_stop.set()
        try:
            await heartbeat_task
        finally:
            try:
                if publisher_task is not None:
                    await event_queue.put(None)
                    await publisher_task
            finally:
                await agent_run_store.release_run_lock(run.id, conversation.id)
                if deferred_resume_run is not None:
                    try:
                        payload = deferred_resume_run.worker_payload
                        if not isinstance(payload, dict):
                            raise RuntimeError("run resume payload is missing")
                        from app.services.agent_submission import dispatch_run

                        await dispatch_run(payload, deferred_resume_run)
                    except Exception as exc:
                        logger.exception(
                            "Failed to dispatch post-park approval resume for run %s",
                            run.id,
                        )
                        await agent_run_store.transition_run_if_status(
                            deferred_resume_run,
                            AgentRunStatus.QUEUED,
                            AgentRunStatus.FAILED,
                            error_code="enqueue_failed",
                            error_message=str(exc),
                        )


async def _create_placeholder(
    conversation: Conversation,
    user_msg: Message,
    run: AgentRun,
) -> Message:
    return await Message.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        content="",
        branch_parent_id=user_msg.id,
        round_id=run.active_round_id or user_msg.round_id,
        round_index=0,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )


async def _finalize_completed(
    canonical: Message,
    result: AgentLoopResult,
    conversation: Conversation,
    agent: Agent,
    stream: AgentRunStream,
    *,
    user_message: Message,
    model_used: str | None,
    locale: str | None,
) -> None:
    from app.api.v1.endpoints.chat import (
        build_max_iterations_terminal_content,
        get_round_terminal_status,
    )
    from app.models.agent import Message as M

    from app.core.i18n import resolve_language

    effective_locale = await resolve_language(locale)
    terminal_content = (
        build_max_iterations_terminal_content(effective_locale)
        if result.max_iterations_reached
        else result.full_content or ""
    )
    round_status = get_round_terminal_status(
        completed=not result.max_iterations_reached,
        max_iterations_reached=result.max_iterations_reached,
    )
    token_usage = {
        "prompt": result.aggregate_input_tokens,
        "completion": result.aggregate_output_tokens,
        "cache_read": result.aggregate_cache_read_tokens,
        "cache_creation": result.aggregate_cache_creation_tokens,
        "total_input": result.aggregate_total_input_tokens,
    }
    canonical.content = terminal_content
    canonical.reasoning_content = result.full_reasoning or None  # type: ignore[assignment]
    canonical.model_used = model_used  # type: ignore[assignment]
    canonical.duration_ms = result.duration_ms
    canonical.first_token_ms = result.first_token_ms
    canonical.is_manually_stopped = False
    canonical.round_status = round_status
    canonical.round_index = result.final_round_index
    canonical.token_usage = token_usage
    await canonical.save()

    from app.services.message_branching import (
        activate_conversation_branch,
        get_prefix_path_before,
    )

    branch_parent = await M.get_or_none(id=canonical.branch_parent_id)
    if branch_parent is not None:
        branch_prefix = await get_prefix_path_before(branch_parent)
        branch_path = [*branch_prefix, branch_parent, canonical]
    else:
        branch_path = [canonical]
    await activate_conversation_branch(conversation.id, branch_path)

    created_message_count = max(result.created_message_count, 2)
    total_tokens = result.aggregate_input_tokens + result.aggregate_output_tokens
    title_update = {}
    if not conversation.title:
        title_source = user_message.content or ""
        title_update["title"] = title_source[:50] + (
            "..." if len(title_source) > 50 else ""
        )
    await Conversation.filter(id=conversation.id).update(
        message_count=conversation.message_count + created_message_count,
        token_usage=conversation.token_usage + total_tokens,
        updated_at=now_utc(),
        **title_update,
    )
    await Agent.filter(id=agent.id).update(
        message_count=agent.message_count + created_message_count,
        total_tokens=agent.total_tokens + total_tokens,
    )
    usage = {
        "prompt_tokens": result.aggregate_input_tokens,
        "completion_tokens": result.aggregate_output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": result.aggregate_cache_read_tokens,
        "cache_creation_tokens": result.aggregate_cache_creation_tokens,
        "total_input_tokens": result.aggregate_total_input_tokens,
    }
    await stream.publish("message_end", {"usage": usage})


async def _finalize_stopped(
    canonical: Message,
    result: AgentLoopResult,
    stream: AgentRunStream,
) -> None:
    canonical.content = result.full_content
    canonical.reasoning_content = result.full_reasoning or None  # type: ignore[assignment]
    canonical.is_manually_stopped = True
    canonical.round_status = MessageRoundStatus.MANUALLY_STOPPED
    await canonical.save()
    await stream.publish("message_end", {"usage": {}})
