"""
Chat API endpoints for Agent conversations.
Provides streaming and non-streaming chat with AI agents.
"""

from __future__ import annotations
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ast
import json
import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.models.api_key import APIKey

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from tortoise.expressions import F, Q
from tortoise.transactions import in_transaction

from app.api import deps
from app.core.i18n import t
from app.models.asset import MessageAsset
from app.models.user import User, Team
from app.models.model import TeamModel
from app.models.user import TeamMember
from app.models.agent import (
    Agent,
    AgentKnowledgeBase,
    AgentVisibility,
    Conversation,
    Message,
    MessageRole,
    MessageRoundRole,
    MessageRoundStatus,
)

from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    MessageVersion,
    SwitchVersionRequest,
    RegenerateRequest,
    EditMessageRequest,
    SSEEventType,
    AgentPublicOut,
    CreatorInfo,
    RunOut,
    RunEventOut,
    RunInputCreate,
)
from app.models.agent_run import AgentRun as _AgentRunModel

from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.llm.errors import InsufficientQuotaError
from app.llm.tools import tool_registry
from app.llm.types import ChatStreamChunk, Message as LLMChatMessage, ToolCall
from app.llm.token_counter import (
    count_message_tokens,
    count_tokens,
    count_tool_definition_tokens,
    serialize_tool_calls,
)
from app.core.timezone import now_utc
from app.services.chat_context import (
    build_context_plan,
    build_model_messages,
    prepare_model_context,
)
from app.services.message_branching import (
    activate_conversation_branch,
    find_descendant_branch_from,
    get_last_active_canonical_message,
    get_prefix_path_before,
    get_visible_conversation_messages,
    get_version_count as get_branch_version_count,
    get_version_root_id,
)
from app.services.asset import asset_service
from app.services.audit_log import AuditLogService

# Import helper functions from modules
from app.api.v1.endpoints.chat_helpers import (
    get_streaming_config,
    parse_user_input_request,
    resolve_agent_chat_model,
    get_compression_trigger,
    append_generated_images,
    collect_conversation_images,
    append_conversation_image_inventory,
    StreamIdleTimeoutError,
    send_heartbeat_if_needed,
)
from app.api.v1.endpoints.chat_tools import (
    build_file_content_for_context,
    execute_tool_call,
)
from app.api.v1.endpoints.chat_rag import (
    perform_rag_retrieval,
    aggregate_rag_contexts,
    build_rag_prompt,
)
from app.api.v1.endpoints.chat_sse import (
    build_compression_events,
    build_compression_start_event,
    build_tool_call_sse_event,
)


router = APIRouter()
logger = logging.getLogger(__name__)
GENERIC_STREAM_ERROR_KEY = "unknown_error"
AUTO_RAG_HISTORY_LIMIT = 6
AUDIT_MESSAGE_CONTENT_PREVIEW_LENGTH = 500


def _calculate_model_usage(
    *,
    messages: list[dict[str, Any]],
    content: str | None,
    reasoning_content: str | None,
    tool_calls: list[Any] | None,
    tools: list[Any] | None,
    usage: Any | None,
    model_id: str | None,
    provider: str | None,
) -> tuple[int, int, int, int, int]:
    """Prefer provider totals and estimate only when they are unavailable.

    Returns (prompt, completion, cache_read, cache_creation, total_input).
    """
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    cache_read_tokens = int(getattr(usage, "cache_read_tokens", 0) or 0)
    cache_creation_tokens = int(getattr(usage, "cache_creation_tokens", 0) or 0)
    total_input_tokens = int(getattr(usage, "total_input_tokens", 0) or prompt_tokens)
    if prompt_tokens or completion_tokens:
        return (
            prompt_tokens,
            completion_tokens,
            cache_read_tokens,
            cache_creation_tokens,
            total_input_tokens,
        )

    estimated_prompt_tokens = count_message_tokens(
        messages, model_id, provider, include_tool_calls=True
    ) + count_tool_definition_tokens(tools, model_id, provider)
    estimated_completion_tokens = count_tokens(
        content or "", model_id, provider
    ) + count_tokens(reasoning_content or "", model_id, provider)
    if tool_calls:
        estimated_completion_tokens += count_tokens(
            serialize_tool_calls(tool_calls), model_id, provider
        )

    return (
        estimated_prompt_tokens,
        estimated_completion_tokens,
        cache_read_tokens,
        cache_creation_tokens,
        estimated_prompt_tokens,
    )


async def _append_asset_manifest(
    message: str,
    *,
    conversation_id: UUID,
    agent: Agent,
    user: User,
) -> str:
    if MessageAsset._meta.default_connection is None:
        return message
    manifest = await asset_service.build_conversation_manifest(
        conversation_id=conversation_id,
        team_id=UUID(str(agent.team_id)) if agent.team_id else None,
        user_id=user.id,
    )
    manifest_text = asset_service.format_manifest(manifest)
    if not manifest_text:
        return message
    return f"{message}\n\n{manifest_text}" if message else manifest_text


async def _resolve_message_assets(
    *,
    attachments: list[Any],
    agent: Agent,
    user: User,
    conversation_id: UUID | None = None,
) -> list[tuple[Any, str, int]]:
    """Authorize attachment references before creating their message."""
    from app.models.asset import AssetScopeType

    team_id = UUID(str(agent.team_id)) if agent.team_id else None
    resolved_assets: list[tuple[Any, str, int]] = []
    for position, attachment in enumerate(attachments):
        asset_id = getattr(attachment, "asset_id", None)
        asset_ref = getattr(attachment, "asset_ref", None)
        if asset_id is not None:
            asset = await asset_service.get_authorized(
                asset_id,
                team_id=team_id,
                user_id=user.id,
            )
        elif asset_ref and conversation_id is not None:
            asset = await asset_service.resolve_ref(
                scope_type=AssetScopeType.CONVERSATION,
                scope_id=conversation_id,
                ref=asset_ref,
                team_id=team_id,
                user_id=user.id,
            )
        else:
            continue
        resolved_assets.append(
            (asset, "selected_reference" if asset_ref else "attachment", position)
        )
    return resolved_assets


@asynccontextmanager
async def _message_asset_transaction(
    has_assets: bool,
) -> AsyncIterator[None]:
    """Keep a persisted message and its Asset links atomic."""
    if not has_assets or MessageAsset._meta.default_connection is None:
        yield
        return
    async with in_transaction():
        yield


async def _attach_message_assets(
    *,
    message_id: UUID,
    assets: list[tuple[Any, str, int]],
) -> None:
    """Persist already-authorized durable Asset links for a user message."""
    for asset, role, position in assets:
        await asset_service.attach_to_message(
            asset=asset,
            message_id=message_id,
            role=role,
            position=position,
        )


def _message_content_audit_preview(content: str) -> dict[str, Any]:
    return {
        "content_preview": content[:AUDIT_MESSAGE_CONTENT_PREVIEW_LENGTH],
        "content_length": len(content),
        "truncated": len(content) > AUDIT_MESSAGE_CONTENT_PREVIEW_LENGTH,
    }


def _is_model_stream_activity(chunk: ChatStreamChunk) -> bool:
    delta = chunk.delta
    return bool(
        delta.content
        or delta.reasoning_content
        or delta.tool_calls
        or delta.tool_call_starts
        or delta.stream_activity
        or chunk.finish_reason
    )


def _build_tool_call_start_sse_events(
    tool_calls: list[ToolCall] | None,
    display_names: dict[str, str],
) -> list[str]:
    events: list[str] = []
    for tool_call in tool_calls or []:
        tool_name = tool_call.function.name
        if not tool_name:
            continue
        events.append(
            build_tool_call_sse_event(
                tool_call_id=tool_call.id,
                tool_name=tool_name,
                tool_display_name=display_names.get(tool_name, tool_name),
                arguments={},
            )
        )
    return events


def _extract_llm_error_message(error: Exception) -> str:
    message = getattr(error, "message", None) or str(error)
    marker = " - "
    if marker in message:
        payload_text = message.split(marker, 1)[1]
        try:
            payload = ast.literal_eval(payload_text)
        except (SyntaxError, ValueError):
            return message
        provider_message = payload.get("error", {}).get("message")
        if isinstance(provider_message, str) and provider_message:
            return provider_message
    return message


def _format_llm_error_message(error: Exception) -> str:
    message = _extract_llm_error_message(error)
    if not message:
        return t("model_call_failed")
    return t("model_service_request_failed", message=message)


async def check_agent_chat_access(agent_id: UUID, user: User) -> Agent:
    """Check if user can chat with the agent."""
    agent = (
        await Agent.filter(id=agent_id).prefetch_related("team", "created_by").first()
    )

    if not agent:
        raise BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    if agent.visibility == AgentVisibility.PRIVATE:
        if (
            agent.created_by
            and agent.created_by.id != user.id
            and not user.is_superuser
        ):
            raise BusinessError(
                code=ResponseCode.AGENT_ACCESS_DENIED,
                msg_key="agent_access_denied",
                status_code=403,
            )
        if not agent.created_by and not user.is_superuser:
            is_member = await TeamMember.filter(
                team_id=agent.team_id, user_id=user.id
            ).exists()
            if not is_member:
                raise BusinessError(
                    code=ResponseCode.AGENT_ACCESS_DENIED,
                    msg_key="agent_access_denied",
                    status_code=403,
                )
    elif not user.is_superuser:
        is_member = await TeamMember.filter(
            team_id=agent.team_id, user_id=user.id
        ).exists()
        if not is_member:
            raise BusinessError(
                code=ResponseCode.AGENT_ACCESS_DENIED,
                msg_key="agent_access_denied",
                status_code=403,
            )

    return agent


async def get_public_agent(agent_id: UUID, user: User | None = None) -> Agent:
    """
    Get agent for chat page.
    - Must be logged in to access any agent
    - Private agents: creator only
    - Team/public agents: team members only
    """
    # Must be logged in
    if not user:
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="not_authenticated",
            status_code=401,
        )

    agent = (
        await Agent.filter(id=agent_id).prefetch_related("team", "created_by").first()
    )

    if not agent:
        raise BusinessError(
            code=ResponseCode.AGENT_NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    if agent.visibility == AgentVisibility.PRIVATE:
        if (
            agent.created_by
            and agent.created_by.id != user.id
            and not user.is_superuser
        ):
            raise BusinessError(
                code=ResponseCode.AGENT_ACCESS_DENIED,
                msg_key="agent_access_denied",
                status_code=403,
            )
        if not agent.created_by and not user.is_superuser:
            is_member = await TeamMember.filter(
                team_id=agent.team_id, user_id=user.id
            ).exists()
            if not is_member:
                raise BusinessError(
                    code=ResponseCode.AGENT_ACCESS_DENIED,
                    msg_key="agent_access_denied",
                    status_code=403,
                )
    elif not user.is_superuser:
        is_member = await TeamMember.filter(
            team_id=agent.team_id, user_id=user.id
        ).exists()
        if not is_member:
            raise BusinessError(
                code=ResponseCode.AGENT_ACCESS_DENIED,
                msg_key="agent_access_denied",
                status_code=403,
            )

    return agent


async def get_or_create_conversation(
    agent: Agent, user: User, conversation_id: UUID | None, variables: dict
) -> Conversation:
    """Get existing conversation or create a new one."""
    if conversation_id:
        conversation = await Conversation.filter(
            id=conversation_id,
            agent_id=agent.id,
            user=user,
        ).first()
        if not conversation:
            raise BusinessError(
                code=ResponseCode.CONVERSATION_NOT_FOUND,
                msg_key="conversation_not_found",
                status_code=404,
            )
        return conversation

    # Create new conversation
    conversation = await Conversation.create(
        agent=agent,
        user=user,
        variables=variables,
    )

    # Update agent stats atomically to prevent race conditions
    await Agent.filter(id=agent.id).update(
        conversation_count=F("conversation_count") + 1
    )

    # Update team stats
    await Team.filter(id=agent.team.id).update(
        total_conversations=F("total_conversations") + 1
    )

    return conversation


async def get_next_user_branch_parent_id(conversation: Conversation) -> UUID | None:
    last_message = await get_last_active_canonical_message(conversation.id)
    return last_message.id if last_message else None


async def update_message_stats(agent: Agent, token_usage: dict | None = None):
    """
    Update cumulative statistics for agent and team when a message is created.

    Args:
        agent: The agent
        token_usage: Token usage dict with 'prompt' and 'completion' keys
    """
    # Calculate total tokens
    total_tokens = 0
    if token_usage:
        total_tokens = (token_usage.get("prompt", 0) or 0) + (
            token_usage.get("completion", 0) or 0
        )

    # Update agent stats atomically
    await Agent.filter(id=agent.id).update(
        message_count=F("message_count") + 1,
        total_tokens=F("total_tokens") + total_tokens,
    )

    # Update team stats atomically
    await Team.filter(id=agent.team.id).update(
        total_messages=F("total_messages") + 1,
        total_tokens=F("total_tokens") + total_tokens,
    )


async def build_round_steps_map(
    messages: list[Message],
) -> dict[UUID, list[dict[str, Any]]]:
    """Group non-canonical round messages under their round_id for response payloads."""
    round_ids = {
        message.round_id
        for message in messages
        if message.round_id and message.is_round_canonical
    }
    if not round_ids:
        return {}

    step_messages = (
        await Message.filter(
            conversation_id=messages[0].conversation_id,
            is_active=True,
            round_id__in=list(round_ids),
            is_round_canonical=False,
        )
        .order_by("created_at", "round_index")
        .all()
    )

    grouped: dict[UUID, list[dict[str, Any]]] = {}
    for step in step_messages:
        if step.round_id:
            grouped.setdefault(step.round_id, []).append(
                {
                    "id": step.id,
                    "role": step.role.value,
                    "content": step.content,
                    "tool_calls": step.tool_calls,
                    "tool_call_id": step.tool_call_id,
                    "tool_name": step.tool_name,
                    "reasoning_content": step.reasoning_content,
                    "model_used": step.model_used,
                    "token_usage": step.token_usage,
                    "duration_ms": step.duration_ms,
                    "is_manually_stopped": step.is_manually_stopped,
                    "rag_context": step.rag_context,
                    "created_at": step.created_at,
                    "round_id": step.round_id,
                    "round_index": step.round_index,
                    "round_role": step.round_role.value if step.round_role else None,
                    "is_round_canonical": step.is_round_canonical,
                    "iteration_index": step.iteration_index,
                    "round_status": step.round_status.value
                    if step.round_status
                    else None,
                }
            )
    return grouped


async def build_message_round_payloads(messages: list[Message]) -> list[dict[str, Any]]:
    """Serialize canonical round messages with nested non-canonical step payloads."""
    steps_by_round = await build_round_steps_map(messages)
    payloads: list[dict[str, Any]] = []
    for message in messages:
        if message.round_id and not message.is_round_canonical:
            continue
        msg_data = MessageOut.model_validate(message).model_dump()
        if message.round_id and message.round_role == MessageRoundRole.ASSISTANT_FINAL:
            msg_data["steps"] = steps_by_round.get(message.round_id)
        payloads.append(msg_data)
    return payloads


def append_round_history_entry(
    history: list[dict[str, Any]],
    *,
    role: str,
    content: str,
    round_id: UUID,
    round_index: int,
    round_role: str,
    is_round_canonical: bool,
    iteration_index: int | None = None,
    round_status: str | None = None,
    reasoning_content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
) -> None:
    entry: dict[str, Any] = {
        "role": role,
        "content": content,
        "round_id": str(round_id),
        "round_index": round_index,
        "round_role": round_role,
        "is_round_canonical": is_round_canonical,
    }
    if iteration_index is not None:
        entry["iteration_index"] = iteration_index
    if round_status is not None:
        entry["round_status"] = round_status
    if reasoning_content is not None:
        entry["reasoning_content"] = reasoning_content
    if tool_calls is not None:
        entry["tool_calls"] = tool_calls
    if tool_call_id is not None:
        entry["tool_call_id"] = tool_call_id
    if tool_name is not None:
        entry["tool_name"] = tool_name
    history.append(entry)


async def build_messages(
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    file_content: str | None = None,
    user_locale: str | None = None,
    history_override: list[Any] | None = None,
    current_images: list[Any] | None = None,
    model_supports_vision: bool = False,
    current_user_message_id: UUID | None = None,
) -> list[LLMChatMessage]:
    """Build message list for LLM call."""
    return await build_model_messages(
        agent=agent,
        conversation=conversation,
        user_message=user_message,
        file_content=file_content,
        user_locale=user_locale,
        history_override=history_override,
        current_images=current_images,
        model_supports_vision=model_supports_vision,
        current_user_message_id=current_user_message_id,
    )


async def get_model_identifier(agent: Agent) -> str | None:
    """Get the database UUID of the agent's bound model, if any."""
    if not getattr(agent, "model_id", None):
        return None

    team_model = (
        await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
    )
    if team_model and getattr(team_model, "model", None):
        return str(team_model.model.id)

    return None


async def get_agent_chat_model(agent: Agent) -> TeamModel | None:
    """Get the chat TeamModel for an agent.

    Kept as a backward-compatible seam for tests that inject a fake TeamModel.
    Production code resolves the full chat model (including the global default)
    via ``resolve_agent_chat_model``.
    """
    if not getattr(agent, "model_id", None):
        return None

    return await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()


def get_round_terminal_status(
    *,
    completed: bool,
    manually_stopped: bool = False,
    max_iterations_reached: bool = False,
    errored: bool = False,
) -> MessageRoundStatus:
    if manually_stopped:
        return MessageRoundStatus.MANUALLY_STOPPED
    if max_iterations_reached:
        return MessageRoundStatus.MAX_ITERATIONS_REACHED
    if errored:
        return MessageRoundStatus.ERROR
    if completed:
        return MessageRoundStatus.COMPLETED
    return MessageRoundStatus.ERROR


def build_max_iterations_terminal_content(user_locale: str | None = None) -> str:
    return t("chat_max_iterations_reached", lang=user_locale)


async def round_has_persisted_trace(message: Message | None) -> bool:
    if message is None or message.round_id is None:
        return False
    return await Message.filter(
        conversation_id=message.conversation_id,
        round_id=message.round_id,
        is_round_canonical=False,
    ).exists()


def _first_token_ms(start_time: float, first_token_time: float | None) -> int | None:
    if first_token_time is None:
        return None
    return int((first_token_time - start_time) * 1000)


async def persist_partial_round_error(
    message: Message | None,
    *,
    content: str,
    reasoning: str,
    model_used: str | None,
    start_time: float,
    first_token_time: float | None = None,
    fallback_content: str | None = None,
) -> bool:
    if message is None:
        return False

    has_progress = bool(content or reasoning)
    if not has_progress:
        has_progress = await round_has_persisted_trace(message)
    if not has_progress and not fallback_content:
        return False

    final_content: str
    if content:
        final_content = content
    elif fallback_content:
        final_content = fallback_content
    else:
        final_content = ""
    message.content = final_content
    message.reasoning_content = reasoning if reasoning else None  # type: ignore[assignment]
    message.model_used = model_used  # type: ignore[assignment]
    message.model_used = model_used
    message.duration_ms = int((time.time() - start_time) * 1000)
    message.first_token_ms = _first_token_ms(start_time, first_token_time)
    message.is_manually_stopped = False
    message.round_status = MessageRoundStatus.ERROR
    message.created_at = now_utc()
    await message.save()
    return True


async def get_agent_tools(agent: Agent) -> list[dict]:
    """
    Get tools configured for the agent.

    Returns OpenAI-compatible tool definitions.
    Automatically includes knowledge_search tool if agent has knowledge bases and rag_mode is 'agentic'.
    Automatically includes memory tools if agent has enable_memory=True.
    """
    from app.models.tool import Tool
    from app.models.agent import RAGMode
    from app.llm.tools.memory_tools import get_memory_tools

    tools_config = list(
        agent.tools_config or []
    )  # Make a copy to avoid modifying original
    openai_tools: list[dict] = []
    seen_tool_names: set[str] = set()

    def append_openai_tool(tool_def: dict) -> None:
        function_name = (
            tool_def.get("function", {}).get("name")
            if isinstance(tool_def, dict)
            else None
        )
        if not function_name or function_name in seen_tool_names:
            return
        openai_tools.append(tool_def)
        seen_tool_names.add(function_name)

    # Add memory tools if enabled
    if agent.enable_memory:
        memory_tools = get_memory_tools()
        memory_config = agent.memory_config or {}
        auto_extract = memory_config.get("auto_extract", True)

        for tool in memory_tools:
            # If auto_extract is disabled, only provide search_memory tool
            if not auto_extract and tool["name"] != "search_memory":
                continue

            # Convert Claude format (input_schema) to OpenAI format (parameters)
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
            )
            logger.debug(f"Added memory tool: {tool['name']}")

        logger.info(
            f"Memory tools enabled: auto_extract={auto_extract}, tools_count={len([t for t in openai_tools if 'memory' in t['function']['name']])}"
        )

    # Add knowledge_search tool only for agentic RAG mode
    if agent.rag_mode == RAGMode.AGENTIC:
        kb_associations = await AgentKnowledgeBase.filter(
            agent_id=agent.id
        ).prefetch_related("knowledge_base")
        if kb_associations:
            kb_info = []
            for akb in kb_associations:
                kb = akb.knowledge_base
                kb_desc = f"「{kb.name}」"
                if kb.description:
                    kb_desc += f": {kb.description}"
                kb_info.append(kb_desc)
            kb_list = "\n".join(f"- {info}" for info in kb_info)

            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "knowledge_search",
                        "description": f"""Search internal knowledge bases for information. Available knowledge bases:
{kb_list}

CRITICAL RULES:
1. When you encounter ANY information you don't know or are uncertain about, ALWAYS search the knowledge base FIRST before responding.
2. NEVER say "I don't know" or "I don't have that information" without searching first.
3. NEVER ask the user for more details if you can try searching with the available keywords.
4. For vague or incomplete questions, extract whatever keywords you can and search anyway.
5. If the first search doesn't find results, try different keywords or broader terms.

Examples of when to search:
- User mentions a name, place, product, or event you don't recognize → SEARCH IT
- User asks about company/organization info → SEARCH IT
- User references something from a previous conversation you don't have context for → SEARCH IT
- User asks "what about X" or "tell me about X" → SEARCH IT""",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search keywords extracted from the user's message. Use nouns, names, and key phrases. For vague questions, use the most specific terms available.",
                                }
                            },
                            "required": ["query"],
                        },
                    },
                }
            )

    if getattr(agent, "enable_attachments", False):
        asset_tools = [
            {
                "type": "function",
                "function": {
                    "name": "inspect_asset",
                    "description": t("asset_tool_inspect_description"),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ref": {
                                "type": "string",
                                "pattern": "^[0-9a-f]{4}$",
                                "description": t("asset_tool_ref_description"),
                            }
                        },
                        "required": ["ref"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_asset",
                    "description": t("asset_tool_read_description"),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ref": {
                                "type": "string",
                                "pattern": "^[0-9a-f]{4}$",
                                "description": t("asset_tool_ref_description"),
                            },
                            "max_chars": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 50000,
                                "default": 12000,
                            },
                        },
                        "required": ["ref"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "parse_asset",
                    "description": t("asset_tool_parse_description"),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ref": {
                                "type": "string",
                                "pattern": "^[0-9a-f]{4}$",
                                "description": t("asset_tool_ref_description"),
                            }
                        },
                        "required": ["ref"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "materialize_asset",
                    "description": t("asset_tool_materialize_description"),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ref": {
                                "type": "string",
                                "pattern": "^[0-9a-f]{4}$",
                                "description": t("asset_tool_ref_description"),
                            },
                            "path": {
                                "type": "string",
                                "description": t(
                                    "asset_tool_materialize_path_description"
                                ),
                            },
                        },
                        "required": ["ref", "path"],
                    },
                },
            },
        ]
        for asset_tool in asset_tools:
            append_openai_tool(asset_tool)

    if agent.enable_image_generation:
        for builtin_tool in tool_registry.to_openai_tools(["generate_image"]):
            append_openai_tool(builtin_tool)

    if agent.enable_video_generation:
        for builtin_tool in tool_registry.to_openai_tools(["generate_video"]):
            append_openai_tool(builtin_tool)

    for config in tools_config:
        tool_type = config.get("type")

        if tool_type == "builtin":
            tool_name = config.get("name")
            if tool_name:
                builtin_tools = tool_registry.to_openai_tools([tool_name])
                sandbox_tools = tool_registry.to_openai_sandbox_tools([tool_name])
                for builtin_tool in [*builtin_tools, *sandbox_tools]:
                    append_openai_tool(builtin_tool)

        elif tool_type == "custom":
            tool_id = config.get("tool_id")
            if tool_id:
                # Get custom tool from database
                custom_tool = await Tool.filter(id=tool_id, is_enabled=True).first()
                if custom_tool:
                    # Convert parameters to JSON Schema format
                    properties = {}
                    required = []
                    for param in custom_tool.parameters:
                        param_name = param.get("name")
                        properties[param_name] = {
                            "type": param.get("type", "string"),
                            "description": param.get("description", ""),
                        }
                        if param.get("required"):
                            required.append(param_name)

                    openai_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": f"custom_{custom_tool.name}",
                                "description": custom_tool.description,
                                "parameters": {
                                    "type": "object",
                                    "properties": properties,
                                    "required": required,
                                },
                            },
                        }
                    )

        elif tool_type == "skill":
            from app.services.skill import SkillService

            skill_id = config.get("skill_id")
            if skill_id:
                try:
                    skill = await SkillService.get_skill_for_team(
                        skill_id,
                        agent.team_id,
                        enabled_only=True,
                    )
                    append_openai_tool(
                        SkillService.to_tool_info(skill).to_openai_schema()
                    )
                    for sandbox_tool in tool_registry.to_openai_sandbox_tools(
                        ["read", "edit", "write", "bash"]
                    ):
                        append_openai_tool(sandbox_tool)
                except Exception as e:
                    logger.warning("Failed to get skill tool %s: %s", skill_id, e)

        elif tool_type == "mcp":
            # MCP tool - get tools from MCP server
            # Frontend uses server_id for MCP tools
            tool_id = config.get("server_id") or config.get("tool_id")
            if tool_id:
                from app.llm.tools.mcp_client import list_mcp_tools

                mcp_tool = await Tool.filter(id=tool_id, is_enabled=True).first()
                if mcp_tool and mcp_tool.mcp_config:
                    try:
                        # Get tools from MCP server
                        mcp_tools = await list_mcp_tools(mcp_tool.mcp_config)
                        for mt in mcp_tools:
                            # Convert MCP tool to OpenAI format
                            # Use mcp_<server_name>_<tool_name> for readability
                            openai_tools.append(
                                {
                                    "type": "function",
                                    "function": {
                                        "name": f"mcp_{mcp_tool.name}_{mt.name}",
                                        "description": mt.description
                                        or f"MCP tool: {mt.name}",
                                        "parameters": mt.parameters
                                        if mt.parameters
                                        else {
                                            "type": "object",
                                            "properties": {},
                                            "required": [],
                                        },
                                    },
                                }
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to get MCP tools from {mcp_tool.name}: {e}"
                        )

    return openai_tools


async def get_tool_display_names(
    agent: Agent, user_locale: str | None = None
) -> dict[str, str]:
    """
    Get a mapping from tool internal names to display names.

    Args:
        agent: The agent
        user_locale: User's locale from database for i18n display names

    Returns a dict like:
    {
        "knowledge_search": "Knowledge Search",
        "get_current_time": "Get Current Time",
        "custom_my_tool": "My Tool",
        "mcp_server_tool": "MCP Tool",
    }
    """
    from app.models.tool import Tool
    from app.models.agent import RAGMode
    from app.schemas.tool import BUILTIN_TOOLS_METADATA
    from app.core.i18n import t

    display_names: dict[str, str] = {}
    tools_config = list(agent.tools_config or [])

    # Add attachment tool display names if attachments are enabled
    if getattr(agent, "enable_attachments", False):
        display_names.update(
            {
                "inspect_asset": t("asset_tool_inspect", lang=user_locale),
                "read_asset": t("asset_tool_read", lang=user_locale),
                "parse_asset": t("asset_tool_parse", lang=user_locale),
                "materialize_asset": t("asset_tool_materialize", lang=user_locale),
            }
        )

    # Add knowledge_search display name for agentic RAG mode
    if agent.rag_mode == RAGMode.AGENTIC:
        kb_associations = await AgentKnowledgeBase.filter(agent_id=agent.id).count()
        if kb_associations > 0:
            display_names["knowledge_search"] = t(
                "tool_knowledge_search", lang=user_locale
            )

    # Add memory tool display names if memory is enabled
    if agent.enable_memory:
        display_names["create_memory_entity"] = t(
            "tool_create_memory_entity", lang=user_locale
        )
        display_names["create_memory_relation"] = t(
            "tool_create_memory_relation", lang=user_locale
        )
        display_names["update_memory_entity"] = t(
            "tool_update_memory_entity", lang=user_locale
        )
        display_names["search_memory"] = t("tool_search_memory", lang=user_locale)

    if agent.enable_image_generation:
        metadata = BUILTIN_TOOLS_METADATA.get("generate_image", {})
        display_name_key = metadata.get("display_name_key")
        display_names["generate_image"] = (
            t(display_name_key, lang=user_locale)
            if display_name_key
            else "generate_image"
        )

    if agent.enable_video_generation:
        metadata = BUILTIN_TOOLS_METADATA.get("generate_video", {})
        display_name_key = metadata.get("display_name_key")
        display_names["generate_video"] = (
            t(display_name_key, lang=user_locale)
            if display_name_key
            else "generate_video"
        )

    for config in tools_config:
        tool_type = config.get("type")

        if tool_type == "builtin":
            tool_name = config.get("name")
            if tool_name:
                metadata = BUILTIN_TOOLS_METADATA.get(tool_name, {})
                display_name_key = metadata.get("display_name_key")
                if display_name_key:
                    display_names[tool_name] = t(display_name_key, lang=user_locale)
                else:
                    display_names[tool_name] = metadata.get("display_name", tool_name)

        elif tool_type == "custom":
            tool_id = config.get("tool_id")
            if tool_id:
                custom_tool = await Tool.filter(id=tool_id, is_enabled=True).first()
                if custom_tool:
                    # Custom tools use custom_<name> format
                    display_names[f"custom_{custom_tool.name}"] = (
                        custom_tool.display_name
                    )

        elif tool_type == "skill":
            from app.services.skill import SkillService

            skill_id = config.get("skill_id")
            if skill_id:
                try:
                    skill = await SkillService.get_skill_for_team(
                        skill_id,
                        agent.team_id,
                        enabled_only=True,
                    )
                    display_names[SkillService.build_tool_name(skill)] = (
                        skill.display_name
                    )
                except Exception:
                    pass

        elif tool_type == "mcp":
            tool_id = config.get("server_id") or config.get("tool_id")
            if tool_id:
                from app.llm.tools.mcp_client import list_mcp_tools

                mcp_tool = await Tool.filter(id=tool_id, is_enabled=True).first()
                if mcp_tool and mcp_tool.mcp_config:
                    try:
                        mcp_tools = await list_mcp_tools(mcp_tool.mcp_config)
                        for mt in mcp_tools:
                            # MCP tools use mcp_<server_name>_<tool_name> format
                            tool_key = f"mcp_{mcp_tool.name}_{mt.name}"
                            # Use MCP tool's description as display name, or server/tool name
                            display_names[tool_key] = (
                                f"{mcp_tool.display_name}/{mt.name}"
                            )
                    except Exception:
                        pass

    return display_names


# ============ Public Endpoints (Optional Auth) ============


@router.get("/{agent_id}/public", response_model=Response[AgentPublicOut])
async def get_public_agent_info(
    agent_id: UUID,
    current_user: User | None = Depends(deps.get_current_user_optional),
) -> Any:
    """
    Get agent info for chat page.
    - With authentication: returns agent if user has access (team member, etc.)
    - Without authentication: only returns published public agents
    """
    agent = await get_public_agent(agent_id, current_user)

    # Build public response with minimal info
    creator_info = None
    if agent.created_by:
        creator_info = CreatorInfo(
            id=agent.created_by.id,
            username=agent.created_by.username,
            avatar_url=agent.created_by.avatar_url,
        )

    return success(
        data=AgentPublicOut(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            icon=agent.icon,
            avatar_url=agent.avatar_url,
            opening_message=agent.opening_message,
            suggested_questions=agent.suggested_questions or [],
            powered_by_text=agent.powered_by_text,
            variables=agent.variables or [],
            enable_attachments=agent.enable_attachments,
            attachment_config=agent.attachment_config,
            hide_tool_calls=agent.hide_tool_calls,
            hide_message_actions=agent.hide_message_actions,
            hide_reasoning=agent.hide_reasoning,
            created_by=creator_info,
        )
    )


# ============ Chat Endpoints ============


@router.post("/{agent_id}/chat", response_model=Response[ChatResponse])
async def chat(
    agent_id: UUID,
    chat_in: ChatRequest,
    auth_result: tuple[User, "APIKey | None"] = Depends(
        deps.get_current_user_or_api_key
    ),
) -> Any:
    """
    Chat with an agent (non-streaming).
    Supports both JWT Token and API Key authentication.

    Creates a new conversation if conversation_id is not provided.
    """
    current_user, api_key = auth_result

    # 检查用户是否激活
    if not current_user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key="inactive_user",
            status_code=401,
        )

    # 如果使用 API Key，检查是否有权访问该 Agent
    await deps.check_api_key_agent_access(api_key, agent_id)

    agent = await check_agent_chat_access(agent_id, current_user)
    conversation = await get_or_create_conversation(
        agent, current_user, chat_in.conversation_id, chat_in.variables
    )

    from app.models.agent import RAGMode

    # Handle RAG based on mode
    rag_contexts: list[dict] = []
    final_message = chat_in.message

    if agent.rag_mode == RAGMode.AUTO:
        # Traditional RAG: automatically retrieve on every message
        rag_contexts = await perform_rag_retrieval(
            agent,
            chat_in.message,
            await get_visible_conversation_messages(
                conversation.id, limit=AUTO_RAG_HISTORY_LIMIT
            ),
        )
        rag_contexts = aggregate_rag_contexts(rag_contexts)
        final_message = build_rag_prompt(rag_contexts, chat_in.message)

    message_assets = await _resolve_message_assets(
        attachments=[*chat_in.images, *chat_in.file_urls],
        agent=agent,
        user=current_user,
        conversation_id=conversation.id,
    )
    round_id = uuid4()

    user_branch_parent_id = await get_next_user_branch_parent_id(conversation)

    # Save user message with images and file_urls.
    async with _message_asset_transaction(bool(message_assets)):
        user_msg = await Message.create(
            conversation=conversation,
            role=MessageRole.USER,
            content=chat_in.message,
            images=[img.model_dump() for img in chat_in.images]
            if chat_in.images
            else None,
            file_urls=[f.model_dump() for f in chat_in.file_urls]
            if chat_in.file_urls
            else None,
            rag_context=rag_contexts if rag_contexts else None,
            branch_parent_id=user_branch_parent_id,
            round_id=round_id,
            round_index=0,
            round_role=MessageRoundRole.USER_INPUT,
            is_round_canonical=True,
        )
        await _attach_message_assets(
            message_id=user_msg.id,
            assets=message_assets,
        )
    final_message = await _append_asset_manifest(
        final_message,
        conversation_id=conversation.id,
        agent=agent,
        user=current_user,
    )

    # Update message stats (user message, no tokens)
    await update_message_stats(agent, token_usage=None)

    # Resolve the chat model up front so context budgeting uses the same
    # metadata as the eventual team_chat call (including the global default).
    chat_model = await resolve_agent_chat_model(agent)
    model_id = chat_model.model_id
    model_context_limit = chat_model.context_length
    model_max_output_tokens = chat_model.max_output_tokens
    model_provider = chat_model.provider
    tokenizer_model_id = chat_model.tokenizer_model_id
    model_used = model_id

    model_supports_vision = bool(
        chat_in.images and agent.enable_attachments and chat_model.supports_vision
    )

    streaming_config = get_streaming_config(agent)
    tool_timeouts = streaming_config["tool_timeouts"]
    from app.services.sandbox.gateway import sandbox_gateway

    sandbox_session_id = await sandbox_gateway.create_session(
        agent_id=str(agent.id),
        team_id=str(agent.team_id) if agent.team_id else None,
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
    )
    file_content_str, updated_file_urls = await build_file_content_for_context(
        agent=agent,
        file_urls=chat_in.file_urls,
        legacy_files=chat_in.files,
        user_locale=current_user.locale,
        tool_timeouts=tool_timeouts,
        user=current_user,
    )
    if updated_file_urls is not None and user_msg.file_urls != updated_file_urls:
        user_msg.file_urls = updated_file_urls
        await user_msg.save(update_fields=["file_urls"])

    working_history_override = (
        [message.model_dump(exclude_none=True) for message in chat_in.history_override]
        if chat_in.history_override
        else None
    )
    image_pool, image_inventory = collect_conversation_images(
        await get_visible_conversation_messages(conversation.id),
        current_message_id=user_msg.id,
        current_images=chat_in.images,
    )
    model_message = append_conversation_image_inventory(final_message, image_inventory)

    try:
        # Import here to avoid circular import
        from app.llm import model_manager
        from app.llm.errors import QuotaExceededError, LLMError
        from app.llm.types import ToolDefinition, FunctionDefinition

        # Build tool definitions
        tools_openai = await get_agent_tools(agent)
        tool_display_names = await get_tool_display_names(agent, current_user.locale)
        tools: list[ToolDefinition] | None = None
        if tools_openai:
            tools = [
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

        from app.services.agent_loop import AgentLoop, AgentLoopContext, ContextTurn

        max_iterations = agent.max_iterations or 5

        async def build_turn(
            **kwargs,
        ):
            """Non-stream turns summarize silently via prepare_model_context."""
            prepared = await prepare_model_context(**kwargs)
            return ContextTurn(
                prepared=prepared,
                will_summarize=False,
                compression=prepared.compression,
            )

        loop = AgentLoop(
            AgentLoopContext(
                agent=agent,
                conversation=conversation,
                user=current_user,
                user_message=model_message,
                model_id=model_id,
                tokenizer_model_id=tokenizer_model_id,
                model_provider=model_provider,
                model_context_limit=model_context_limit,
                model_max_output_tokens=model_max_output_tokens,
                model_used=model_used,
                model_supports_vision=model_supports_vision,
                tools=tools,
                tool_display_names=tool_display_names,
                tool_timeouts=tool_timeouts,
                sandbox_session_id=sandbox_session_id,
                file_content=file_content_str,
                current_images=chat_in.images,
                working_history_override=working_history_override,
                image_pool=image_pool,
                image_inventory=image_inventory,
                append_generated_images=append_generated_images,
                current_user_message_id=user_msg.id,
                round_id=round_id,
                protected_round_id=round_id,
                user_locale=current_user.locale,
                max_iterations=max_iterations,
                enable_user_input_request=agent.enable_user_input_request,
                streaming=False,
                build_turn=build_turn,
                execute_tool_call=execute_tool_call,
                team_chat=model_manager.team_chat,
                calculate_usage=_calculate_model_usage,
                first_round_index=1,
            )
        )
        async for _event in loop.run():
            pass  # no SSE in the non-stream API
        loop_result = loop.result
        max_iterations_reached = loop_result.max_iterations_reached
        total_prompt_tokens = loop_result.aggregate_input_tokens
        total_completion_tokens = loop_result.aggregate_output_tokens
        total_cache_read_tokens = loop_result.aggregate_cache_read_tokens
        total_cache_creation_tokens = loop_result.aggregate_cache_creation_tokens
        total_usage_input_tokens = loop_result.aggregate_total_input_tokens
        duration_ms = loop_result.duration_ms
        duration_ms = loop_result.duration_ms

        clean_final_content = (
            build_max_iterations_terminal_content(current_user.locale)
            if max_iterations_reached
            else (loop_result.full_content or "")
        )
        if (
            not max_iterations_reached
            and agent.enable_user_input_request
            and clean_final_content
        ):
            _, clean_final_content = parse_user_input_request(clean_final_content)

        final_tool_calls = None

        prompt_tokens = total_prompt_tokens
        completion_tokens = total_completion_tokens
        round_status = get_round_terminal_status(
            completed=not max_iterations_reached,
            max_iterations_reached=max_iterations_reached,
        )

        # Save assistant message (final response)
        assistant_msg = await Message.create(
            conversation=conversation,
            role=MessageRole.ASSISTANT,
            content=clean_final_content,
            reasoning_content=(
                None if max_iterations_reached else (loop_result.full_reasoning or None)
            ),
            model_used=model_used,
            token_usage={
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "cache_read": total_cache_read_tokens,
                "cache_creation": total_cache_creation_tokens,
                "total_input": total_usage_input_tokens,
            },
            duration_ms=duration_ms,
            tool_calls=final_tool_calls,
            branch_parent_id=user_msg.id,
            round_id=round_id,
            round_index=loop_result.final_round_index,
            round_role=MessageRoundRole.ASSISTANT_FINAL,
            is_round_canonical=True,
            round_status=round_status,
        )

        # Update message stats with token usage
        await update_message_stats(
            agent,
            token_usage={
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "cache_read": total_cache_read_tokens,
                "cache_creation": total_cache_creation_tokens,
            },
        )

        # Update conversation stats atomically
        title_update = {}
        if not conversation.title:
            # Auto-generate title from first message
            title_update["title"] = chat_in.message[:50] + (
                "..." if len(chat_in.message) > 50 else ""
            )

        await Conversation.filter(id=conversation.id).update(
            message_count=F("message_count") + 2,
            token_usage=F("token_usage") + (prompt_tokens + completion_tokens),
            updated_at=now_utc(),
            **title_update,
        )

        branch_prefix = await get_prefix_path_before(user_msg)
        await activate_conversation_branch(
            conversation.id,
            [*branch_prefix, user_msg, assistant_msg],
        )

        return success(
            data=ChatResponse(
                conversation_id=conversation.id,
                message=MessageOut.model_validate(assistant_msg),
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cache_read_tokens": total_cache_read_tokens,
                    "cache_creation_tokens": total_cache_creation_tokens,
                    "total_input_tokens": total_usage_input_tokens,
                },
            ),
            msg_key="chat_success",
        )

    except (QuotaExceededError, InsufficientQuotaError) as e:
        raise BusinessError(
            code=ResponseCode.MODEL_QUOTA_EXCEEDED,
            msg_key="model_quota_exceeded",
            status_code=429,
            data={"quota_type": e.quota_type},
        )
    except LLMError as e:
        logger.exception(
            "LLM error during chat: conversation=%s agent=%s error=%s",
            conversation.id,
            agent.id,
            e,
        )
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="llm_processing_failed",
            status_code=500,
        )


@router.post("/{agent_id}/chat/stream")
async def chat_stream(
    agent_id: UUID,
    chat_in: ChatRequest,
    request: Request,
    auth_result: tuple[User, "APIKey | None"] = Depends(
        deps.get_current_user_or_api_key
    ),
) -> StreamingResponse:
    """
    Chat with an agent (streaming via SSE).
    Supports both JWT Token and API Key authentication.

    Returns Server-Sent Events with the following event types:
    - message_start: {"conversation_id": "...", "message_id": "..."}
    - rag_start: {}
    - rag_context: {"contexts": [...]}
    - reasoning_start: {}
    - reasoning_delta: {"delta": "..."}
    - reasoning_end: {}
    - content_delta: {"delta": "..."}
    - tool_call: {"tool_name": "...", "arguments": {...}}
    - tool_result: {"tool_name": "...", "result": {...}}
    - media_result: {"kind": "media.image"|"media.video", ...} (UI-only media payload for rendering in assistant body, not for LLM replay)
    - compression_start: {"stage": "...", "trigger": "..."}
    - compression_end: {"stage": "...", "trigger": "...", ...}
    - output_truncated: {}
    - iteration_cap_reached: {"content": "..."}
    - message_end: {"usage": {...}}
    - error: {"code": ..., "msg": "..."}
    """
    current_user, api_key = auth_result

    # 检查用户是否激活
    if not current_user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key="inactive_user",
            status_code=401,
        )

    # 如果使用 API Key，检查是否有权访问该 Agent
    await deps.check_api_key_agent_access(api_key, agent_id)

    agent = await check_agent_chat_access(agent_id, current_user)
    conversation = await get_or_create_conversation(
        agent, current_user, chat_in.conversation_id, chat_in.variables
    )

    async def event_generator():
        # Record start time and last event time
        start_time = time.time()
        first_token_time: float | None = None
        last_event_time = start_time
        full_content = ""
        full_reasoning = ""
        message_id = None
        assistant_msg: Message | None = None
        model_id: str | None = None
        model_used: str | None = None
        global_timeout: float = 1800.0  # Default 30 minutes
        idle_timeout: float = 300.0  # Default 5 minutes

        try:
            # Import here to avoid circular import at module level
            from app.llm import model_manager
            from app.llm.errors import (
                QuotaExceededError,
                LLMError,
                ModelNotFoundError,
                AuthenticationError,
                RateLimitError,
            )
            from app.llm.types import (
                ToolDefinition,
                FunctionDefinition,
            )

            # Get streaming configuration
            streaming_config = get_streaming_config(agent)
            global_timeout = streaming_config["global_timeout"]
            heartbeat_interval = streaming_config["heartbeat_interval"]
            tool_timeouts = streaming_config["tool_timeouts"]
            idle_timeout = streaming_config["idle_timeout"]

            # Create sandbox session for stateful execution
            from app.services.sandbox.gateway import sandbox_gateway

            sandbox_session_id = await sandbox_gateway.create_session(
                agent_id=str(agent.id),
                team_id=str(agent.team_id) if agent.team_id else None,
                user_id=str(current_user.id),
                ttl_hours=24,
                conversation_id=str(conversation.id),
            )

            logger.info(
                f"Starting stream for conversation {conversation.id}, "
                f"global_timeout={global_timeout}s, heartbeat_interval={heartbeat_interval}s"
            )

            # Use asyncio.timeout to wrap entire streaming logic
            import asyncio

            async with asyncio.timeout(global_timeout):
                try:
                    from app.models.agent import RAGMode

                    # Handle RAG based on mode
                    rag_contexts: list[dict] = []
                    final_message = chat_in.message

                    if agent.rag_mode == RAGMode.AUTO:
                        # Traditional RAG: automatically retrieve on every message
                        has_knowledge_bases = await AgentKnowledgeBase.exists(
                            agent_id=agent.id
                        )
                        if has_knowledge_bases:
                            yield f"event: {SSEEventType.RAG_START}\ndata: {json.dumps({})}\n\n"
                            last_event_time = time.time()
                            rag_contexts = await perform_rag_retrieval(
                                agent,
                                chat_in.message,
                                await get_visible_conversation_messages(
                                    conversation.id, limit=AUTO_RAG_HISTORY_LIMIT
                                ),
                            )
                            if rag_contexts:
                                rag_contexts = aggregate_rag_contexts(rag_contexts)
                                yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                                last_event_time = time.time()
                            final_message = build_rag_prompt(
                                rag_contexts, chat_in.message
                            )

                    message_assets = await _resolve_message_assets(
                        attachments=[*chat_in.images, *chat_in.file_urls],
                        agent=agent,
                        user=current_user,
                        conversation_id=conversation.id,
                    )
                    round_id = uuid4()
                    user_branch_parent_id = await get_next_user_branch_parent_id(
                        conversation
                    )

                    # Save user message with images and file_urls.
                    async with _message_asset_transaction(bool(message_assets)):
                        user_msg = await Message.create(
                            conversation=conversation,
                            role=MessageRole.USER,
                            content=chat_in.message,
                            images=[img.model_dump() for img in chat_in.images]
                            if chat_in.images
                            else None,
                            file_urls=[f.model_dump() for f in chat_in.file_urls]
                            if chat_in.file_urls
                            else None,
                            rag_context=rag_contexts if rag_contexts else None,
                            branch_parent_id=user_branch_parent_id,
                            round_id=round_id,
                            round_index=0,
                            round_role=MessageRoundRole.USER_INPUT,
                            is_round_canonical=True,
                        )
                        await _attach_message_assets(
                            message_id=user_msg.id,
                            assets=message_assets,
                        )
                    final_message = await _append_asset_manifest(
                        final_message,
                        conversation_id=conversation.id,
                        agent=agent,
                        user=current_user,
                    )

                    # Create placeholder for assistant message
                    assistant_msg = await Message.create(
                        conversation=conversation,
                        role=MessageRole.ASSISTANT,
                        content="",  # Will be updated
                        branch_parent_id=user_msg.id,
                        round_id=round_id,
                        round_index=0,
                        round_role=MessageRoundRole.ASSISTANT_FINAL,
                        is_round_canonical=True,
                    )
                    message_id = str(assistant_msg.id)

                    # Send message_start event
                    yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': message_id, 'user_message_id': str(user_msg.id)})}\n\n"
                    last_event_time = time.time()

                    (
                        file_content_str,
                        updated_file_urls,
                    ) = await build_file_content_for_context(
                        agent=agent,
                        file_urls=chat_in.file_urls,
                        legacy_files=chat_in.files,
                        user_locale=current_user.locale,
                        tool_timeouts=tool_timeouts,
                        user=current_user,
                    )
                    if (
                        updated_file_urls is not None
                        and user_msg.file_urls != updated_file_urls
                    ):
                        user_msg.file_urls = updated_file_urls
                        await user_msg.save(update_fields=["file_urls"])

                    chat_model = await resolve_agent_chat_model(agent)
                    model_id = chat_model.model_id
                    model_context_limit = chat_model.context_length
                    model_max_output_tokens = chat_model.max_output_tokens
                    model_provider = chat_model.provider
                    tokenizer_model_id = chat_model.tokenizer_model_id
                    model_used = model_id
                    model_supports_vision = bool(
                        chat_in.images
                        and agent.enable_attachments
                        and chat_model.supports_vision
                    )
                    working_history_override = (
                        [
                            message.model_dump(exclude_none=True)
                            for message in chat_in.history_override
                        ]
                        if chat_in.history_override
                        else None
                    )
                    image_pool, image_inventory = collect_conversation_images(
                        await get_visible_conversation_messages(
                            conversation.id, limit=AUTO_RAG_HISTORY_LIMIT
                        ),
                        current_message_id=user_msg.id,
                        current_images=chat_in.images,
                    )
                    model_message = append_conversation_image_inventory(
                        final_message, image_inventory
                    )

                    # Get model identifier

                    # Get agent tools
                    tools_openai = await get_agent_tools(agent)
                    tool_display_names = await get_tool_display_names(
                        agent, current_user.locale
                    )
                    tools: list[ToolDefinition] | None = None
                    if tools_openai:
                        tools = [
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

                    from app.services.agent_loop import (
                        AgentLoop,
                        AgentLoopContext,
                        ContextTurn,
                    )

                    max_iterations = agent.max_iterations or 5

                    def sse_formatter(event_name: str, payload: dict) -> str | None:
                        """Build SSE strings and mirror deltas into generator
                        scope so error handlers keep seeing partial state."""
                        nonlocal full_content, full_reasoning, first_token_time
                        nonlocal last_event_time
                        if event_name == "heartbeat":
                            return ": heartbeat\n\n"
                        if event_name == "content_delta":
                            delta = payload.get("delta", "")
                            full_content += delta
                            if first_token_time is None:
                                first_token_time = time.time()
                            last_event_time = time.time()
                            return (
                                f"event: {SSEEventType.CONTENT_DELTA}\n"
                                f"data: {json.dumps({'delta': delta})}\n\n"
                            )
                        if event_name == "reasoning_start":
                            last_event_time = time.time()
                            return f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                        if event_name == "reasoning_delta":
                            delta = payload.get("delta", "")
                            full_reasoning += delta
                            if first_token_time is None:
                                first_token_time = time.time()
                            last_event_time = time.time()
                            return (
                                f"event: {SSEEventType.REASONING_DELTA}\n"
                                f"data: {json.dumps({'delta': delta})}\n\n"
                            )
                        if event_name == "reasoning_end":
                            return f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        if event_name == "tool_call":
                            return payload.get("sse")
                        if event_name == "tool_result":
                            return payload.get("sse")
                        if event_name == "media_result":
                            return payload.get("sse")
                        if event_name == "compression_start":
                            event_str = build_compression_start_event(
                                agent=agent,
                                stage=payload.get("stage", "macro"),
                                trigger=payload.get("trigger"),
                            )
                            if event_str:
                                last_event_time = time.time()
                            return event_str
                        if event_name == "compression_end":
                            _, end_str = build_compression_events(
                                agent=agent,
                                compression=payload.get("compression"),
                                trigger=payload.get("trigger"),
                            )
                            if end_str:
                                last_event_time = time.time()
                            return end_str
                        if event_name == "output_truncated":
                            return f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                        if event_name == "iteration_cap_reached":
                            return (
                                f"event: {SSEEventType.ITERATION_CAP_REACHED}\n"
                                f"data: {json.dumps({'content': payload.get('content', '')})}\n\n"
                            )
                        return None

                    async def build_turn(**kwargs):
                        plan = await build_context_plan(**kwargs)
                        return ContextTurn(
                            prepared=None,
                            will_summarize=plan.will_summarize,
                            compression=plan.compression,
                            plan=plan,
                        )

                    loop = AgentLoop(
                        AgentLoopContext(
                            agent=agent,
                            conversation=conversation,
                            user=current_user,
                            user_message=model_message,
                            model_id=model_id,
                            tokenizer_model_id=tokenizer_model_id,
                            model_provider=model_provider,
                            model_context_limit=model_context_limit,
                            model_max_output_tokens=model_max_output_tokens,
                            model_used=model_used,
                            model_supports_vision=model_supports_vision,
                            tools=tools,
                            tool_display_names=tool_display_names,
                            tool_timeouts=tool_timeouts,
                            global_timeout=global_timeout,
                            idle_timeout=idle_timeout,
                            heartbeat_interval=heartbeat_interval,
                            sandbox_session_id=sandbox_session_id,
                            file_content=file_content_str,
                            current_images=chat_in.images,
                            working_history_override=working_history_override,
                            image_pool=image_pool,
                            image_inventory=image_inventory,
                            append_generated_images=append_generated_images,
                            current_user_message_id=user_msg.id,
                            exclude_message_ids=[assistant_msg.id],
                            include_current_user_message=True,
                            round_id=round_id,
                            protected_round_id=round_id,
                            user_locale=current_user.locale,
                            max_iterations=max_iterations,
                            streaming=True,
                            build_turn=build_turn,
                            execute_tool_call=execute_tool_call,
                            count_tool_definition_tokens=count_tool_definition_tokens,
                            trigger_for_compression=get_compression_trigger,
                            team_chat_stream=model_manager.team_chat_stream,
                            team_chat=model_manager.team_chat,
                            record_stream_usage=model_manager.record_stream_usage,
                            calculate_usage=_calculate_model_usage,
                            send_heartbeat_if_needed=send_heartbeat_if_needed,
                            is_disconnected=request.is_disconnected,
                            request=request,
                            initial_last_event_time=last_event_time,
                            formatter=sse_formatter,
                            first_round_index=1,
                            cap_content=lambda: build_max_iterations_terminal_content(
                                current_user.locale
                            ),
                        )
                    )
                    async for sse_chunk in loop.run():
                        if sse_chunk:
                            yield sse_chunk
                            last_event_time = time.time()
                    loop_result = loop.result
                    max_iterations_reached = loop_result.max_iterations_reached
                    full_content = loop_result.full_content
                    full_reasoning = loop_result.full_reasoning
                    aggregate_input_tokens = loop_result.aggregate_input_tokens
                    aggregate_output_tokens = loop_result.aggregate_output_tokens
                    aggregate_cache_read_tokens = (
                        loop_result.aggregate_cache_read_tokens
                    )
                    aggregate_cache_creation_tokens = (
                        loop_result.aggregate_cache_creation_tokens
                    )
                    aggregate_total_input_tokens = (
                        loop_result.aggregate_total_input_tokens
                    )

                    if loop_result.manually_stopped:
                        # Client disconnected: persist the stopped assistant
                        # (partial content/reasoning) and end the round without
                        # finalizing the branch or emitting message_end.
                        assistant_msg.content = full_content
                        assistant_msg.reasoning_content = (
                            full_reasoning if full_reasoning else None
                        )
                        assistant_msg.model_used = model_used
                        assistant_msg.duration_ms = int(
                            (time.time() - start_time) * 1000
                        )
                        assistant_msg.first_token_ms = _first_token_ms(
                            start_time, first_token_time
                        )
                        assistant_msg.is_manually_stopped = True
                        assistant_msg.round_status = MessageRoundStatus.MANUALLY_STOPPED
                        assistant_msg.created_at = now_utc()
                        await assistant_msg.save()
                        return

                    duration_ms = int((time.time() - start_time) * 1000)
                    terminal_content = (
                        build_max_iterations_terminal_content(current_user.locale)
                        if max_iterations_reached
                        else full_content
                    )
                    terminal_round_status = get_round_terminal_status(
                        completed=not max_iterations_reached,
                        max_iterations_reached=max_iterations_reached,
                    )

                    # Update assistant message (final response, no tool_calls)
                    assistant_msg.content = terminal_content
                    assistant_msg.reasoning_content = (
                        None
                        if max_iterations_reached
                        else (full_reasoning if full_reasoning else None)
                    )
                    assistant_msg.model_used = model_used
                    assistant_msg.duration_ms = duration_ms
                    assistant_msg.first_token_ms = _first_token_ms(
                        start_time, first_token_time
                    )
                    assistant_msg.is_manually_stopped = False
                    assistant_msg.round_status = terminal_round_status
                    # Ensure assistant message appears after tool calls/results in history
                    assistant_msg.created_at = now_utc()
                    input_tokens = aggregate_input_tokens
                    output_tokens = aggregate_output_tokens
                    assistant_msg.token_usage = {
                        "prompt": input_tokens,
                        "completion": output_tokens,
                        "cache_read": aggregate_cache_read_tokens,
                        "cache_creation": aggregate_cache_creation_tokens,
                        "total_input": aggregate_total_input_tokens,
                    }
                    await assistant_msg.save()
                    branch_prefix = await get_prefix_path_before(user_msg)
                    await activate_conversation_branch(
                        conversation.id,
                        [*branch_prefix, user_msg, assistant_msg],
                    )

                    # Update conversation stats atomically
                    title_update = {}
                    if not conversation.title:
                        title_update["title"] = chat_in.message[:50] + (
                            "..." if len(chat_in.message) > 50 else ""
                        )

                    await Conversation.filter(id=conversation.id).update(
                        message_count=F("message_count") + 2,
                        token_usage=F("token_usage") + (input_tokens + output_tokens),
                        updated_at=now_utc(),
                        **title_update,
                    )

                    # Update agent stats atomically
                    await Agent.filter(id=agent.id).update(
                        message_count=F("message_count") + 2,
                        total_tokens=F("total_tokens") + (input_tokens + output_tokens),
                    )

                    # Update team stats atomically
                    await Team.filter(id=agent.team.id).update(
                        total_messages=F("total_messages") + 2,
                        total_tokens=F("total_tokens") + (input_tokens + output_tokens),
                    )

                    # Send message_end event with version info and timing
                    first_token_ms = assistant_msg.first_token_ms
                    tokens_per_second = (
                        round(output_tokens / (duration_ms / 1000), 1)
                        if duration_ms > 0 and output_tokens > 0
                        else None
                    )
                    yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens, 'cache_read_tokens': aggregate_cache_read_tokens, 'cache_creation_tokens': aggregate_cache_creation_tokens, 'total_input_tokens': aggregate_total_input_tokens}, 'timing': {'first_token_ms': first_token_ms, 'duration_ms': duration_ms, 'tokens_per_second': tokens_per_second}, 'version_number': 1, 'version_count': 1})}\n\n"

                except (QuotaExceededError, InsufficientQuotaError) as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.warning(
                        "Quota exceeded during stream: conversation=%s agent=%s error=%s",
                        conversation.id,
                        agent.id,
                        e,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except ModelNotFoundError as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.error(
                        "Model not found error during stream: conversation=%s agent=%s error=%s",
                        conversation.id,
                        agent.id,
                        e,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_NOT_FOUND, 'msg': t('model_not_found')})}\n\n"
                except AuthenticationError as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.error(
                        "Authentication error during stream: conversation=%s agent=%s error=%s",
                        conversation.id,
                        agent.id,
                        e,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNAUTHORIZED, 'msg': t('unauthorized')})}\n\n"
                except RateLimitError as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.warning(
                        "Rate limit error during stream: conversation=%s agent=%s error=%s",
                        conversation.id,
                        agent.id,
                        e,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('rate_limit_exceeded')})}\n\n"
                except LLMError as e:
                    logger.exception(
                        "LLM error during stream: conversation=%s agent=%s",
                        conversation.id,
                        agent.id,
                    )
                    error_message = _format_llm_error_message(e)
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=error_message,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': error_message})}\n\n"
                except StreamIdleTimeoutError:
                    logger.warning(
                        "Stream idle timeout (%ss) for conversation %s",
                        idle_timeout,
                        conversation.id,
                        extra={"timeout_type": "idle", "timeout_seconds": idle_timeout},
                    )
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t("stream_timeout_exceeded"),
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': idle_timeout})}\n\n"
                except BusinessError as e:
                    error_message = t(e.msg_key or GENERIC_STREAM_ERROR_KEY, **e.kwargs)
                    logger.warning(
                        "Business error during stream: conversation=%s agent=%s code=%s msg=%s",
                        conversation.id,
                        agent.id,
                        e.code,
                        error_message,
                    )
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=error_message,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': e.code, 'msg': error_message})}\n\n"

                except Exception:
                    logger.exception(
                        "Unexpected error during stream: conversation=%s agent=%s",
                        conversation.id,
                        agent.id,
                    )
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"

        except TimeoutError:
            # Global timeout
            logger.warning(
                "Stream global timeout (%ss) for conversation %s",
                global_timeout,
                conversation.id,
                extra={"timeout_type": "global", "timeout_seconds": global_timeout},
            )
            await persist_partial_round_error(
                assistant_msg,
                content=full_content,
                reasoning=full_reasoning,
                model_used=model_used,
                start_time=start_time,
                first_token_time=first_token_time,
                fallback_content=t("stream_timeout_exceeded"),
            )
            # Send timeout error event
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': global_timeout})}\n\n"
        except asyncio.CancelledError:
            logger.info(
                "Stream cancelled for conversation %s; persisting stopped assistant state",
                conversation.id,
            )
            if assistant_msg:
                assistant_msg.content = full_content
                assistant_msg.reasoning_content = full_reasoning or None
                assistant_msg.model_used = model_used
                assistant_msg.duration_ms = int((time.time() - start_time) * 1000)
                assistant_msg.first_token_ms = _first_token_ms(
                    start_time, first_token_time
                )
                assistant_msg.is_manually_stopped = True
                assistant_msg.round_status = MessageRoundStatus.MANUALLY_STOPPED
                assistant_msg.created_at = now_utc()
                if (
                    assistant_msg.content
                    or assistant_msg.reasoning_content
                    or assistant_msg.tool_calls
                ):
                    await assistant_msg.save()
                else:
                    await assistant_msg.delete()
            return
        except Exception as exc:
            logger.error(
                "Unhandled stream error: conversation=%s agent=%s exc=%s",
                conversation.id,
                agent.id,
                type(exc).__name__,
                exc_info=True,
            )
            if assistant_msg:
                await persist_partial_round_error(
                    assistant_msg,
                    content=full_content,
                    reasoning=full_reasoning,
                    model_used=model_used,
                    start_time=start_time,
                    first_token_time=first_token_time,
                    fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                )
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"
            return

        finally:
            # Resource cleanup and logging
            duration = time.time() - start_time
            logger.info(
                f"Stream ended for conversation {conversation.id}, "
                f"duration={duration:.2f}s"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ Message Version Endpoints ============


async def get_message_versions(message: Message) -> list[MessageVersion]:
    """Get all versions of a message (including itself if it's the root)."""
    # Determine the root message ID
    root_id = message.parent_id or message.id

    # Get all messages in this version group
    versions = await Message.filter(id=root_id).all()

    # Tool steps can share the root parent_id but are not message versions.
    child_versions = (
        await Message.filter(parent_id=root_id)
        .filter(Q(round_id__isnull=True) | Q(is_round_canonical=True))
        .all()
    )

    all_versions = versions + child_versions
    all_versions.sort(key=lambda m: m.version_number)

    return [
        MessageVersion(
            id=v.id,
            version_number=v.version_number,
            is_active=v.is_active,
            content=v.content,
            created_at=v.created_at,
        )
        for v in all_versions
    ]


async def get_version_count(message: Message) -> int:
    """Get total version count for a message group."""
    root_id = message.parent_id or message.id
    count = (
        await Message.filter(parent_id=root_id)
        .filter(Q(round_id__isnull=True) | Q(is_round_canonical=True))
        .count()
    )
    return count + 1  # +1 for the root message itself


async def build_message_out_with_versions(
    message: Message, include_versions: bool = False
) -> MessageOut:
    """Build MessageOut with version info."""
    version_count = await get_version_count(message)
    versions = None
    if include_versions:
        versions = await get_message_versions(message)

    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role.value,
        content=message.content,
        tool_calls=message.tool_calls,
        tool_call_id=message.tool_call_id,
        tool_name=message.tool_name,
        reasoning_content=message.reasoning_content,
        model_used=message.model_used,
        token_usage=message.token_usage,
        duration_ms=message.duration_ms,
        first_token_ms=message.first_token_ms,
        is_manually_stopped=message.is_manually_stopped,
        rag_context=message.rag_context,
        created_at=message.created_at,
        round_id=message.round_id,
        round_index=message.round_index,
        round_role=message.round_role.value if message.round_role else None,
        is_round_canonical=message.is_round_canonical,
        iteration_index=message.iteration_index,
        round_status=message.round_status.value if message.round_status else None,
        parent_id=message.parent_id,
        is_active=message.is_active,
        version_number=message.version_number,
        version_count=version_count,
        versions=versions,
    )


@router.get(
    "/{agent_id}/messages/{message_id}/versions",
    response_model=Response[list[MessageVersion]],
)
async def get_message_version_list(
    agent_id: UUID,
    message_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get all versions of a message."""
    message = (
        await Message.filter(id=message_id).prefetch_related("conversation").first()
    )
    if not message:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="message_not_found",
            status_code=404,
        )

    # Check access - user must own the conversation
    conversation = await Conversation.filter(
        id=message.conversation_id, user=current_user
    ).first()
    if not conversation:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )

    versions = await get_message_versions(message)
    return success(data=versions)


@router.post(
    "/{agent_id}/messages/{message_id}/switch-version",
    response_model=Response[MessageOut],
)
async def switch_message_version(
    agent_id: UUID,
    message_id: UUID,
    request: SwitchVersionRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Switch to a different version of a message.

    This deactivates all other versions and activates the specified one.
    Also deactivates all messages that came AFTER this message in the conversation
    (since they were based on the old version).
    """
    # Get the current message
    message = await Message.filter(id=message_id).first()
    if not message:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="message_not_found",
            status_code=404,
        )

    # Check access
    conversation = await Conversation.filter(
        id=message.conversation_id, user=current_user
    ).first()
    if not conversation:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )

    # Get the target version
    target_version = await Message.filter(id=request.version_id).first()
    if not target_version:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="version_not_found",
            status_code=404,
        )

    # Verify target version belongs to the same version group
    root_id = get_version_root_id(message)
    target_root_id = get_version_root_id(target_version)
    if root_id != target_root_id:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="version_not_in_group",
            status_code=400,
        )

    # The prefix must come from the version-group ROOT (the message this
    # version replaces), not from the target version itself: a target's branch
    # chain can be polluted with the sibling version's subtree (the old reply
    # and the replaced user message), which would otherwise be reactivated
    # alongside the switched version.
    root_message = (
        target_version
        if target_version.id == root_id
        else await Message.filter(id=root_id).first()
    )
    prefix = await get_prefix_path_before(root_message)
    descendant_branch = await find_descendant_branch_from(target_version)
    await activate_conversation_branch(
        message.conversation_id,
        [*prefix, *descendant_branch],
    )

    return success(
        data=await build_message_out_with_versions(
            target_version, include_versions=True
        )
    )


@router.post("/{agent_id}/messages/{message_id}/edit/stream")
async def edit_user_message_stream(
    agent_id: UUID,
    message_id: UUID,
    edit_request: EditMessageRequest,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """Edit a user message by creating a new version and regenerating its reply."""
    message = await Message.filter(id=message_id).first()
    if not message:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="message_not_found",
            status_code=404,
        )

    if message.role != MessageRole.USER:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="can_only_edit_user_message",
            status_code=400,
        )

    edited_content = edit_request.content.strip()
    if not edited_content:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="message_content_required",
            status_code=400,
        )
    if edited_content == message.content.strip():
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="message_content_unchanged",
            status_code=400,
        )

    conversation = await Conversation.filter(
        id=message.conversation_id,
        agent_id=agent_id,
        user=current_user,
    ).first()
    if not conversation:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )

    agent = await Agent.filter(id=agent_id).prefetch_related("team").first()
    if not agent:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    original_prefix = await get_prefix_path_before(message, trimmed=False)
    original_descendant_branch = await find_descendant_branch_from(message)

    async def event_generator():
        start_time = time.time()
        first_token_time: float | None = None
        last_event_time = start_time
        full_content = ""
        full_reasoning = ""
        edited_user_msg: Message | None = None
        assistant_msg: Message | None = None
        assistant_msg_id: str | None = None
        model_id: str | None = None
        model_used: str | None = None
        global_timeout: float = 1800.0
        idle_timeout: float = 300.0

        async def _lock_conversation(conn) -> None:
            await (
                Conversation.filter(id=conversation.id)
                .using_db(conn)
                .select_for_update()
                .first()
            )

        async def restore_original_path() -> None:
            if not edited_user_msg:
                return
            async with in_transaction() as conn:
                await _lock_conversation(conn)
                edited_is_active = await (
                    Message.filter(id=edited_user_msg.id, is_active=True)
                    .using_db(conn)
                    .exists()
                )
                if not edited_is_active:
                    return
                await activate_conversation_branch(
                    conversation.id,
                    [*original_prefix, *original_descendant_branch],
                    using_db=conn,
                )

        async def activate_edited_path() -> None:
            if not edited_user_msg:
                return
            prefix = await get_prefix_path_before(edited_user_msg)
            path = [*prefix, edited_user_msg]
            if assistant_msg:
                path.append(assistant_msg)
            async with in_transaction() as conn:
                await _lock_conversation(conn)
                edited_is_active = await (
                    Message.filter(id=edited_user_msg.id, is_active=True)
                    .using_db(conn)
                    .exists()
                )
                if not edited_is_active:
                    return
                await activate_conversation_branch(conversation.id, path, using_db=conn)

        try:
            from app.llm import model_manager
            from app.llm.errors import QuotaExceededError, LLMError
            from app.llm.types import ToolDefinition, FunctionDefinition
            from app.models.agent import RAGMode
            import asyncio

            streaming_config = get_streaming_config(agent)
            global_timeout = streaming_config["global_timeout"]
            heartbeat_interval = streaming_config["heartbeat_interval"]
            tool_timeouts = streaming_config["tool_timeouts"]
            idle_timeout = streaming_config["idle_timeout"]

            from app.services.sandbox.gateway import sandbox_gateway

            sandbox_session_id = await sandbox_gateway.create_session(
                agent_id=str(agent.id),
                team_id=str(agent.team_id) if agent.team_id else None,
                user_id=str(current_user.id),
                conversation_id=str(conversation.id),
            )

            async with asyncio.timeout(global_timeout):
                try:
                    root_id = get_version_root_id(message)
                    branch_parent_id = message.branch_parent_id
                    if branch_parent_id is None:
                        prefix = await get_prefix_path_before(message)
                        branch_parent_id = prefix[-1].id if prefix else None

                    rag_contexts: list[dict] = []
                    final_message = edited_content
                    if agent.rag_mode == RAGMode.AUTO:
                        has_knowledge_bases = await AgentKnowledgeBase.exists(
                            agent_id=agent.id
                        )
                        if has_knowledge_bases:
                            yield f"event: {SSEEventType.RAG_START}\ndata: {json.dumps({})}\n\n"
                            last_event_time = time.time()
                            rag_contexts = await perform_rag_retrieval(
                                agent,
                                edited_content,
                                await get_prefix_path_before(
                                    message,
                                    limit=AUTO_RAG_HISTORY_LIMIT,
                                    trimmed=False,
                                ),
                            )
                            if rag_contexts:
                                rag_contexts = aggregate_rag_contexts(rag_contexts)
                                yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                                last_event_time = time.time()
                            final_message = build_rag_prompt(
                                rag_contexts, edited_content
                            )

                    final_message = await _append_asset_manifest(
                        final_message,
                        conversation_id=conversation.id,
                        agent=agent,
                        user=current_user,
                    )

                    round_id = uuid4()
                    async with in_transaction() as conn:
                        await _lock_conversation(conn)
                        await (
                            Message.filter(Q(id=root_id) | Q(parent_id=root_id))
                            .using_db(conn)
                            .select_for_update()
                            .all()
                        )
                        current_version_count = await (
                            Message.filter(Q(id=root_id) | Q(parent_id=root_id))
                            .filter(
                                Q(round_id__isnull=True) | Q(is_round_canonical=True)
                            )
                            .using_db(conn)
                            .count()
                        )
                        new_user_version_number = current_version_count + 1
                        edited_user_msg = await Message.create(
                            conversation=conversation,
                            role=MessageRole.USER,
                            content=edited_content,
                            parent_id=root_id,
                            is_active=True,
                            version_number=new_user_version_number,
                            branch_parent_id=branch_parent_id,
                            images=message.images,
                            file_urls=message.file_urls,
                            rag_context=rag_contexts if rag_contexts else None,
                            round_id=round_id,
                            round_index=0,
                            round_role=MessageRoundRole.USER_INPUT,
                            is_round_canonical=True,
                            using_db=conn,
                        )
                        await activate_conversation_branch(
                            conversation.id,
                            [*original_prefix, edited_user_msg],
                            using_db=conn,
                        )

                    if MessageAsset._meta.default_connection is not None:
                        await asset_service.copy_message_attachments(
                            source_message_id=message.id,
                            target_message_id=edited_user_msg.id,
                        )

                    assistant_msg = await Message.create(
                        conversation=conversation,
                        role=MessageRole.ASSISTANT,
                        content="",
                        branch_parent_id=edited_user_msg.id,
                        round_id=round_id,
                        round_index=1,
                        round_role=MessageRoundRole.ASSISTANT_FINAL,
                        is_round_canonical=True,
                    )
                    assistant_msg_id = str(assistant_msg.id)
                    image_pool, image_inventory = collect_conversation_images(
                        [*original_prefix, edited_user_msg],
                    )
                    model_message = append_conversation_image_inventory(
                        final_message, image_inventory
                    )

                    yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': assistant_msg_id, 'edited_message_id': str(edited_user_msg.id), 'edited_version_number': new_user_version_number, 'edited_version_count': new_user_version_number, 'edited_parent_id': str(root_id)})}\n\n"
                    last_event_time = time.time()

                    chat_model = await resolve_agent_chat_model(agent)
                    model_id = chat_model.model_id
                    model_context_limit = chat_model.context_length
                    model_max_output_tokens = chat_model.max_output_tokens
                    model_provider = chat_model.provider
                    tokenizer_model_id = chat_model.tokenizer_model_id
                    model_used = model_id
                    tools_openai = await get_agent_tools(agent)
                    tool_display_names = await get_tool_display_names(
                        agent, current_user.locale
                    )
                    tools: list[ToolDefinition] | None = None
                    if tools_openai:
                        tools = [
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

                    from app.services.agent_loop import (
                        AgentLoop,
                        AgentLoopContext,
                        ContextTurn,
                    )

                    max_iterations = agent.max_iterations or 5

                    max_iterations_reached = False
                    working_history_override: list[dict[str, Any]] | None = None
                    aggregate_input_tokens = 0
                    aggregate_output_tokens = 0
                    aggregate_cache_read_tokens = 0
                    aggregate_cache_creation_tokens = 0
                    aggregate_total_input_tokens = 0
                    created_message_count = 2

                    def sse_formatter(event_name: str, payload: dict) -> str | None:
                        """Build SSE strings and mirror deltas into generator
                        scope so error handlers keep seeing partial state."""
                        nonlocal full_content, full_reasoning, first_token_time
                        nonlocal last_event_time
                        if event_name == "heartbeat":
                            return ": heartbeat\n\n"
                        if event_name == "content_delta":
                            delta = payload.get("delta", "")
                            full_content += delta
                            if first_token_time is None:
                                first_token_time = time.time()
                            last_event_time = time.time()
                            return (
                                f"event: {SSEEventType.CONTENT_DELTA}\n"
                                f"data: {json.dumps({'delta': delta})}\n\n"
                            )
                        if event_name == "reasoning_start":
                            last_event_time = time.time()
                            return f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                        if event_name == "reasoning_delta":
                            delta = payload.get("delta", "")
                            full_reasoning += delta
                            if first_token_time is None:
                                first_token_time = time.time()
                            last_event_time = time.time()
                            return (
                                f"event: {SSEEventType.REASONING_DELTA}\n"
                                f"data: {json.dumps({'delta': delta})}\n\n"
                            )
                        if event_name == "reasoning_end":
                            return f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        if event_name == "tool_call":
                            return payload.get("sse")
                        if event_name == "tool_result":
                            return payload.get("sse")
                        if event_name == "media_result":
                            return payload.get("sse")
                        if event_name == "compression_start":
                            event_str = build_compression_start_event(
                                agent=agent,
                                stage=payload.get("stage", "macro"),
                                trigger=payload.get("trigger"),
                            )
                            if event_str:
                                last_event_time = time.time()
                            return event_str
                        if event_name == "compression_end":
                            _, end_str = build_compression_events(
                                agent=agent,
                                compression=payload.get("compression"),
                                trigger=payload.get("trigger"),
                            )
                            if end_str:
                                last_event_time = time.time()
                            return end_str
                        if event_name == "output_truncated":
                            return f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                        if event_name == "iteration_cap_reached":
                            return (
                                f"event: {SSEEventType.ITERATION_CAP_REACHED}\n"
                                f"data: {json.dumps({'content': payload.get('content', '')})}\n\n"
                            )
                        return None

                    async def build_turn(**kwargs):
                        plan = await build_context_plan(**kwargs)
                        return ContextTurn(
                            prepared=None,
                            will_summarize=plan.will_summarize,
                            compression=plan.compression,
                            plan=plan,
                        )

                    loop = AgentLoop(
                        AgentLoopContext(
                            agent=agent,
                            conversation=conversation,
                            user=current_user,
                            user_message=model_message,
                            model_id=model_id,
                            tokenizer_model_id=tokenizer_model_id,
                            model_provider=model_provider,
                            model_context_limit=model_context_limit,
                            model_max_output_tokens=model_max_output_tokens,
                            model_used=model_used,
                            model_supports_vision=False,
                            tools=tools,
                            tool_display_names=tool_display_names,
                            tool_timeouts=tool_timeouts,
                            global_timeout=global_timeout,
                            idle_timeout=idle_timeout,
                            heartbeat_interval=heartbeat_interval,
                            sandbox_session_id=sandbox_session_id,
                            file_content=None,
                            current_images=None,
                            working_history_override=working_history_override,
                            image_pool=image_pool,
                            image_inventory=image_inventory,
                            append_generated_images=append_generated_images,
                            current_user_message_id=edited_user_msg.id,
                            exclude_message_ids=[assistant_msg.id],
                            include_current_user_message=True,
                            round_id=round_id,
                            protected_round_id=round_id,
                            user_locale=current_user.locale,
                            max_iterations=max_iterations,
                            streaming=True,
                            build_turn=build_turn,
                            execute_tool_call=execute_tool_call,
                            count_tool_definition_tokens=count_tool_definition_tokens,
                            trigger_for_compression=get_compression_trigger,
                            team_chat_stream=model_manager.team_chat_stream,
                            team_chat=model_manager.team_chat,
                            record_stream_usage=model_manager.record_stream_usage,
                            calculate_usage=_calculate_model_usage,
                            send_heartbeat_if_needed=send_heartbeat_if_needed,
                            is_disconnected=request.is_disconnected,
                            request=request,
                            initial_last_event_time=last_event_time,
                            formatter=sse_formatter,
                            persist_step_per_tool=True,
                            step_branch_parent_id=assistant_msg.id,
                            first_round_index=2,
                            created_message_count=2,
                            cap_content=lambda: build_max_iterations_terminal_content(
                                current_user.locale
                            ),
                        )
                    )
                    async for sse_chunk in loop.run():
                        if sse_chunk:
                            yield sse_chunk
                            last_event_time = time.time()
                    loop_result = loop.result
                    max_iterations_reached = loop_result.max_iterations_reached
                    full_content = loop_result.full_content
                    full_reasoning = loop_result.full_reasoning
                    aggregate_input_tokens = loop_result.aggregate_input_tokens
                    aggregate_output_tokens = loop_result.aggregate_output_tokens
                    aggregate_cache_read_tokens = (
                        loop_result.aggregate_cache_read_tokens
                    )
                    aggregate_cache_creation_tokens = (
                        loop_result.aggregate_cache_creation_tokens
                    )
                    aggregate_total_input_tokens = (
                        loop_result.aggregate_total_input_tokens
                    )
                    created_message_count = loop_result.created_message_count

                    if loop_result.manually_stopped:
                        assistant_msg.content = full_content
                        assistant_msg.reasoning_content = full_reasoning or None
                        assistant_msg.model_used = model_used
                        assistant_msg.duration_ms = int(
                            (time.time() - start_time) * 1000
                        )
                        assistant_msg.first_token_ms = _first_token_ms(
                            start_time, first_token_time
                        )
                        assistant_msg.is_manually_stopped = True
                        assistant_msg.round_status = MessageRoundStatus.MANUALLY_STOPPED
                        assistant_msg.created_at = now_utc()
                        await assistant_msg.save()
                        await activate_edited_path()
                        return

                    duration_ms = int((time.time() - start_time) * 1000)
                    terminal_content = (
                        build_max_iterations_terminal_content(current_user.locale)
                        if max_iterations_reached
                        else full_content
                    )
                    terminal_round_status = get_round_terminal_status(
                        completed=not max_iterations_reached,
                        max_iterations_reached=max_iterations_reached,
                    )
                    assistant_msg.content = terminal_content
                    assistant_msg.reasoning_content = (
                        None
                        if max_iterations_reached
                        else (full_reasoning if full_reasoning else None)
                    )
                    assistant_msg.model_used = model_used
                    assistant_msg.duration_ms = duration_ms
                    assistant_msg.first_token_ms = _first_token_ms(
                        start_time, first_token_time
                    )
                    assistant_msg.is_manually_stopped = False
                    assistant_msg.round_status = terminal_round_status
                    assistant_msg.created_at = now_utc()
                    input_tokens = aggregate_input_tokens
                    output_tokens = aggregate_output_tokens
                    assistant_msg.token_usage = {
                        "prompt": input_tokens,
                        "completion": output_tokens,
                        "cache_read": aggregate_cache_read_tokens,
                        "cache_creation": aggregate_cache_creation_tokens,
                        "total_input": aggregate_total_input_tokens,
                    }
                    await assistant_msg.save()
                    await activate_edited_path()
                    total_tokens = input_tokens + output_tokens
                    await Agent.filter(id=agent.id).update(
                        message_count=F("message_count") + created_message_count,
                        total_tokens=F("total_tokens") + total_tokens,
                    )
                    if agent.team_id:
                        await Team.filter(id=agent.team_id).update(
                            total_messages=F("total_messages") + created_message_count,
                            total_tokens=F("total_tokens") + total_tokens,
                        )
                    await Conversation.filter(id=conversation.id).update(
                        message_count=F("message_count") + created_message_count,
                        token_usage=F("token_usage") + total_tokens,
                        updated_at=now_utc(),
                    )
                    tokens_per_second = (
                        round(output_tokens / (duration_ms / 1000), 1)
                        if duration_ms > 0 and output_tokens > 0
                        else None
                    )
                    try:
                        await AuditLogService.log(
                            user=current_user,
                            action="edit_message",
                            resource_type="message",
                            resource_id=edited_user_msg.id,
                            resource_name=str(conversation.id),
                            operation="update",
                            status="success",
                            request=request,
                            changes={
                                "before": _message_content_audit_preview(
                                    message.content
                                ),
                                "after": _message_content_audit_preview(edited_content),
                            },
                            metadata={
                                "agent_id": str(agent.id),
                                "conversation_id": str(conversation.id),
                                "original_message_id": str(message.id),
                                "new_message_id": str(edited_user_msg.id),
                                "version_number": new_user_version_number,
                            },
                        )
                    except Exception:
                        logger.exception("Failed to write message edit audit log")
                    yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': total_tokens, 'cache_read_tokens': aggregate_cache_read_tokens, 'cache_creation_tokens': aggregate_cache_creation_tokens, 'total_input_tokens': aggregate_total_input_tokens}, 'timing': {'first_token_ms': assistant_msg.first_token_ms, 'duration_ms': duration_ms, 'tokens_per_second': tokens_per_second}, 'edited_version_number': new_user_version_number, 'edited_version_count': new_user_version_number})}\n\n"
                except (QuotaExceededError, InsufficientQuotaError) as e:
                    logger.warning(
                        "Quota exceeded during message edit: conversation=%s agent=%s error=%s",
                        conversation.id,
                        agent.id,
                        e,
                    )
                    preserved_partial = await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    if preserved_partial:
                        await activate_edited_path()
                    else:
                        if assistant_msg_id:
                            await Message.filter(id=assistant_msg_id).delete()
                        if edited_user_msg:
                            await Message.filter(id=edited_user_msg.id).update(
                                is_active=False
                            )
                        await restore_original_path()
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except LLMError as e:
                    error_message = _format_llm_error_message(e)
                    preserved_partial = await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=error_message,
                    )
                    if preserved_partial:
                        await activate_edited_path()
                    else:
                        if assistant_msg_id:
                            await Message.filter(id=assistant_msg_id).delete()
                        if edited_user_msg:
                            await Message.filter(id=edited_user_msg.id).update(
                                is_active=False
                            )
                        await restore_original_path()
                    logger.exception(
                        "LLM error during message edit: conversation=%s agent=%s",
                        conversation.id,
                        agent.id,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': error_message})}\n\n"
                except StreamIdleTimeoutError:
                    logger.warning(
                        "Message edit stream idle timeout (%ss) for conversation %s agent=%s",
                        idle_timeout,
                        conversation.id,
                        agent.id,
                        extra={"timeout_type": "idle", "timeout_seconds": idle_timeout},
                    )
                    preserved_partial = await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t("stream_timeout_exceeded"),
                    )
                    if preserved_partial:
                        await activate_edited_path()
                    else:
                        if assistant_msg_id:
                            await Message.filter(id=assistant_msg_id).delete()
                        if edited_user_msg:
                            await Message.filter(id=edited_user_msg.id).update(
                                is_active=False
                            )
                        await restore_original_path()
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': idle_timeout})}\n\n"
        except TimeoutError:
            preserved_partial = await persist_partial_round_error(
                assistant_msg,
                content=full_content,
                reasoning=full_reasoning,
                model_used=model_used,
                start_time=start_time,
                first_token_time=first_token_time,
                fallback_content=t("stream_timeout_exceeded"),
            )
            if preserved_partial:
                await activate_edited_path()
            else:
                if assistant_msg_id:
                    await Message.filter(id=assistant_msg_id).delete()
                if edited_user_msg:
                    await Message.filter(id=edited_user_msg.id).update(is_active=False)
                await restore_original_path()
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': global_timeout})}\n\n"
        except asyncio.CancelledError:
            if assistant_msg:
                assistant_msg.content = full_content
                assistant_msg.reasoning_content = full_reasoning or None
                assistant_msg.model_used = model_used
                assistant_msg.duration_ms = int((time.time() - start_time) * 1000)
                assistant_msg.first_token_ms = _first_token_ms(
                    start_time, first_token_time
                )
                assistant_msg.is_manually_stopped = True
                assistant_msg.round_status = MessageRoundStatus.MANUALLY_STOPPED
                assistant_msg.created_at = now_utc()
                if assistant_msg.content or assistant_msg.reasoning_content:
                    await assistant_msg.save()
                    await activate_edited_path()
                else:
                    await Message.filter(id=assistant_msg.id).delete()
                    if edited_user_msg:
                        await Message.filter(id=edited_user_msg.id).update(
                            is_active=False
                        )
                    await restore_original_path()
            return
        except BusinessError as e:
            error_message = t(e.msg_key or GENERIC_STREAM_ERROR_KEY, **e.kwargs)
            logger.warning(
                "Business error during message edit: conversation=%s agent=%s code=%s msg=%s",
                conversation.id,
                agent.id,
                e.code,
                error_message,
            )
            preserved_partial = await persist_partial_round_error(
                assistant_msg,
                content=full_content,
                reasoning=full_reasoning,
                model_used=model_used,
                start_time=start_time,
                first_token_time=first_token_time,
                fallback_content=error_message,
            )
            if preserved_partial:
                await activate_edited_path()
            else:
                if assistant_msg_id:
                    await Message.filter(id=assistant_msg_id).delete()
                if edited_user_msg:
                    await Message.filter(id=edited_user_msg.id).update(is_active=False)
                await restore_original_path()
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': e.code, 'msg': error_message})}\n\n"

        except Exception:
            logger.exception(
                "Unexpected error during message edit: conversation=%s agent=%s",
                conversation.id,
                agent.id,
            )
            preserved_partial = await persist_partial_round_error(
                assistant_msg,
                content=full_content,
                reasoning=full_reasoning,
                model_used=model_used,
                start_time=start_time,
                first_token_time=first_token_time,
                fallback_content=t(GENERIC_STREAM_ERROR_KEY),
            )
            if preserved_partial:
                await activate_edited_path()
            else:
                if assistant_msg_id:
                    await Message.filter(id=assistant_msg_id).delete()
                if edited_user_msg:
                    await Message.filter(id=edited_user_msg.id).update(is_active=False)
                await restore_original_path()
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"
            return
        finally:
            duration = time.time() - start_time
            logger.info(
                "Message edit stream ended for conversation %s, duration=%.2fs",
                conversation.id,
                duration,
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ AgentRun Endpoints ============


@router.get(
    "/{agent_id}/chat/runs/{run_id}",
    response_model=Response[RunOut],
)
async def get_run_status(
    agent_id: UUID,
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get durable run status; owner-scoped."""
    run = await _load_owned_run(agent_id, run_id, current_user)
    return success(data=_run_to_out(run))


@router.get(
    "/{agent_id}/chat/runs/{run_id}/events",
    response_model=Response[list[RunEventOut]],
)
async def get_run_events(
    agent_id: UUID,
    run_id: UUID,
    after_sequence: int = 0,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Replay buffered run events after ``after_sequence`` (authorized scope)."""
    await _load_owned_run(agent_id, run_id, current_user)
    from app.services.agent_run_stream import AgentRunStream

    stream = AgentRunStream(run_id)
    events = await stream.get_all_events()
    filtered = [e for e in events if e.get("sequence", 0) > after_sequence]
    return success(data=[RunEventOut(**e) for e in filtered])


@router.post(
    "/{agent_id}/chat/runs/{run_id}/inputs",
    response_model=Response[RunOut],
)
async def post_run_input(
    agent_id: UUID,
    run_id: UUID,
    body: RunInputCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Queue steering / follow-up / stop for a running agent."""
    run = await _load_owned_run(agent_id, run_id, current_user)
    from app.models.agent_run import AgentRunInputKind

    kind = {
        "steer": AgentRunInputKind.STEER,
        "follow_up": AgentRunInputKind.FOLLOW_UP,
        "stop": AgentRunInputKind.STOP,
    }.get(body.delivery, AgentRunInputKind.STEER)
    from app.services.agent_run_store import enqueue_input

    await enqueue_input(
        run_id=run_id,
        kind=kind,
        content=body.content,
        attachment_meta={"attachments": body.attachments},
        request_id=body.request_id,
    )
    return success(data=_run_to_out(run))


@router.post(
    "/{agent_id}/chat/runs/{run_id}/stop",
    response_model=Response[RunOut],
)
async def stop_run(
    agent_id: UUID,
    run_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Cooperative stop: persist ``stopping`` and wake the worker."""
    run = await _load_owned_run(agent_id, run_id, current_user)
    from app.models.agent_run import (
        AgentRunInputKind,
        AgentRunStatus,
    )
    from app.services.agent_run_store import enqueue_input, transition_run

    if run.status not in (
        AgentRunStatus.RUNNING,
        AgentRunStatus.STOPPING,
        AgentRunStatus.QUEUED,
    ):
        # terminal: idempotent no-op
        return success(data=_run_to_out(run))
    if run.status != AgentRunStatus.STOPPING:
        await transition_run(run, AgentRunStatus.STOPPING)
    await enqueue_input(run_id=run_id, kind=AgentRunInputKind.STOP)
    return success(data=_run_to_out(run))


async def _load_owned_run(
    agent_id: UUID,
    run_id: UUID,
    current_user: User,
) -> _AgentRunModel:
    """Owner/agent scoped run lookup used by all run endpoints."""
    from app.models.agent_run import AgentRun
    from app.models.agent import Conversation as _Conv

    run = await AgentRun.get_or_none(id=run_id, agent_id=agent_id)
    if not run:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="run_not_found",
            status_code=404,
        )
    conversation = await _Conv.get_or_none(id=run.conversation_id, user=current_user)
    if not conversation:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )
    return run


def _run_to_out(run: _AgentRunModel) -> RunOut:
    return RunOut(
        id=run.id,
        agent_id=run.agent_id,
        conversation_id=run.conversation_id,
        mode=run.mode.value if hasattr(run.mode, "value") else str(run.mode),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        source_message_id=run.source_message_id,
        canonical_message_id=run.canonical_message_id,
        active_round_id=run.active_round_id,
        error_code=run.error_code,
        error_message=run.error_message,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
    )


@router.post("/{agent_id}/messages/{message_id}/regenerate")
async def regenerate_message(
    agent_id: UUID,
    message_id: UUID,
    regen_request: RegenerateRequest,
    request: Request,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """
    Regenerate an assistant message (create a new version).

    This creates a new version of the message and streams the response.
    The new version becomes active, and the old version is deactivated.
    """
    # Get the message to regenerate
    message = await Message.filter(id=message_id).first()
    if not message:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="message_not_found",
            status_code=404,
        )

    if message.role != MessageRole.ASSISTANT:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="can_only_regenerate_assistant",
            status_code=400,
        )

    # Get conversation and verify access
    conversation = await Conversation.filter(
        id=message.conversation_id, user=current_user
    ).first()
    if not conversation:
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="access_denied",
            status_code=403,
        )

    # Get the agent
    agent = (
        await Agent.filter(id=conversation.agent_id).prefetch_related("team").first()
    )
    if not agent:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="agent_not_found",
            status_code=404,
        )

    prefix_for_message = await get_prefix_path_before(message, trimmed=False)
    user_message = next(
        (
            item
            for item in reversed(prefix_for_message)
            if item.role == MessageRole.USER
        ),
        None,
    )

    if not user_message:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="no_user_message_found",
            status_code=400,
        )

    async def event_generator():
        start_time = time.time()
        first_token_time: float | None = None
        last_event_time = start_time
        full_content = ""
        full_reasoning = ""
        new_message_id = None
        new_message: Message | None = None
        in_place_retry = False
        model_id: str | None = None
        model_used: str | None = None
        global_timeout: float = 1800.0  # Default 30 minutes
        idle_timeout: float = 300.0  # Default 5 minutes

        try:
            from app.llm import model_manager
            from app.llm.errors import QuotaExceededError, LLMError
            from app.llm.types import (
                ToolDefinition,
                FunctionDefinition,
            )

            async def activate_regenerated_path() -> None:
                if not new_message:
                    return
                prefix = await get_prefix_path_before(new_message)
                await activate_conversation_branch(
                    conversation.id,
                    [*prefix, new_message],
                )

            async def restore_original_path() -> None:
                prefix = await get_prefix_path_before(message)
                descendant_branch = await find_descendant_branch_from(message)
                await activate_conversation_branch(
                    conversation.id,
                    [*prefix, *descendant_branch],
                )

            # Get streaming configuration
            streaming_config = get_streaming_config(agent)
            global_timeout = streaming_config["global_timeout"]
            heartbeat_interval = streaming_config["heartbeat_interval"]
            tool_timeouts = streaming_config["tool_timeouts"]
            idle_timeout = streaming_config["idle_timeout"]

            from app.services.sandbox.gateway import sandbox_gateway

            sandbox_session_id = await sandbox_gateway.create_session(
                agent_id=str(agent.id),
                team_id=str(agent.team_id) if agent.team_id else None,
                user_id=str(current_user.id),
                conversation_id=str(conversation.id),
            )

            logger.info(
                f"Starting regenerate stream for message {message_id}, "
                f"global_timeout={global_timeout}s, heartbeat_interval={heartbeat_interval}s"
            )

            # Use asyncio.timeout to wrap entire streaming logic
            import asyncio

            async with asyncio.timeout(global_timeout):
                try:
                    from app.models.agent import RAGMode

                    # Determine the root message ID for versioning
                    root_id = get_version_root_id(message)

                    # An errored message is retried IN PLACE: no new version or
                    # branch is created, so failed attempts never pollute the
                    # version history.
                    in_place_retry = message.round_status == MessageRoundStatus.ERROR

                    # Get current version count
                    current_version_count = await get_branch_version_count(message)
                    new_version_number = current_version_count + 1
                    branch_parent_id = message.branch_parent_id
                    if branch_parent_id is None:
                        prefix = await get_prefix_path_before(message)
                        branch_parent_id = prefix[-1].id if prefix else None

                    round_id = uuid4()

                    if in_place_retry:
                        # Reuse the existing row: clear the failed attempt,
                        # rotate to a fresh round (so stale tool steps of the
                        # errored round cannot resurface), and keep the version
                        # numbers unchanged.
                        message.content = ""
                        message.reasoning_content = None
                        message.tool_calls = None
                        message.token_usage = None
                        message.duration_ms = None
                        message.first_token_ms = None
                        message.round_status = None
                        message.round_id = round_id
                        message.created_at = now_utc()
                        await message.save()
                        new_message = message
                        new_message_id = str(message.id)
                        effective_version_number = message.version_number
                        effective_version_count = await get_branch_version_count(
                            message
                        )
                        yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': new_message_id, 'version_number': effective_version_number, 'version_count': effective_version_count})}\n\n"
                    else:
                        # Create new version message
                        new_message = await Message.create(
                            conversation=conversation,
                            role=MessageRole.ASSISTANT,
                            content="",
                            parent_id=root_id,
                            is_active=True,
                            version_number=new_version_number,
                            branch_parent_id=branch_parent_id,
                            round_id=round_id,
                            round_index=0,
                            round_role=MessageRoundRole.ASSISTANT_FINAL,
                            is_round_canonical=True,
                        )
                        new_message_id = str(new_message.id)
                        effective_version_number = new_version_number
                        effective_version_count = new_version_number

                        # Send message_start event with version info
                        yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': new_message_id, 'version_number': effective_version_number, 'version_count': effective_version_count, 'parent_id': str(root_id)})}\n\n"
                    last_event_time = time.time()

                    # Handle RAG
                    rag_contexts: list[dict] = []
                    final_message = user_message.content

                    if agent.rag_mode == RAGMode.AUTO:
                        has_knowledge_bases = await AgentKnowledgeBase.exists(
                            agent_id=agent.id
                        )
                        if has_knowledge_bases:
                            yield f"event: {SSEEventType.RAG_START}\ndata: {json.dumps({})}\n\n"
                            last_event_time = time.time()
                            rag_contexts = await perform_rag_retrieval(
                                agent,
                                user_message.content,
                                await get_prefix_path_before(
                                    user_message,
                                    limit=AUTO_RAG_HISTORY_LIMIT,
                                    trimmed=False,
                                ),
                            )
                            if rag_contexts:
                                rag_contexts = aggregate_rag_contexts(rag_contexts)
                                yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                                last_event_time = time.time()
                            final_message = build_rag_prompt(
                                rag_contexts, user_message.content
                            )

                    final_message = await _append_asset_manifest(
                        final_message,
                        conversation_id=conversation.id,
                        agent=agent,
                        user=current_user,
                    )

                    image_pool, image_inventory = collect_conversation_images(
                        prefix_for_message,
                    )
                    model_message = append_conversation_image_inventory(
                        final_message, image_inventory
                    )
                    chat_model = await resolve_agent_chat_model(agent)
                    model_id = chat_model.model_id
                    model_context_limit = chat_model.context_length
                    model_max_output_tokens = chat_model.max_output_tokens
                    model_provider = chat_model.provider
                    tokenizer_model_id = chat_model.tokenizer_model_id
                    model_used = model_id
                    working_history_override = None

                    # Get model and tools
                    tools_openai = await get_agent_tools(agent)
                    tool_display_names = await get_tool_display_names(
                        agent, current_user.locale
                    )
                    tools: list[ToolDefinition] | None = None
                    if tools_openai:
                        tools = [
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

                    # Streaming generation (simplified - same as main chat)
                    from app.services.agent_loop import (
                        AgentLoop,
                        AgentLoopContext,
                        ContextTurn,
                    )

                    max_iterations = agent.max_iterations or 5
                    max_iterations_reached = False
                    aggregate_input_tokens = 0
                    aggregate_output_tokens = 0
                    aggregate_cache_read_tokens = 0
                    aggregate_cache_creation_tokens = 0
                    aggregate_total_input_tokens = 0

                    def sse_formatter(event_name: str, payload: dict) -> str | None:
                        """Build SSE strings and mirror deltas into generator
                        scope so error handlers keep seeing partial state."""
                        nonlocal full_content, full_reasoning, first_token_time
                        nonlocal last_event_time
                        if event_name == "heartbeat":
                            return ": heartbeat\n\n"
                        if event_name == "content_delta":
                            delta = payload.get("delta", "")
                            full_content += delta
                            if first_token_time is None:
                                first_token_time = time.time()
                            last_event_time = time.time()
                            return (
                                f"event: {SSEEventType.CONTENT_DELTA}\n"
                                f"data: {json.dumps({'delta': delta})}\n\n"
                            )
                        if event_name == "reasoning_start":
                            last_event_time = time.time()
                            return f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                        if event_name == "reasoning_delta":
                            delta = payload.get("delta", "")
                            full_reasoning += delta
                            if first_token_time is None:
                                first_token_time = time.time()
                            last_event_time = time.time()
                            return (
                                f"event: {SSEEventType.REASONING_DELTA}\n"
                                f"data: {json.dumps({'delta': delta})}\n\n"
                            )
                        if event_name == "reasoning_end":
                            return f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        if event_name == "tool_call":
                            return payload.get("sse")
                        if event_name == "tool_result":
                            return payload.get("sse")
                        if event_name == "media_result":
                            return payload.get("sse")
                        if event_name == "compression_start":
                            event_str = build_compression_start_event(
                                agent=agent,
                                stage=payload.get("stage", "macro"),
                                trigger=payload.get("trigger"),
                            )
                            if event_str:
                                last_event_time = time.time()
                            return event_str
                        if event_name == "compression_end":
                            _, end_str = build_compression_events(
                                agent=agent,
                                compression=payload.get("compression"),
                                trigger=payload.get("trigger"),
                            )
                            if end_str:
                                last_event_time = time.time()
                            return end_str
                        if event_name == "output_truncated":
                            return f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                        if event_name == "iteration_cap_reached":
                            return (
                                f"event: {SSEEventType.ITERATION_CAP_REACHED}\n"
                                f"data: {json.dumps({'content': payload.get('content', '')})}\n\n"
                            )
                        return None

                    async def build_turn(**kwargs):
                        plan = await build_context_plan(**kwargs)
                        return ContextTurn(
                            prepared=None,
                            will_summarize=plan.will_summarize,
                            compression=plan.compression,
                            plan=plan,
                        )

                    loop = AgentLoop(
                        AgentLoopContext(
                            agent=agent,
                            conversation=conversation,
                            user=current_user,
                            user_message=model_message,
                            model_id=model_id,
                            tokenizer_model_id=tokenizer_model_id,
                            model_provider=model_provider,
                            model_context_limit=model_context_limit,
                            model_max_output_tokens=model_max_output_tokens,
                            model_used=model_used,
                            model_supports_vision=False,
                            tools=tools,
                            tool_display_names=tool_display_names,
                            tool_timeouts=tool_timeouts,
                            global_timeout=global_timeout,
                            idle_timeout=idle_timeout,
                            heartbeat_interval=heartbeat_interval,
                            sandbox_session_id=sandbox_session_id,
                            file_content=None,
                            current_images=None,
                            working_history_override=working_history_override,
                            image_pool=image_pool,
                            image_inventory=image_inventory,
                            append_generated_images=append_generated_images,
                            current_user_message_id=user_message.id,
                            include_current_user_message=False,
                            history_before_message_created_at=user_message.created_at,
                            round_id=round_id,
                            protected_round_id=round_id,
                            user_locale=current_user.locale,
                            max_iterations=max_iterations,
                            streaming=True,
                            build_turn=build_turn,
                            execute_tool_call=execute_tool_call,
                            count_tool_definition_tokens=count_tool_definition_tokens,
                            trigger_for_compression=get_compression_trigger,
                            team_chat_stream=model_manager.team_chat_stream,
                            team_chat=model_manager.team_chat,
                            record_stream_usage=model_manager.record_stream_usage,
                            calculate_usage=_calculate_model_usage,
                            send_heartbeat_if_needed=send_heartbeat_if_needed,
                            is_disconnected=request.is_disconnected,
                            request=request,
                            initial_last_event_time=last_event_time,
                            formatter=sse_formatter,
                            persist_step_per_tool=True,
                            step_branch_parent_id=new_message.id,
                            first_round_index=1,
                            created_message_count=1,
                            cap_content=lambda: build_max_iterations_terminal_content(
                                current_user.locale
                            ),
                        )
                    )
                    async for sse_chunk in loop.run():
                        if sse_chunk:
                            yield sse_chunk
                            last_event_time = time.time()
                    loop_result = loop.result
                    max_iterations_reached = loop_result.max_iterations_reached
                    full_content = loop_result.full_content
                    full_reasoning = loop_result.full_reasoning
                    aggregate_input_tokens = loop_result.aggregate_input_tokens
                    aggregate_output_tokens = loop_result.aggregate_output_tokens
                    aggregate_cache_read_tokens = (
                        loop_result.aggregate_cache_read_tokens
                    )
                    aggregate_cache_creation_tokens = (
                        loop_result.aggregate_cache_creation_tokens
                    )
                    aggregate_total_input_tokens = (
                        loop_result.aggregate_total_input_tokens
                    )

                    if loop_result.manually_stopped:
                        new_message.content = full_content
                        new_message.reasoning_content = (
                            full_reasoning if full_reasoning else None
                        )
                        new_message.model_used = model_used
                        new_message.duration_ms = int((time.time() - start_time) * 1000)
                        new_message.first_token_ms = _first_token_ms(
                            start_time, first_token_time
                        )
                        new_message.is_manually_stopped = True
                        new_message.round_status = MessageRoundStatus.MANUALLY_STOPPED
                        new_message.created_at = now_utc()
                        await new_message.save()
                        await activate_regenerated_path()
                        return

                    duration_ms = int((time.time() - start_time) * 1000)
                    terminal_content = (
                        build_max_iterations_terminal_content(current_user.locale)
                        if max_iterations_reached
                        else full_content
                    )
                    terminal_round_status = get_round_terminal_status(
                        completed=not max_iterations_reached,
                        max_iterations_reached=max_iterations_reached,
                    )

                    # Update new message
                    new_message.content = terminal_content
                    new_message.reasoning_content = (
                        None
                        if max_iterations_reached
                        else (full_reasoning if full_reasoning else None)
                    )
                    new_message.model_used = model_used
                    new_message.duration_ms = duration_ms
                    new_message.first_token_ms = _first_token_ms(
                        start_time, first_token_time
                    )
                    new_message.is_manually_stopped = False
                    new_message.round_status = terminal_round_status
                    # Ensure regenerated message appears after tool calls/results in history
                    new_message.created_at = now_utc()
                    input_tokens = aggregate_input_tokens
                    output_tokens = aggregate_output_tokens
                    new_message.token_usage = {
                        "prompt": input_tokens,
                        "completion": output_tokens,
                        "cache_read": aggregate_cache_read_tokens,
                        "cache_creation": aggregate_cache_creation_tokens,
                        "total_input": aggregate_total_input_tokens,
                    }
                    await new_message.save()
                    prefix = await get_prefix_path_before(new_message)
                    await activate_conversation_branch(
                        conversation.id,
                        [*prefix, new_message],
                    )

                    # Update agent and team stats for regenerated message
                    total_tokens = input_tokens + output_tokens
                    await Agent.filter(id=agent.id).update(
                        message_count=F("message_count") + 1,
                        total_tokens=F("total_tokens") + total_tokens,
                    )
                    await Team.filter(id=agent.team.id).update(
                        total_messages=F("total_messages") + 1,
                        total_tokens=F("total_tokens") + total_tokens,
                    )
                    await Conversation.filter(id=conversation.id).update(
                        message_count=F("message_count") + 1,
                        token_usage=F("token_usage") + total_tokens,
                        updated_at=now_utc(),
                    )

                    first_token_ms = new_message.first_token_ms
                    tokens_per_second = (
                        round(output_tokens / (duration_ms / 1000), 1)
                        if duration_ms > 0 and output_tokens > 0
                        else None
                    )
                    yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens, 'cache_read_tokens': aggregate_cache_read_tokens, 'cache_creation_tokens': aggregate_cache_creation_tokens, 'total_input_tokens': aggregate_total_input_tokens}, 'timing': {'first_token_ms': first_token_ms, 'duration_ms': duration_ms, 'tokens_per_second': tokens_per_second}, 'version_number': effective_version_number, 'version_count': effective_version_count})}\n\n"

                except (QuotaExceededError, InsufficientQuotaError) as e:
                    logger.warning(
                        "Quota exceeded during regenerate: conversation=%s agent=%s error=%s",
                        conversation.id,
                        agent.id,
                        e,
                    )
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id and not in_place_retry:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.warning("Quota exceeded during regenerate: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except LLMError as e:
                    error_message = _format_llm_error_message(e)
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=error_message,
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id and not in_place_retry:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.exception(
                        "LLM error during regenerate: conversation=%s agent=%s",
                        conversation.id,
                        agent.id,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': error_message})}\n\n"
                except StreamIdleTimeoutError:
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t("stream_timeout_exceeded"),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id and not in_place_retry:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.warning(
                        "Regenerate stream idle timeout (%ss) for conversation %s agent=%s",
                        idle_timeout,
                        conversation.id,
                        agent.id,
                        extra={"timeout_type": "idle", "timeout_seconds": idle_timeout},
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': idle_timeout})}\n\n"
                except BusinessError as e:
                    error_message = t(e.msg_key or GENERIC_STREAM_ERROR_KEY, **e.kwargs)
                    logger.warning(
                        "Business error during regenerate: conversation=%s agent=%s code=%s msg=%s",
                        conversation.id,
                        agent.id,
                        e.code,
                        error_message,
                    )
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=error_message,
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id and not in_place_retry:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': e.code, 'msg': error_message})}\n\n"

                except Exception:
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_used=model_used,
                        start_time=start_time,
                        first_token_time=first_token_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id and not in_place_retry:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.exception(
                        "Unexpected error during regenerate: conversation=%s agent=%s",
                        conversation.id,
                        agent.id,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"

        except TimeoutError:
            # Global timeout
            logger.warning(
                "Regenerate stream global timeout (%ss) for message %s",
                global_timeout,
                message_id,
                extra={"timeout_type": "global", "timeout_seconds": global_timeout},
            )
            preserved_partial = await persist_partial_round_error(
                new_message,
                content=full_content,
                reasoning=full_reasoning,
                model_used=model_used,
                start_time=start_time,
                first_token_time=first_token_time,
                fallback_content=t("stream_timeout_exceeded"),
            )
            if preserved_partial:
                await activate_regenerated_path()
            elif new_message_id and not in_place_retry:
                await Message.filter(id=new_message_id).delete()
                await restore_original_path()
            # Send timeout error event
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': global_timeout})}\n\n"
        except asyncio.CancelledError:
            logger.info(
                "Regenerate stream cancelled for message %s; persisting stopped assistant state",
                message_id,
            )
            if new_message:
                new_message.content = full_content
                new_message.reasoning_content = full_reasoning or None
                new_message.model_used = model_used
                new_message.duration_ms = int((time.time() - start_time) * 1000)
                new_message.first_token_ms = _first_token_ms(
                    start_time, first_token_time
                )
                new_message.is_manually_stopped = True
                new_message.round_status = MessageRoundStatus.MANUALLY_STOPPED
                new_message.created_at = now_utc()
                if (
                    new_message.content
                    or new_message.reasoning_content
                    or new_message.tool_calls
                ):
                    await new_message.save()
                    await activate_regenerated_path()
                else:
                    await Message.filter(id=new_message.id).delete()
                    await restore_original_path()
            return

        except Exception as exc:
            logger.error(
                "Unhandled regenerate stream error: conversation=%s agent=%s exc=%s",
                conversation.id,
                agent.id,
                type(exc).__name__,
                exc_info=True,
            )
            preserved_partial = await persist_partial_round_error(
                new_message,
                content=full_content,
                reasoning=full_reasoning,
                model_used=model_used,
                start_time=start_time,
                first_token_time=first_token_time,
                fallback_content=t(GENERIC_STREAM_ERROR_KEY),
            )
            if preserved_partial:
                await activate_regenerated_path()
            elif new_message_id and not in_place_retry:
                await Message.filter(id=new_message_id).delete()
                await restore_original_path()
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"
            return

        finally:
            # Resource cleanup and logging
            duration = time.time() - start_time
            logger.info(
                f"Regenerate stream ended for message {message_id}, "
                f"duration={duration:.2f}s"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
