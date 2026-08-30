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
3. runs the loop with a run-stream formatter (events persisted then
   broadcast),
4. finalizes the canonical assistant + branch + stats exactly like the
   pre-extraction route paths,
5. transitions to a terminal state and releases the lock.

Failures propagate as typed error events; the run becomes ``failed`` with the
partial content preserved. Worker loss is detected later as ``interrupted``
(never auto-replayed).
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from app.core.timezone import now_utc
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
    AgentRunMode,
    AgentRunStatus,
)
from app.services import agent_run_store
from app.services.agent_loop import (
    AgentLoop,
    AgentLoopContext,
    AgentLoopResult,
    ContextTurn,
)
from app.services.agent_run_stream import AgentRunStream

logger = logging.getLogger(__name__)


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
    history_override: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    source_message_id: UUID | None = None,
    edited_user_message_id: UUID | None = None,
    canonical_message_id: UUID | None = None,
    in_place_retry: bool = False,
    branch_parent_id: UUID | None = None,
    locale: str | None = None,
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
    }


class _RunFormatter:
    """Adapts the loop's formatter contract to the run stream.

    The loop calls ``formatter(event_name, payload)`` expecting a formatted
    SSE string; here we publish the typed event and return ``None`` so the
    loop does not double-emit strings.
    """

    def __init__(self, stream: AgentRunStream, *, emit_sse: bool = False) -> None:
        self.stream = stream
        self.emit_sse = emit_sse

    def __call__(self, event_name: str, payload: dict[str, Any]) -> str | None:
        if self.emit_sse:
            return _format_sse(event_name, payload)
        return None


def _format_sse(event_name: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event_name}\ndata: {data}\n\n"


async def _rebuild_context(
    payload: dict[str, Any],
    *,
    agent: Agent,
    conversation: Conversation,
) -> tuple[AgentLoopContext, Message, AgentLoop]:
    """Rebuild the loop context and the user message from the payload."""
    from app.api.v1.endpoints.chat_helpers import (
        resolve_agent_chat_model,
        get_streaming_config,
        append_generated_images,
        collect_conversation_images,
        append_conversation_image_inventory,
    )
    from app.llm import model_manager
    from app.llm.token_counter import count_tool_definition_tokens
    from app.services.sandbox.gateway import sandbox_gateway
    from app.api.v1.endpoints.chat import _calculate_model_usage

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
    tools_openai = await _load_tools(agent)
    tool_display_names = await _load_tool_display_names(agent)
    image_pool, image_inventory = collect_conversation_images(
        await _visible_messages(conversation.id),
        current_message_id=user_msg.id,
    )

    mode = AgentRunMode(payload["mode"])
    tools = _tools_definitions(tools_openai)
    is_streaming = mode != AgentRunMode.NON_STREAM
    user_message_text = payload["message"]
    history_override = payload.get("history_override")

    # RAG is prepared at route level and stored on the user message.
    rag_contexts = user_msg.rag_context or []
    if agent.rag_mode == RAGMode.AUTO and rag_contexts:
        from app.api.v1.endpoints.chat_rag import build_rag_prompt

        user_message_text = build_rag_prompt(rag_contexts, user_message_text)
    image_inventory_text = append_conversation_image_inventory(
        user_message_text, image_inventory
    )

    stream = AgentRunStream(UUID(payload["run_id"]))
    await stream.seed_sequence()

    loop_context = AgentLoopContext(
        agent=agent,
        conversation=conversation,
        user=SimpleNamespace(
            id=conversation.user_id,
            locale=payload.get("locale") or "en",
        ),
        user_message=image_inventory_text,
        model_id=chat_model.model_id,
        tokenizer_model_id=chat_model.tokenizer_model_id,
        model_provider=chat_model.provider,
        model_context_limit=chat_model.context_length,
        model_max_output_tokens=chat_model.max_output_tokens,
        model_used=chat_model.model_id,
        model_supports_vision=chat_model.supports_vision,
        tools=tools,
        tool_display_names=tool_display_names,
        tool_timeouts=streaming_config["tool_timeouts"],
        global_timeout=streaming_config["global_timeout"],
        idle_timeout=streaming_config["idle_timeout"],
        heartbeat_interval=streaming_config["heartbeat_interval"],
        sandbox_session_id=sandbox_session_id,
        file_content=None,
        current_images=payload.get("images") or None,
        working_history_override=history_override,
        image_pool=image_pool,
        image_inventory=image_inventory,
        append_generated_images=append_generated_images,
        current_user_message_id=user_msg.id,
        include_current_user_message=True,
        round_id=UUID(payload["round_id"]),
        protected_round_id=UUID(payload["round_id"]),
        user_locale=payload.get("locale"),
        max_iterations=agent.max_iterations or 5,
        streaming=is_streaming,
        execute_tool_call=__import__(
            "app.api.v1.endpoints.chat_tools", fromlist=["execute_tool_call"]
        ).execute_tool_call,
        team_chat_stream=model_manager.team_chat_stream,
        team_chat=model_manager.team_chat,
        record_stream_usage=None,
        calculate_usage=_calculate_model_usage,
        count_tool_definition_tokens=count_tool_definition_tokens,
        formatter=_RunFormatter(stream),
        first_round_index=1,
        cap_content=lambda: "",
    )
    loop_context.trigger_for_compression = lambda _c: None

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


async def _load_tools(agent: Agent):
    from app.api.v1.endpoints.chat import get_agent_tools

    return await get_agent_tools(agent)


async def _load_tool_display_names(agent: Agent):
    from app.api.v1.endpoints.chat import get_tool_display_names

    return await get_tool_display_names(agent, "en")


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


async def run_agent_round(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute one run payload to terminal and persist the canonical round."""
    run = await agent_run_store.get_run(UUID(payload["run_id"]))
    if not run:
        raise LookupError("run not found")
    agent = await Agent.get_or_none(id=UUID(payload["agent_id"]))
    conversation = await Conversation.get_or_none(id=UUID(payload["conversation_id"]))
    if not agent or not conversation:
        await agent_run_store.transition_run(
            run,
            AgentRunStatus.FAILED,
            error_code="context_lost",
            error_message="Agent or conversation missing",
        )
        return {"status": AgentRunStatus.FAILED.value}

    stream = AgentRunStream(run.id)
    owned = await agent_run_store.acquire_run_lock(run.id, conversation.id)
    if not owned:
        await agent_run_store.transition_run(
            run,
            AgentRunStatus.FAILED,
            error_code="lock_busy",
            error_message="Another run is active for this conversation",
        )
        return {"status": AgentRunStatus.FAILED.value}

    await agent_run_store.transition_run(run, AgentRunStatus.RUNNING)
    await stream.publish("run_start", {"status": "running", "run_id": str(run.id)})

    try:
        loop_context, user_msg, loop = await _rebuild_context(
            payload, agent=agent, conversation=conversation
        )
        if run.canonical_message_id:
            canonical = await Message.get_or_none(id=run.canonical_message_id)
        else:
            canonical = None
        if canonical is None:
            canonical = await _create_placeholder(conversation, user_msg, run)
            run.canonical_message_id = canonical.id
            await run.save(update_fields=["canonical_message_id"])

        await stream.publish(
            "message_start",
            {
                "conversation_id": str(conversation.id),
                "message_id": str(canonical.id),
                "user_message_id": str(user_msg.id),
            },
        )

        async for _chunk in loop.run():
            pass
        result = loop.result

        if result.manually_stopped:
            await _finalize_stopped(canonical, result, stream)
            await agent_run_store.transition_run(run, AgentRunStatus.STOPPED)
            await stream.publish(
                "run_end", {"status": "stopped", "message_id": str(canonical.id)}
            )
            return {
                "status": AgentRunStatus.STOPPED.value,
                "message_id": str(canonical.id),
            }

        await _finalize_completed(canonical, result, conversation, agent, stream)
        await agent_run_store.transition_run(run, AgentRunStatus.COMPLETED)
        await stream.publish(
            "run_end",
            {"status": "completed", "message_id": str(canonical.id)},
        )
        return {
            "status": AgentRunStatus.COMPLETED.value,
            "message_id": str(canonical.id),
        }

    except Exception as exc:
        logger.exception("Agent run %s failed", run.id)
        await agent_run_store.transition_run(
            run,
            AgentRunStatus.FAILED,
            error_code=type(exc).__name__,
            error_message=str(exc),
        )
        await stream.publish(
            "error",
            {"code": "run_failed", "msg": str(exc)},
        )
        await stream.publish(
            "run_end",
            {"status": "failed", "message_id": str(run.canonical_message_id or "")},
        )
        return {"status": AgentRunStatus.FAILED.value, "error": str(exc)}
    finally:
        await agent_run_store.release_run_lock(run.id, conversation.id)


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
) -> None:
    from app.api.v1.endpoints.chat import get_round_terminal_status
    from app.models.agent import Message as M

    terminal_content = result.full_content or ""
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
    canonical.model_used = _model_used(result)  # type: ignore[assignment]
    canonical.duration_ms = result.duration_ms
    canonical.first_token_ms = result.first_token_ms
    canonical.is_manually_stopped = False
    canonical.round_status = round_status
    canonical.token_usage = token_usage
    await canonical.save()

    from app.services.message_branching import (
        activate_conversation_branch,
        get_prefix_path_before,
    )

    branch_prefix = await get_prefix_path_before(
        await M.get_or_none(id=canonical.branch_parent_id) or canonical
    )
    await activate_conversation_branch(conversation.id, [*branch_prefix, canonical])
    # Conversation stats
    await Conversation.filter(id=conversation.id).update(
        message_count=conversation.message_count + 2,
        token_usage=conversation.token_usage
        + result.aggregate_input_tokens
        + result.aggregate_output_tokens,
        updated_at=now_utc(),
    )
    await Agent.filter(id=agent.id).update(
        message_count=agent.message_count + 2,
        total_tokens=agent.total_tokens
        + result.aggregate_input_tokens
        + result.aggregate_output_tokens,
    )
    usage = {
        "prompt_tokens": result.aggregate_input_tokens,
        "completion_tokens": result.aggregate_output_tokens,
        "total_tokens": result.aggregate_input_tokens + result.aggregate_output_tokens,
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


def _model_used(result: AgentLoopResult) -> str | None:
    return getattr(result, "model_used", None) or None
