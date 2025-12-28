"""
Chat API endpoints for Agent conversations.
Provides streaming and non-streaming chat with AI agents.
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Any
from uuid import UUID
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tortoise.expressions import F

from app.api import deps
from app.models.user import User
from app.models.model import TeamModel
from app.models.agent import (
    Agent,
    AgentKnowledgeBase,
    AgentStatus,
    AgentVisibility,
    Conversation,
    Message,
    MessageRole,
)

from app.schemas.agent import (
    ChatRequest,
    ChatResponse,
    MessageOut,
    MessageVersion,
    SwitchVersionRequest,
    RegenerateRequest,
    SSEEventType,
)
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.llm.tools import tool_registry

if TYPE_CHECKING:
    from app.models.tool import Tool


# Local message types to avoid circular import
class LLMMessageRole(str, Enum):
    """LLM message role"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """LLM chat message"""

    role: LLMMessageRole
    content: str | None = None
    tool_call_id: str | None = None


router = APIRouter()
logger = logging.getLogger(__name__)


# ============ Helper Functions ============


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

    # Draft agents can only be used by creator
    if agent.status == AgentStatus.DRAFT:
        if agent.created_by.id != user.id and not user.is_superuser:
            raise BusinessError(
                code=ResponseCode.AGENT_NOT_PUBLISHED,
                msg_key="agent_not_published",
                status_code=403,
            )

    # Check visibility
    if agent.visibility == AgentVisibility.PRIVATE:
        if agent.created_by.id != user.id and not user.is_superuser:
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

    return conversation


async def build_messages(
    agent: Agent, conversation: Conversation, user_message: str
) -> list[LLMMessage]:
    """Build message list for LLM call."""
    messages: list[LLMMessage] = []

    # System prompt
    if agent.system_prompt:
        # Replace variables in system prompt
        system_prompt = agent.system_prompt
        for key, value in conversation.variables.items():
            system_prompt = system_prompt.replace(f"{{{{{key}}}}}", str(value))

        messages.append(LLMMessage(role=LLMMessageRole.SYSTEM, content=system_prompt))

    # Load conversation history (only active messages)
    history = await Message.filter(
        conversation_id=conversation.id, is_active=True
    ).order_by("created_at")
    for msg in history:
        if msg.role == MessageRole.USER:
            messages.append(LLMMessage(role=LLMMessageRole.USER, content=msg.content))
        elif msg.role == MessageRole.ASSISTANT:
            messages.append(
                LLMMessage(role=LLMMessageRole.ASSISTANT, content=msg.content)
            )
        elif msg.role == MessageRole.TOOL:
            messages.append(
                LLMMessage(
                    role=LLMMessageRole.TOOL,
                    content=msg.content,
                    tool_call_id=msg.tool_call_id,
                )
            )

    # Add current user message
    messages.append(LLMMessage(role=LLMMessageRole.USER, content=user_message))

    return messages


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
    """
    from app.models.tool import Tool
    from app.models.agent import RAGMode

    tools_config = agent.tools_config or []
    openai_tools: list[dict] = []

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

    for config in tools_config:
        tool_type = config.get("type")

        if tool_type == "builtin":
            tool_name = config.get("name")
            if tool_name:
                # Get builtin tool definition
                builtin_tools = tool_registry.to_openai_tools([tool_name])
                openai_tools.extend(builtin_tools)

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


async def execute_tool_call(
    tool_name: str, arguments: dict, agent: Agent | None = None
) -> str:
    """
    Execute a tool and return the result as string.

    Args:
        tool_name: Tool name (for builtin) or custom_<name> (for custom) or mcp_<tool_id>_<tool_name> (for MCP)
        arguments: Tool arguments
        agent: Agent instance (required for knowledge_search)
    """
    from app.models.tool import Tool, CustomToolType

    try:
        # Handle knowledge_search - internal tool for RAG
        if tool_name == "knowledge_search":
            if not agent:
                return json.dumps(
                    {"error": "Agent context required for knowledge_search"},
                    ensure_ascii=False,
                )

            query = arguments.get("query", "")
            if not query:
                return json.dumps(
                    {"error": "Query parameter is required"}, ensure_ascii=False
                )

            # Use existing RAG retrieval function
            rag_contexts = await perform_rag_retrieval(agent, query)

            if not rag_contexts:
                return json.dumps(
                    {"message": "No relevant information found in the knowledge base."},
                    ensure_ascii=False,
                )

            # Format results for LLM
            results = []
            for ctx in rag_contexts:
                results.append(
                    {
                        "source": f"{ctx['kb_name']} - {ctx['document_name']}",
                        "content": ctx["content"],
                        "relevance_score": ctx.get("score", 0),
                    }
                )

            return json.dumps({"results": results}, ensure_ascii=False)

        # Check if it's an MCP tool (format: mcp_<server_name>_<tool_name>)
        if tool_name.startswith("mcp_"):
            from app.llm.tools.mcp_client import execute_mcp_tool

            # Parse server_name and actual tool name
            parts = tool_name.split(
                "_", 2
            )  # Split into ["mcp", "<server_name>", "<tool_name>"]
            if len(parts) < 3:
                return json.dumps(
                    {"error": f"Invalid MCP tool name format: {tool_name}"},
                    ensure_ascii=False,
                )

            server_name = parts[1]
            actual_tool_name = parts[2]

            # Get MCP tool from database by name (need agent's team_id)
            if not agent:
                return json.dumps(
                    {"error": "Agent context required for MCP tool"}, ensure_ascii=False
                )

            mcp_tool = await Tool.filter(
                name=server_name, team_id=agent.team_id, is_enabled=True
            ).first()
            if not mcp_tool:
                return json.dumps(
                    {"error": f"MCP tool not found: {server_name}"}, ensure_ascii=False
                )

            if not mcp_tool.mcp_config:
                return json.dumps(
                    {"error": f"MCP tool has no configuration: {mcp_tool.name}"},
                    ensure_ascii=False,
                )

            # Execute MCP tool
            result = await execute_mcp_tool(
                mcp_tool.mcp_config, actual_tool_name, arguments
            )

            if result.success:
                if isinstance(result.result, (dict, list)):
                    return json.dumps(result.result, ensure_ascii=False)
                return str(result.result) if result.result is not None else ""
            else:
                return json.dumps(
                    {"error": result.error or "MCP tool execution failed"},
                    ensure_ascii=False,
                )

        # Check if it's a custom tool
        if tool_name.startswith("custom_"):
            actual_name = tool_name[7:]  # Remove "custom_" prefix

            # Get custom tool from database
            custom_tool = await Tool.filter(name=actual_name, is_enabled=True).first()
            if not custom_tool:
                return json.dumps(
                    {"error": f"Custom tool '{actual_name}' not found"},
                    ensure_ascii=False,
                )

            # Execute based on custom_type
            if custom_tool.custom_type == CustomToolType.HTTP:
                result = await execute_http_tool(custom_tool, arguments)
                return result
            elif custom_tool.custom_type == CustomToolType.CODE:
                result = await execute_code_tool(custom_tool, arguments)
                return result
            else:
                return json.dumps(
                    {
                        "error": f"Unsupported custom tool type: {custom_tool.custom_type}"
                    },
                    ensure_ascii=False,
                )
        else:
            # Builtin tool
            result = await tool_registry.execute(tool_name, arguments)
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
    except Exception as e:
        logger.exception(f"Tool execution error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def execute_http_tool(tool: "Tool", arguments: dict) -> str:
    """
    Execute an HTTP-based custom tool.
    """
    from app.llm.tools.executors import (
        execute_http_tool as shared_execute_http_tool,
        format_http_result_for_llm,
    )

    result = await shared_execute_http_tool(
        http_config=tool.http_config,
        arguments=arguments,
        credentials=tool.credentials,
    )
    return format_http_result_for_llm(result)


async def execute_code_tool(tool: "Tool", arguments: dict) -> str:
    """
    Execute a code-based custom tool.

    Args:
        tool: The Tool model instance
        arguments: Tool arguments passed from LLM

    Returns:
        JSON string with execution result
    """
    from app.llm.tools.sandbox import execute_code

    code_config = tool.code_config or {}
    language = code_config.get("language", "python")
    code = code_config.get("code", "")

    if not code:
        return json.dumps(
            {"error": "No code defined for this tool"}, ensure_ascii=False
        )

    try:
        exec_result = await execute_code(
            language=language,
            code=code,
            params=arguments,
            timeout=30.0,
        )

        if exec_result.success:
            result = exec_result.result
            # Include stdout logs if present
            if exec_result.stdout:
                if isinstance(result, dict):
                    result["__logs__"] = exec_result.stdout
                else:
                    result = {"value": result, "__logs__": exec_result.stdout}
            return (
                json.dumps(result, ensure_ascii=False)
                if isinstance(result, (dict, list))
                else str(result)
            )
        else:
            return json.dumps(
                {
                    "error": exec_result.error or "Code execution failed",
                    "logs": exec_result.stdout or "",
                },
                ensure_ascii=False,
            )

    except Exception as e:
        logger.exception(f"Code tool execution error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def perform_rag_retrieval(agent: Agent, query: str) -> list[dict]:
    """Perform RAG retrieval from knowledge bases."""
    from app.services.vector_store import VectorStore

    rag_contexts: list[dict] = []

    # Get knowledge base associations
    kb_associations = await AgentKnowledgeBase.filter(
        agent_id=agent.id
    ).prefetch_related("knowledge_base")

    for akb in kb_associations:
        kb = akb.knowledge_base

        # Skip if KB has no embedding model
        if not kb.embedding_model_id:
            continue

        try:
            vector_store = VectorStore(
                embedding_model_id=str(kb.embedding_model_id),
                team_id=str(kb.team_id),
            )

            results = await vector_store.search(
                kb_id=kb.id,
                query=query,
                search_mode="hybrid",
                top_k=akb.retrieval_top_k,
                score_threshold=akb.score_threshold,
            )

            for result in results:
                rag_contexts.append(
                    {
                        "kb_id": str(kb.id),
                        "kb_name": kb.name,
                        "document_id": str(result.get("document_id")),
                        "document_name": result.get("document_name"),
                        "content": result.get("content"),
                        "score": result.get("score"),
                    }
                )
        except Exception as e:
            logger.warning(f"RAG retrieval failed for KB {kb.id}: {e}")

    return rag_contexts


def build_rag_prompt(rag_contexts: list[dict], user_message: str) -> str:
    """Build user message with RAG context and citation instructions."""
    if not rag_contexts:
        return user_message

    # Build numbered references
    references = []
    for i, ctx in enumerate(rag_contexts, 1):
        references.append(
            f"[[ref:{i}]] {ctx['kb_name']} - {ctx['document_name']}:\n{ctx['content']}"
        )

    context_text = "\n\n---\n\n".join(references)

    return f"""The following reference materials may help you answer the user's question.
Use them ONLY if they are relevant to the question.

If you use information from a reference, cite it using [[cite:N]] format where N is the reference number.
Only cite sources you actually use. Do not cite if the information comes from your general knowledge.

Reference Materials:

{context_text}

---

User question: {user_message}

Remember: Only use [[cite:N]] citations when you actually use information from the references above."""


# ============ Chat Endpoints ============


@router.post("/{agent_id}/chat", response_model=Response[ChatResponse])
async def chat(
    agent_id: UUID,
    chat_in: ChatRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Chat with an agent (non-streaming).

    Creates a new conversation if conversation_id is not provided.
    """
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
        final_message = build_rag_prompt(rag_contexts, chat_in.message)

    # Save user message
    await Message.create(
        conversation=conversation,
        role=MessageRole.USER,
        content=chat_in.message,
        rag_context=rag_contexts if rag_contexts else None,
    )

    # Build messages for LLM
    messages = await build_messages(agent, conversation, final_message)

    # Get model identifier
    model_id = await get_model_identifier(agent)

    try:
        # Import here to avoid circular import
        from app.llm import model_manager
        from app.llm.errors import QuotaExceededError, LLMError

        # Call LLM with team-level tracking
        response = await model_manager.team_chat(
            team_id=str(agent.team_id),
            messages=messages,
            model_id=model_id,
        )

        duration_ms = int((time.time() - start_time) * 1000)

        # Save assistant message
        assistant_msg = await Message.create(
            conversation=conversation,
            role=MessageRole.ASSISTANT,
            content=response.content or "",
            model_used=response.model,
            token_usage={
                "prompt": response.usage.prompt_tokens if response.usage else 0,
                "completion": response.usage.completion_tokens if response.usage else 0,
            },
            duration_ms=duration_ms,
            tool_calls=[tc.model_dump() for tc in response.tool_calls]
            if response.tool_calls
            else None,
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
            token_usage=F("token_usage")
            + (response.usage.total_tokens if response.usage else 0),
            **title_update,
        )

        # Update agent stats atomically
        await Agent.filter(id=agent.id).update(message_count=F("message_count") + 2)

        return success(
            data=ChatResponse(
                conversation_id=conversation.id,
                message=MessageOut.model_validate(assistant_msg),
                usage=response.usage.model_dump() if response.usage else None,
            ),
            msg_key="chat_success",
        )

    except QuotaExceededError as e:
        raise BusinessError(
            code=ResponseCode.MODEL_QUOTA_EXCEEDED,
            msg_key="model_quota_exceeded",
            status_code=429,
            data={"quota_type": e.quota_type},
        )
    except LLMError as e:
        logger.exception(f"LLM error during chat: {e}")
        raise BusinessError(
            code=ResponseCode.UNKNOWN_ERROR,
            msg=str(e),
            status_code=500,
        )


@router.post("/{agent_id}/chat/stream")
async def chat_stream(
    agent_id: UUID,
    chat_in: ChatRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> StreamingResponse:
    """
    Chat with an agent (streaming via SSE).

    Returns Server-Sent Events with the following event types:
    - message_start: {"conversation_id": "...", "message_id": "..."}
    - content_delta: {"delta": "..."}
    - rag_context: {"contexts": [...]}
    - tool_call: {"tool_name": "...", "arguments": {...}}
    - tool_result: {"tool_name": "...", "result": {...}}
    - message_end: {"usage": {...}}
    - error: {"code": ..., "msg": "..."}
    """
    agent = await check_agent_chat_access(agent_id, current_user)
    conversation = await get_or_create_conversation(
        agent, current_user, chat_in.conversation_id, chat_in.variables
    )

    async def event_generator():
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
            Message as LLMTypeMessage,
            MessageRole as LLMTypeRole,
            ToolDefinition,
            FunctionDefinition,
            ToolCall as LLMToolCall,
            FunctionCall as LLMFunctionCall,
            ContentPart,
            ContentType,
            ImageContent,
        )

        start_time = time.time()
        full_content = ""
        message_id = None

        try:
            from app.models.agent import RAGMode

            # Check if model supports vision when images are provided (before creating messages)
            model_supports_vision = False
            if chat_in.images and agent.enable_vision:
                model_capabilities = await get_model_capabilities(agent)
                model_supports_vision = model_capabilities.get("vision", False)
                if not model_supports_vision:
                    # Model doesn't support vision - send error event with i18n key
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_VISION_NOT_SUPPORTED, 'msg': 'model_vision_not_supported'})}\n\n"
                    return

            # Handle RAG based on mode
            rag_contexts: list[dict] = []
            final_message = chat_in.message

            if agent.rag_mode == RAGMode.AUTO:
                # Traditional RAG: automatically retrieve on every message
                has_knowledge_bases = await AgentKnowledgeBase.exists(agent_id=agent.id)
                if has_knowledge_bases:
                    yield f"event: {SSEEventType.RAG_START}\ndata: {json.dumps({})}\n\n"
                    rag_contexts = await perform_rag_retrieval(agent, chat_in.message)
                    if rag_contexts:
                        yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                    final_message = build_rag_prompt(rag_contexts, chat_in.message)

            # Save user message
            user_msg = await Message.create(
                conversation=conversation,
                role=MessageRole.USER,
                content=chat_in.message,
                rag_context=rag_contexts if rag_contexts else None,
            )

            # Create placeholder for assistant message
            assistant_msg = await Message.create(
                conversation=conversation,
                role=MessageRole.ASSISTANT,
                content="",  # Will be updated
            )
            message_id = str(assistant_msg.id)

            # Send message_start event
            yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': message_id})}\n\n"

            # Build messages for LLM using proper types
            messages_for_llm: list[LLMTypeMessage] = []

            if agent.system_prompt:
                system_prompt = agent.system_prompt
                for key, value in conversation.variables.items():
                    system_prompt = system_prompt.replace(f"{{{{{key}}}}}", str(value))
                messages_for_llm.append(
                    LLMTypeMessage(role=LLMTypeRole.SYSTEM, content=system_prompt)
                )

            # Helper function to build multimodal content for vision
            def build_vision_content(text: str, images: list) -> list[ContentPart]:
                """Build multimodal content array for vision-enabled messages."""
                content_parts: list[ContentPart] = [
                    ContentPart(type=ContentType.TEXT, text=text)
                ]
                for img in images:
                    # Parse the image URL - could be data URL or remote URL
                    img_url = img.url
                    if img_url.startswith("data:"):
                        # Extract base64 from data URL: data:image/png;base64,xxxxx
                        # Format: data:<mediatype>;base64,<data>
                        try:
                            _, data_part = img_url.split(",", 1)
                            content_parts.append(
                                ContentPart(
                                    type=ContentType.IMAGE,
                                    image=ImageContent(base64=data_part),
                                )
                            )
                        except ValueError:
                            # Fallback: treat as URL
                            content_parts.append(
                                ContentPart(
                                    type=ContentType.IMAGE,
                                    image=ImageContent(url=img_url),
                                )
                            )
                    else:
                        # Remote URL
                        content_parts.append(
                            ContentPart(
                                type=ContentType.IMAGE, image=ImageContent(url=img_url)
                            )
                        )
                return content_parts

            # Track which tool_call_ids have been seen from assistant messages
            valid_tool_call_ids: set[str] = set()

            # Check if history_override is provided (for version switching / regeneration)
            if chat_in.history_override is not None:
                # Use history from frontend instead of database
                for hist_msg in chat_in.history_override:
                    if hist_msg.role == "user":
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.USER, content=hist_msg.content
                            )
                        )
                    elif hist_msg.role == "assistant":
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.ASSISTANT, content=hist_msg.content
                            )
                        )

                # Add current user message with RAG and vision support
                current_content: str | list = final_message
                if chat_in.images and model_supports_vision:
                    current_content = build_vision_content(
                        final_message, chat_in.images
                    )
                messages_for_llm.append(
                    LLMTypeMessage(role=LLMTypeRole.USER, content=current_content)
                )
            else:
                # Load history from database including the user message we just saved (only active messages)
                history = (
                    await Message.filter(
                        conversation_id=conversation.id,
                        is_active=True,
                    )
                    .exclude(id=assistant_msg.id)
                    .order_by("created_at")
                )

                for msg in history:
                    if msg.role == MessageRole.USER:
                        # Use RAG-enhanced message for the current user message (auto mode)
                        text_content = (
                            final_message if msg.id == user_msg.id else msg.content
                        )

                        # Check if this is the current message with images and vision is enabled
                        if (
                            msg.id == user_msg.id
                            and chat_in.images
                            and model_supports_vision
                        ):
                            # Build multimodal content for vision
                            content = build_vision_content(text_content, chat_in.images)
                        else:
                            content = text_content

                        messages_for_llm.append(
                            LLMTypeMessage(role=LLMTypeRole.USER, content=content)
                        )
                    elif msg.role == MessageRole.ASSISTANT:
                        # Include tool_calls if present
                        llm_tool_calls = None
                        if msg.tool_calls:
                            llm_tool_calls = []
                            for tc in msg.tool_calls:
                                tc_id = tc.get("id", "")
                                valid_tool_call_ids.add(tc_id)
                                llm_tool_calls.append(
                                    LLMToolCall(
                                        id=tc_id,
                                        type="function",
                                        function=LLMFunctionCall(
                                            name=tc.get("name", ""),
                                            arguments=json.dumps(
                                                tc.get("arguments", {})
                                            ),
                                        ),
                                    )
                                )
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.ASSISTANT,
                                content=msg.content,
                                tool_calls=llm_tool_calls if llm_tool_calls else None,
                            )
                        )
                    elif msg.role == MessageRole.TOOL:
                        # Only include tool messages that have a corresponding tool_call
                        if msg.tool_call_id and msg.tool_call_id in valid_tool_call_ids:
                            messages_for_llm.append(
                                LLMTypeMessage(
                                    role=LLMTypeRole.TOOL,
                                    content=msg.content,
                                    tool_call_id=msg.tool_call_id,
                                )
                            )
                        else:
                            # Skip orphaned tool messages
                            logger.warning(
                                f"Skipping orphaned tool message with tool_call_id={msg.tool_call_id}"
                            )

            # Get model identifier
            model_id = await get_model_identifier(agent)

            # Get agent tools
            tools_openai = await get_agent_tools(agent)
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

            while iteration < max_iterations:
                iteration += 1

                # Track reasoning state for this iteration
                reasoning_started = False
                full_reasoning = ""
                iteration_content = ""
                iteration_reasoning = ""
                pending_tool_calls = []
                collected_tool_calls = []  # For collecting tool calls from stream

                # Calculate input chars for this iteration
                iteration_input_chars = sum(
                    len(m.content or "") if isinstance(m.content, str) else 0
                    for m in messages_for_llm
                )

                # Use streaming call - works for both with and without tools
                async for chunk in model_manager.team_chat_stream(
                    team_id=str(agent.team_id),
                    messages=messages_for_llm,
                    model_id=model_id,
                    tools=tools,
                ):
                    # Handle reasoning content (思维链)
                    if chunk.delta.reasoning_content:
                        if not reasoning_started:
                            reasoning_started = True
                            yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                        full_reasoning += chunk.delta.reasoning_content
                        iteration_reasoning += chunk.delta.reasoning_content
                        yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': chunk.delta.reasoning_content})}\n\n"

                    # Handle content - stream it immediately
                    if chunk.delta.content:
                        if reasoning_started and not full_content:
                            yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        full_content += chunk.delta.content
                        iteration_content += chunk.delta.content
                        yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.delta.content})}\n\n"

                    # Collect tool calls when they arrive
                    if chunk.delta.tool_calls:
                        collected_tool_calls = chunk.delta.tool_calls

                    # Handle finish
                    if chunk.finish_reason:
                        if reasoning_started and not full_content:
                            yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        break

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
                    # Process each tool call
                    for tc in collected_tool_calls:
                        tool_name = tc.function.name
                        try:
                            arguments = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                        # Send tool_call event
                        yield f"event: {SSEEventType.TOOL_CALL}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'arguments': arguments})}\n\n"

                        # Execute the tool (pass agent for knowledge_search)
                        result = await execute_tool_call(
                            tool_name, arguments, agent=agent
                        )

                        # Send tool_result event
                        yield f"event: {SSEEventType.TOOL_RESULT}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'result': result})}\n\n"

                        # Add to pending tool calls for message building
                        pending_tool_calls.append(
                            {
                                "id": tc.id,
                                "name": tool_name,
                                "arguments": arguments,
                                "result": result,
                            }
                        )

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
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": safe_parse_arguments(tc.function.arguments),
                        }
                        for tc in collected_tool_calls
                    ]
                    await Message.create(
                        conversation=conversation,
                        role=MessageRole.ASSISTANT,
                        content=iteration_content,
                        tool_calls=intermediate_tool_calls,
                    )

                    # Save tool response messages to database
                    for tc_data in pending_tool_calls:
                        await Message.create(
                            conversation=conversation,
                            role=MessageRole.TOOL,
                            content=tc_data["result"],
                            tool_call_id=tc_data["id"],
                            tool_name=tc_data["name"],
                        )

                    # Add assistant message with tool calls to message history for LLM
                    assistant_tool_calls = [
                        LLMToolCall(
                            id=tc.id,
                            type="function",
                            function=LLMFunctionCall(
                                name=tc.function.name,
                                arguments=tc.function.arguments,
                            ),
                        )
                        for tc in collected_tool_calls
                    ]
                    messages_for_llm.append(
                        LLMTypeMessage(
                            role=LLMTypeRole.ASSISTANT,
                            content=iteration_content,
                            tool_calls=assistant_tool_calls,
                        )
                    )

                    # Add tool results to message history
                    for tc_data in pending_tool_calls:
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.TOOL,
                                content=tc_data["result"],
                                tool_call_id=tc_data["id"],
                            )
                        )

                    # Continue the loop to get the final response
                    pending_tool_calls = []
                    collected_tool_calls = []
                    continue
                else:
                    # No tool calls, we're done
                    break

            duration_ms = int((time.time() - start_time) * 1000)

            # Update assistant message (final response, no tool_calls)
            assistant_msg.content = full_content
            assistant_msg.model_used = model_id
            assistant_msg.duration_ms = duration_ms
            # Estimate token usage
            input_tokens = sum(len(m.content or "") // 4 for m in messages_for_llm)
            output_tokens = len(full_content) // 4
            assistant_msg.token_usage = {
                "prompt": input_tokens,
                "completion": output_tokens,
            }
            await assistant_msg.save()

            # Update conversation stats atomically
            title_update = {}
            if not conversation.title:
                title_update["title"] = chat_in.message[:50] + (
                    "..." if len(chat_in.message) > 50 else ""
                )

            await Conversation.filter(id=conversation.id).update(
                message_count=F("message_count") + 2,
                token_usage=F("token_usage") + input_tokens + output_tokens,
                **title_update,
            )

            # Update agent stats atomically
            await Agent.filter(id=agent.id).update(message_count=F("message_count") + 2)

            # Send message_end event with version info
            yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens}, 'version_number': 1, 'version_count': 1})}\n\n"

        except QuotaExceededError as e:
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': str(e), 'quota_type': e.quota_type})}\n\n"
        except ModelNotFoundError as e:
            logger.error(f"Model not found error: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_NOT_FOUND, 'msg': str(e)})}\n\n"
        except AuthenticationError as e:
            logger.error(f"Authentication error: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNAUTHORIZED, 'msg': str(e)})}\n\n"
        except RateLimitError as e:
            logger.warning(f"Rate limit error: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': str(e)})}\n\n"
        except LLMError as e:
            logger.exception(f"LLM error during stream: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': str(e)})}\n\n"
        except Exception as e:
            logger.exception(f"Unexpected error during stream: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': str(e)})}\n\n"

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
        model_used=message.model_used,
        token_usage=message.token_usage,
        duration_ms=message.duration_ms,
        rag_context=message.rag_context,
        created_at=message.created_at,
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
    root_id = message.parent_id or message.id
    target_root_id = target_version.parent_id or target_version.id
    if root_id != target_root_id:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="version_not_in_group",
            status_code=400,
        )

    # Deactivate all versions in this group
    await Message.filter(id=root_id).update(is_active=False)
    await Message.filter(parent_id=root_id).update(is_active=False)

    # Activate the target version
    target_version.is_active = True
    await target_version.save()

    # Get the root message to use its created_at for deactivating subsequent messages
    root_message = await Message.filter(id=root_id).first()
    if root_message:
        # Deactivate all messages after the root message in the conversation
        # (they need to be regenerated based on the new active version)
        await Message.filter(
            conversation_id=message.conversation_id,
            created_at__gt=root_message.created_at,
            is_active=True,
        ).update(is_active=False)

    return success(
        data=await build_message_out_with_versions(
            target_version, include_versions=True
        )
    )


@router.post("/{agent_id}/messages/{message_id}/regenerate")
async def regenerate_message(
    agent_id: UUID,
    message_id: UUID,
    request: RegenerateRequest,
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

    # Find the user message before this assistant message
    # We need to get the active user message that preceded this response
    user_message = (
        await Message.filter(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            created_at__lt=message.created_at,
            is_active=True,
        )
        .order_by("-created_at")
        .first()
    )

    if not user_message:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="no_user_message_found",
            status_code=400,
        )

    async def event_generator():
        from app.llm import model_manager
        from app.llm.errors import QuotaExceededError, LLMError
        from app.llm.types import (
            Message as LLMTypeMessage,
            MessageRole as LLMTypeRole,
            ToolDefinition,
            FunctionDefinition,
            ToolCall as LLMToolCall,
            FunctionCall as LLMFunctionCall,
        )

        start_time = time.time()
        full_content = ""
        new_message_id = None

        try:
            from app.models.agent import RAGMode

            # Determine the root message ID for versioning
            root_id = message.parent_id or message.id

            # Get current version count
            current_version_count = await Message.filter(parent_id=root_id).count() + 1
            new_version_number = current_version_count + 1

            # Deactivate all versions in this group
            await Message.filter(id=root_id).update(is_active=False)
            await Message.filter(parent_id=root_id).update(is_active=False)

            # Create new version message
            new_message = await Message.create(
                conversation=conversation,
                role=MessageRole.ASSISTANT,
                content="",
                parent_id=root_id,
                is_active=True,
                version_number=new_version_number,
            )
            new_message_id = str(new_message.id)

            # Send message_start event with version info
            yield f"event: {SSEEventType.MESSAGE_START}\ndata: {json.dumps({'conversation_id': str(conversation.id), 'message_id': new_message_id, 'version_number': new_version_number, 'version_count': new_version_number, 'parent_id': str(root_id)})}\n\n"

            # Handle RAG
            rag_contexts: list[dict] = []
            final_message = user_message.content

            if agent.rag_mode == RAGMode.AUTO:
                has_knowledge_bases = await AgentKnowledgeBase.exists(agent_id=agent.id)
                if has_knowledge_bases:
                    yield f"event: {SSEEventType.RAG_START}\ndata: {json.dumps({})}\n\n"
                    rag_contexts = await perform_rag_retrieval(
                        agent, user_message.content
                    )
                    if rag_contexts:
                        yield f"event: {SSEEventType.RAG_CONTEXT}\ndata: {json.dumps({'contexts': rag_contexts})}\n\n"
                    final_message = build_rag_prompt(rag_contexts, user_message.content)

            # Build messages for LLM - only include ACTIVE messages before this one
            messages_for_llm: list[LLMTypeMessage] = []

            if agent.system_prompt:
                system_prompt = agent.system_prompt
                for key, value in conversation.variables.items():
                    system_prompt = system_prompt.replace(f"{{{{{key}}}}}", str(value))
                messages_for_llm.append(
                    LLMTypeMessage(role=LLMTypeRole.SYSTEM, content=system_prompt)
                )

            # Load active history before this message
            history = await Message.filter(
                conversation_id=conversation.id,
                created_at__lt=message.created_at,
                is_active=True,
            ).order_by("created_at")

            valid_tool_call_ids: set[str] = set()

            for msg in history:
                if msg.role == MessageRole.USER:
                    # Use RAG-enhanced message for the trigger user message
                    text_content = (
                        final_message if msg.id == user_message.id else msg.content
                    )
                    messages_for_llm.append(
                        LLMTypeMessage(role=LLMTypeRole.USER, content=text_content)
                    )
                elif msg.role == MessageRole.ASSISTANT:
                    llm_tool_calls = None
                    if msg.tool_calls:
                        llm_tool_calls = []
                        for tc in msg.tool_calls:
                            tc_id = tc.get("id", "")
                            valid_tool_call_ids.add(tc_id)
                            llm_tool_calls.append(
                                LLMToolCall(
                                    id=tc_id,
                                    type="function",
                                    function=LLMFunctionCall(
                                        name=tc.get("name", ""),
                                        arguments=json.dumps(tc.get("arguments", {})),
                                    ),
                                )
                            )
                    messages_for_llm.append(
                        LLMTypeMessage(
                            role=LLMTypeRole.ASSISTANT,
                            content=msg.content,
                            tool_calls=llm_tool_calls if llm_tool_calls else None,
                        )
                    )
                elif msg.role == MessageRole.TOOL:
                    if msg.tool_call_id and msg.tool_call_id in valid_tool_call_ids:
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.TOOL,
                                content=msg.content,
                                tool_call_id=msg.tool_call_id,
                            )
                        )

            # Get model and tools
            model_id = await get_model_identifier(agent)
            tools_openai = await get_agent_tools(agent)
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

            while iteration < max_iterations:
                iteration += 1
                reasoning_started = False
                collected_tool_calls = []

                async for chunk in model_manager.team_chat_stream(
                    team_id=str(agent.team_id),
                    messages=messages_for_llm,
                    model_id=model_id,
                    tools=tools,
                ):
                    if chunk.delta.reasoning_content:
                        if not reasoning_started:
                            reasoning_started = True
                            yield f"event: {SSEEventType.REASONING_START}\ndata: {json.dumps({})}\n\n"
                        yield f"event: {SSEEventType.REASONING_DELTA}\ndata: {json.dumps({'delta': chunk.delta.reasoning_content})}\n\n"

                    if chunk.delta.content:
                        if reasoning_started and not full_content:
                            yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        full_content += chunk.delta.content
                        yield f"event: {SSEEventType.CONTENT_DELTA}\ndata: {json.dumps({'delta': chunk.delta.content})}\n\n"

                    if chunk.delta.tool_calls:
                        collected_tool_calls = chunk.delta.tool_calls

                    if chunk.finish_reason:
                        if reasoning_started and not full_content:
                            yield f"event: {SSEEventType.REASONING_END}\ndata: {json.dumps({})}\n\n"
                        break

                if collected_tool_calls:
                    # Handle tool calls (simplified)
                    for tc in collected_tool_calls:
                        tool_name = tc.function.name
                        try:
                            arguments = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                        yield f"event: {SSEEventType.TOOL_CALL}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'arguments': arguments})}\n\n"
                        result = await execute_tool_call(
                            tool_name, arguments, agent=agent
                        )
                        yield f"event: {SSEEventType.TOOL_RESULT}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'result': result})}\n\n"

                        # Add to message history for next iteration
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.ASSISTANT,
                                content="",
                                tool_calls=[
                                    LLMToolCall(
                                        id=tc.id,
                                        type="function",
                                        function=LLMFunctionCall(
                                            name=tool_name,
                                            arguments=tc.function.arguments,
                                        ),
                                    )
                                ],
                            )
                        )
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.TOOL,
                                content=result,
                                tool_call_id=tc.id,
                            )
                        )
                    continue
                else:
                    break

            duration_ms = int((time.time() - start_time) * 1000)

            # Update new message
            new_message.content = full_content
            new_message.model_used = model_id
            new_message.duration_ms = duration_ms
            input_tokens = sum(len(m.content or "") // 4 for m in messages_for_llm)
            output_tokens = len(full_content) // 4
            new_message.token_usage = {
                "prompt": input_tokens,
                "completion": output_tokens,
            }
            await new_message.save()

            yield f"event: {SSEEventType.MESSAGE_END}\ndata: {json.dumps({'usage': {'prompt_tokens': input_tokens, 'completion_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens}, 'version_number': new_version_number, 'version_count': new_version_number})}\n\n"

        except QuotaExceededError as e:
            # Rollback: delete new message and restore original
            if new_message_id:
                await Message.filter(id=new_message_id).delete()
                # Restore original message as active
                await Message.filter(id=message.id).update(is_active=True)
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': str(e), 'quota_type': e.quota_type})}\n\n"
        except LLMError as e:
            # Rollback: delete new message and restore original
            if new_message_id:
                await Message.filter(id=new_message_id).delete()
                # Restore original message as active
                await Message.filter(id=message.id).update(is_active=True)
            logger.exception(f"LLM error during regenerate: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': str(e)})}\n\n"
        except Exception as e:
            # Rollback: delete new message and restore original
            if new_message_id:
                await Message.filter(id=new_message_id).delete()
                # Restore original message as active
                await Message.filter(id=message.id).update(is_active=True)
            logger.exception(f"Unexpected error during regenerate: {e}")
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
