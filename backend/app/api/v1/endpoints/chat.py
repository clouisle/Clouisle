"""
Chat API endpoints for Agent conversations.
Provides streaming and non-streaming chat with AI agents.
"""

from __future__ import annotations

import json
import logging
import re
import time
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.tool import Tool
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tortoise.expressions import F

from app.api import deps
from app.core.config import settings
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
from app.llm.tools import tool_registry
from app.llm.tools.builtin.media import ToolExecutionResult
from app.core.timezone import now_utc


# Language instruction templates - must be strong and explicit
LANGUAGE_INSTRUCTIONS = {
    "en": "IMPORTANT: You MUST respond in English only. Do not use any other language.",
    "zh": "重要：你必须使用中文回复。不要使用其他语言。",
}


def get_language_instruction(user_locale: str | None = None) -> str:
    """Get language instruction based on user's locale setting.

    Args:
        user_locale: User's locale from database (e.g., "en", "zh")
    """
    lang = user_locale or "en"
    # Normalize language code (e.g., "zh-CN" -> "zh")
    lang = lang.lower().split("-")[0]
    return LANGUAGE_INSTRUCTIONS.get(lang, LANGUAGE_INSTRUCTIONS["en"])


def build_system_prompt_with_language(
    system_prompt: str | None, user_locale: str | None = None
) -> str:
    """Build system prompt with language instruction.

    Always returns a system prompt with language instruction,
    even if the original system prompt is empty.

    Args:
        system_prompt: The original system prompt (can be None or empty)
        user_locale: User's locale from database (e.g., "en", "zh")
    """
    instruction = get_language_instruction(user_locale)
    if not system_prompt:
        return instruction
    # Check if instruction already exists (avoid duplication)
    if instruction in system_prompt:
        return system_prompt
    # Append instruction at the end
    return f"{system_prompt}\n\n{instruction}"


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
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


router = APIRouter()
logger = logging.getLogger(__name__)
GENERIC_STREAM_ERROR_MSG = "An internal error occurred while processing the request"
MEDIA_TOOL_KINDS = {"media.image", "media.video"}


# ============ Helper Functions ============


def get_streaming_config(agent: Agent) -> dict[str, Any]:
    """
    Get streaming configuration from agent or use defaults.

    Returns:
        dict with keys: global_timeout, heartbeat_interval, tool_timeouts
    """
    from app.core.config import settings

    # Start with defaults from settings
    tool_timeouts: dict[str, Any] = {
        "http": settings.STREAM_TOOL_TIMEOUT_HTTP,
        "code": settings.STREAM_TOOL_TIMEOUT_CODE,
        "mcp": settings.STREAM_TOOL_TIMEOUT_MCP,
        "download": settings.STREAM_TOOL_TIMEOUT_DOWNLOAD,
    }
    config: dict[str, Any] = {
        "global_timeout": settings.STREAM_GLOBAL_TIMEOUT,
        "heartbeat_interval": settings.STREAM_HEARTBEAT_INTERVAL,
        "tool_timeouts": tool_timeouts,
    }

    # Override with agent-specific config if present
    if agent.streaming_config:
        if "global_timeout" in agent.streaming_config:
            config["global_timeout"] = agent.streaming_config["global_timeout"]
        if "heartbeat_interval" in agent.streaming_config:
            config["heartbeat_interval"] = agent.streaming_config["heartbeat_interval"]
        raw_tool_timeouts = agent.streaming_config.get("tool_timeouts")
        if isinstance(raw_tool_timeouts, dict):
            tool_timeouts.update(raw_tool_timeouts)

    return config


def _safe_json_loads(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _build_media_llm_summary(
    tool_name: str | None, payload: dict[str, Any]
) -> str | None:
    kind = payload.get("kind")
    if kind not in MEDIA_TOOL_KINDS:
        return None

    if kind == "media.image":
        if payload.get("error"):
            return f"Image generation failed: {payload['error']}"
        count = len(payload.get("images") or [])
        model = payload.get("model")
        model_suffix = f" using model {model}" if model else ""
        return (
            f"Image generation succeeded. Generated {count} image"
            f"{'s' if count != 1 else ''}{model_suffix}."
        )

    status = payload.get("status") or "unknown"
    if payload.get("error") or status == "failed":
        message = payload.get("error") or "unknown error"
        return f"Video generation failed: {message}"
    if status in {"pending", "processing"}:
        task_id = payload.get("task_id") or "unknown"
        return f"Video generation started. Task {task_id} is {status}."
    model = payload.get("model")
    model_suffix = f" using model {model}" if model else ""
    return f"Video generation succeeded{model_suffix}."


def summarize_tool_result_for_llm(
    tool_name: str | None,
    stored_content: str,
) -> str:
    payload = _safe_json_loads(stored_content)
    if not payload:
        return stored_content
    return _build_media_llm_summary(tool_name, payload) or stored_content


def get_tool_execution_payloads(result: Any) -> tuple[str, str]:
    if isinstance(result, ToolExecutionResult):
        display_result = json.dumps(result.display_result, ensure_ascii=False)
        return display_result, result.llm_result
    if isinstance(result, dict):
        payload = json.dumps(result, ensure_ascii=False)
        return payload, payload
    stringified = str(result) if result is not None else ""
    return stringified, stringified


def extract_media_display_payload(display_result: str) -> dict[str, Any] | None:
    payload = _safe_json_loads(display_result)
    if not payload:
        return None
    if payload.get("kind") not in MEDIA_TOOL_KINDS:
        return None
    return payload


async def send_heartbeat_if_needed(
    last_event_time: float, heartbeat_interval: float, request: Request
) -> tuple[bool, float]:
    """
    Send heartbeat if needed and check client connection.

    Returns:
        (should_continue, new_last_event_time)
    """
    current_time = time.time()
    if current_time - last_event_time >= heartbeat_interval:
        # Check if client is still connected
        if await request.is_disconnected():
            logger.info("Client disconnected during heartbeat check")
            return False, last_event_time
        return True, current_time
    return True, last_event_time


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


def parse_user_input_request(content: str) -> tuple[dict | None, str]:
    """
    Parse user_input_request XML from content.

    Returns:
        Tuple of (parsed_data, remaining_content)
        - parsed_data is None if no valid user_input_request found
        - remaining_content is content with user_input_request removed

    Example parsed_data:
    {
        "question": "What would you like to do?",
        "options": ["Option 1", "Option 2", "Option 3"]
    }
    """
    pattern = r"<user_input_request>(.*?)</user_input_request>"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        return None, content

    xml_block = match.group(0)
    xml_content = match.group(1)

    try:
        logger.info(f"Parsing user_input_request XML: {xml_content[:200]}")
        root = ET.fromstring(f"<root>{xml_content}</root>")

        # Extract question
        question_elem = root.find("question")
        if question_elem is None or not question_elem.text:
            return None, content
        question = question_elem.text.strip()

        # Extract options
        options_elem = root.find("options")
        if options_elem is None:
            return None, content

        option_elems = options_elem.findall("option")
        if len(option_elems) < 2:
            return None, content

        options = []
        for opt in option_elems:
            if opt.text:
                option_text = opt.text.strip()
                if option_text and len(option_text) <= 200:
                    options.append(option_text)

        if len(options) < 2:
            return None, content

        parsed_data = {
            "question": question[:500],
            "options": options,  # 不限制选项数量，全部渲染
        }

        remaining_content = content.replace(xml_block, "").strip()
        logger.info(
            f"Successfully parsed user_input_request: question={question[:50]}, options_count={len(options)}"
        )
        return parsed_data, remaining_content

    except ET.ParseError as e:
        logger.error(f"Failed to parse user_input_request XML: {e}")
        return None, content


def get_user_input_request_instruction(locale: str = "en") -> str:
    """Get user input request instruction for system prompt."""
    if locale == "zh":
        return """## 用户输入请求功能

当你需要用户从预定义选项中选择时，可以使用以下 XML 格式：

<user_input_request>
<question>你的问题文本</question>
<options>
<option>选项 1</option>
<option>选项 2</option>
<option>选项 3</option>
</options>
</user_input_request>

**使用规则：**
- 问题应该清晰简洁
- 提供 2-6 个选项（超过 6 个也会显示，但建议控制数量以保持界面简洁）
- 每个选项应该简短（建议不超过 50 字符）
- 用户可以点击选项或输入自定义文本
- 在一条消息中只使用一次
- 不要在 user_input_request 标签外添加其他内容

**使用场景：**
- 需要用户做出选择时
- 提供快捷操作选项时
- 引导对话流程时"""
    else:
        return """## User Input Request Feature

When you need the user to choose from predefined options, use this XML format:

<user_input_request>
<question>Your question text</question>
<options>
<option>Option 1</option>
<option>Option 2</option>
<option>Option 3</option>
</options>
</user_input_request>

**Rules:**
- Keep questions clear and concise
- Provide 2-6 options
- Keep each option short (recommended max 50 characters)
- Users can click an option or type custom text
- Use only once per message
- Don't add other content outside the user_input_request tags

**Use cases:**
- When user needs to make a choice
- Providing quick action options
- Guiding conversation flow"""


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


async def build_messages(
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    file_content: str | None = None,
    file_urls: list[dict] | None = None,
    user_locale: str | None = None,
) -> list[LLMMessage]:
    """Build message list for LLM call.

    Args:
        agent: The agent
        conversation: The conversation
        user_message: User's message text
        file_content: Legacy file content to inject into {{fileContent}} variable
        file_urls: List of file URLs for tool-based file processing
        user_locale: User's locale from database for language instruction
    """
    messages: list[LLMMessage] = []

    # System prompt - always add with language instruction
    system_prompt = agent.system_prompt or ""
    if system_prompt:
        # Replace variables in system prompt
        for key, value in conversation.variables.items():
            system_prompt = system_prompt.replace(f"{{{{{key}}}}}", str(value))

        # Inject {{query}} variable - user's current input
        system_prompt = system_prompt.replace("{{query}}", user_message)

        # Inject file content into {{fileContent}} variable (legacy)
        if file_content:
            system_prompt = system_prompt.replace("{{fileContent}}", file_content)
        else:
            # Remove the placeholder if no file content
            system_prompt = system_prompt.replace("{{fileContent}}", "")

    # Add memory instructions if enabled
    if agent.enable_memory:
        memory_instruction = """

# Memory System
You have access to a memory system with these tools:
- search_memory(query): Search what you know about the user
- create_memory_entity(name, entity_type, description): Save new information
- update_memory_entity(entity_name, description): Update existing information
- create_memory_relation(source, target, relation_type): Connect related information

**CRITICAL MEMORY RULES - YOU MUST FOLLOW THESE STEPS:**

RULE 1: Before ANY create_memory_entity() call, you MUST call search_memory() first!
RULE 2: When user shares ANY information (name, preference, skill, etc.):
   STEP 1: Call search_memory(query="keywords about the information")
   STEP 2: Read the search results carefully
   STEP 3: Decide based on results:
      - Found similar entity? → Use update_memory_entity(entity_name="existing name", ...)
      - Nothing found? → Use create_memory_entity(name="new name", ...)

RULE 3: NEVER skip search_memory() - even if you think it's new information!
RULE 4: NEVER say "I don't have access to memory" - you DO have these tools!

WRONG Example (DO NOT DO THIS):
User: "I'm Alice"
❌ Assistant directly calls create_memory_entity(name="Alice", ...) ← WRONG! No search first!

CORRECT Example (ALWAYS DO THIS):
User: "I'm Alice"
✓ Step 1: Assistant calls search_memory(query="user name")
✓ Step 2: Check results → No "Alice" found
✓ Step 3: Assistant calls create_memory_entity(name="Alice", entity_type="person", description="User's name")
Assistant: "Nice to meet you, Alice! I've saved your name."

User: "Actually, I'm Alice Smith"
✓ Step 1: Assistant calls search_memory(query="user name Alice")
✓ Step 2: Check results → Found entity "Alice"
✓ Step 3: Assistant calls update_memory_entity(entity_name="Alice", description="Full name: Alice Smith")
Assistant: "Got it! I've updated your name to Alice Smith."

User: "What's my name?"
Assistant: [calls search_memory(query="user name")]
Assistant: "Your name is Alice."
"""
        system_prompt += memory_instruction
        logger.info(f"Added memory instructions to system prompt for agent {agent.id}")

    # Build system prompt with language instruction (always added)
    system_prompt = build_system_prompt_with_language(system_prompt, user_locale)
    messages.append(LLMMessage(role=LLMMessageRole.SYSTEM, content=system_prompt))

    # Load conversation history (only active messages)
    history = await Message.filter(
        conversation_id=conversation.id, is_active=True
    ).order_by("created_at")
    valid_tool_call_ids: set[str] = set()
    for msg in history:
        if msg.role == MessageRole.USER:
            messages.append(LLMMessage(role=LLMMessageRole.USER, content=msg.content))
        elif msg.role == MessageRole.ASSISTANT:
            tool_calls = None
            if msg.tool_calls:
                tool_calls = []
                for tc in msg.tool_calls:
                    tc_id = tc.get("id", "")
                    valid_tool_call_ids.add(tc_id)
                    arguments = tc.get("arguments", {})
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments)
                    tool_calls.append(
                        {
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": arguments,
                            },
                        }
                    )
            messages.append(
                LLMMessage(
                    role=LLMMessageRole.ASSISTANT,
                    content=msg.content,
                    reasoning_content=msg.reasoning_content,
                    tool_calls=tool_calls,
                )
            )
        elif msg.role == MessageRole.TOOL:
            if msg.tool_call_id and msg.tool_call_id in valid_tool_call_ids:
                messages.append(
                    LLMMessage(
                        role=LLMMessageRole.TOOL,
                        content=summarize_tool_result_for_llm(
                            msg.tool_name,
                            msg.content,
                        ),
                        tool_call_id=msg.tool_call_id,
                    )
                )

    # Build current user message with file info
    final_user_message = user_message
    if file_urls:
        # Add file info to the message so LLM knows to use markitdown tool
        file_info_lines = [t("chat_file_upload_instruction")]
        for f in file_urls:
            file_info_lines.append(f"- {f['filename']} ({f['url']})")
        file_info = "\n".join(file_info_lines)
        final_user_message = f"{file_info}\n\n{user_message}"

    messages.append(LLMMessage(role=LLMMessageRole.USER, content=final_user_message))

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
                # Get builtin tool definition
                builtin_tools = tool_registry.to_openai_tools([tool_name])
                for builtin_tool in builtin_tools:
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
                # Get display name from builtin metadata with i18n
                metadata = BUILTIN_TOOLS_METADATA.get(tool_name, {})
                display_name_key = metadata.get("display_name_key")
                if display_name_key:
                    display_names[tool_name] = t(display_name_key, lang=user_locale)
                else:
                    display_names[tool_name] = tool_name

        elif tool_type == "custom":
            tool_id = config.get("tool_id")
            if tool_id:
                custom_tool = await Tool.filter(id=tool_id, is_enabled=True).first()
                if custom_tool:
                    # Custom tools use custom_<name> format
                    display_names[f"custom_{custom_tool.name}"] = (
                        custom_tool.display_name
                    )

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


async def execute_tool_call(
    tool_name: str,
    arguments: dict,
    agent: Agent | None = None,
    tool_timeouts: dict | None = None,
    user: User | None = None,
) -> Any:
    """
    Execute a tool and return the result payload.

    Args:
        tool_name: Tool name (for builtin) or custom_<name> (for custom) or mcp_<tool_id>_<tool_name> (for MCP)
        arguments: Tool arguments
        agent: Agent instance (required for knowledge_search)
        tool_timeouts: Tool timeout configuration dict
        user: User instance (required for memory tools)
    """
    from app.models.tool import Tool, CustomToolType

    # Initialize default timeouts if not provided
    if tool_timeouts is None:
        tool_timeouts = {
            "http": 30,
            "code": 60,
            "mcp": 60,
            "download": 60,
        }

    try:
        if not tool_name:
            return json.dumps({"error": t("tool_name_required")}, ensure_ascii=False)
        # Handle knowledge_search - internal tool for RAG
        if tool_name == "knowledge_search":
            if not agent:
                return json.dumps(
                    {"error": t("agent_context_required_for_knowledge_search")},
                    ensure_ascii=False,
                )

            query = arguments.get("query", "")
            if not query:
                return json.dumps(
                    {"error": t("query_parameter_required")}, ensure_ascii=False
                )

            # Use existing RAG retrieval function
            rag_contexts = await perform_rag_retrieval(agent, query)

            if not rag_contexts:
                return json.dumps(
                    {"message": t("kb_no_results")},
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

        # Handle memory tools
        if tool_name in [
            "create_memory_entity",
            "create_memory_relation",
            "update_memory_entity",
            "search_memory",
        ]:
            from app.services.memory import MemoryService

            if not user:
                return json.dumps(
                    {"error": t("user_context_required_for_memory_tools")},
                    ensure_ascii=False,
                )

            try:
                if tool_name == "create_memory_entity":
                    name = arguments.get("name")
                    entity_type = arguments.get("entity_type")
                    description = arguments.get("description")
                    if not isinstance(name, str) or not isinstance(entity_type, str):
                        return json.dumps(
                            {
                                "error": t(
                                    "memory_tool_create_entity_requires_name_and_entity_type"
                                )
                            },
                            ensure_ascii=False,
                        )
                    result = await MemoryService.handle_create_entity(
                        user_id=user.id,
                        name=name,
                        entity_type=entity_type,
                        description=description
                        if isinstance(description, str)
                        else None,
                        properties=arguments.get("properties", {}),
                    )
                elif tool_name == "create_memory_relation":
                    source_entity_name = arguments.get("source_entity_name")
                    target_entity_name = arguments.get("target_entity_name")
                    relation_type = arguments.get("relation_type")
                    description = arguments.get("description")
                    if (
                        not isinstance(source_entity_name, str)
                        or not isinstance(target_entity_name, str)
                        or not isinstance(relation_type, str)
                    ):
                        return json.dumps(
                            {
                                "error": t(
                                    "memory_tool_create_relation_requires_fields"
                                )
                            },
                            ensure_ascii=False,
                        )
                    result = await MemoryService.handle_create_relation(
                        user_id=user.id,
                        source_entity_name=source_entity_name,
                        target_entity_name=target_entity_name,
                        relation_type=relation_type,
                        description=description
                        if isinstance(description, str)
                        else None,
                    )
                elif tool_name == "update_memory_entity":
                    entity_name = arguments.get("entity_name")
                    description = arguments.get("description")
                    if not isinstance(entity_name, str):
                        return json.dumps(
                            {
                                "error": t(
                                    "memory_tool_update_entity_requires_entity_name"
                                )
                            },
                            ensure_ascii=False,
                        )
                    result = await MemoryService.handle_update_entity(
                        user_id=user.id,
                        entity_name=entity_name,
                        description=description
                        if isinstance(description, str)
                        else None,
                        properties=arguments.get("properties"),
                    )
                elif tool_name == "search_memory":
                    query = arguments.get("query")
                    if not isinstance(query, str):
                        return json.dumps(
                            {"error": t("memory_tool_search_requires_query")},
                            ensure_ascii=False,
                        )
                    result = await MemoryService.handle_search_memory(
                        user_id=user.id,
                        query=query,
                        top_k=arguments.get("top_k", 5),
                    )

                return json.dumps(result, ensure_ascii=False)
            except Exception as e:
                logger.error("Memory tool execution failed: %s", e)
                return json.dumps(
                    {"success": False, "error": t("memory_tool_execution_failed")},
                    ensure_ascii=False,
                )

        # Check if it's an MCP tool (format: mcp_<server_name>_<tool_name>)
        if tool_name.startswith("mcp_"):
            from app.llm.tools.mcp_client import execute_mcp_tool

            # Parse server_name and actual tool name
            parts = tool_name.split(
                "_", 2
            )  # Split into ["mcp", "<server_name>", "<tool_name>"]
            if len(parts) < 3:
                return json.dumps(
                    {"error": t("invalid_mcp_tool_name_format", tool_name=tool_name)},
                    ensure_ascii=False,
                )

            server_name = parts[1]
            actual_tool_name = parts[2]

            # Get MCP tool from database by name (need agent's team_id)
            if not agent:
                return json.dumps(
                    {"error": t("agent_context_required_for_mcp_tool")}, ensure_ascii=False
                )

            mcp_tool = await Tool.filter(
                name=server_name, team_id=agent.team_id, is_enabled=True
            ).first()
            if not mcp_tool:
                return json.dumps(
                    {"error": t("mcp_tool_not_found", server_name=server_name)}, ensure_ascii=False
                )

            if not mcp_tool.mcp_config:
                return json.dumps(
                    {"error": t("mcp_tool_missing_configuration", tool_name=mcp_tool.name)},
                    ensure_ascii=False,
                )

            # Execute MCP tool
            mcp_result = await execute_mcp_tool(
                mcp_tool.mcp_config,
                actual_tool_name,
                arguments,
                timeout=tool_timeouts.get("mcp", 60),
            )

            if mcp_result.success:
                if isinstance(mcp_result.result, (dict, list)):
                    return json.dumps(mcp_result.result, ensure_ascii=False)
                return str(mcp_result.result) if mcp_result.result is not None else ""
            else:
                return json.dumps(
                    {"error": mcp_result.error or t("mcp_tool_execution_failed")},
                    ensure_ascii=False,
                )

        # Check if it's a custom tool
        if tool_name.startswith("custom_"):
            actual_name = tool_name[7:]  # Remove "custom_" prefix

            # Get custom tool from database
            custom_tool = await Tool.filter(name=actual_name, is_enabled=True).first()
            if not custom_tool:
                return json.dumps(
                    {"error": t("custom_tool_not_found", tool_name=actual_name)},
                    ensure_ascii=False,
                )

            # Execute based on custom_type
            if custom_tool.custom_type == CustomToolType.HTTP:
                http_result = await execute_http_tool(
                    custom_tool, arguments, timeout=tool_timeouts.get("http", 30)
                )
                return http_result
            elif custom_tool.custom_type == CustomToolType.CODE:
                code_result = await execute_code_tool(
                    custom_tool, arguments, timeout=tool_timeouts.get("code", 60)
                )
                return code_result
            else:
                return json.dumps(
                    {
                        "error": t(
                            "unsupported_custom_tool_type",
                            tool_type=custom_tool.custom_type,
                        )
                    },
                    ensure_ascii=False,
                )
        else:
            # Builtin tool
            # Get credentials from ToolConfig table
            credentials = {}
            if agent and agent.team_id:
                from app.models.tool_config import ToolConfig

                # Try team-specific config first
                tool_config = await ToolConfig.filter(
                    tool_name=tool_name, team_id=agent.team_id
                ).first()
                if tool_config:
                    credentials = tool_config.credentials or {}

                # If no team config, try global config
                if not credentials:
                    global_config = await ToolConfig.filter(
                        tool_name=tool_name, team_id=None
                    ).first()
                    if global_config:
                        credentials = global_config.credentials or {}

            result = await tool_registry.execute(
                tool_name,
                arguments,
                credentials=credentials,
                agent=agent,
                team_id=str(agent.team_id) if agent and agent.team_id else None,
                user_id=str(user.id) if user else None,
            )
            if isinstance(result, ToolExecutionResult):
                return result
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
    except Exception as e:
        logger.exception("Tool execution error: %s", e)
        return json.dumps({"error": t("tool_execution_failed")}, ensure_ascii=False)


async def execute_http_tool(
    tool: "Tool", arguments: dict, timeout: float = 30.0
) -> str:
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
        timeout=timeout,
    )
    return format_http_result_for_llm(result)


async def execute_code_tool(
    tool: "Tool", arguments: dict, timeout: float = 60.0
) -> str:
    """
    Execute a code-based custom tool.

    Args:
        tool: The Tool model instance
        arguments: Tool arguments passed from LLM
        timeout: Execution timeout in seconds

    Returns:
        JSON string with execution result
    """
    from app.llm.tools.sandbox import execute_code

    code_config = tool.code_config or {}
    language = code_config.get("language", "python")
    code = code_config.get("code", "")

    if not code:
        return json.dumps(
            {"error": t("tool_code_not_defined")}, ensure_ascii=False
        )

    try:
        exec_result = await execute_code(
            language=language,
            code=code,
            params=arguments,
            timeout=timeout,
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
                    "error": exec_result.error or t("code_execution_failed"),
                    "logs": exec_result.stdout or "",
                },
                ensure_ascii=False,
            )

    except Exception as e:
        logger.exception("Code tool execution error: %s", e)
        return json.dumps({"error": t("code_tool_execution_failed")}, ensure_ascii=False)


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
                rerank_model_id=str(kb.rerank_model_id) if kb.rerank_model_id else None,
                team_id=str(kb.team_id),
            )

            results = await vector_store.search(
                kb_id=kb.id,
                query=query,
                search_mode=akb.search_mode,
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


def aggregate_rag_contexts(rag_contexts: list[dict]) -> list[dict]:
    """Aggregate RAG contexts by document to align citations with document-level sources."""
    if not rag_contexts:
        return []

    aggregated: list[dict] = []
    index_map: dict[tuple[str | None, str | None], int] = {}

    for ctx in rag_contexts:
        kb_id = ctx.get("kb_id")
        doc_id = ctx.get("document_id") or ctx.get("document_name")
        key = (kb_id, doc_id)

        if key in index_map:
            idx = index_map[key]
            if ctx.get("content"):
                aggregated[idx]["content_parts"].append(ctx.get("content"))
            score = ctx.get("score")
            if isinstance(score, (int, float)):
                existing_score = aggregated[idx].get("score")
                current_score = (
                    float(existing_score)
                    if isinstance(existing_score, (int, float))
                    else 0.0
                )
                aggregated[idx]["score"] = max(current_score, float(score))
            continue

        index_map[key] = len(aggregated)
        aggregated.append(
            {
                "kb_id": kb_id,
                "kb_name": ctx.get("kb_name"),
                "document_id": ctx.get("document_id"),
                "document_name": ctx.get("document_name"),
                "score": ctx.get("score"),
                "content_parts": [ctx.get("content")] if ctx.get("content") else [],
            }
        )

    for item in aggregated:
        item["content"] = "\n\n".join([p for p in item.get("content_parts", []) if p])
        item.pop("content_parts", None)

    return aggregated


def build_rag_prompt(rag_contexts: list[dict], user_message: str) -> str:
    """Build user message with RAG context and citation instructions."""
    if not rag_contexts:
        return user_message

    rag_contexts = aggregate_rag_contexts(rag_contexts)

    # Build numbered references
    references = []
    for i, ctx in enumerate(rag_contexts, 1):
        references.append(
            f"[[ref:{i}]] {ctx['kb_name']} - {ctx['document_name']}:\n{ctx['content']}"
        )

    context_text = "\n\n---\n\n".join(references)

    return f"""The following reference materials may help you answer the user's question.
Use them ONLY if they are relevant to the question.

Citation format requirement:
- Use ONLY [[cite:N]] where N is the reference number.
- Do NOT use (ref:N), [ref:N], "ref:N", or any other citation format.
Only cite sources you actually use. Do not cite if the information comes from your general knowledge.

Reference Materials:

{context_text}

---

User question: {user_message}

Remember: Only use [[cite:N]] citations when you actually use information from the references above."""


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

    # Save user message with images and file_urls
    await Message.create(
        conversation=conversation,
        role=MessageRole.USER,
        content=chat_in.message,
        images=[img.model_dump() for img in chat_in.images] if chat_in.images else None,
        file_urls=[f.model_dump() for f in chat_in.file_urls]
        if chat_in.file_urls
        else None,
        rag_context=rag_contexts if rag_contexts else None,
    )

    # Update message stats (user message, no tokens)
    await update_message_stats(agent, token_usage=None)

    # Build messages for LLM
    messages = await build_messages(
        agent, conversation, final_message, user_locale=current_user.locale
    )

    # Get model identifier
    model_id = await get_model_identifier(agent)

    try:
        # Import here to avoid circular import
        from app.llm import model_manager
        from app.llm.errors import QuotaExceededError, LLMError
        from app.llm.types import ToolDefinition, FunctionDefinition

        # Build tool definitions
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

        # Tool call loop (non-streaming)
        max_iterations = agent.max_iterations or 5
        iteration = 0
        final_response = None
        total_prompt_tokens = 0
        total_completion_tokens = 0

        while iteration < max_iterations:
            iteration += 1
            response = await model_manager.team_chat(
                team_id=str(agent.team_id),
                messages=[m.model_dump() for m in messages],
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
                        "arguments": safe_parse_arguments(tc.function.arguments),
                    }
                    for tc in response.tool_calls
                ]

                # Save intermediate assistant message with tool calls
                await Message.create(
                    conversation=conversation,
                    role=MessageRole.ASSISTANT,
                    content=response.content or "",
                    reasoning_content=response.reasoning_content or None,
                    model_used=response.model,
                    tool_calls=intermediate_tool_calls,
                )

                # Append assistant tool calls to LLM messages for next iteration
                messages.append(
                    LLMMessage(
                        role=LLMMessageRole.ASSISTANT,
                        content=response.content or "",
                        reasoning_content=response.reasoning_content or None,
                        tool_calls=[
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in response.tool_calls
                        ],
                    )
                )

                # Execute tools and add tool results to message history
                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                    result = await execute_tool_call(
                        tool_name, arguments, agent=agent, user=current_user
                    )
                    display_result, llm_result = get_tool_execution_payloads(result)

                    await Message.create(
                        conversation=conversation,
                        role=MessageRole.TOOL,
                        content=display_result,
                        tool_call_id=tc.id,
                        tool_name=tool_name,
                    )

                    messages.append(
                        LLMMessage(
                            role=LLMMessageRole.TOOL,
                            content=llm_result,
                            tool_call_id=tc.id,
                        )
                    )
                continue

            final_response = response
            break

        if final_response is None:
            final_response = response

        duration_ms = int((time.time() - start_time) * 1000)

        # Save assistant message (final response)
        assistant_msg = await Message.create(
            conversation=conversation,
            role=MessageRole.ASSISTANT,
            content=final_response.content or "",
            reasoning_content=final_response.reasoning_content or None,
            model_used=final_response.model,
            token_usage={
                "prompt": total_prompt_tokens
                if total_prompt_tokens
                else (
                    final_response.usage.prompt_tokens if final_response.usage else 0
                ),
                "completion": total_completion_tokens
                if total_completion_tokens
                else (
                    final_response.usage.completion_tokens
                    if final_response.usage
                    else 0
                ),
            },
            duration_ms=duration_ms,
            tool_calls=[tc.model_dump() for tc in final_response.tool_calls]
            if final_response.tool_calls
            else None,
        )

        # Update message stats with token usage
        await update_message_stats(
            agent,
            token_usage={
                "prompt": total_prompt_tokens
                if total_prompt_tokens
                else (
                    final_response.usage.prompt_tokens if final_response.usage else 0
                ),
                "completion": total_completion_tokens
                if total_completion_tokens
                else (
                    final_response.usage.completion_tokens
                    if final_response.usage
                    else 0
                ),
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
            token_usage=F("token_usage")
            + (
                (total_prompt_tokens + total_completion_tokens)
                if (total_prompt_tokens or total_completion_tokens)
                else (final_response.usage.total_tokens if final_response.usage else 0)
            ),
            **title_update,
        )

        # Update agent stats atomically
        await Agent.filter(id=agent.id).update(message_count=F("message_count") + 2)

        return success(
            data=ChatResponse(
                conversation_id=conversation.id,
                message=MessageOut.model_validate(assistant_msg),
                usage={
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                }
                if (total_prompt_tokens or total_completion_tokens)
                else (
                    final_response.usage.model_dump() if final_response.usage else None
                ),
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
    - content_delta: {"delta": "..."}
    - rag_context: {"contexts": [...]}
    - tool_call: {"tool_name": "...", "arguments": {...}}
    - tool_result: {"tool_name": "...", "result": {...}}
    - media_result: {"kind": "media.image"|"media.video", ...} (UI-only media payload for rendering in assistant body, not for LLM replay)
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
            FinishReason,
        )

        # Get streaming configuration
        streaming_config = get_streaming_config(agent)
        global_timeout = streaming_config["global_timeout"]
        heartbeat_interval = streaming_config["heartbeat_interval"]
        tool_timeouts = streaming_config["tool_timeouts"]

        # Record start time and last event time
        start_time = time.time()
        first_token_time: float | None = None
        last_event_time = start_time
        full_content = ""
        full_reasoning = ""
        message_id = None

        logger.info(
            f"Starting stream for conversation {conversation.id}, "
            f"global_timeout={global_timeout}s, heartbeat_interval={heartbeat_interval}s"
        )

        try:
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
                            # Model doesn't support vision - send error event with i18n key
                            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_VISION_NOT_SUPPORTED, 'msg': 'model_vision_not_supported'})}\n\n"
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
                    last_event_time = time.time()

                    # Build messages for LLM using proper types
                    messages_for_llm: list[LLMTypeMessage] = []

                    # Build file content string for injection into {{fileContent}}
                    file_content_str = ""
                    if agent.enable_file_upload:
                        from app.services.file_parser import (
                            file_parser_service,
                            ParsedFile,
                            FileParseConfig,
                        )

                        parsed_files: list[ParsedFile] = []

                        # Get file upload config
                        file_config = agent.file_upload_config or {}
                        parser_config = file_config.get("parser")
                        parse_config = FileParseConfig(
                            max_content_length=file_config.get(
                                "max_content_length", 100000
                            ),
                            truncate_strategy=file_config.get(
                                "truncate_strategy", "end"
                            ),
                        )

                        # Handle file_urls: download and parse files
                        if chat_in.file_urls and parser_config:
                            import httpx

                            # Check parser type
                            parser_type = parser_config.get("type", "builtin")
                            parser_name = parser_config.get("name", "markitdown")
                            parser_tool_id = parser_config.get("tool_id")

                            if parser_type == "builtin" and parser_name == "markitdown":
                                # Use built-in file_parser_service with configurable timeout
                                download_timeout = tool_timeouts.get("download", 60)
                                async with httpx.AsyncClient(
                                    timeout=download_timeout, follow_redirects=True
                                ) as client:
                                    for f in chat_in.file_urls:
                                        try:
                                            url = f.url
                                            # Handle internal URLs - prepend API_BASE_URL
                                            if url.startswith("/"):
                                                base_url = settings.API_BASE_URL.rstrip(
                                                    "/"
                                                )
                                                url = f"{base_url}{url}"

                                            response = await client.get(url)
                                            response.raise_for_status()
                                            file_content = response.content

                                            # Parse file
                                            parsed = (
                                                await file_parser_service.parse_file(
                                                    file_content,
                                                    f.filename,
                                                    parse_config,
                                                )
                                            )
                                            parsed_files.append(parsed)
                                        except Exception as e:
                                            logger.warning(
                                                "Failed to parse file %s: %s",
                                                f.filename,
                                                e,
                                            )
                                            # Add error placeholder
                                            parsed_files.append(
                                                ParsedFile(
                                                    filename=f.filename,
                                                    content=t("file_parse_failed_placeholder"),
                                                    mime_type=f.mime_type,
                                                    size=f.size,
                                                )
                                            )

                            elif parser_type == "custom" and parser_tool_id:
                                # Use custom tool for parsing
                                from app.models.tool import Tool

                                custom_tool = await Tool.filter(
                                    id=parser_tool_id, is_enabled=True
                                ).first()
                                if custom_tool:
                                    try:
                                        # Call custom tool with files_url parameter
                                        urls = [f.url for f in chat_in.file_urls]
                                        result = await execute_tool_call(
                                            f"custom_{custom_tool.name}",
                                            {"files_url": urls},
                                            agent,
                                            user=current_user,
                                        )
                                        display_result, _ = get_tool_execution_payloads(
                                            result
                                        )
                                        # Custom tool returns parsed content as string
                                        if display_result:
                                            parsed_files.append(
                                                ParsedFile(
                                                    filename="自定义解析结果",
                                                    content=display_result,
                                                    mime_type="text/plain",
                                                    size=len(display_result),
                                                )
                                            )
                                    except Exception as e:
                                        logger.warning("Custom parser failed: %s", e)
                                        parsed_files.append(
                                            ParsedFile(
                                                filename=t("custom_parser_filename"),
                                                content=t("custom_parser_failed_placeholder"),
                                                mime_type="text/plain",
                                                size=0,
                                            )
                                        )

                            # Handle legacy files field (deprecated, frontend sends parsed content)
                            elif chat_in.files:
                                for f in chat_in.files:
                                    parsed_files.append(
                                        ParsedFile(
                                            filename=f.filename,
                                            content=f.content,
                                            mime_type=f.mime_type,
                                            size=f.size,
                                            truncated=f.truncated,
                                            original_length=f.original_length,
                                        )
                                    )

                            if parsed_files:
                                file_content_str = (
                                    file_parser_service.format_files_for_prompt(
                                        parsed_files, locale=current_user.locale
                                    )
                                )

                    # System prompt - always add with language instruction
                    system_prompt = agent.system_prompt or ""
                    if system_prompt:
                        for key, value in conversation.variables.items():
                            system_prompt = system_prompt.replace(
                                f"{{{{{key}}}}}", str(value)
                            )

                        # Inject {{query}} variable - user's current input
                        system_prompt = system_prompt.replace(
                            "{{query}}", chat_in.message
                        )

                        # Inject file content into {{fileContent}} variable
                        if file_content_str:
                            system_prompt = system_prompt.replace(
                                "{{fileContent}}", file_content_str
                            )
                        else:
                            system_prompt = system_prompt.replace("{{fileContent}}", "")

                    # Build system prompt with language instruction (always added)
                    system_prompt = build_system_prompt_with_language(
                        system_prompt, current_user.locale
                    )

                    # Add user input request instructions if enabled
                    if agent.enable_user_input_request:
                        user_input_instruction = get_user_input_request_instruction(
                            current_user.locale
                        )
                        system_prompt = f"{system_prompt}\n\n{user_input_instruction}"

                    messages_for_llm.append(
                        LLMTypeMessage(role=LLMTypeRole.SYSTEM, content=system_prompt)
                    )

                    # Helper function to build multimodal content for vision
                    def build_vision_content(
                        text: str, images: list
                    ) -> list[ContentPart]:
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
                                        type=ContentType.IMAGE,
                                        image=ImageContent(url=img_url),
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
                                        role=LLMTypeRole.ASSISTANT,
                                        content=hist_msg.content,
                                        reasoning_content=getattr(
                                            hist_msg, "reasoning_content", None
                                        ),
                                    )
                                )

                        # Add current user message with RAG and vision support
                        current_content: str | list = final_message
                        if chat_in.images and model_supports_vision:
                            current_content = build_vision_content(
                                final_message, chat_in.images
                            )
                        messages_for_llm.append(
                            LLMTypeMessage(
                                role=LLMTypeRole.USER, content=current_content
                            )
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
                                    final_message
                                    if msg.id == user_msg.id
                                    else msg.content
                                )

                                # Check if this is the current message with images and vision is enabled
                                if (
                                    msg.id == user_msg.id
                                    and chat_in.images
                                    and model_supports_vision
                                ):
                                    # Build multimodal content for vision
                                    content = build_vision_content(
                                        text_content, chat_in.images
                                    )
                                else:
                                    content = text_content

                                messages_for_llm.append(
                                    LLMTypeMessage(
                                        role=LLMTypeRole.USER, content=content
                                    )
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
                                        reasoning_content=msg.reasoning_content,
                                        tool_calls=llm_tool_calls
                                        if llm_tool_calls
                                        else None,
                                    )
                                )
                            elif msg.role == MessageRole.TOOL:
                                # Only include tool messages that have a corresponding tool_call
                                if (
                                    msg.tool_call_id
                                    and msg.tool_call_id in valid_tool_call_ids
                                ):
                                    messages_for_llm.append(
                                        LLMTypeMessage(
                                            role=LLMTypeRole.TOOL,
                                            content=summarize_tool_result_for_llm(
                                                msg.tool_name,
                                                msg.content,
                                            ),
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
                            # Client disconnected, save partial content and exit
                            if full_content or full_reasoning:
                                assistant_msg.content = full_content
                                assistant_msg.reasoning_content = (
                                    full_reasoning if full_reasoning else None
                                )
                                assistant_msg.model_used = model_id
                                assistant_msg.duration_ms = int(
                                    (time.time() - start_time) * 1000
                                )
                                await assistant_msg.save()
                            return

                        # If we need to send heartbeat
                        if new_last_event_time > last_event_time:
                            yield ": heartbeat\n\n"
                            last_event_time = new_last_event_time

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
                        emitted_any = False
                        client_disconnected = False
                        async for chunk in model_manager.team_chat_stream(
                            team_id=str(agent.team_id),
                            messages=messages_for_llm,
                            model_id=model_id,
                            tools=tools,
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
                                # Stream content normally
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
                            # Save partial content if any was generated
                            if full_content or full_reasoning:
                                assistant_msg.content = full_content
                                assistant_msg.reasoning_content = (
                                    full_reasoning if full_reasoning else None
                                )
                                assistant_msg.model_used = model_id
                                assistant_msg.duration_ms = int(
                                    (time.time() - start_time) * 1000
                                )
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
                            # Process each tool call
                            for tc in collected_tool_calls:
                                # Check if client disconnected before tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected before tool execution"
                                    )
                                    if full_content or full_reasoning:
                                        assistant_msg.content = full_content
                                        assistant_msg.reasoning_content = (
                                            full_reasoning if full_reasoning else None
                                        )
                                        assistant_msg.model_used = model_id
                                        assistant_msg.duration_ms = int(
                                            (time.time() - start_time) * 1000
                                        )
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
                                )
                                display_result, llm_result = (
                                    get_tool_execution_payloads(result)
                                )

                                # Check if client disconnected after tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected after tool execution"
                                    )
                                    if full_content or full_reasoning:
                                        assistant_msg.content = full_content
                                        assistant_msg.reasoning_content = (
                                            full_reasoning if full_reasoning else None
                                        )
                                        assistant_msg.model_used = model_id
                                        assistant_msg.duration_ms = int(
                                            (time.time() - start_time) * 1000
                                        )
                                        await assistant_msg.save()
                                    return

                                # Send tool_result event
                                yield f"event: {SSEEventType.TOOL_RESULT}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'tool_display_name': tool_display_name, 'result': display_result})}\n\n"
                                media_payload = extract_media_display_payload(
                                    display_result
                                )
                                if media_payload:
                                    yield f"event: {SSEEventType.MEDIA_RESULT}\ndata: {json.dumps(media_payload, ensure_ascii=False)}\n\n"
                                last_event_time = time.time()

                                # Add to pending tool calls for message building
                                pending_tool_calls.append(
                                    {
                                        "id": tc.id,
                                        "name": tool_name,
                                        "arguments": arguments,
                                        "display_result": display_result,
                                        "llm_result": llm_result,
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
                                    "display_name": tool_display_names.get(
                                        tc.function.name, tc.function.name
                                    ),
                                    "arguments": safe_parse_arguments(
                                        tc.function.arguments
                                    ),
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
                                    content=tc_data["display_result"],
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
                                    reasoning_content=iteration_reasoning or None,
                                    tool_calls=assistant_tool_calls,
                                )
                            )

                            # Add tool results to message history
                            for tc_data in pending_tool_calls:
                                messages_for_llm.append(
                                    LLMTypeMessage(
                                        role=LLMTypeRole.TOOL,
                                        content=tc_data["llm_result"],
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
                    assistant_msg.reasoning_content = (
                        full_reasoning if full_reasoning else None
                    )
                    assistant_msg.model_used = model_id
                    assistant_msg.duration_ms = duration_ms
                    # Ensure assistant message appears after tool calls/results in history
                    assistant_msg.created_at = now_utc()
                    # Estimate token usage
                    input_tokens = sum(
                        len(m.content or "") // 4 for m in messages_for_llm
                    )
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

                except QuotaExceededError as e:
                    logger.warning("Quota exceeded during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except ModelNotFoundError as e:
                    logger.error("Model not found error during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_NOT_FOUND, 'msg': t('model_not_found')})}\n\n"
                except AuthenticationError as e:
                    logger.error("Authentication error during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNAUTHORIZED, 'msg': t('unauthorized')})}\n\n"
                except RateLimitError as e:
                    logger.warning("Rate limit error during stream: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('rate_limit_exceeded')})}\n\n"
                except LLMError as e:
                    logger.exception(f"LLM error during stream: {e}")
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': GENERIC_STREAM_ERROR_MSG})}\n\n"
                except Exception as e:
                    logger.exception(f"Unexpected error during stream: {e}")
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': GENERIC_STREAM_ERROR_MSG})}\n\n"

        except TimeoutError:
            # Global timeout
            logger.warning(
                f"Stream global timeout ({global_timeout}s) for conversation {conversation.id}"
            )
            # Save partial content
            if full_content or full_reasoning:
                assistant_msg.content = full_content
                assistant_msg.reasoning_content = (
                    full_reasoning if full_reasoning else None
                )
                assistant_msg.model_used = model_id
                assistant_msg.duration_ms = int((time.time() - start_time) * 1000)
                await assistant_msg.save()
            # Send timeout error event
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': global_timeout})}\n\n"

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
        # Get all tool_call_ids from the target version
        target_tool_call_ids = set()
        if target_version.tool_calls:
            for tc in target_version.tool_calls:
                if isinstance(tc, dict) and "id" in tc:
                    target_tool_call_ids.add(tc["id"])

        # Deactivate all messages after the root message in the conversation
        # EXCEPT the target version itself and tool messages that belong to it
        messages_to_deactivate = await Message.filter(
            conversation_id=message.conversation_id,
            created_at__gt=root_message.created_at,
            is_active=True,
        ).all()

        for msg in messages_to_deactivate:
            # Keep the target version itself
            if msg.id == target_version.id:
                continue
            # Keep tool messages that belong to the target version
            if (
                msg.role == MessageRole.TOOL
                and msg.tool_call_id in target_tool_call_ids
            ):
                continue
            # Deactivate all other messages
            msg.is_active = False
            await msg.save()

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
            FinishReason,
        )

        # Get streaming configuration
        streaming_config = get_streaming_config(agent)
        global_timeout = streaming_config["global_timeout"]
        heartbeat_interval = streaming_config["heartbeat_interval"]
        tool_timeouts = streaming_config["tool_timeouts"]

        # Record start time and last event time
        start_time = time.time()
        first_token_time: float | None = None
        last_event_time = start_time
        full_content = ""
        full_reasoning = ""
        new_message_id = None

        logger.info(
            f"Starting regenerate stream for message {message_id}, "
            f"global_timeout={global_timeout}s, heartbeat_interval={heartbeat_interval}s"
        )

        try:
            # Use asyncio.timeout to wrap entire streaming logic
            import asyncio

            async with asyncio.timeout(global_timeout):
                try:
                    from app.models.agent import RAGMode

                    # Determine the root message ID for versioning
                    root_id = message.parent_id or message.id

                    # Get current version count
                    current_version_count = (
                        await Message.filter(parent_id=root_id).count() + 1
                    )
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

                    # Build messages for LLM - only include ACTIVE messages before this one
                    messages_for_llm: list[LLMTypeMessage] = []

                    # System prompt - always add with language instruction
                    system_prompt = agent.system_prompt or ""
                    if system_prompt:
                        for key, value in conversation.variables.items():
                            system_prompt = system_prompt.replace(
                                f"{{{{{key}}}}}", str(value)
                            )
                        # Inject {{query}} variable - user's current input
                        system_prompt = system_prompt.replace(
                            "{{query}}", user_message.content
                        )

                    # Build system prompt with language instruction (always added)
                    system_prompt = build_system_prompt_with_language(
                        system_prompt, current_user.locale
                    )

                    # Add user input request instructions if enabled
                    if agent.enable_user_input_request:
                        user_input_instruction = get_user_input_request_instruction(
                            current_user.locale
                        )
                        system_prompt = f"{system_prompt}\n\n{user_input_instruction}"

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
                                final_message
                                if msg.id == user_message.id
                                else msg.content
                            )
                            messages_for_llm.append(
                                LLMTypeMessage(
                                    role=LLMTypeRole.USER, content=text_content
                                )
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
                                    reasoning_content=msg.reasoning_content,
                                    tool_calls=llm_tool_calls
                                    if llm_tool_calls
                                    else None,
                                )
                            )
                        elif msg.role == MessageRole.TOOL:
                            if (
                                msg.tool_call_id
                                and msg.tool_call_id in valid_tool_call_ids
                            ):
                                messages_for_llm.append(
                                    LLMTypeMessage(
                                        role=LLMTypeRole.TOOL,
                                        content=summarize_tool_result_for_llm(
                                            msg.tool_name,
                                            msg.content,
                                        ),
                                        tool_call_id=msg.tool_call_id,
                                    )
                                )

                    # Get model and tools
                    model_id = await get_model_identifier(agent)
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
                            # Client disconnected, save partial content and exit
                            if full_content or full_reasoning:
                                new_message.content = full_content
                                new_message.reasoning_content = (
                                    full_reasoning if full_reasoning else None
                                )
                                new_message.model_used = model_id
                                new_message.duration_ms = int(
                                    (time.time() - start_time) * 1000
                                )
                                await new_message.save()
                            return

                        # If we need to send heartbeat
                        if new_last_event_time > last_event_time:
                            yield ": heartbeat\n\n"
                            last_event_time = new_last_event_time

                        reasoning_started = False
                        collected_tool_calls = []
                        client_disconnected = False

                        async for chunk in model_manager.team_chat_stream(
                            team_id=str(agent.team_id),
                            messages=messages_for_llm,
                            model_id=model_id,
                            tools=tools,
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

                        # If client disconnected, save partial content and exit
                        if client_disconnected:
                            if full_content or full_reasoning:
                                new_message.content = full_content
                                new_message.reasoning_content = (
                                    full_reasoning if full_reasoning else None
                                )
                                new_message.model_used = model_id
                                new_message.duration_ms = int(
                                    (time.time() - start_time) * 1000
                                )
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
                                    if full_content or full_reasoning:
                                        new_message.content = full_content
                                        new_message.reasoning_content = (
                                            full_reasoning if full_reasoning else None
                                        )
                                        new_message.model_used = model_id
                                        new_message.duration_ms = int(
                                            (time.time() - start_time) * 1000
                                        )
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
                                )
                                display_result, llm_result = (
                                    get_tool_execution_payloads(result)
                                )

                                # Check if client disconnected after tool execution
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected after tool execution in regenerate"
                                    )
                                    if full_content or full_reasoning:
                                        new_message.content = full_content
                                        new_message.reasoning_content = (
                                            full_reasoning if full_reasoning else None
                                        )
                                        new_message.model_used = model_id
                                        new_message.duration_ms = int(
                                            (time.time() - start_time) * 1000
                                        )
                                        await new_message.save()
                                    return

                                yield f"event: {SSEEventType.TOOL_RESULT}\ndata: {json.dumps({'tool_call_id': tc.id, 'tool_name': tool_name, 'tool_display_name': tool_display_name, 'result': display_result})}\n\n"
                                last_event_time = time.time()

                                await Message.create(
                                    conversation=conversation,
                                    role=MessageRole.TOOL,
                                    content=display_result,
                                    tool_call_id=tc.id,
                                    tool_name=tool_name,
                                    parent_id=new_message.parent_id or new_message.id,
                                    version_number=new_version_number,
                                )

                                # Add to message history for next iteration
                                messages_for_llm.append(
                                    LLMTypeMessage(
                                        role=LLMTypeRole.ASSISTANT,
                                        content="",
                                        reasoning_content="",
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
                                        content=llm_result,
                                        tool_call_id=tc.id,
                                    )
                                )
                            continue
                        else:
                            break

                    duration_ms = int((time.time() - start_time) * 1000)

                    # Update new message
                    new_message.content = full_content
                    new_message.reasoning_content = (
                        full_reasoning if full_reasoning else None
                    )
                    new_message.model_used = model_id
                    new_message.duration_ms = duration_ms
                    # Ensure regenerated message appears after tool calls/results in history
                    new_message.created_at = now_utc()
                    input_tokens = sum(
                        len(m.content or "") // 4 for m in messages_for_llm
                    )
                    output_tokens = len(full_content) // 4
                    new_message.token_usage = {
                        "prompt": input_tokens,
                        "completion": output_tokens,
                    }
                    await new_message.save()

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

                except QuotaExceededError as e:
                    # Rollback: delete new message and restore original
                    if new_message_id:
                        await Message.filter(id=new_message_id).delete()
                        # Restore original message as active
                        await Message.filter(id=message.id).update(is_active=True)
                    logger.warning("Quota exceeded during regenerate: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.MODEL_QUOTA_EXCEEDED, 'msg': t('model_quota_exceeded'), 'quota_type': e.quota_type})}\n\n"
                except LLMError as e:
                    # Rollback: delete new message and restore original
                    if new_message_id:
                        await Message.filter(id=new_message_id).delete()
                        # Restore original message as active
                        await Message.filter(id=message.id).update(is_active=True)
                    logger.exception("LLM error during regenerate: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': GENERIC_STREAM_ERROR_MSG})}\n\n"
                except Exception as e:
                    # Rollback: delete new message and restore original
                    if new_message_id:
                        await Message.filter(id=new_message_id).delete()
                        # Restore original message as active
                        await Message.filter(id=message.id).update(is_active=True)
                    logger.exception("Unexpected error during regenerate: %s", e)
                    yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': GENERIC_STREAM_ERROR_MSG})}\n\n"

        except TimeoutError:
            # Global timeout
            logger.warning(
                f"Regenerate stream global timeout ({global_timeout}s) for message {message_id}"
            )
            # Save partial content
            if full_content or full_reasoning:
                new_message.content = full_content
                new_message.reasoning_content = (
                    full_reasoning if full_reasoning else None
                )
                new_message.model_used = model_id
                new_message.duration_ms = int((time.time() - start_time) * 1000)
                await new_message.save()
            # Send timeout error event
            yield f"event: {SSEEventType.ERROR}\ndata: {json.dumps({'code': ResponseCode.UNKNOWN_ERROR, 'msg': t('stream_timeout_exceeded'), 'timeout': global_timeout})}\n\n"

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
