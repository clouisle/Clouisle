"""
Chat API endpoints for Agent conversations.
Provides streaming and non-streaming chat with AI agents.
"""

from __future__ import annotations
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ast
import asyncio
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
    AgentPublicOut,
    CreatorInfo,
    RunOut,
    RunStartOut,
    RunEventOut,
    RunInputCreate,
    RunAnswerCreate,
)
from app.models.agent_run import AgentRun as _AgentRunModel

from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.llm.tools import tool_registry, NON_SELECTABLE_BUILTIN_TOOLS
from app.llm.types import ChatStreamChunk, Message as LLMChatMessage, ToolCall
from app.llm.token_counter import (
    count_message_tokens,
    count_tokens,
    count_tool_definition_tokens,
    serialize_tool_calls,
)
from app.core.timezone import now_utc
from app.services.chat_context import (
    build_model_messages,
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

# Import helper functions from modules
from app.api.v1.endpoints.chat_helpers import (
    get_streaming_config,
)
from app.api.v1.endpoints.chat_tools import (
    build_file_content_for_context,
)
from app.api.v1.endpoints.chat_rag import (
    perform_rag_retrieval,
    aggregate_rag_contexts,
)
from app.api.v1.endpoints.chat_sse import (
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

    # Expose the interactive question tool only when enabled for this agent.
    if getattr(agent, "enable_user_input_request", False):
        for builtin_tool in tool_registry.to_openai_tools(["ask_user"]):
            append_openai_tool(builtin_tool)

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
            # Feature-switch tools are never user-selectable.
            if tool_name and tool_name not in NON_SELECTABLE_BUILTIN_TOOLS:
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
    if getattr(agent, "enable_user_input_request", False):
        display_names["ask_user"] = "Ask user"

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


AGENT_RUN_NON_STREAM_TIMEOUT_SECONDS = 3600


async def _wait_for_agent_run(run_id: UUID) -> _AgentRunModel:
    """Wait for a queued non-stream run without owning its execution."""
    from app.models.agent_run import AgentRunStatus

    loop = asyncio.get_running_loop()
    deadline = loop.time() + AGENT_RUN_NON_STREAM_TIMEOUT_SECONDS
    terminal_statuses = {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.STOPPED,
        AgentRunStatus.FAILED,
        AgentRunStatus.INTERRUPTED,
    }
    while True:
        run = await _AgentRunModel.get_or_none(id=run_id)
        if run is None:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="run_not_found",
                status_code=404,
            )
        if run.status in terminal_statuses:
            return run
        if loop.time() >= deadline:
            raise BusinessError(
                code=ResponseCode.UNKNOWN_ERROR,
                msg_key="llm_processing_failed",
                status_code=504,
            )
        await asyncio.sleep(0.25)


def _run_usage(message: Message) -> dict[str, int]:
    raw_usage = message.token_usage or {}

    def value(*keys: str) -> int:
        for key in keys:
            raw_value = raw_usage.get(key)
            if raw_value is not None:
                return int(raw_value or 0)
        return 0

    prompt_tokens = value("prompt", "prompt_tokens")
    completion_tokens = value("completion", "completion_tokens")
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cache_read_tokens": value("cache_read", "cache_read_tokens"),
        "cache_creation_tokens": value("cache_creation", "cache_creation_tokens"),
        "total_input_tokens": value("total_input", "total_input_tokens"),
    }


async def _build_non_stream_run_response(run: _AgentRunModel) -> dict:
    """Convert the worker's canonical message into the legacy chat response."""
    from app.models.agent_run import AgentRunStatus

    if run.status == AgentRunStatus.FAILED:
        if run.error_code in {
            "model_quota_exceeded",
            "QuotaExceededError",
            "InsufficientQuotaError",
        }:
            raise BusinessError(
                code=ResponseCode.MODEL_QUOTA_EXCEEDED,
                msg_key="model_quota_exceeded",
                status_code=429,
            )
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="llm_processing_failed",
            status_code=500,
        )
    if run.status == AgentRunStatus.INTERRUPTED:
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="llm_processing_failed",
            status_code=500,
        )
    if not run.canonical_message_id:
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg_key="llm_processing_failed",
            status_code=500,
        )
    assistant_message = await Message.get_or_none(id=run.canonical_message_id)
    if assistant_message is None:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="message_not_found",
            status_code=404,
        )
    usage = _run_usage(assistant_message)
    return success(
        data=ChatResponse(
            conversation_id=run.conversation_id,
            message=MessageOut.model_validate(assistant_message),
            usage=usage,
        ),
        msg_key="chat_success",
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
    """Queue a durable non-stream run and return its canonical result."""
    from app.models.agent_run import AgentRunMode

    started = await _enqueue_durable_chat_run(
        agent_id,
        chat_in,
        auth_result,
        mode=AgentRunMode.NON_STREAM,
    )
    start_data = RunStartOut.model_validate(started["data"])
    run = await _wait_for_agent_run(start_data.run_id)
    return await _build_non_stream_run_response(run)


@router.post("/{agent_id}/chat/stream")
async def chat_stream(
    agent_id: UUID,
    chat_in: ChatRequest,
    request: Request,
    auth_result: tuple[User, "APIKey | None"] = Depends(
        deps.get_current_user_or_api_key
    ),
) -> StreamingResponse:
    """Queue a durable run and subscribe to its replayable SSE events."""
    del request
    started = await start_chat_run(agent_id, chat_in, auth_result)
    start_data = RunStartOut.model_validate(started["data"])
    from app.services.agent_run_stream import sse_events

    return StreamingResponse(
        sse_events(start_data.run_id),
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
    """Create an edited user version and queue its durable reply run."""
    del request
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

    from app.models.agent import RAGMode
    from app.models.agent_run import AgentRunMode

    original_prefix = await get_prefix_path_before(message, trimmed=False)
    root_id = get_version_root_id(message)
    branch_parent_id = message.branch_parent_id
    if branch_parent_id is None:
        branch_parent_id = original_prefix[-1].id if original_prefix else None
    rag_contexts: list[dict[str, Any]] = []
    if agent.rag_mode == RAGMode.AUTO and await AgentKnowledgeBase.exists(
        agent_id=agent.id
    ):
        rag_contexts = aggregate_rag_contexts(
            await perform_rag_retrieval(
                agent,
                edited_content,
                original_prefix[-AUTO_RAG_HISTORY_LIMIT:],
            )
        )

    current_version_count = await (
        Message.filter(Q(id=root_id) | Q(parent_id=root_id))
        .filter(Q(round_id__isnull=True) | Q(is_round_canonical=True))
        .count()
    )
    new_version_number = current_version_count + 1
    round_id = uuid4()
    async with in_transaction() as conn:
        await (
            Conversation.filter(id=conversation.id)
            .using_db(conn)
            .select_for_update()
            .first()
        )
        edited_user_msg = await Message.create(
            conversation=conversation,
            role=MessageRole.USER,
            content=edited_content,
            parent_id=root_id,
            is_active=True,
            version_number=new_version_number,
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
        round_index=0,
        round_role=MessageRoundRole.ASSISTANT_FINAL,
        is_round_canonical=True,
    )
    started = await _enqueue_existing_message_run(
        agent=agent,
        conversation=conversation,
        current_user=current_user,
        mode=AgentRunMode.EDIT,
        user_message=edited_user_msg,
        message=edited_content,
        round_id=round_id,
        source_message_id=message.id,
        canonical_message_id=assistant_msg.id,
        branch_parent_id=edited_user_msg.id,
        images=message.images,
        file_urls=message.file_urls,
        rag_contexts=rag_contexts,
        exclude_message_ids=[assistant_msg.id],
        created_message_count=2,
        first_round_index=2,
        message_start={
            "edited_message_id": str(edited_user_msg.id),
            "edited_version_number": new_version_number,
            "edited_version_count": new_version_number,
            "edited_parent_id": str(root_id),
        },
    )
    return _stream_queued_run(started)


def _stream_queued_run(started: dict) -> StreamingResponse:
    """Subscribe to a queued run using the legacy streaming response shape."""
    start_data = RunStartOut.model_validate(started["data"])
    from app.services.agent_run_stream import sse_events

    return StreamingResponse(
        sse_events(start_data.run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ AgentRun Endpoints ============


async def _enqueue_existing_message_run(
    *,
    agent: Agent,
    conversation: Conversation,
    current_user: User,
    mode: Any,
    user_message: Message,
    message: str,
    round_id: UUID,
    source_message_id: UUID,
    canonical_message_id: UUID,
    branch_parent_id: UUID | None,
    images: list[dict[str, Any]] | None = None,
    file_urls: list[dict[str, Any]] | None = None,
    legacy_files: list[dict[str, Any]] | None = None,
    variables: dict[str, Any] | None = None,
    include_current_user_message: bool = True,
    history_before_message_created_at: Any = None,
    exclude_message_ids: list[UUID] | None = None,
    created_message_count: int = 2,
    first_round_index: int = 1,
    rag_contexts: list[dict[str, Any]] | None = None,
    in_place_retry: bool = False,
    message_start: dict[str, Any] | None = None,
) -> dict:
    """Queue a run whose user and assistant rows already exist."""
    from app.services.agent_run_store import create_run, transition_run
    from app.services.agent_run_worker import build_payload

    run = await create_run(
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
        mode=mode,
        source_message_id=source_message_id,
    )
    run.active_round_id = round_id
    run.canonical_message_id = canonical_message_id
    await run.save(update_fields=["active_round_id", "canonical_message_id"])
    payload = build_payload(
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
        mode=mode,
        user_message_id=user_message.id,
        round_id=round_id,
        run_id=run.id,
        message=message,
        images=images,
        file_urls=file_urls,
        legacy_files=legacy_files,
        variables=variables,
        source_message_id=source_message_id,
        edited_user_message_id=user_message.id if mode.value == "edit" else None,
        canonical_message_id=canonical_message_id,
        in_place_retry=in_place_retry,
        branch_parent_id=branch_parent_id,
        locale=current_user.locale,
        include_current_user_message=include_current_user_message,
        history_before_message_created_at=history_before_message_created_at,
        exclude_message_ids=exclude_message_ids,
        created_message_count=created_message_count,
        first_round_index=first_round_index,
        message_start=message_start,
        rag_contexts=rag_contexts,
    )
    run.worker_payload = payload
    await run.save(update_fields=["worker_payload"])
    try:
        from app.tasks.agent import run_agent_task

        task_result = run_agent_task.apply_async(args=(payload,))
        task_id = getattr(task_result, "id", None)
        if task_id:
            run.celery_task_id = task_id
            await run.save(update_fields=["celery_task_id"])
    except Exception as exc:
        from app.models.agent_run import AgentRunStatus

        await transition_run(
            run,
            AgentRunStatus.FAILED,
            error_code="enqueue_failed",
            error_message=str(exc),
        )
        raise
    return success(
        data=RunStartOut(
            run_id=run.id,
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            status=run.status.value,
            stream_url=f"/agents/{agent.id}/chat/runs/{run.id}/stream",
        )
    )


async def _enqueue_durable_chat_run(
    agent_id: UUID,
    chat_in: ChatRequest,
    auth_result: Any,
    *,
    mode: Any,
) -> dict:
    """Create the durable input row and enqueue one worker-owned run."""
    current_user, api_key = _split_run_auth(auth_result)
    if not current_user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key="inactive_user",
            status_code=401,
        )
    await deps.check_api_key_agent_access(api_key, agent_id)

    agent = await check_agent_chat_access(agent_id, current_user)
    conversation = await get_or_create_conversation(
        agent, current_user, chat_in.conversation_id, chat_in.variables
    )

    from app.models.agent import RAGMode

    rag_contexts: list[dict[str, Any]] = []
    if agent.rag_mode == RAGMode.AUTO:
        rag_contexts = await perform_rag_retrieval(
            agent,
            chat_in.message,
            await get_visible_conversation_messages(
                conversation.id, limit=AUTO_RAG_HISTORY_LIMIT
            ),
        )
        rag_contexts = aggregate_rag_contexts(rag_contexts)

    message_assets = await _resolve_message_assets(
        attachments=[*chat_in.images, *chat_in.file_urls],
        agent=agent,
        user=current_user,
        conversation_id=conversation.id,
    )
    round_id = uuid4()
    user_branch_parent_id = await get_next_user_branch_parent_id(conversation)

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

    await update_message_stats(agent, token_usage=None)
    streaming_config = get_streaming_config(agent)
    _, updated_file_urls = await build_file_content_for_context(
        agent=agent,
        file_urls=chat_in.file_urls,
        legacy_files=chat_in.files,
        user_locale=current_user.locale,
        tool_timeouts=streaming_config["tool_timeouts"],
        user=current_user,
    )
    if updated_file_urls is not None and user_msg.file_urls != updated_file_urls:
        user_msg.file_urls = updated_file_urls
        await user_msg.save(update_fields=["file_urls"])

    from app.services.agent_run_store import create_run, transition_run
    from app.services.agent_run_worker import build_payload

    run = await create_run(
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
        mode=mode,
        source_message_id=user_msg.id,
    )
    run.active_round_id = round_id
    await run.save(update_fields=["active_round_id"])
    payload = build_payload(
        agent_id=agent.id,
        conversation_id=conversation.id,
        user_id=current_user.id,
        mode=mode,
        user_message_id=user_msg.id,
        round_id=round_id,
        run_id=run.id,
        message=chat_in.message,
        images=[image.model_dump() for image in chat_in.images],
        file_urls=updated_file_urls
        if updated_file_urls is not None
        else [file.model_dump() for file in chat_in.file_urls],
        legacy_files=[file.model_dump() for file in chat_in.files],
        history_override=(
            [
                message.model_dump(exclude_none=True)
                for message in chat_in.history_override
            ]
            if chat_in.history_override
            else None
        ),
        variables=chat_in.variables,
        branch_parent_id=user_branch_parent_id,
        locale=current_user.locale,
    )
    run.worker_payload = payload
    await run.save(update_fields=["worker_payload"])

    try:
        from app.tasks.agent import run_agent_task

        task_result = run_agent_task.apply_async(args=(payload,))
        task_id = getattr(task_result, "id", None)
        if task_id:
            run.celery_task_id = task_id
            await run.save(update_fields=["celery_task_id"])
    except Exception as exc:
        from app.models.agent_run import AgentRunStatus

        await transition_run(
            run,
            AgentRunStatus.FAILED,
            error_code="enqueue_failed",
            error_message=str(exc),
        )
        raise

    return success(
        data=RunStartOut(
            run_id=run.id,
            conversation_id=conversation.id,
            user_message_id=user_msg.id,
            status=run.status.value,
            stream_url=f"/agents/{agent_id}/chat/runs/{run.id}/stream",
        )
    )


# ============ AgentRun Endpoints ==========
@router.post(
    "/{agent_id}/chat/runs",
    response_model=Response[RunStartOut],
    status_code=202,
)
async def start_chat_run(
    agent_id: UUID,
    chat_in: ChatRequest,
    auth_result: tuple[User, "APIKey | None"] = Depends(
        deps.get_current_user_or_api_key
    ),
) -> Any:
    """Persist a chat request and enqueue its durable AgentRun worker."""
    from app.models.agent_run import AgentRunMode

    return await _enqueue_durable_chat_run(
        agent_id,
        chat_in,
        auth_result,
        mode=AgentRunMode.SEND,
    )


@router.get(
    "/{agent_id}/chat/runs/{run_id}/stream",
)
async def stream_chat_run(
    agent_id: UUID,
    run_id: UUID,
    after_sequence: int = 0,
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> StreamingResponse:
    """Replay and follow one durable run until its terminal event."""
    current_user, api_key = _split_run_auth(auth_result)
    await deps.check_api_key_agent_access(api_key, agent_id)
    await _load_owned_run(agent_id, run_id, current_user)
    from app.services.agent_run_stream import sse_events

    return StreamingResponse(
        sse_events(run_id, from_sequence=max(after_sequence, 0)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{agent_id}/chat/runs/{run_id}",
    response_model=Response[RunOut],
)
async def get_run_status(
    agent_id: UUID,
    run_id: UUID,
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> Any:
    """Get durable run status; owner-scoped."""
    current_user, api_key = _split_run_auth(auth_result)
    await deps.check_api_key_agent_access(api_key, agent_id)
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
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> Any:
    """Replay buffered run events after ``after_sequence`` (authorized scope)."""
    current_user, api_key = _split_run_auth(auth_result)
    await deps.check_api_key_agent_access(api_key, agent_id)
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
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> Any:
    """Queue steering / follow-up / stop for a running agent."""
    current_user, api_key = _split_run_auth(auth_result)
    await deps.check_api_key_agent_access(api_key, agent_id)
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
    "/{agent_id}/chat/runs/{run_id}/answers",
    response_model=Response[RunOut],
)
async def post_run_answer(
    agent_id: UUID,
    run_id: UUID,
    body: RunAnswerCreate,
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> Any:
    """Validate and submit one answer set for a waiting ask_user call."""
    current_user, api_key = _split_run_auth(auth_result)
    await deps.check_api_key_agent_access(api_key, agent_id)
    run = await _load_owned_run(agent_id, run_id, current_user)
    from app.models.agent_run import AgentRunStatus
    from app.services.agent_run_store import submit_user_answers

    try:
        resumed = await submit_user_answers(
            run_id,
            tool_call_id=body.tool_call_id,
            answers=body.answers,
            skipped=body.skipped,
        )
    except ValueError as exc:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg=str(exc),
            status_code=400,
        ) from exc

    if resumed is None:
        if run.status != AgentRunStatus.WAITING:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg="run is not waiting for user answers",
                status_code=409,
            )
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg="tool call does not match the pending interaction",
            status_code=409,
        )

    try:
        from app.tasks.agent import run_agent_task

        payload = resumed.worker_payload
        if not isinstance(payload, dict):
            raise RuntimeError("run resume payload is missing")
        task_result = run_agent_task.apply_async(args=(payload,))
        task_id = getattr(task_result, "id", None)
        if task_id:
            resumed.celery_task_id = task_id
            await resumed.save(update_fields=["celery_task_id"])
    except Exception as exc:
        from app.models.agent_run import AgentRunStatus
        from app.services.agent_run_store import transition_run
        from app.services.agent_run_stream import AgentRunStream

        await transition_run(
            resumed,
            AgentRunStatus.FAILED,
            error_code="enqueue_failed",
            error_message=str(exc),
        )
        stream = AgentRunStream(run_id)
        await stream.seed_sequence()
        await stream.publish(
            "error", {"code": "enqueue_failed", "msg": "Unable to resume run"}
        )
        await stream.publish("run_end", {"status": "failed"})
        raise

    return success(data=_run_to_out(resumed))


@router.post(
    "/{agent_id}/chat/runs/{run_id}/stop",
    response_model=Response[RunOut],
)
async def stop_run(
    agent_id: UUID,
    run_id: UUID,
    auth_result: Any = Depends(deps.get_current_user_or_api_key),
) -> Any:
    """Cooperatively stop a run, including a non-terminal waiting run."""
    current_user, api_key = _split_run_auth(auth_result)
    await deps.check_api_key_agent_access(api_key, agent_id)
    run = await _load_owned_run(agent_id, run_id, current_user)
    from app.models.agent_run import (
        AgentRunInputKind,
        AgentRunStatus,
    )
    from app.services.agent_run_store import enqueue_input, transition_run

    if run.status == AgentRunStatus.WAITING:
        from app.services.agent_run_store import stop_waiting_run

        stopped = await stop_waiting_run(run_id)

        if stopped is not None:
            from app.services.agent_run_stream import AgentRunStream

            stream = AgentRunStream(run_id)
            await stream.seed_sequence()
            await stream.publish("run_end", {"status": "stopped"})
            return success(data=_run_to_out(stopped))
        run = await _AgentRunModel.get_or_none(id=run_id) or run

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


def _split_run_auth(auth_result: Any) -> tuple[User, "APIKey | None"]:
    """Accept dependency tuples and direct-user calls used by unit tests."""
    if isinstance(auth_result, tuple) and len(auth_result) == 2:
        return auth_result
    return auth_result, None


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
    if getattr(current_user, "is_superuser", False):
        conversation = await _Conv.get_or_none(id=run.conversation_id)
    else:
        conversation = await _Conv.get_or_none(
            id=run.conversation_id, user=current_user
        )
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
        pending_tool_call_id=getattr(run, "pending_tool_call_id", None),
        pending_tool_name=getattr(run, "pending_tool_name", None),
        pending_tool_input=getattr(run, "pending_tool_input", None),
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
) -> Any:
    """Queue a new assistant version (or retry an errored one) durably."""
    del request
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

    from app.models.agent import RAGMode
    from app.models.agent_run import AgentRunMode

    in_place_retry = message.round_status == MessageRoundStatus.ERROR
    root_id = get_version_root_id(message)
    branch_parent_id = message.branch_parent_id
    if branch_parent_id is None:
        branch_parent_id = prefix_for_message[-1].id if prefix_for_message else None
    current_version_count = await get_branch_version_count(message)
    new_version_number = current_version_count + 1
    round_id = uuid4()

    if in_place_retry:
        message.content = ""
        message.reasoning_content = None
        message.tool_calls = None
        message.token_usage = None
        message.duration_ms = None
        message.first_token_ms = None
        message.round_status = None
        message.round_id = round_id
        message.round_index = 0
        message.created_at = now_utc()
        await message.save()
        assistant_msg = message
        version_number = message.version_number
        version_count = current_version_count
    else:
        assistant_msg = await Message.create(
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
        version_number = new_version_number
        version_count = new_version_number

    rag_contexts: list[dict[str, Any]] = []
    if agent.rag_mode == RAGMode.AUTO and await AgentKnowledgeBase.exists(
        agent_id=agent.id
    ):
        rag_contexts = aggregate_rag_contexts(
            await perform_rag_retrieval(
                agent,
                user_message.content,
                prefix_for_message[-AUTO_RAG_HISTORY_LIMIT:],
            )
        )
    started = await _enqueue_existing_message_run(
        agent=agent,
        conversation=conversation,
        current_user=current_user,
        mode=AgentRunMode.REGENERATE,
        user_message=user_message,
        message=user_message.content,
        round_id=round_id,
        source_message_id=message.id,
        canonical_message_id=assistant_msg.id,
        branch_parent_id=branch_parent_id,
        images=user_message.images,
        file_urls=user_message.file_urls,
        variables=regen_request.variables,
        include_current_user_message=False,
        history_before_message_created_at=user_message.created_at,
        exclude_message_ids=[assistant_msg.id],
        created_message_count=0 if in_place_retry else 1,
        first_round_index=2,
        in_place_retry=in_place_retry,
        rag_contexts=rag_contexts,
        message_start={
            "version_number": version_number,
            "version_count": version_count,
            **({"parent_id": str(root_id)} if not in_place_retry else {}),
        },
    )
    return _stream_queued_run(started)
