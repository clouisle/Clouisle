"""
Chat API endpoints for Agent conversations.
Provides streaming and non-streaming chat with AI agents.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from app.models.api_key import APIKey

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from tortoise.expressions import F

from app.api import deps
from app.core.i18n import t
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
    SSEEventType,
    AgentPublicOut,
    CreatorInfo,
)
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.llm.errors import ContextLengthError, InsufficientQuotaError
from app.llm.tools import tool_registry
from app.llm.types import ChatStreamChunk, Message as LLMChatMessage
from app.core.timezone import now_utc
from app.services.chat_context import (
    build_model_messages,
    get_context_compression_config,
    prepare_model_context,
    retry_prepare_model_context,
)
from app.services.message_branching import (
    activate_conversation_branch,
    find_descendant_branch_from,
    get_last_active_canonical_message,
    get_prefix_path_before,
    get_version_count as get_branch_version_count,
    get_version_root_id,
    stale_session_memory_if_source_outside_active_branch,
)

# Import helper functions from modules
from app.api.v1.endpoints.chat_helpers import (
    get_streaming_config,
    parse_user_input_request,
    should_retry_context_length,
    get_compression_trigger,
    get_tool_execution_payloads,
    StreamIdleTimeoutError,
    iter_with_idle_timeout,
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
    build_tool_result_sse_event,
    build_media_result_sse_event,
)


router = APIRouter()
logger = logging.getLogger(__name__)
GENERIC_STREAM_ERROR_KEY = "unknown_error"


def _is_model_stream_activity(chunk: ChatStreamChunk) -> bool:
    delta = chunk.delta
    return bool(
        delta.content
        or delta.reasoning_content
        or delta.tool_calls
        or delta.stream_activity
        or chunk.finish_reason
    )


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
    """Get model identifier for the agent."""
    if not agent.model_id:
        return None

    team_model = (
        await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
    )
    if team_model:
        return f"{team_model.model.provider}/{team_model.model.model_id}"

    return None


async def get_agent_chat_model(agent: Agent) -> TeamModel | None:
    """Get the chat TeamModel for an agent."""
    if not agent.model_id:
        return None

    return await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()


def enqueue_session_memory_extraction(
    agent: Agent,
    conversation: Conversation,
    assistant_message: Message,
) -> None:
    """Best-effort enqueue for async session memory extraction."""
    compression_config = get_context_compression_config(agent)
    if not compression_config.get("session_memory_enabled", True):
        return
    if not compression_config.get("session_memory_async_extract", True):
        return

    try:
        from app.tasks.session_memory import extract_session_memory_task

        extract_session_memory_task.delay(
            str(conversation.id),
            str(assistant_message.id),
        )
    except Exception as e:
        logger.warning(
            "Failed to enqueue session memory extraction for conversation %s "
            "message %s: %s",
            conversation.id,
            assistant_message.id,
            e,
        )


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


async def persist_partial_round_error(
    message: Message | None,
    *,
    content: str,
    reasoning: str,
    model_id: str | None,
    start_time: float,
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
    message.model_used = model_id  # type: ignore[assignment]
    message.model_used = model_id
    message.duration_ms = int((time.time() - start_time) * 1000)
    message.is_manually_stopped = False
    message.round_status = MessageRoundStatus.ERROR
    message.created_at = now_utc()
    await message.save()
    return True


async def get_model_capabilities(agent: Agent) -> dict:
    """Get model capabilities (vision, function_call, etc.) for the agent."""
    if not agent.model_id:
        return {}

    team_model = (
        await TeamModel.filter(id=agent.model_id).prefetch_related("model").first()
    )
    if team_model and team_model.model.capabilities:
        return team_model.model.capabilities

    return {}


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
                        ["read", "write", "bash"]
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
            variables=agent.variables or [],
            enable_vision=agent.enable_vision,
            enable_file_upload=agent.enable_file_upload,
            file_upload_config=agent.file_upload_config,
            hide_tool_calls=agent.hide_tool_calls,
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

    start_time = time.time()

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
        rag_contexts = await perform_rag_retrieval(agent, chat_in.message)
        rag_contexts = aggregate_rag_contexts(rag_contexts)
        final_message = build_rag_prompt(rag_contexts, chat_in.message)

    round_id = uuid4()
    next_round_index = 1
    user_branch_parent_id = await get_next_user_branch_parent_id(conversation)

    # Save user message with images and file_urls
    user_msg = await Message.create(
        conversation=conversation,
        role=MessageRole.USER,
        content=chat_in.message,
        images=[img.model_dump() for img in chat_in.images] if chat_in.images else None,
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

    # Update message stats (user message, no tokens)
    await update_message_stats(agent, token_usage=None)

    # Get model identifier
    team_model = await get_agent_chat_model(agent)
    model_id = (
        f"{team_model.model.provider}/{team_model.model.model_id}"
        if team_model
        else None
    )

    model_supports_vision = False
    if chat_in.images and agent.enable_vision:
        model_capabilities = await get_model_capabilities(agent)
        model_supports_vision = model_capabilities.get("vision", False)
        if not model_supports_vision:
            raise BusinessError(
                code=ResponseCode.MODEL_VISION_NOT_SUPPORTED,
                msg_key="model_vision_not_supported",
                status_code=400,
            )

    streaming_config = get_streaming_config(agent)
    tool_timeouts = streaming_config["tool_timeouts"]
    from app.services.sandbox.gateway import sandbox_gateway

    sandbox_session_id = await sandbox_gateway.create_session(
        agent_id=str(agent.id),
        team_id=str(agent.team_id) if agent.team_id else None,
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

    try:
        # Import here to avoid circular import
        from app.llm import model_manager
        from app.llm.errors import ContextLengthError, QuotaExceededError, LLMError
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

        # Tool call loop (non-streaming)
        max_iterations = agent.max_iterations or 5
        iteration = 0
        final_response = None
        total_prompt_tokens = 0
        total_completion_tokens = 0
        max_iterations_reached = False

        while iteration < max_iterations:
            iteration += 1
            prepare_context = prepare_model_context
            context_retry_used = False
            try:
                prepared_context = await prepare_context(
                    agent=agent,
                    conversation=conversation,
                    user_message=final_message,
                    model_id=model_id or "gpt-4",
                    model_context_limit=team_model.model.context_length
                    if team_model
                    else None,
                    model_max_output_tokens=team_model.model.max_output_tokens
                    if team_model
                    else None,
                    provider=team_model.model.provider if team_model else None,
                    file_content=file_content_str,
                    user_locale=current_user.locale,
                    history_override=working_history_override,
                    current_images=chat_in.images,
                    model_supports_vision=model_supports_vision,
                    current_user_message_id=user_msg.id,
                    tool_timeouts=tool_timeouts,
                    user=current_user,
                    protected_round_id=round_id,
                )
            except ContextLengthError:
                if not should_retry_context_length(agent):
                    raise
                prepared_context = await retry_prepare_model_context(
                    agent=agent,
                    conversation=conversation,
                    user_message=final_message,
                    model_id=model_id or "gpt-4",
                    model_context_limit=team_model.model.context_length
                    if team_model
                    else None,
                    model_max_output_tokens=team_model.model.max_output_tokens
                    if team_model
                    else None,
                    provider=team_model.model.provider if team_model else None,
                    file_content=file_content_str,
                    user_locale=current_user.locale,
                    history_override=working_history_override,
                    current_images=chat_in.images,
                    model_supports_vision=model_supports_vision,
                    current_user_message_id=user_msg.id,
                    tool_timeouts=tool_timeouts,
                    user=current_user,
                    protected_round_id=round_id,
                )
                context_retry_used = True
            try:
                response = await model_manager.team_chat(
                    team_id=str(agent.team_id),
                    messages=[m.model_dump() for m in prepared_context.messages],
                    model_id=model_id,
                    tools=tools,
                )
            except ContextLengthError:
                if context_retry_used or not should_retry_context_length(agent):
                    raise
                prepared_context = await retry_prepare_model_context(
                    agent=agent,
                    conversation=conversation,
                    user_message=final_message,
                    model_id=model_id or "gpt-4",
                    model_context_limit=team_model.model.context_length
                    if team_model
                    else None,
                    model_max_output_tokens=team_model.model.max_output_tokens
                    if team_model
                    else None,
                    provider=team_model.model.provider if team_model else None,
                    file_content=file_content_str,
                    user_locale=current_user.locale,
                    history_override=working_history_override,
                    current_images=chat_in.images,
                    model_supports_vision=model_supports_vision,
                    current_user_message_id=user_msg.id,
                    tool_timeouts=tool_timeouts,
                    user=current_user,
                    protected_round_id=round_id,
                )
                context_retry_used = True
                response = await model_manager.team_chat(
                    team_id=str(agent.team_id),
                    messages=[m.model_dump() for m in prepared_context.messages],
                    model_id=model_id,
                    tools=tools,
                )

            if response.usage:
                total_prompt_tokens += response.usage.prompt_tokens or 0
                total_completion_tokens += response.usage.completion_tokens or 0

            if response.tool_calls:

                def safe_parse_arguments(args):
                    if not args:
                        return {}
                    if isinstance(args, dict):
                        return args
                    try:
                        return json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        return {}

                intermediate_tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "display_name": tool_display_names.get(
                            tc.function.name, tc.function.name
                        ),
                        "arguments": safe_parse_arguments(tc.function.arguments),
                    }
                    for tc in response.tool_calls
                ]

                # Save intermediate assistant message with tool calls
                assistant_step_index = next_round_index
                await Message.create(
                    conversation=conversation,
                    role=MessageRole.ASSISTANT,
                    content=response.content or "",
                    reasoning_content=response.reasoning_content or None,
                    model_used=response.model,
                    tool_calls=intermediate_tool_calls,
                    round_id=round_id,
                    round_index=assistant_step_index,
                    round_role=MessageRoundRole.ASSISTANT_STEP,
                    is_round_canonical=False,
                    iteration_index=iteration,
                )
                next_round_index += 1

                if working_history_override is None:
                    working_history_override = []
                append_round_history_entry(
                    working_history_override,
                    role="assistant",
                    content=response.content or "",
                    reasoning_content=response.reasoning_content or None,
                    tool_calls=intermediate_tool_calls,
                    round_id=round_id,
                    round_index=assistant_step_index,
                    round_role=MessageRoundRole.ASSISTANT_STEP.value,
                    is_round_canonical=False,
                    iteration_index=iteration,
                )

                # Execute tools and add tool results to message history
                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    result = await execute_tool_call(
                        tool_name,
                        arguments,
                        agent=agent,
                        tool_timeouts=tool_timeouts,
                        user=current_user,
                        session_id=sandbox_session_id,
                    )
                    display_result, llm_result = get_tool_execution_payloads(result)

                    tool_step_index = next_round_index
                    await Message.create(
                        conversation=conversation,
                        role=MessageRole.TOOL,
                        content=display_result,
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        round_id=round_id,
                        round_index=tool_step_index,
                        round_role=MessageRoundRole.TOOL_RESULT,
                        is_round_canonical=False,
                        iteration_index=iteration,
                    )
                    next_round_index += 1
                    if working_history_override is None:
                        working_history_override = []
                    append_round_history_entry(
                        working_history_override,
                        role="tool",
                        content=llm_result,
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                        round_id=round_id,
                        round_index=tool_step_index,
                        round_role=MessageRoundRole.TOOL_RESULT.value,
                        is_round_canonical=False,
                        iteration_index=iteration,
                    )
                if iteration >= max_iterations:
                    max_iterations_reached = True
                    break
                continue

            final_response = response
            break

        if final_response is None and not max_iterations_reached:
            final_response = response

        duration_ms = int((time.time() - start_time) * 1000)

        clean_final_content = (
            build_max_iterations_terminal_content(current_user.locale)
            if max_iterations_reached
            else (final_response.content if final_response else "")
        )
        if (
            not max_iterations_reached
            and agent.enable_user_input_request
            and clean_final_content
        ):
            _, clean_final_content = parse_user_input_request(clean_final_content)

        final_tool_calls = None
        if final_response and final_response.tool_calls:
            final_tool_calls = []
            for tc in final_response.tool_calls:
                final_tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "display_name": tool_display_names.get(
                            tc.function.name, tc.function.name
                        ),
                        "arguments": safe_parse_arguments(tc.function.arguments),
                    }
                )

        prompt_tokens = total_prompt_tokens or (
            final_response.usage.prompt_tokens
            if final_response and final_response.usage
            else 0
        )
        completion_tokens = total_completion_tokens or (
            final_response.usage.completion_tokens
            if final_response and final_response.usage
            else 0
        )
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
                None
                if max_iterations_reached
                else (final_response.reasoning_content if final_response else None)
            ),
            model_used=(final_response.model if final_response else model_id),
            token_usage={
                "prompt": prompt_tokens,
                "completion": completion_tokens,
            },
            duration_ms=duration_ms,
            tool_calls=final_tool_calls,
            branch_parent_id=user_msg.id,
            round_id=round_id,
            round_index=next_round_index,
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
            **title_update,
        )

        # Update agent stats atomically
        await Agent.filter(id=agent.id).update(message_count=F("message_count") + 2)

        branch_prefix = await get_prefix_path_before(user_msg)
        await activate_conversation_branch(
            conversation.id,
            [*branch_prefix, user_msg, assistant_msg],
        )
        enqueue_session_memory_extraction(agent, conversation, assistant_msg)

        return success(
            data=ChatResponse(
                conversation_id=conversation.id,
                message=MessageOut.model_validate(assistant_msg),
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
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
        logger.exception("LLM error during chat: %s", e)
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
                FinishReason,
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

                    # Check if model supports vision when images are provided (before creating messages)
                    model_supports_vision = False
                    if chat_in.images and agent.enable_vision:
                        model_capabilities = await get_model_capabilities(agent)
                        model_supports_vision = model_capabilities.get("vision", False)
                        if not model_supports_vision:
                            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_VISION_NOT_SUPPORTED, 'msg': t('model_vision_not_supported')})}\n\n"
                            return

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
                                agent, chat_in.message
                            )
                            if rag_contexts:
                                rag_contexts = aggregate_rag_contexts(rag_contexts)
                                yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                                last_event_time = time.time()
                            final_message = build_rag_prompt(
                                rag_contexts, chat_in.message
                            )

                    round_id = uuid4()
                    next_round_index = 1
                    user_branch_parent_id = await get_next_user_branch_parent_id(
                        conversation
                    )

                    # Save user message with images and file_urls
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
                    yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': message_id})}\n\n"
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

                    team_model = await get_agent_chat_model(agent)
                    model_id = (
                        f"{team_model.model.provider}/{team_model.model.model_id}"
                        if team_model
                        else None
                    )
                    working_history_override = (
                        [
                            message.model_dump(exclude_none=True)
                            for message in chat_in.history_override
                        ]
                        if chat_in.history_override
                        else None
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

                    # Tool call loop
                    max_iterations = agent.max_iterations or 5
                    iteration = 0
                    max_iterations_reached = False

                    while iteration < max_iterations:
                        iteration += 1

                        # Heartbeat check and send
                        (
                            should_continue,
                            new_last_event_time,
                        ) = await send_heartbeat_if_needed(
                            last_event_time, heartbeat_interval, request
                        )
                        if not should_continue:
                            # Client disconnected, save current stopped state and exit
                            assistant_msg.content = full_content
                            assistant_msg.reasoning_content = (
                                full_reasoning if full_reasoning else None
                            )
                            assistant_msg.model_used = model_id
                            assistant_msg.duration_ms = int(
                                (time.time() - start_time) * 1000
                            )
                            assistant_msg.is_manually_stopped = True
                            assistant_msg.round_status = (
                                MessageRoundStatus.MANUALLY_STOPPED
                            )
                            assistant_msg.created_at = now_utc()
                            await assistant_msg.save()
                            return

                        # If we need to send heartbeat
                        if new_last_event_time > last_event_time:
                            yield ": heartbeat\n\n"
                            last_event_time = new_last_event_time

                        # Track state for this iteration
                        reasoning_started = False
                        full_content = ""
                        full_reasoning = ""
                        iteration_content = ""
                        iteration_reasoning = ""
                        collected_tool_calls = []  # For collecting tool calls from stream

                        prepare_context = prepare_model_context
                        context_retry_used = False
                        try:
                            prepared_context = await prepare_context(
                                agent=agent,
                                conversation=conversation,
                                user_message=final_message,
                                model_id=model_id or "gpt-4",
                                model_context_limit=team_model.model.context_length
                                if team_model
                                else None,
                                model_max_output_tokens=team_model.model.max_output_tokens
                                if team_model
                                else None,
                                provider=team_model.model.provider
                                if team_model
                                else None,
                                file_content=file_content_str,
                                user_locale=current_user.locale,
                                history_override=working_history_override,
                                current_images=chat_in.images,
                                model_supports_vision=model_supports_vision,
                                current_user_message_id=user_msg.id,
                                include_current_user_message=True,
                                exclude_message_ids=[assistant_msg.id],
                                tool_timeouts=tool_timeouts,
                                user=current_user,
                                protected_round_id=round_id,
                            )
                            compression_start, compression_end = (
                                build_compression_events(
                                    agent=agent,
                                    compression=prepared_context.compression,
                                    trigger=get_compression_trigger(
                                        prepared_context.compression
                                    ),
                                )
                            )
                            if compression_start:
                                yield compression_start
                                last_event_time = time.time()
                            if compression_end:
                                yield compression_end
                                last_event_time = time.time()
                        except ContextLengthError:
                            if not should_retry_context_length(agent):
                                raise
                            prepared_context = await retry_prepare_model_context(
                                agent=agent,
                                conversation=conversation,
                                user_message=final_message,
                                model_id=model_id or "gpt-4",
                                model_context_limit=team_model.model.context_length
                                if team_model
                                else None,
                                model_max_output_tokens=team_model.model.max_output_tokens
                                if team_model
                                else None,
                                provider=team_model.model.provider
                                if team_model
                                else None,
                                file_content=file_content_str,
                                user_locale=current_user.locale,
                                history_override=working_history_override,
                                current_images=chat_in.images,
                                model_supports_vision=model_supports_vision,
                                current_user_message_id=user_msg.id,
                                include_current_user_message=True,
                                exclude_message_ids=[assistant_msg.id],
                                tool_timeouts=tool_timeouts,
                                user=current_user,
                                protected_round_id=round_id,
                            )
                            compression_start, compression_end = (
                                build_compression_events(
                                    agent=agent,
                                    compression=prepared_context.compression,
                                    trigger="context_length_error",
                                    retry_index=1,
                                    stage_override="reactive_retry",
                                )
                            )
                            if compression_start:
                                yield compression_start
                                last_event_time = time.time()
                            if compression_end:
                                yield compression_end
                                last_event_time = time.time()
                            context_retry_used = True
                        messages_for_llm = [
                            message.model_dump(exclude_none=True)
                            for message in prepared_context.messages
                        ]

                        # Calculate input chars for this iteration
                        iteration_input_chars = sum(
                            len(m.get("content") or "")
                            if isinstance(m.get("content"), str)
                            else 0
                            for m in messages_for_llm
                        )

                        # Use streaming call - works for both with and without tools
                        emitted_any = False
                        client_disconnected = False
                        try:
                            stream = model_manager.team_chat_stream(
                                team_id=str(agent.team_id),
                                messages=messages_for_llm,
                                model_id=model_id,
                                tools=tools,
                            )
                            async for chunk in iter_with_idle_timeout(
                                stream,
                                timeout_seconds=idle_timeout,
                                activity_predicate=_is_model_stream_activity,
                            ):
                                # Check if client disconnected - stop LLM generation to save tokens
                                if await request.is_disconnected():
                                    client_disconnected = True
                                    logger.info(
                                        f"Client disconnected during stream, stopping LLM generation for conversation {conversation.id}"
                                    )
                                    break

                                # Handle reasoning content (思维链)
                                if chunk.delta.reasoning_content:
                                    if not reasoning_started:
                                        reasoning_started = True
                                        yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                                    full_reasoning += chunk.delta.reasoning_content
                                    iteration_reasoning += chunk.delta.reasoning_content
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': chunk.delta.reasoning_content})}\n\n"
                                    last_event_time = time.time()
                                    emitted_any = True

                                # Handle content - stream it immediately
                                if chunk.delta.content:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    full_content += chunk.delta.content
                                    iteration_content += chunk.delta.content

                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.delta.content})}\n\n"
                                    last_event_time = time.time()
                                    emitted_any = True

                                # Collect tool calls when they arrive
                                if chunk.delta.tool_calls:
                                    collected_tool_calls = chunk.delta.tool_calls
                                    emitted_any = True

                                # Handle finish
                                if chunk.finish_reason:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    if chunk.finish_reason == FinishReason.LENGTH:
                                        yield f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                                    break
                        except ContextLengthError:
                            if context_retry_used or not should_retry_context_length(
                                agent
                            ):
                                raise
                            prepared_context = await retry_prepare_model_context(
                                agent=agent,
                                conversation=conversation,
                                user_message=final_message,
                                model_id=model_id or "gpt-4",
                                model_context_limit=team_model.model.context_length
                                if team_model
                                else None,
                                model_max_output_tokens=team_model.model.max_output_tokens
                                if team_model
                                else None,
                                provider=team_model.model.provider
                                if team_model
                                else None,
                                file_content=file_content_str,
                                user_locale=current_user.locale,
                                history_override=working_history_override,
                                current_images=chat_in.images,
                                model_supports_vision=model_supports_vision,
                                current_user_message_id=user_msg.id,
                                include_current_user_message=True,
                                exclude_message_ids=[assistant_msg.id],
                                tool_timeouts=tool_timeouts,
                                user=current_user,
                                protected_round_id=round_id,
                            )
                            compression_start, compression_end = (
                                build_compression_events(
                                    agent=agent,
                                    compression=prepared_context.compression,
                                    trigger="context_length_error",
                                    retry_index=1,
                                    stage_override="reactive_retry",
                                )
                            )
                            if compression_start:
                                yield compression_start
                                last_event_time = time.time()
                            if compression_end:
                                yield compression_end
                                last_event_time = time.time()
                            context_retry_used = True
                            messages_for_llm = [
                                message.model_dump(exclude_none=True)
                                for message in prepared_context.messages
                            ]
                            iteration_input_chars = sum(
                                len(m.get("content") or "")
                                if isinstance(m.get("content"), str)
                                else 0
                                for m in messages_for_llm
                            )
                            emitted_any = False
                            client_disconnected = False
                            stream = model_manager.team_chat_stream(
                                team_id=str(agent.team_id),
                                messages=messages_for_llm,
                                model_id=model_id,
                                tools=tools,
                            )
                            async for chunk in iter_with_idle_timeout(
                                stream,
                                timeout_seconds=idle_timeout,
                                activity_predicate=_is_model_stream_activity,
                            ):
                                if await request.is_disconnected():
                                    client_disconnected = True
                                    logger.info(
                                        f"Client disconnected during stream, stopping LLM generation for conversation {conversation.id}"
                                    )
                                    break

                                if chunk.delta.reasoning_content:
                                    if not reasoning_started:
                                        reasoning_started = True
                                        yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                                    full_reasoning += chunk.delta.reasoning_content
                                    iteration_reasoning += chunk.delta.reasoning_content
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': chunk.delta.reasoning_content})}\n\n"
                                    last_event_time = time.time()
                                    emitted_any = True

                                if chunk.delta.content:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    full_content += chunk.delta.content
                                    iteration_content += chunk.delta.content
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.delta.content})}\n\n"
                                    last_event_time = time.time()
                                    emitted_any = True

                                if chunk.delta.tool_calls:
                                    collected_tool_calls = chunk.delta.tool_calls
                                    emitted_any = True

                                if chunk.finish_reason:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    if chunk.finish_reason == FinishReason.LENGTH:
                                        yield f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                                    break

                        # Fallback: if stream yields nothing and no tool calls, do a non-stream call
                        if (
                            not emitted_any
                            and not collected_tool_calls
                            and not client_disconnected
                        ):
                            response = await model_manager.team_chat(
                                team_id=str(agent.team_id),
                                messages=messages_for_llm,
                                model_id=model_id,
                                tools=tools,
                            )
                            if response.reasoning_content:
                                yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                                full_reasoning += response.reasoning_content
                                iteration_reasoning += response.reasoning_content
                                if first_token_time is None:
                                    first_token_time = time.time()
                                yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': response.reasoning_content})}\n\n"
                                yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                            if response.content:
                                full_content += response.content
                                iteration_content += response.content
                                if first_token_time is None:
                                    first_token_time = time.time()
                                yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': response.content})}\n\n"

                        # If client disconnected, save partial content and exit
                        if client_disconnected:
                            # Record usage for partial generation
                            iteration_output_chars = len(iteration_content) + len(
                                iteration_reasoning
                            )
                            if iteration_output_chars > 0:
                                await model_manager.record_stream_usage(
                                    team_id=str(agent.team_id),
                                    model_id=model_id,
                                    input_text_length=iteration_input_chars,
                                    output_text_length=iteration_output_chars,
                                )
                            assistant_msg.content = full_content
                            assistant_msg.reasoning_content = (
                                full_reasoning if full_reasoning else None
                            )
                            assistant_msg.model_used = model_id
                            assistant_msg.duration_ms = int(
                                (time.time() - start_time) * 1000
                            )
                            assistant_msg.is_manually_stopped = True
                            assistant_msg.round_status = (
                                MessageRoundStatus.MANUALLY_STOPPED
                            )
                            assistant_msg.created_at = now_utc()
                            await assistant_msg.save()
                            return  # Exit generator - client is gone

                        # Record usage for this iteration (important: do this after each stream ends)
                        iteration_output_chars = len(iteration_content) + len(
                            iteration_reasoning
                        )
                        await model_manager.record_stream_usage(
                            team_id=str(agent.team_id),
                            model_id=model_id,
                            input_text_length=iteration_input_chars,
                            output_text_length=iteration_output_chars,
                        )

                        # Check if there are tool calls to execute
                        if collected_tool_calls:
                            pending_tool_calls = []
                            # Process each tool call
                            for tc in collected_tool_calls:
                                # Check if client disconnected before tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected before tool execution"
                                    )
                                    assistant_msg.content = full_content
                                    assistant_msg.reasoning_content = (
                                        full_reasoning if full_reasoning else None
                                    )
                                    assistant_msg.model_used = model_id
                                    assistant_msg.duration_ms = int(
                                        (time.time() - start_time) * 1000
                                    )
                                    assistant_msg.is_manually_stopped = True
                                    assistant_msg.round_status = (
                                        MessageRoundStatus.MANUALLY_STOPPED
                                    )
                                    assistant_msg.created_at = now_utc()
                                    await assistant_msg.save()
                                    return

                                tool_name = tc.function.name
                                if not tool_name:
                                    logger.warning("Skipping tool call with empty name")
                                    continue
                                try:
                                    arguments = json.loads(tc.function.arguments)
                                except json.JSONDecodeError:
                                    arguments = {}

                                # Send tool_call event
                                tool_display_name = tool_display_names.get(
                                    tool_name, tool_name
                                )
                                yield f"event: {SSEEventType.TOOL_CALL}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'tool_display_name': tool_display_name, 'arguments': arguments})}\n\n"
                                last_event_time = time.time()

                                # Execute the tool (pass agent and tool_timeouts)
                                result = await execute_tool_call(
                                    tool_name,
                                    arguments,
                                    agent=agent,
                                    tool_timeouts=tool_timeouts,
                                    user=current_user,
                                    session_id=sandbox_session_id,
                                )
                                display_result, llm_result = (
                                    get_tool_execution_payloads(result)
                                )
                                pending_tool_calls.append(
                                    {
                                        "id": tc.id,
                                        "name": tool_name,
                                        "arguments": arguments,
                                        "display_result": display_result,
                                        "llm_result": llm_result,
                                        "display_name": tool_display_name,
                                    }
                                )

                                # Check if client disconnected after tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected after tool execution"
                                    )
                                    assistant_msg.content = full_content
                                    assistant_msg.reasoning_content = (
                                        full_reasoning if full_reasoning else None
                                    )
                                    assistant_msg.model_used = model_id
                                    assistant_msg.duration_ms = int(
                                        (time.time() - start_time) * 1000
                                    )
                                    assistant_msg.is_manually_stopped = True
                                    assistant_msg.round_status = (
                                        MessageRoundStatus.MANUALLY_STOPPED
                                    )
                                    assistant_msg.created_at = now_utc()
                                    await assistant_msg.save()
                                    return

                                # Send tool_result event
                                yield build_tool_result_sse_event(
                                    tool_call_id=tc.id,
                                    tool_name=tool_name,
                                    tool_display_name=tool_display_name,
                                    display_result=display_result,
                                )
                                media_result_event = build_media_result_sse_event(
                                    display_result
                                )
                                if media_result_event:
                                    yield media_result_event
                                last_event_time = time.time()

                            # Helper to safely parse arguments
                            def safe_parse_arguments(args):
                                if not args:
                                    return {}
                                if isinstance(args, dict):
                                    return args
                                try:
                                    return json.loads(args)
                                except (json.JSONDecodeError, TypeError):
                                    return {}

                            # Save intermediate assistant message with tool_calls to database
                            intermediate_tool_calls = [
                                {
                                    "id": tc_data["id"],
                                    "name": tc_data["name"],
                                    "display_name": tc_data["display_name"],
                                    "arguments": tc_data["arguments"],
                                }
                                for tc_data in pending_tool_calls
                            ]
                            assistant_step_index = next_round_index
                            await Message.create(
                                conversation=conversation,
                                role=MessageRole.ASSISTANT,
                                content=iteration_content,
                                reasoning_content=iteration_reasoning or None,
                                tool_calls=intermediate_tool_calls,
                                round_id=round_id,
                                round_index=assistant_step_index,
                                round_role=MessageRoundRole.ASSISTANT_STEP,
                                is_round_canonical=False,
                                iteration_index=iteration,
                            )
                            next_round_index += 1
                            if working_history_override is None:
                                working_history_override = []
                            append_round_history_entry(
                                working_history_override,
                                role="assistant",
                                content=iteration_content,
                                reasoning_content=iteration_reasoning or None,
                                tool_calls=intermediate_tool_calls,
                                round_id=round_id,
                                round_index=assistant_step_index,
                                round_role=MessageRoundRole.ASSISTANT_STEP.value,
                                is_round_canonical=False,
                                iteration_index=iteration,
                            )

                            # Save tool response messages to database
                            for tc_data in pending_tool_calls:
                                tool_step_index = next_round_index
                                await Message.create(
                                    conversation=conversation,
                                    role=MessageRole.TOOL,
                                    content=tc_data["display_result"],
                                    tool_call_id=tc_data["id"],
                                    tool_name=tc_data["name"],
                                    round_id=round_id,
                                    round_index=tool_step_index,
                                    round_role=MessageRoundRole.TOOL_RESULT,
                                    is_round_canonical=False,
                                    iteration_index=iteration,
                                )
                                next_round_index += 1
                                append_round_history_entry(
                                    working_history_override,
                                    role="tool",
                                    content=tc_data["llm_result"],
                                    tool_call_id=tc_data["id"],
                                    tool_name=tc_data["name"],
                                    round_id=round_id,
                                    round_index=tool_step_index,
                                    round_role=MessageRoundRole.TOOL_RESULT.value,
                                    is_round_canonical=False,
                                    iteration_index=iteration,
                                )

                            if iteration >= max_iterations:
                                max_iterations_reached = True
                                yield f"event: {SSEEventType.ITERATION_CAP_REACHED}\ndata: {json.dumps({'content': build_max_iterations_terminal_content(current_user.locale)})}\n\n"
                                last_event_time = time.time()
                                full_content = ""
                                full_reasoning = ""
                                break

                            # Continue the loop to get the final response
                            pending_tool_calls = []
                            collected_tool_calls = []
                            full_content = ""
                            full_reasoning = ""
                            continue
                        else:
                            # No tool calls, we're done
                            break

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
                    assistant_msg.model_used = model_id
                    assistant_msg.duration_ms = duration_ms
                    assistant_msg.is_manually_stopped = False
                    assistant_msg.round_status = terminal_round_status
                    # Ensure assistant message appears after tool calls/results in history
                    assistant_msg.created_at = now_utc()
                    # Estimate token usage
                    final_prepared_context = await prepare_model_context(
                        agent=agent,
                        conversation=conversation,
                        user_message=final_message,
                        model_id=model_id or "gpt-4",
                        model_context_limit=team_model.model.context_length
                        if team_model
                        else None,
                        model_max_output_tokens=team_model.model.max_output_tokens
                        if team_model
                        else None,
                        provider=team_model.model.provider if team_model else None,
                        file_content=file_content_str,
                        user_locale=current_user.locale,
                        history_override=working_history_override,
                        current_images=chat_in.images,
                        model_supports_vision=model_supports_vision,
                        current_user_message_id=user_msg.id,
                        include_current_user_message=True,
                        exclude_message_ids=[assistant_msg.id],
                        tool_timeouts=tool_timeouts,
                        user=current_user,
                        protected_round_id=round_id,
                    )
                    input_tokens = sum(
                        len(message_content or "") // 4
                        for message_content in (
                            message.get("content")
                            if isinstance(message, dict)
                            else None
                            for message in [
                                item.model_dump(exclude_none=True)
                                for item in final_prepared_context.messages
                            ]
                        )
                        if isinstance(message_content, str)
                    )
                    output_tokens = len(terminal_content) // 4
                    assistant_msg.token_usage = {
                        "prompt": input_tokens,
                        "completion": output_tokens,
                    }
                    await assistant_msg.save()
                    branch_prefix = await get_prefix_path_before(user_msg)
                    await activate_conversation_branch(
                        conversation.id,
                        [*branch_prefix, user_msg, assistant_msg],
                    )
                    enqueue_session_memory_extraction(
                        agent, conversation, assistant_msg
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
                    first_token_ms = (
                        int((first_token_time - start_time) * 1000)
                        if first_token_time
                        else None
                    )
                    tokens_per_second = (
                        round(output_tokens / (duration_ms / 1000), 1)
                        if duration_ms > 0 and output_tokens > 0
                        else None
                    )
                    yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens}, 'timing': {'first_token_ms': first_token_ms, 'duration_ms': duration_ms, 'tokens_per_second': tokens_per_second}, 'version_number': 1, 'version_count': 1})}\n\n"

                except (QuotaExceededError, InsufficientQuotaError) as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.warning("Quota exceeded during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except ModelNotFoundError as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.error("Model not found error during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_NOT_FOUND, 'msg': t('model_not_found')})}\n\n"
                except AuthenticationError as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.error("Authentication error during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNAUTHORIZED, 'msg': t('unauthorized')})}\n\n"
                except RateLimitError as e:
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    logger.warning("Rate limit error during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('rate_limit_exceeded')})}\n\n"
                except LLMError:
                    logger.exception("LLM error during stream")
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"
                except StreamIdleTimeoutError:
                    logger.warning(
                        "Stream idle timeout (%ss) for conversation %s",
                        idle_timeout,
                        conversation.id,
                    )
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t("stream_timeout_exceeded"),
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': idle_timeout})}\n\n"
                except Exception:
                    logger.exception("Unexpected error during stream")
                    await persist_partial_round_error(
                        assistant_msg,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"

        except TimeoutError:
            # Global timeout
            logger.warning(
                f"Stream global timeout ({global_timeout}s) for conversation {conversation.id}"
            )
            await persist_partial_round_error(
                assistant_msg,
                content=full_content,
                reasoning=full_reasoning,
                model_id=model_id,
                start_time=start_time,
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
                assistant_msg.model_used = model_id
                assistant_msg.duration_ms = int((time.time() - start_time) * 1000)
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
            logger.error("Unhandled stream error: %s", type(exc).__name__)
            if assistant_msg:
                await persist_partial_round_error(
                    assistant_msg,
                    content=full_content,
                    reasoning=full_reasoning,
                    model_id=model_id,
                    start_time=start_time,
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

    # Also get all child versions
    child_versions = await Message.filter(parent_id=root_id).all()

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
    count = await Message.filter(parent_id=root_id).count()
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

    prefix = await get_prefix_path_before(target_version)
    descendant_branch = await find_descendant_branch_from(target_version)
    await activate_conversation_branch(
        message.conversation_id,
        [*prefix, *descendant_branch],
    )
    await stale_session_memory_if_source_outside_active_branch(message.conversation_id)

    return success(
        data=await build_message_out_with_versions(
            target_version, include_versions=True
        )
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

    prefix_for_message = await get_prefix_path_before(message)
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
        model_id: str | None = None
        global_timeout: float = 1800.0  # Default 30 minutes
        idle_timeout: float = 300.0  # Default 5 minutes

        try:
            from app.llm import model_manager
            from app.llm.errors import QuotaExceededError, LLMError
            from app.llm.types import (
                ToolDefinition,
                FunctionDefinition,
                FinishReason,
            )

            async def activate_regenerated_path() -> None:
                if not new_message:
                    return
                prefix = await get_prefix_path_before(new_message)
                await activate_conversation_branch(
                    conversation.id,
                    [*prefix, new_message],
                )
                await stale_session_memory_if_source_outside_active_branch(
                    conversation.id
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

                    # Get current version count
                    current_version_count = await get_branch_version_count(message)
                    new_version_number = current_version_count + 1
                    branch_parent_id = message.branch_parent_id
                    if branch_parent_id is None:
                        prefix = await get_prefix_path_before(message)
                        branch_parent_id = prefix[-1].id if prefix else None

                    round_id = uuid4()
                    next_round_index = 1

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

                    # Send message_start event with version info
                    yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': new_message_id, 'version_number': new_version_number, 'version_count': new_version_number, 'parent_id': str(root_id)})}\n\n"
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
                                agent, user_message.content
                            )
                            if rag_contexts:
                                rag_contexts = aggregate_rag_contexts(rag_contexts)
                                yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                                last_event_time = time.time()
                            final_message = build_rag_prompt(
                                rag_contexts, user_message.content
                            )

                    team_model = await get_agent_chat_model(agent)
                    model_id = (
                        f"{team_model.model.provider}/{team_model.model.model_id}"
                        if team_model
                        else None
                    )
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
                    max_iterations = agent.max_iterations or 5
                    iteration = 0
                    max_iterations_reached = False

                    while iteration < max_iterations:
                        iteration += 1

                        pending_tool_calls = []

                        # Heartbeat check and send
                        (
                            should_continue,
                            new_last_event_time,
                        ) = await send_heartbeat_if_needed(
                            last_event_time, heartbeat_interval, request
                        )
                        if not should_continue:
                            # Client disconnected, save current stopped state and exit
                            new_message.content = full_content
                            new_message.reasoning_content = (
                                full_reasoning if full_reasoning else None
                            )
                            new_message.model_used = model_id
                            new_message.duration_ms = int(
                                (time.time() - start_time) * 1000
                            )
                            new_message.is_manually_stopped = True
                            new_message.round_status = (
                                MessageRoundStatus.MANUALLY_STOPPED
                            )
                            new_message.created_at = now_utc()
                            await new_message.save()
                            await activate_regenerated_path()
                            return

                        # If we need to send heartbeat
                        if new_last_event_time > last_event_time:
                            yield ": heartbeat\n\n"
                            last_event_time = new_last_event_time

                        reasoning_started = False
                        full_content = ""
                        full_reasoning = ""
                        collected_tool_calls = []
                        client_disconnected = False
                        context_retry_used = False
                        try:
                            prepared_context = await prepare_model_context(
                                agent=agent,
                                conversation=conversation,
                                user_message=final_message,
                                model_id=model_id or "gpt-4",
                                model_context_limit=team_model.model.context_length
                                if team_model
                                else None,
                                model_max_output_tokens=team_model.model.max_output_tokens
                                if team_model
                                else None,
                                provider=team_model.model.provider
                                if team_model
                                else None,
                                user_locale=current_user.locale,
                                history_override=working_history_override,
                                current_user_message_id=user_message.id,
                                include_current_user_message=True,
                                history_before_message_created_at=message.created_at,
                                tool_timeouts=tool_timeouts,
                                user=current_user,
                                protected_round_id=round_id,
                            )
                            compression_start, compression_end = (
                                build_compression_events(
                                    agent=agent,
                                    compression=prepared_context.compression,
                                    trigger=get_compression_trigger(
                                        prepared_context.compression
                                    ),
                                )
                            )
                            if compression_start:
                                yield compression_start
                                last_event_time = time.time()
                            if compression_end:
                                yield compression_end
                                last_event_time = time.time()
                        except ContextLengthError:
                            if not should_retry_context_length(agent):
                                raise
                            prepared_context = await retry_prepare_model_context(
                                agent=agent,
                                conversation=conversation,
                                user_message=final_message,
                                model_id=model_id or "gpt-4",
                                model_context_limit=team_model.model.context_length
                                if team_model
                                else None,
                                model_max_output_tokens=team_model.model.max_output_tokens
                                if team_model
                                else None,
                                provider=team_model.model.provider
                                if team_model
                                else None,
                                user_locale=current_user.locale,
                                history_override=working_history_override,
                                current_user_message_id=user_message.id,
                                include_current_user_message=True,
                                history_before_message_created_at=message.created_at,
                                tool_timeouts=tool_timeouts,
                                user=current_user,
                                protected_round_id=round_id,
                            )
                            compression_start, compression_end = (
                                build_compression_events(
                                    agent=agent,
                                    compression=prepared_context.compression,
                                    trigger="context_length_error",
                                    retry_index=1,
                                    stage_override="reactive_retry",
                                )
                            )
                            if compression_start:
                                yield compression_start
                                last_event_time = time.time()
                            if compression_end:
                                yield compression_end
                                last_event_time = time.time()
                            context_retry_used = True
                        messages_for_llm = [
                            item.model_dump(exclude_none=True)
                            for item in prepared_context.messages
                        ]

                        try:
                            stream = model_manager.team_chat_stream(
                                team_id=str(agent.team_id),
                                messages=messages_for_llm,
                                model_id=model_id,
                                tools=tools,
                            )
                            async for chunk in iter_with_idle_timeout(
                                stream,
                                timeout_seconds=idle_timeout,
                                activity_predicate=_is_model_stream_activity,
                            ):
                                # Check if client disconnected - stop LLM generation to save tokens
                                if await request.is_disconnected():
                                    client_disconnected = True
                                    logger.info(
                                        f"Client disconnected during regenerate stream, stopping LLM generation for message {new_message_id}"
                                    )
                                    break

                                if chunk.delta.reasoning_content:
                                    if not reasoning_started:
                                        reasoning_started = True
                                        yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                                    full_reasoning += chunk.delta.reasoning_content
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': chunk.delta.reasoning_content})}\n\n"
                                    last_event_time = time.time()

                                if chunk.delta.content:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    full_content += chunk.delta.content

                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    # Stream content normally
                                    yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.delta.content})}\n\n"
                                    last_event_time = time.time()

                                if chunk.delta.tool_calls:
                                    collected_tool_calls = chunk.delta.tool_calls

                                if chunk.finish_reason:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    if chunk.finish_reason == FinishReason.LENGTH:
                                        yield f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                                    break
                        except ContextLengthError:
                            if context_retry_used or not should_retry_context_length(
                                agent
                            ):
                                raise
                            prepared_context = await retry_prepare_model_context(
                                agent=agent,
                                conversation=conversation,
                                user_message=final_message,
                                model_id=model_id or "gpt-4",
                                model_context_limit=team_model.model.context_length
                                if team_model
                                else None,
                                model_max_output_tokens=team_model.model.max_output_tokens
                                if team_model
                                else None,
                                provider=team_model.model.provider
                                if team_model
                                else None,
                                user_locale=current_user.locale,
                                history_override=working_history_override,
                                current_user_message_id=user_message.id,
                                include_current_user_message=True,
                                history_before_message_created_at=message.created_at,
                                tool_timeouts=tool_timeouts,
                                user=current_user,
                                protected_round_id=round_id,
                            )
                            compression_start, compression_end = (
                                build_compression_events(
                                    agent=agent,
                                    compression=prepared_context.compression,
                                    trigger="context_length_error",
                                    retry_index=1,
                                    stage_override="reactive_retry",
                                )
                            )
                            if compression_start:
                                yield compression_start
                                last_event_time = time.time()
                            if compression_end:
                                yield compression_end
                                last_event_time = time.time()
                            context_retry_used = True
                            messages_for_llm = [
                                item.model_dump(exclude_none=True)
                                for item in prepared_context.messages
                            ]
                            stream = model_manager.team_chat_stream(
                                team_id=str(agent.team_id),
                                messages=messages_for_llm,
                                model_id=model_id,
                                tools=tools,
                            )
                            async for chunk in iter_with_idle_timeout(
                                stream,
                                timeout_seconds=idle_timeout,
                                activity_predicate=_is_model_stream_activity,
                            ):
                                if await request.is_disconnected():
                                    client_disconnected = True
                                    logger.info(
                                        f"Client disconnected during regenerate stream, stopping LLM generation for message {new_message_id}"
                                    )
                                    break

                                if chunk.delta.reasoning_content:
                                    if not reasoning_started:
                                        reasoning_started = True
                                        yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                                    full_reasoning += chunk.delta.reasoning_content
                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': chunk.delta.reasoning_content})}\n\n"
                                    last_event_time = time.time()

                                if chunk.delta.content:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    full_content += chunk.delta.content

                                    if first_token_time is None:
                                        first_token_time = time.time()
                                    yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.delta.content})}\n\n"
                                    last_event_time = time.time()

                                if chunk.delta.tool_calls:
                                    collected_tool_calls = chunk.delta.tool_calls

                                if chunk.finish_reason:
                                    if reasoning_started and not full_content:
                                        yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                                    if chunk.finish_reason == FinishReason.LENGTH:
                                        yield f"event: {SSEEventType.OUTPUT_TRUNCATED}\ndata: {json.dumps({})}\n\n"
                                    break

                        # If client disconnected, save current stopped state and exit
                        if client_disconnected:
                            new_message.content = full_content
                            new_message.reasoning_content = (
                                full_reasoning if full_reasoning else None
                            )
                            new_message.model_used = model_id
                            new_message.duration_ms = int(
                                (time.time() - start_time) * 1000
                            )
                            new_message.is_manually_stopped = True
                            new_message.round_status = (
                                MessageRoundStatus.MANUALLY_STOPPED
                            )
                            new_message.created_at = now_utc()
                            await new_message.save()
                            return  # Exit generator - client is gone

                        if collected_tool_calls:
                            # Handle tool calls (simplified)
                            for tc in collected_tool_calls:
                                # Check if client disconnected before tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected before tool execution in regenerate"
                                    )
                                    new_message.content = full_content
                                    new_message.reasoning_content = (
                                        full_reasoning if full_reasoning else None
                                    )
                                    new_message.model_used = model_id
                                    new_message.duration_ms = int(
                                        (time.time() - start_time) * 1000
                                    )
                                    new_message.is_manually_stopped = True
                                    new_message.round_status = (
                                        MessageRoundStatus.MANUALLY_STOPPED
                                    )
                                    new_message.created_at = now_utc()
                                    await new_message.save()
                                    return

                                tool_name = tc.function.name
                                try:
                                    arguments = json.loads(tc.function.arguments)
                                except json.JSONDecodeError:
                                    arguments = {}

                                tool_display_name = tool_display_names.get(
                                    tool_name, tool_name
                                )
                                yield f"event: {SSEEventType.TOOL_CALL}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'tool_display_name': tool_display_name, 'arguments': arguments})}\n\n"
                                last_event_time = time.time()

                                result = await execute_tool_call(
                                    tool_name,
                                    arguments,
                                    agent=agent,
                                    tool_timeouts=tool_timeouts,
                                    user=current_user,
                                    session_id=sandbox_session_id,
                                )
                                display_result, llm_result = (
                                    get_tool_execution_payloads(result)
                                )
                                pending_tool_calls.append(
                                    {
                                        "id": tc.id,
                                        "name": tool_name,
                                        "arguments": arguments,
                                        "display_result": display_result,
                                        "llm_result": llm_result,
                                        "display_name": tool_display_name,
                                    }
                                )

                                # Check if client disconnected after tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected after tool execution in regenerate"
                                    )
                                    new_message.content = full_content
                                    new_message.reasoning_content = (
                                        full_reasoning if full_reasoning else None
                                    )
                                    new_message.model_used = model_id
                                    new_message.duration_ms = int(
                                        (time.time() - start_time) * 1000
                                    )
                                    new_message.is_manually_stopped = True
                                    new_message.round_status = (
                                        MessageRoundStatus.MANUALLY_STOPPED
                                    )
                                    new_message.created_at = now_utc()
                                    await new_message.save()
                                    return

                                yield build_tool_result_sse_event(
                                    tool_call_id=tc.id,
                                    tool_name=tool_name,
                                    tool_display_name=tool_display_name,
                                    display_result=display_result,
                                )
                                media_result_event = build_media_result_sse_event(
                                    display_result
                                )
                                if media_result_event:
                                    yield media_result_event
                                last_event_time = time.time()

                                assistant_step_index = next_round_index
                                await Message.create(
                                    conversation=conversation,
                                    role=MessageRole.ASSISTANT,
                                    content=full_content,
                                    reasoning_content=full_reasoning or None,
                                    tool_calls=[
                                        {
                                            "id": tc.id,
                                            "name": tool_name,
                                            "display_name": tool_display_name,
                                            "arguments": arguments,
                                        }
                                    ],
                                    parent_id=new_message.parent_id or new_message.id,
                                    version_number=new_version_number,
                                    branch_parent_id=new_message.id,
                                    round_id=round_id,
                                    round_index=assistant_step_index,
                                    round_role=MessageRoundRole.ASSISTANT_STEP,
                                    is_round_canonical=False,
                                    iteration_index=iteration,
                                )
                                next_round_index += 1
                                tool_step_index = next_round_index
                                await Message.create(
                                    conversation=conversation,
                                    role=MessageRole.TOOL,
                                    content=display_result,
                                    tool_call_id=tc.id,
                                    tool_name=tool_name,
                                    parent_id=new_message.parent_id or new_message.id,
                                    version_number=new_version_number,
                                    branch_parent_id=new_message.id,
                                    round_id=round_id,
                                    round_index=tool_step_index,
                                    round_role=MessageRoundRole.TOOL_RESULT,
                                    is_round_canonical=False,
                                    iteration_index=iteration,
                                )
                                next_round_index += 1
                                if working_history_override is None:
                                    working_history_override = []
                                append_round_history_entry(
                                    working_history_override,
                                    role="assistant",
                                    content=full_content,
                                    reasoning_content=full_reasoning or None,
                                    tool_calls=[
                                        {
                                            "id": tc.id,
                                            "name": tool_name,
                                            "display_name": tool_display_name,
                                            "arguments": arguments,
                                        }
                                    ],
                                    round_id=round_id,
                                    round_index=assistant_step_index,
                                    round_role=MessageRoundRole.ASSISTANT_STEP.value,
                                    is_round_canonical=False,
                                    iteration_index=iteration,
                                )
                                append_round_history_entry(
                                    working_history_override,
                                    role="tool",
                                    content=llm_result,
                                    tool_call_id=tc.id,
                                    tool_name=tool_name,
                                    round_id=round_id,
                                    round_index=tool_step_index,
                                    round_role=MessageRoundRole.TOOL_RESULT.value,
                                    is_round_canonical=False,
                                    iteration_index=iteration,
                                )
                                full_content = ""
                                full_reasoning = ""

                            if iteration >= max_iterations:
                                max_iterations_reached = True
                                yield f"event: {SSEEventType.ITERATION_CAP_REACHED}\ndata: {json.dumps({'content': build_max_iterations_terminal_content(current_user.locale)})}\n\n"
                                last_event_time = time.time()
                                full_content = ""
                                full_reasoning = ""
                                break

                            continue
                        else:
                            break

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
                    new_message.model_used = model_id
                    new_message.duration_ms = duration_ms
                    new_message.is_manually_stopped = False
                    new_message.round_status = terminal_round_status
                    # Ensure regenerated message appears after tool calls/results in history
                    new_message.created_at = now_utc()
                    final_prepared_context = await prepare_model_context(
                        agent=agent,
                        conversation=conversation,
                        user_message=final_message,
                        model_id=model_id or "gpt-4",
                        model_context_limit=team_model.model.context_length
                        if team_model
                        else None,
                        model_max_output_tokens=team_model.model.max_output_tokens
                        if team_model
                        else None,
                        provider=team_model.model.provider if team_model else None,
                        user_locale=current_user.locale,
                        history_override=working_history_override,
                        current_user_message_id=user_message.id,
                        include_current_user_message=True,
                        history_before_message_created_at=message.created_at,
                        tool_timeouts=tool_timeouts,
                        user=current_user,
                        protected_round_id=round_id,
                    )
                    input_tokens = sum(
                        len(message_content or "") // 4
                        for message_content in (
                            message.get("content")
                            if isinstance(message, dict)
                            else None
                            for message in [
                                item.model_dump(exclude_none=True)
                                for item in final_prepared_context.messages
                            ]
                        )
                        if isinstance(message_content, str)
                    )
                    output_tokens = len(terminal_content) // 4
                    new_message.token_usage = {
                        "prompt": input_tokens,
                        "completion": output_tokens,
                    }
                    await new_message.save()
                    prefix = await get_prefix_path_before(new_message)
                    await activate_conversation_branch(
                        conversation.id,
                        [*prefix, new_message],
                    )
                    await stale_session_memory_if_source_outside_active_branch(
                        conversation.id
                    )
                    enqueue_session_memory_extraction(agent, conversation, new_message)

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

                    first_token_ms = (
                        int((first_token_time - start_time) * 1000)
                        if first_token_time
                        else None
                    )
                    tokens_per_second = (
                        round(output_tokens / (duration_ms / 1000), 1)
                        if duration_ms > 0 and output_tokens > 0
                        else None
                    )
                    yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens}, 'timing': {'first_token_ms': first_token_ms, 'duration_ms': duration_ms, 'tokens_per_second': tokens_per_second}, 'version_number': new_version_number, 'version_count': new_version_number})}\n\n"

                except (QuotaExceededError, InsufficientQuotaError) as e:
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.warning("Quota exceeded during regenerate: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except LLMError:
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.exception("LLM error during regenerate")
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"
                except StreamIdleTimeoutError:
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t("stream_timeout_exceeded"),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.warning(
                        "Regenerate stream idle timeout (%ss) for message %s",
                        idle_timeout,
                        message_id,
                    )
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': idle_timeout})}\n\n"
                except Exception:
                    preserved_partial = await persist_partial_round_error(
                        new_message,
                        content=full_content,
                        reasoning=full_reasoning,
                        model_id=model_id,
                        start_time=start_time,
                        fallback_content=t(GENERIC_STREAM_ERROR_KEY),
                    )
                    if preserved_partial:
                        await activate_regenerated_path()
                    else:
                        if new_message_id:
                            await Message.filter(id=new_message_id).delete()
                        await restore_original_path()
                    logger.exception("Unexpected error during regenerate")
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t(GENERIC_STREAM_ERROR_KEY)})}\n\n"

        except TimeoutError:
            # Global timeout
            logger.warning(
                f"Regenerate stream global timeout ({global_timeout}s) for message {message_id}"
            )
            preserved_partial = await persist_partial_round_error(
                new_message,
                content=full_content,
                reasoning=full_reasoning,
                model_id=model_id,
                start_time=start_time,
                fallback_content=t("stream_timeout_exceeded"),
            )
            if preserved_partial:
                await activate_regenerated_path()
            elif new_message_id:
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
                new_message.model_used = model_id
                new_message.duration_ms = int((time.time() - start_time) * 1000)
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
            logger.error("Unhandled regenerate stream error: %s", type(exc).__name__)
            preserved_partial = await persist_partial_round_error(
                new_message,
                content=full_content,
                reasoning=full_reasoning,
                model_id=model_id,
                start_time=start_time,
                fallback_content=t(GENERIC_STREAM_ERROR_KEY),
            )
            if preserved_partial:
                await activate_regenerated_path()
            elif new_message_id:
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
