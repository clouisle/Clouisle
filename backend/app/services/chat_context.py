"""Shared chat context preparation helpers for agent chat flows."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from app.llm.errors import ContextLengthError
from app.llm.adapters.media_utils import parse_image_data_url
from app.llm.token_counter import count_message_tokens
from app.llm.types import (
    ContentPart,
    ContentType,
    FunctionCall,
    ImageContent,
    Message,
    MessageRole,
    ToolCall,
)
from app.models.agent import (
    Agent,
    Conversation,
    Message as ConversationMessage,
    MessageRole as ConversationMessageRole,
)
from app.services.message_branching import (
    get_visible_conversation_messages,
    is_message_on_active_branch,
)

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_LIMIT = 32000
DEFAULT_OUTPUT_TOKEN_RESERVE = 4000
DEFAULT_SAFETY_MARGIN_TOKENS = 1000
DEFAULT_RECENT_REASONING_MESSAGES = 2
DEFAULT_RECENT_RAW_TURNS = 3
DEFAULT_RECENT_TOOL_TURNS = 2
DEFAULT_SUMMARY_MAX_TOKENS = 1000
DEFAULT_SUMMARY_MAX_CHARS = DEFAULT_SUMMARY_MAX_TOKENS * 4
DEFAULT_BLOCK_SUMMARY_CHARS = 320
DEFAULT_WARNING_RATIO = 0.7
DEFAULT_AUTO_COMPACT_TRIGGER_RATIO = 0.8
DEFAULT_BLOCKING_RATIO = 0.92
DEFAULT_COMPACTION_POLICY = "staged"
DEFAULT_RETENTION_STRATEGY = "recent_raw_and_tool_first"
DEFAULT_KEEP_RECENT_TOOL_RESULTS = 2
DEFAULT_KEEP_RECENT_TOOL_RESULT_MINUTES = 20
DEFAULT_TOOL_RESULT_COMPACT_MIN_TOKENS = 256
DEFAULT_SESSION_MEMORY_MAX_TOKENS = 400
DEFAULT_SESSION_MEMORY_MIN_TURNS = 4
DEFAULT_SESSION_MEMORY_FAILURE_THRESHOLD = 3
DEFAULT_SESSION_MEMORY_COOLDOWN_SECONDS = 600
DEFAULT_LEGACY_COMPACT_FAILURE_THRESHOLD = 2
DEFAULT_LEGACY_COMPACT_COOLDOWN_SECONDS = 600
AGGRESSIVE_RECENT_REASONING_MESSAGES = 0
AGGRESSIVE_RECENT_RAW_TURNS = 2
AGGRESSIVE_RECENT_TOOL_TURNS = 1
AGGRESSIVE_SUMMARY_MAX_CHARS = 2400
AGGRESSIVE_BLOCK_SUMMARY_CHARS = 220
DEFAULT_FILE_CONTENT_HEAD_CHARS = 12000
DEFAULT_FILE_CONTENT_TAIL_CHARS = 4000
FILE_CONTENT_PLACEHOLDER = "{{fileContent}}"
MARKDOWN_IMAGE_DISPLAY_INSTRUCTION = """## Markdown Output

When the user asks you to show or display an image, output the image using normal Markdown image syntax, for example `![alt text](image-url)`. Do not wrap the Markdown image in a code block unless the user explicitly asks for the literal Markdown source.

When writing math, use standard Markdown/LaTeX delimiters that render correctly:
- Use `$...$` for inline math.
- Use `$$...$$` on separate lines for display/block math.
- Do not use nonstandard math delimiters such as `[ ... ]`, `\[ ... \]`, `( ... )`, `\( ... \)`, or bare parenthesized TeX like `(\mathbf{A})`. Write those as `$\mathbf{A}$` inline, or use `$$...$$` for standalone equations. Keep the whole formula inside one delimiter pair; do not put only part of an equation in `$...$`."""
DEFAULT_CONTEXT_COMPRESSION_CONFIG = {
    "enabled": True,
    "micro_compaction_enabled": True,
    "macro_compaction_enabled": True,
    "preflight_guard_enabled": True,
    "reactive_retry_enabled": True,
    "recent_raw_turns": DEFAULT_RECENT_RAW_TURNS,
    "recent_tool_turns": DEFAULT_RECENT_TOOL_TURNS,
    "output_token_reserve": DEFAULT_OUTPUT_TOKEN_RESERVE,
    "safety_margin_tokens": DEFAULT_SAFETY_MARGIN_TOKENS,
    "summary_max_tokens": DEFAULT_SUMMARY_MAX_TOKENS,
    "drop_historical_reasoning_first": True,
    "emit_sse_events": True,
    "warning_ratio": DEFAULT_WARNING_RATIO,
    "auto_compact_trigger_ratio": DEFAULT_AUTO_COMPACT_TRIGGER_RATIO,
    "blocking_ratio": DEFAULT_BLOCKING_RATIO,
    "compaction_policy": DEFAULT_COMPACTION_POLICY,
    "macro_on_trigger": False,
    "retention_strategy": DEFAULT_RETENTION_STRATEGY,
    "keep_recent_tool_results": DEFAULT_KEEP_RECENT_TOOL_RESULTS,
    "keep_recent_tool_result_minutes": DEFAULT_KEEP_RECENT_TOOL_RESULT_MINUTES,
    "tool_result_compact_min_tokens": DEFAULT_TOOL_RESULT_COMPACT_MIN_TOKENS,
    "session_memory_enabled": True,
    "session_memory_async_extract": True,
    "session_memory_max_tokens": DEFAULT_SESSION_MEMORY_MAX_TOKENS,
    "session_memory_min_turns": DEFAULT_SESSION_MEMORY_MIN_TURNS,
    "session_memory_failure_threshold": DEFAULT_SESSION_MEMORY_FAILURE_THRESHOLD,
    "session_memory_cooldown_seconds": DEFAULT_SESSION_MEMORY_COOLDOWN_SECONDS,
    "legacy_compact_enabled": True,
    "legacy_compact_failure_threshold": DEFAULT_LEGACY_COMPACT_FAILURE_THRESHOLD,
    "legacy_compact_cooldown_seconds": DEFAULT_LEGACY_COMPACT_COOLDOWN_SECONDS,
}


@dataclass(slots=True)
class TokenBudget:
    context_limit: int
    output_reserve: int
    safety_margin: int
    input_budget: int


@dataclass(slots=True)
class CompressionThresholds:
    warning_input_budget: int
    trigger_input_budget: int
    blocking_input_budget: int


@dataclass(slots=True)
class CompressionMeta:
    stage: Literal["none", "micro", "macro", "reactive_retry"]
    before_tokens: int
    after_tokens: int
    input_budget: int
    reasoning_trimmed: bool = False
    tool_results_trimmed: bool = False
    file_content_trimmed: bool = False
    summary_turns: int = 0
    pressure_level: Literal[
        "normal", "warning", "auto_compact", "blocking", "over_budget"
    ] = "normal"
    trigger_ratio: float = 1.0
    warning_ratio: float = DEFAULT_WARNING_RATIO
    blocking_ratio: float = DEFAULT_BLOCKING_RATIO
    trigger_budget: int = 0
    hard_budget: int = 0
    utilization_before: float = 0.0
    utilization_after: float = 0.0
    policy_used: str = DEFAULT_COMPACTION_POLICY
    actions: list[str] | None = None
    retained_recent_turns: int = 0
    retained_tool_turns: int = 0
    compacted_blocks: int = 0
    session_memory_compacted: bool = False


@dataclass(slots=True)
class PreparedModelContext:
    messages: list[Message]
    token_budget: TokenBudget
    compression: CompressionMeta
    protected_indexes: set[int] = field(default_factory=set)


def _clone_messages(
    messages: Sequence[Message],
    protected_indexes: set[int] | None = None,
) -> tuple[list[Message], set[int]]:
    return [message.model_copy(deep=True) for message in messages], {
        index for index in (protected_indexes or set()) if 0 <= index < len(messages)
    }


def _matches_protected_round(
    round_id: Any,
    protected_round_id: UUID | str | None,
) -> bool:
    return (
        protected_round_id is not None
        and round_id is not None
        and str(round_id) == str(protected_round_id)
    )


def _append_message(
    messages: list[Message],
    protected_indexes: set[int],
    message: Message,
    *,
    protect: bool = False,
) -> None:
    messages.append(message)
    if protect:
        protected_indexes.add(len(messages) - 1)


def _extend_with_original_indexes(
    target_messages: list[Message],
    target_protected_indexes: set[int],
    source_messages: Sequence[Message],
    original_indexes: Sequence[int],
    protected_indexes: set[int] | None = None,
) -> None:
    protected_indexes = protected_indexes or set()
    for message, original_index in zip(source_messages, original_indexes, strict=False):
        _append_message(
            target_messages,
            target_protected_indexes,
            message.model_copy(deep=True),
            protect=original_index in protected_indexes,
        )


LANGUAGE_INSTRUCTIONS = {
    "en": "## Response Language\nYou MUST respond in English only. Do not use any other language.",
    "zh": "## 回复语言\n你必须使用中文回复。不要使用其他语言。",
}

MEMORY_SYSTEM_INSTRUCTION = """
## Memory System

You have access to these memory tools:
- `search_memory(query)`: Search what you know about the user
- `create_memory_entity(name, entity_type, description)`: Save new information
- `update_memory_entity(entity_name, description)`: Update existing information
- `create_memory_relation(source, target, relation_type)`: Connect related information

### Required Workflow

1. Before **any** `create_memory_entity()` call, you **must** call `search_memory()` first.
2. When the user shares information such as a name, preference, or skill:
   - Step 1: Call `search_memory(query="keywords about the information")`
   - Step 2: Read the search results carefully
   - Step 3: Decide based on the results:
     - Found a similar entity → use `update_memory_entity(entity_name="existing name", ...)`
     - Found nothing relevant → use `create_memory_entity(name="new name", ...)`
3. Never skip `search_memory()`, even if you think the information is new.
4. Never say you do not have access to memory tools.

### Examples

**Wrong**

User: "I'm Alice"

❌ Directly calling `create_memory_entity(name="Alice", ...)` is wrong because no search happened first.

**Correct**

User: "I'm Alice"
- Call `search_memory(query="user name")`
- Check results → No "Alice" found
- Call `create_memory_entity(name="Alice", entity_type="person", description="User's name")`

User: "Actually, I'm Alice Smith"
- Call `search_memory(query="user name Alice")`
- Check results → Found entity "Alice"
- Call `update_memory_entity(entity_name="Alice", description="Full name: Alice Smith")`

User: "What's my name?"
- Call `search_memory(query="user name")`
- Then answer using the result
"""

SANDBOX_SYSTEM_INSTRUCTION = """
## Sandbox Environment Guidance

You have access to sandbox tools: `bash`, `read`, `write`, and `artifact`. Use them with an accurate mental model of the environment instead of guessing how the sandbox works.

### Environment Reality

1. **`/workspace` is the intended working area**
   - `/workspace` is a logical alias used by the sandbox tools for the current session workspace
   - Use `/workspace/...` when calling sandbox tools such as `bash`, `read`, `write`, and `artifact`
   - Do not assume code written inside a generated Python or Node script should hardcode `/workspace/...` for its own file I/O
   - Inside generated scripts, prefer paths relative to the script's working directory such as `output/report.docx`, or derive paths from `Path.cwd()` when needed
   - Keep scripts, inputs, temporary files, and outputs under `/workspace`
   - Prefer stable locations such as `/workspace/src`, `/workspace/data`, `/workspace/output`, and `/workspace/tmp`

2. **Path behavior must be observed, not assumed**
   - Do not infer path semantics from one successful command
   - If a path behaves unexpectedly, inspect it with `pwd`, `ls`, `find`, or a short Python check before changing the script or explanation
   - Prefer absolute paths for file operations instead of relying on prior `cd` state

3. **Interpreter and package state may differ from your assumptions**
   - The interpreter that installs a package and the interpreter that runs a script must be treated as concrete facts to verify
   - If an import fails, first verify interpreter identity, import path, and installed package visibility before changing code
   - Do not rely on ad-hoc `PYTHONPATH` or `sys.path` hacks unless the task explicitly requires local package loading

4. **Install output can be misleading if filtered**
   - Do not pipe install output through `tail`, `grep`, or similar filters that can hide errors
   - Do not assume an install succeeded just because the final lines look harmless
   - Confirm package availability with a real import check using the same interpreter that will run the script

5. **Command success should be interpreted narrowly**
   - One successful `touch`, `ls`, or minimal script does not prove the whole environment behaves the same way for another library or another path
   - Treat each surprising result as something to inspect, not something to explain from guesswork

6. **`artifact` depends on backend connectivity, not just local files**
   - A file existing locally does not mean artifact upload will succeed
   - If `artifact` upload fails with a connection or network error, report it clearly instead of retrying with equivalent paths

### Tool Usage Expectations

- Prefer `write` for real scripts instead of embedding complex scripts inline in `bash`
- Keep each `bash` call focused so failures stay attributable
- Use `read`, `ls -lh`, or `find` to confirm what actually exists before changing the approach
- Use `artifact` only for final deliverables after the output file has been verified locally

### Avoid These Mistakes

- Do not explain sandbox behavior from guesswork
- Do not keep retrying the same install or upload with superficial variations
- Do not use relative paths that depend on prior shell state
- Do not mistake filtered output for a successful environment change
"""


def get_language_instruction(user_locale: str | None = None) -> str:
    """Get language instruction based on user's locale setting."""
    lang = user_locale or "en"
    lang = lang.lower().split("-")[0]
    return LANGUAGE_INSTRUCTIONS.get(lang, LANGUAGE_INSTRUCTIONS["en"])


def build_system_prompt_with_language(
    system_prompt: str | None, user_locale: str | None = None
) -> str:
    """Build system prompt with language instruction."""
    instruction = get_language_instruction(user_locale)
    if not system_prompt:
        return instruction
    if instruction in system_prompt:
        return system_prompt
    return f"{system_prompt}\n\n{instruction}"


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
- Do not add any other content outside the user_input_request tags

**Use cases:**
- When you need the user to make a choice
- When offering quick action options
- When guiding the conversation flow"""


def build_vision_content(text: str, images: Sequence[Any]) -> list[ContentPart]:
    """Build multimodal content for vision-capable models."""
    content_parts: list[ContentPart] = [ContentPart(type=ContentType.TEXT, text=text)]
    for index, img in enumerate(images, start=1):
        img_url = getattr(img, "url", None)
        if not img_url and isinstance(img, dict):
            img_url = img.get("url")
        if not img_url:
            continue

        content_parts.append(
            ContentPart(type=ContentType.TEXT, text=f"Uploaded image #{index}:")
        )
        parsed_data_url = parse_image_data_url(img_url)
        if parsed_data_url:
            data_part, image_format = parsed_data_url
            content_parts.append(
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(base64=data_part, format=image_format or "png"),
                )
            )
        else:
            content_parts.append(
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(url=img_url),
                )
            )
    return content_parts


def build_uploaded_image_reference_text(images: Sequence[Any]) -> str:
    labels: list[str] = []
    for index, image in enumerate(images, start=1):
        has_image = bool(getattr(image, "url", None) or getattr(image, "base64", None))
        if isinstance(image, dict):
            has_image = bool(image.get("url") or image.get("base64"))
        if has_image:
            labels.append(f"Uploaded image #{index}: available as a reference image.")
    return "\n".join(labels)


def _safe_json_loads(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _build_skill_llm_summary(payload: dict[str, Any]) -> str | None:
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("type") != "skill_instructions":
        return None

    raw_skill = result.get("skill")
    skill = raw_skill if isinstance(raw_skill, dict) else {}
    display_name = skill.get("display_name") or skill.get("name") or "Skill"
    status = result.get("status") or "loaded"
    return f"Skill instructions for {display_name} were {status}."


def _build_media_llm_summary(
    tool_name: str | None, payload: dict[str, Any]
) -> str | None:
    kind = payload.get("kind")
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

    if kind == "media.video":
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

    return None


def summarize_tool_result_for_llm(
    tool_name: str | None,
    stored_content: str,
) -> str:
    payload = _safe_json_loads(stored_content)
    if not payload:
        return stored_content
    return (
        _build_media_llm_summary(tool_name, payload)
        or _build_skill_llm_summary(payload)
        or stored_content
    )


def _trim_file_content(
    file_content: str | None,
    aggressive: bool = False,
) -> tuple[str | None, bool]:
    head_chars = (
        DEFAULT_FILE_CONTENT_HEAD_CHARS
        if not aggressive
        else max(DEFAULT_FILE_CONTENT_HEAD_CHARS // 2, 1)
    )
    tail_chars = (
        DEFAULT_FILE_CONTENT_TAIL_CHARS
        if not aggressive
        else max(DEFAULT_FILE_CONTENT_TAIL_CHARS // 2, 1)
    )
    if not file_content or len(file_content) <= (head_chars + tail_chars):
        return file_content, False

    head = file_content[:head_chars].rstrip()
    tail = file_content[-tail_chars:].lstrip()
    trimmed = f"{head}\n\n[... file content trimmed for context budget ...]\n\n{tail}"
    return trimmed, True


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def _truncate_text(value: str | None, max_chars: int) -> str:
    normalized = _normalize_text(value)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def _limit_summary_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3].rstrip()}..."


def _stringify_content(content: str | list[ContentPart] | None) -> str:
    if isinstance(content, str):
        return content
    if not content:
        return ""

    parts: list[str] = []
    for part in content:
        if part.type == ContentType.TEXT and part.text:
            parts.append(part.text)
        elif part.type == ContentType.IMAGE:
            parts.append("[image]")
    return "\n".join(parts)


def _get_override_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _normalize_override_role(role: Any) -> str | None:
    if role is None:
        return None
    if hasattr(role, "value"):
        return str(role.value)
    return str(role)


def _has_sandbox_tools(agent: Agent) -> bool:
    tools_config = agent.tools_config or []
    for config in tools_config:
        if config.get("type") == "builtin" and config.get("name") in {
            "bash",
            "read",
            "write",
            "artifact",
        }:
            return True
        if config.get("type") == "skill":
            return True
    return False


def _append_prompt_section(base: str, section: str | None) -> str:
    normalized_section = (section or "").strip()
    if not normalized_section:
        return base
    return f"{base}\n\n{normalized_section}" if base else normalized_section


def _build_system_prompt(
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    user_locale: str | None,
) -> str:
    system_prompt = agent.system_prompt or ""
    if system_prompt:
        for key, value in conversation.variables.items():
            system_prompt = system_prompt.replace(f"{{{{{key}}}}}", str(value))
        system_prompt = system_prompt.replace("{{query}}", user_message)
        system_prompt = system_prompt.replace(FILE_CONTENT_PLACEHOLDER, "")

    system_prompt = _append_prompt_section(
        system_prompt, MARKDOWN_IMAGE_DISPLAY_INSTRUCTION
    )

    if agent.enable_memory:
        system_prompt = _append_prompt_section(system_prompt, MEMORY_SYSTEM_INSTRUCTION)
        logger.info("Added memory instructions to system prompt for agent %s", agent.id)

    if _has_sandbox_tools(agent):
        system_prompt = _append_prompt_section(
            system_prompt, SANDBOX_SYSTEM_INSTRUCTION
        )
        logger.info(
            "Added sandbox instructions to system prompt for agent %s", agent.id
        )

    system_prompt = build_system_prompt_with_language(system_prompt, user_locale)
    if agent.enable_user_input_request:
        system_prompt = _append_prompt_section(
            system_prompt,
            get_user_input_request_instruction(user_locale or "en"),
        )
    return system_prompt


def _build_current_user_content(
    user_message: str,
    current_images: Sequence[Any] | None,
    model_supports_vision: bool,
) -> str | list[ContentPart]:
    if current_images and model_supports_vision:
        return build_vision_content(user_message, current_images)
    if current_images:
        image_reference_text = build_uploaded_image_reference_text(current_images)
        if image_reference_text:
            return (
                f"{user_message}\n\n{image_reference_text}"
                if user_message
                else image_reference_text
            )
    return user_message


def _append_file_content_to_user_content(
    content: str | list[ContentPart],
    file_content: str | None,
) -> str | list[ContentPart]:
    if not file_content:
        return content
    section = f"<uploaded_files>\n{file_content.strip()}\n</uploaded_files>"
    if isinstance(content, list):
        return [
            *content,
            ContentPart(type=ContentType.TEXT, text=section),
        ]
    if not content:
        return section
    return f"{content}\n\n{section}"


async def _build_file_content_for_user_message(
    *,
    agent: Agent,
    file_urls: Sequence[Any] | None,
    legacy_files: Sequence[Any] | None = None,
    user_locale: str | None,
    tool_timeouts: dict[str, Any] | None,
    user: Any,
    source_message: ConversationMessage | None = None,
) -> str:
    if not file_urls and not legacy_files:
        return ""
    from app.api.v1.endpoints.chat_tools import build_file_content_for_context

    content, updated_file_urls = await build_file_content_for_context(
        agent=agent,
        file_urls=list(file_urls) if file_urls else None,
        legacy_files=list(legacy_files) if legacy_files else None,
        user_locale=user_locale,
        tool_timeouts=tool_timeouts,
        user=user,
    )
    if source_message is not None and updated_file_urls is not None:
        if source_message.file_urls != updated_file_urls:
            source_message.file_urls = updated_file_urls
            await source_message.save(update_fields=["file_urls"])
    return content


def _build_assistant_tool_calls(
    raw_tool_calls: list[dict[str, Any]] | None,
) -> tuple[list[ToolCall] | None, set[str]]:
    if not raw_tool_calls:
        return None, set()

    tool_calls: list[ToolCall] = []
    valid_tool_call_ids: set[str] = set()
    for tool_call in raw_tool_calls:
        tool_call_id = tool_call.get("id", "")
        valid_tool_call_ids.add(tool_call_id)
        arguments = tool_call.get("arguments", {})
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments)
        tool_calls.append(
            ToolCall(
                id=tool_call_id,
                type="function",
                function=FunctionCall(
                    name=tool_call.get("name", ""),
                    arguments=arguments,
                ),
            )
        )
    return tool_calls, valid_tool_call_ids


def _message_to_token_payload(message: Message) -> dict[str, Any]:
    return message.model_dump(exclude_none=True, mode="json")


def _estimate_message_tokens(
    messages: Sequence[Message], model_id: str, provider: str | None
) -> int:
    payload = [_message_to_token_payload(message) for message in messages]
    return count_message_tokens(payload, model_id=model_id, provider=provider)


def get_context_compression_config(agent: Agent) -> dict[str, Any]:
    """Get agent context compression config merged with defaults."""
    config = dict(DEFAULT_CONTEXT_COMPRESSION_CONFIG)
    raw_config = agent.context_compression_config or {}
    if isinstance(raw_config, dict):
        config.update(raw_config)
    return config


def _build_token_budget(
    *,
    context_limit: int | None,
    model_max_output_tokens: int | None,
    output_token_reserve: int = DEFAULT_OUTPUT_TOKEN_RESERVE,
    safety_margin_tokens: int = DEFAULT_SAFETY_MARGIN_TOKENS,
) -> TokenBudget:
    resolved_context_limit = context_limit or DEFAULT_CONTEXT_LIMIT
    resolved_output_reserve = min(
        output_token_reserve,
        model_max_output_tokens or output_token_reserve,
        max(resolved_context_limit // 3, 1),
    )
    input_budget = max(
        resolved_context_limit - resolved_output_reserve - safety_margin_tokens,
        1,
    )
    return TokenBudget(
        context_limit=resolved_context_limit,
        output_reserve=resolved_output_reserve,
        safety_margin=safety_margin_tokens,
        input_budget=input_budget,
    )


def _build_compression_thresholds(
    *,
    token_budget: TokenBudget,
    warning_ratio: float,
    trigger_ratio: float,
    blocking_ratio: float,
) -> CompressionThresholds:
    input_budget = token_budget.input_budget
    return CompressionThresholds(
        warning_input_budget=max(
            1, min(int(input_budget * warning_ratio), input_budget)
        ),
        trigger_input_budget=max(
            1, min(int(input_budget * trigger_ratio), input_budget)
        ),
        blocking_input_budget=max(
            1, min(int(input_budget * blocking_ratio), input_budget)
        ),
    )


def _assess_context_pressure(
    *,
    before_tokens: int,
    token_budget: TokenBudget,
    thresholds: CompressionThresholds,
) -> Literal["normal", "warning", "auto_compact", "blocking", "over_budget"]:
    if before_tokens > token_budget.input_budget:
        return "over_budget"
    if before_tokens >= thresholds.blocking_input_budget:
        return "blocking"
    if before_tokens >= thresholds.trigger_input_budget:
        return "auto_compact"
    if before_tokens >= thresholds.warning_input_budget:
        return "warning"
    return "normal"


def _compact_message_reasoning(
    messages: Sequence[Message],
    keep_recent_reasoning_messages: int = DEFAULT_RECENT_REASONING_MESSAGES,
    protected_indexes: set[int] | None = None,
) -> tuple[list[Message], bool, set[int]]:
    kept_reasoning = 0
    compacted: list[Message] = []
    reasoning_trimmed = False
    protected_indexes = protected_indexes or set()
    compacted_protected_indexes: set[int] = set()

    for original_index in range(len(messages) - 1, -1, -1):
        message_copy = messages[original_index].model_copy(deep=True)
        is_protected = original_index in protected_indexes
        if (
            message_copy.role == MessageRole.ASSISTANT
            and message_copy.reasoning_content
        ):
            if is_protected or kept_reasoning < keep_recent_reasoning_messages:
                if not is_protected:
                    kept_reasoning += 1
            else:
                message_copy.reasoning_content = None
                reasoning_trimmed = True
        compacted.append(message_copy)
        if is_protected:
            compacted_protected_indexes.add(len(messages) - 1 - original_index)

    compacted.reverse()
    remapped_protected_indexes = {
        len(messages) - 1 - reverse_index
        for reverse_index in compacted_protected_indexes
    }
    return compacted, reasoning_trimmed, remapped_protected_indexes


def _has_rich_media_context(message: Message) -> bool:
    if isinstance(message.content, list):
        return any(part.type == ContentType.IMAGE for part in message.content)
    text = _stringify_content(message.content)
    return FILE_CONTENT_PLACEHOLDER in text or "[image]" in text


def _estimate_single_message_tokens(
    message: Message,
    *,
    model_id: str,
    provider: str | None,
) -> int:
    return _estimate_message_tokens([message], model_id=model_id, provider=provider)


def _analyze_turn_block(
    block: Sequence[Message],
    *,
    model_id: str,
    provider: str | None,
) -> dict[str, Any]:
    contains_tool = _is_tool_turn(block)
    contains_media = any(_has_rich_media_context(message) for message in block)
    tool_token_total = 0
    tool_messages = 0
    for message in block:
        if message.role == MessageRole.TOOL:
            tool_messages += 1
            tool_token_total += _estimate_single_message_tokens(
                message,
                model_id=model_id,
                provider=provider,
            )
    return {
        "contains_tool": contains_tool,
        "contains_media": contains_media,
        "tool_messages": tool_messages,
        "tool_token_total": tool_token_total,
    }


def _should_keep_tool_result_raw(
    *,
    tool_result_index_from_end: int,
    keep_recent_tool_results: int,
) -> bool:
    return tool_result_index_from_end < keep_recent_tool_results


def _apply_selective_tool_result_compaction(
    messages: Sequence[Message],
    *,
    model_id: str,
    provider: str | None,
    keep_recent_tool_results: int,
    tool_result_compact_min_tokens: int,
    recent_raw_turns: int,
    recent_tool_turns: int,
    protected_indexes: set[int] | None = None,
) -> tuple[list[Message], bool, set[int]]:
    prefix, prefix_indexes, blocks, block_indexes = _split_turn_blocks(messages)
    analyses = [
        _analyze_turn_block(block, model_id=model_id, provider=provider)
        for block in blocks
    ]
    protected_indexes = protected_indexes or set()

    keep_block_indexes: set[int] = set(
        range(max(len(blocks) - recent_raw_turns, 0), len(blocks))
    )
    for index, analysis in enumerate(analyses):
        if analysis["contains_media"]:
            keep_block_indexes.add(index)
        if any(
            message_index in protected_indexes for message_index in block_indexes[index]
        ):
            keep_block_indexes.add(index)

    tool_turns_kept = 0
    for index in range(len(blocks) - 1, -1, -1):
        if analyses[index]["contains_tool"] and index not in keep_block_indexes:
            keep_block_indexes.add(index)
            tool_turns_kept += 1
            if tool_turns_kept >= recent_tool_turns:
                break

    tool_positions_from_end: dict[tuple[int, int], int] = {}
    tool_result_index_from_end = 0
    for block_index in range(len(blocks) - 1, -1, -1):
        block = blocks[block_index]
        for message_index in range(len(block) - 1, -1, -1):
            message = block[message_index]
            if message.role == MessageRole.TOOL and isinstance(message.content, str):
                tool_positions_from_end[(block_index, message_index)] = (
                    tool_result_index_from_end
                )
                tool_result_index_from_end += 1

    compacted: list[Message] = []
    compacted_protected_indexes: set[int] = set()
    _extend_with_original_indexes(
        compacted,
        compacted_protected_indexes,
        prefix,
        prefix_indexes,
        protected_indexes,
    )
    tool_results_trimmed = False
    for block_index, block in enumerate(blocks):
        keep_block_raw = block_index in keep_block_indexes
        for message_index, message in enumerate(block):
            original_index = block_indexes[block_index][message_index]
            message_copy = message.model_copy(deep=True)
            if (
                original_index not in protected_indexes
                and not keep_block_raw
                and message_copy.role == MessageRole.TOOL
                and isinstance(message_copy.content, str)
            ):
                tool_result_index = tool_positions_from_end.get(
                    (block_index, message_index), 999999
                )
                should_keep_raw = _should_keep_tool_result_raw(
                    tool_result_index_from_end=tool_result_index,
                    keep_recent_tool_results=keep_recent_tool_results,
                )
                estimated_tokens = _estimate_single_message_tokens(
                    message_copy,
                    model_id=model_id,
                    provider=provider,
                )
                if (
                    not should_keep_raw
                    and estimated_tokens >= tool_result_compact_min_tokens
                ):
                    summarized = summarize_tool_result_for_llm(
                        None, message_copy.content
                    )
                    if summarized != message_copy.content:
                        message_copy.content = summarized
                        tool_results_trimmed = True
                    elif len(message_copy.content) > 1200:
                        message_copy.content = _truncate_text(
                            message_copy.content, 1200
                        )
                        tool_results_trimmed = True
            _append_message(
                compacted,
                compacted_protected_indexes,
                message_copy,
                protect=original_index in protected_indexes,
            )

    return compacted, tool_results_trimmed, compacted_protected_indexes


async def _apply_session_memory_compaction(
    messages: Sequence[Message],
    *,
    conversation: Conversation,
    model_id: str,
    provider: str | None,
    recent_raw_turns: int = DEFAULT_RECENT_RAW_TURNS,
    recent_tool_turns: int = DEFAULT_RECENT_TOOL_TURNS,
    protected_indexes: set[int] | None = None,
    before_created_at=None,
) -> tuple[list[Message], bool, set[int]]:
    """
    Apply conversation-scoped session memory compaction.

    Replaces older compactable turn blocks with a single assistant summary
    derived from the stored session-memory snapshot, while preserving:
    - System prompt
    - Current user turn
    - Recent raw turns
    - Recent tool turns
    - Media-rich blocks
    """
    from app.services.session_memory import get_ready_session_memory

    protected_indexes = protected_indexes or set()
    try:
        snapshot = await get_ready_session_memory(conversation.id)
        if not snapshot or not snapshot.summary_text or not snapshot.source_message_id:
            cloned_messages, cloned_protected_indexes = _clone_messages(
                messages, protected_indexes
            )
            return cloned_messages, False, cloned_protected_indexes
        if not await is_message_on_active_branch(
            conversation.id,
            snapshot.source_message_id,
            before_created_at=before_created_at,
        ):
            cloned_messages, cloned_protected_indexes = _clone_messages(
                messages, protected_indexes
            )
            return cloned_messages, False, cloned_protected_indexes
    except Exception as e:
        logger.warning(
            "Failed to retrieve session memory for conversation %s: %s",
            conversation.id,
            str(e),
        )
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, False, cloned_protected_indexes

    prefix, prefix_indexes, blocks, block_indexes = _split_turn_blocks(messages)
    if len(blocks) <= recent_raw_turns:
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, False, cloned_protected_indexes

    analyses = [
        _analyze_turn_block(block, model_id=model_id, provider=provider)
        for block in blocks
    ]

    keep_indexes: set[int] = set(
        range(max(len(blocks) - recent_raw_turns, 0), len(blocks))
    )

    for index in range(len(blocks) - 1, -1, -1):
        if analyses[index]["contains_media"]:
            keep_indexes.add(index)
        if any(
            message_index in protected_indexes for message_index in block_indexes[index]
        ):
            keep_indexes.add(index)

    tool_kept = 0
    for index in range(len(blocks) - 1, -1, -1):
        if analyses[index]["contains_tool"] and index not in keep_indexes:
            keep_indexes.add(index)
            tool_kept += 1
            if tool_kept >= recent_tool_turns:
                break

    summary_blocks = [
        blocks[index] for index in range(len(blocks)) if index not in keep_indexes
    ]
    if not summary_blocks:
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, False, cloned_protected_indexes

    compacted: list[Message] = []
    compacted_protected_indexes: set[int] = set()
    _extend_with_original_indexes(
        compacted,
        compacted_protected_indexes,
        prefix,
        prefix_indexes,
        protected_indexes,
    )
    _append_message(
        compacted,
        compacted_protected_indexes,
        Message(role=MessageRole.ASSISTANT, content=snapshot.summary_text),
    )

    for index, block in enumerate(blocks):
        if index in keep_indexes:
            _extend_with_original_indexes(
                compacted,
                compacted_protected_indexes,
                block,
                block_indexes[index],
                protected_indexes,
            )

    return compacted, True, compacted_protected_indexes


async def _build_messages_with_file_content(
    *,
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    file_content: str | None,
    user_locale: str | None,
    history_override: Sequence[Any] | None,
    current_images: Sequence[Any] | None,
    model_supports_vision: bool,
    current_user_message_id: UUID | None,
    include_current_user_message: bool,
    exclude_message_ids: Sequence[UUID] | None,
    history_before_message_created_at: datetime | None,
    tool_timeouts: dict[str, Any] | None = None,
    user: Any = None,
    protected_round_id: UUID | str | None = None,
) -> tuple[list[Message], set[int]]:
    messages: list[Message] = []
    protected_indexes: set[int] = set()
    valid_tool_call_ids: set[str] = set()
    _append_message(
        messages,
        protected_indexes,
        Message(
            role=MessageRole.SYSTEM,
            content=_build_system_prompt(
                agent=agent,
                conversation=conversation,
                user_message=user_message,
                user_locale=user_locale,
            ),
        ),
    )

    current_content = _append_file_content_to_user_content(
        _build_current_user_content(
            user_message=user_message,
            current_images=current_images,
            model_supports_vision=model_supports_vision,
        ),
        file_content,
    )

    if history_override is not None:
        has_current_round_user_in_override = any(
            _normalize_override_role(_get_override_value(hist_msg, "role")) == "user"
            and _matches_protected_round(
                _get_override_value(hist_msg, "round_id"),
                protected_round_id,
            )
            for hist_msg in history_override
        )
        current_user_inserted = False
        for hist_msg in history_override:
            role = _normalize_override_role(_get_override_value(hist_msg, "role"))
            content = _get_override_value(hist_msg, "content")
            protect = _matches_protected_round(
                _get_override_value(hist_msg, "round_id"),
                protected_round_id,
            )
            if (
                protect
                and role != "user"
                and not current_user_inserted
                and not has_current_round_user_in_override
            ):
                _append_message(
                    messages,
                    protected_indexes,
                    Message(role=MessageRole.USER, content=current_content),
                    protect=True,
                )
                current_user_inserted = True
            if role == "user":
                override_file_content = await _build_file_content_for_user_message(
                    agent=agent,
                    file_urls=_get_override_value(hist_msg, "file_urls"),
                    legacy_files=_get_override_value(hist_msg, "files"),
                    user_locale=user_locale,
                    tool_timeouts=tool_timeouts,
                    user=user,
                )
                _append_message(
                    messages,
                    protected_indexes,
                    Message(
                        role=MessageRole.USER,
                        content=_append_file_content_to_user_content(
                            content or "",
                            override_file_content,
                        ),
                    ),
                    protect=protect,
                )
            elif role == "assistant":
                tool_calls, new_tool_call_ids = _build_assistant_tool_calls(
                    _get_override_value(hist_msg, "tool_calls")
                )
                valid_tool_call_ids.update(new_tool_call_ids)
                _append_message(
                    messages,
                    protected_indexes,
                    Message(
                        role=MessageRole.ASSISTANT,
                        content=content,
                        reasoning_content=_get_override_value(
                            hist_msg,
                            "reasoning_content",
                        ),
                        tool_calls=tool_calls,
                    ),
                    protect=protect,
                )
            elif role == "tool":
                tool_call_id = _get_override_value(hist_msg, "tool_call_id")
                if tool_call_id and tool_call_id in valid_tool_call_ids:
                    _append_message(
                        messages,
                        protected_indexes,
                        Message(
                            role=MessageRole.TOOL,
                            content=summarize_tool_result_for_llm(
                                _get_override_value(hist_msg, "tool_name"),
                                content or "",
                            ),
                            tool_call_id=tool_call_id,
                        ),
                        protect=protect,
                    )
        if not current_user_inserted and not has_current_round_user_in_override:
            _append_message(
                messages,
                protected_indexes,
                Message(role=MessageRole.USER, content=current_content),
                protect=protected_round_id is not None,
            )
        return messages, protected_indexes

    history = await get_visible_conversation_messages(
        conversation.id,
        before_created_at=history_before_message_created_at,
        exclude_message_ids=exclude_message_ids,
    )
    historical_file_content_tasks = {
        msg.id: asyncio.create_task(
            _build_file_content_for_user_message(
                agent=agent,
                file_urls=msg.file_urls,
                user_locale=user_locale,
                tool_timeouts=tool_timeouts,
                user=user,
                source_message=msg,
            )
        )
        for msg in history
        if msg.role == ConversationMessageRole.USER
        and not (current_user_message_id and msg.id == current_user_message_id)
    }

    for msg in history:
        protect = _matches_protected_round(msg.round_id, protected_round_id)
        if msg.role == ConversationMessageRole.USER:
            if current_user_message_id and msg.id == current_user_message_id:
                if include_current_user_message:
                    _append_message(
                        messages,
                        protected_indexes,
                        Message(role=MessageRole.USER, content=current_content),
                        protect=protect or protected_round_id is not None,
                    )
                continue
            historical_file_content = await historical_file_content_tasks[msg.id]
            _append_message(
                messages,
                protected_indexes,
                Message(
                    role=MessageRole.USER,
                    content=_append_file_content_to_user_content(
                        msg.content,
                        historical_file_content,
                    ),
                ),
                protect=protect,
            )
            continue

        if msg.role == ConversationMessageRole.ASSISTANT:
            tool_calls, new_tool_call_ids = _build_assistant_tool_calls(msg.tool_calls)
            valid_tool_call_ids.update(new_tool_call_ids)
            _append_message(
                messages,
                protected_indexes,
                Message(
                    role=MessageRole.ASSISTANT,
                    content=msg.content,
                    reasoning_content=msg.reasoning_content,
                    tool_calls=tool_calls,
                ),
                protect=protect,
            )
            continue

        if (
            msg.role == ConversationMessageRole.TOOL
            and msg.tool_call_id
            and msg.tool_call_id in valid_tool_call_ids
        ):
            _append_message(
                messages,
                protected_indexes,
                Message(
                    role=MessageRole.TOOL,
                    content=summarize_tool_result_for_llm(msg.tool_name, msg.content),
                    tool_call_id=msg.tool_call_id,
                ),
                protect=protect,
            )

    if not include_current_user_message:
        _append_message(
            messages,
            protected_indexes,
            Message(role=MessageRole.USER, content=current_content),
            protect=protected_round_id is not None,
        )

    return messages, protected_indexes


def _is_tool_turn(messages: Sequence[Message]) -> bool:
    return any(
        message.role in {MessageRole.ASSISTANT, MessageRole.TOOL}
        and (message.tool_calls or message.tool_call_id)
        for message in messages
    )


def _split_turn_blocks(
    messages: Sequence[Message],
) -> tuple[list[Message], list[int], list[list[Message]], list[list[int]]]:
    if not messages:
        return [], [], [], []

    start_index = 0
    prefix: list[Message] = []
    prefix_indexes: list[int] = []
    if messages[0].role == MessageRole.SYSTEM:
        prefix = [messages[0].model_copy(deep=True)]
        prefix_indexes = [0]
        start_index = 1

    blocks: list[list[Message]] = []
    block_indexes: list[list[int]] = []
    current_block: list[Message] = []
    current_block_indexes: list[int] = []

    for message_index, message in enumerate(messages[start_index:], start=start_index):
        message_copy = message.model_copy(deep=True)
        if message_copy.role == MessageRole.USER:
            if current_block:
                blocks.append(current_block)
                block_indexes.append(current_block_indexes)
            current_block = [message_copy]
            current_block_indexes = [message_index]
        else:
            if not current_block:
                current_block = [message_copy]
                current_block_indexes = [message_index]
            else:
                current_block.append(message_copy)
                current_block_indexes.append(message_index)

    if current_block:
        blocks.append(current_block)
        block_indexes.append(current_block_indexes)

    return prefix, prefix_indexes, blocks, block_indexes


def _summarize_block(
    messages: Sequence[Message],
    *,
    block_summary_chars: int = DEFAULT_BLOCK_SUMMARY_CHARS,
) -> str:
    items: list[str] = []
    user_parts: list[str] = []
    assistant_parts: list[str] = []
    tool_names: list[str] = []
    tool_results: list[str] = []

    for message in messages:
        text = _truncate_text(_stringify_content(message.content), block_summary_chars)
        if message.role == MessageRole.USER and text:
            user_parts.append(text)
        elif message.role == MessageRole.ASSISTANT:
            if text:
                assistant_parts.append(text)
            if message.tool_calls:
                tool_names.extend(
                    tool_call.function.name
                    for tool_call in message.tool_calls
                    if tool_call.function and tool_call.function.name
                )
        elif message.role == MessageRole.TOOL:
            if message.tool_call_id:
                tool_names.append(message.tool_call_id)
            if text:
                tool_results.append(text)

    if user_parts:
        items.append(f"User asked: {_truncate_text(' | '.join(user_parts), 500)}")
    if assistant_parts:
        items.append(
            f"Assistant responded: {_truncate_text(' | '.join(assistant_parts), 500)}"
        )
    if tool_names:
        deduped_tool_names = list(dict.fromkeys(tool_names))
        items.append(
            f"Tools involved: {_truncate_text(', '.join(deduped_tool_names), 300)}"
        )
    if tool_results:
        items.append(f"Tool outcomes: {_truncate_text(' | '.join(tool_results), 500)}")

    if not items:
        return "Conversation turn preserved in compact summary."
    return " ; ".join(items)


MACRO_SUMMARY_PREFIX = "Compressed earlier conversation summary:"


def _build_macro_summary_message(
    blocks: Sequence[Sequence[Message]],
    *,
    summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
    block_summary_chars: int = DEFAULT_BLOCK_SUMMARY_CHARS,
) -> Message | None:
    if not blocks:
        return None

    lines = [MACRO_SUMMARY_PREFIX]
    for index, block in enumerate(blocks, start=1):
        lines.append(
            f"- Turn {index}: {_summarize_block(block, block_summary_chars=block_summary_chars)}"
        )

    summary = _limit_summary_text("\n".join(lines), summary_max_chars)
    return Message(role=MessageRole.ASSISTANT, content=summary)


def _apply_macro_compaction(
    messages: Sequence[Message],
    *,
    model_id: str,
    provider: str | None,
    recent_raw_turns: int = DEFAULT_RECENT_RAW_TURNS,
    recent_tool_turns: int = DEFAULT_RECENT_TOOL_TURNS,
    summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
    block_summary_chars: int = DEFAULT_BLOCK_SUMMARY_CHARS,
    protected_indexes: set[int] | None = None,
) -> tuple[list[Message], int, int, int, int, set[int]]:
    prefix, prefix_indexes, blocks, block_indexes = _split_turn_blocks(messages)
    protected_indexes = protected_indexes or set()
    if len(blocks) <= recent_raw_turns:
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, 0, len(blocks), 0, 0, cloned_protected_indexes

    analyses = [
        _analyze_turn_block(block, model_id=model_id, provider=provider)
        for block in blocks
    ]

    keep_indexes: set[int] = set(
        range(max(len(blocks) - recent_raw_turns, 0), len(blocks))
    )

    for index in range(len(blocks) - 1, -1, -1):
        if analyses[index]["contains_media"]:
            keep_indexes.add(index)
        if any(
            message_index in protected_indexes for message_index in block_indexes[index]
        ):
            keep_indexes.add(index)

    tool_kept = 0
    for index in range(len(blocks) - 1, -1, -1):
        if analyses[index]["contains_tool"] and index not in keep_indexes:
            keep_indexes.add(index)
            tool_kept += 1
            if tool_kept >= recent_tool_turns:
                break

    summary_blocks = [
        blocks[index] for index in range(len(blocks)) if index not in keep_indexes
    ]
    if not summary_blocks:
        retained_tool_turns = sum(
            1 for index in keep_indexes if analyses[index]["contains_tool"]
        )
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return (
            cloned_messages,
            0,
            len(keep_indexes),
            retained_tool_turns,
            0,
            cloned_protected_indexes,
        )

    compacted: list[Message] = []
    compacted_protected_indexes: set[int] = set()
    _extend_with_original_indexes(
        compacted,
        compacted_protected_indexes,
        prefix,
        prefix_indexes,
        protected_indexes,
    )
    summary_message = _build_macro_summary_message(
        summary_blocks,
        summary_max_chars=summary_max_chars,
        block_summary_chars=block_summary_chars,
    )
    if summary_message is not None:
        _append_message(compacted, compacted_protected_indexes, summary_message)

    for index, block in enumerate(blocks):
        if index in keep_indexes:
            _extend_with_original_indexes(
                compacted,
                compacted_protected_indexes,
                block,
                block_indexes[index],
                protected_indexes,
            )

    summary_turns = len(summary_blocks)
    retained_recent_turns = sum(
        1 for index in keep_indexes if index >= len(blocks) - recent_raw_turns
    )
    retained_tool_turns = sum(
        1 for index in keep_indexes if analyses[index]["contains_tool"]
    )
    compacted_blocks = len(summary_blocks)
    return (
        compacted,
        summary_turns,
        retained_recent_turns,
        retained_tool_turns,
        compacted_blocks,
        compacted_protected_indexes,
    )


async def _apply_micro_compaction(
    *,
    messages: Sequence[Message],
    conversation: Conversation,
    model_id: str,
    provider: str | None,
    token_budget: TokenBudget,
    keep_recent_reasoning_messages: int = DEFAULT_RECENT_REASONING_MESSAGES,
    keep_recent_tool_results: int = DEFAULT_KEEP_RECENT_TOOL_RESULTS,
    tool_result_compact_min_tokens: int = DEFAULT_TOOL_RESULT_COMPACT_MIN_TOKENS,
    recent_raw_turns: int = DEFAULT_RECENT_RAW_TURNS,
    recent_tool_turns: int = DEFAULT_RECENT_TOOL_TURNS,
    pressure_level: Literal[
        "normal", "warning", "auto_compact", "blocking", "over_budget"
    ] = "normal",
    trigger_ratio: float = DEFAULT_AUTO_COMPACT_TRIGGER_RATIO,
    warning_ratio: float = DEFAULT_WARNING_RATIO,
    blocking_ratio: float = DEFAULT_BLOCKING_RATIO,
    policy_used: str = DEFAULT_COMPACTION_POLICY,
    trigger_budget: int | None = None,
    protected_indexes: set[int] | None = None,
    before_created_at=None,
) -> tuple[list[Message], CompressionMeta, set[int]]:
    protected_indexes = protected_indexes or set()
    before_tokens = _estimate_message_tokens(
        messages, model_id=model_id, provider=provider
    )
    if before_tokens < (trigger_budget or token_budget.input_budget):
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return (
            cloned_messages,
            CompressionMeta(
                stage="none",
                before_tokens=before_tokens,
                after_tokens=before_tokens,
                input_budget=token_budget.input_budget,
                pressure_level=pressure_level,
                trigger_ratio=trigger_ratio,
                warning_ratio=warning_ratio,
                blocking_ratio=blocking_ratio,
                trigger_budget=trigger_budget or token_budget.input_budget,
                hard_budget=token_budget.input_budget,
                utilization_before=(before_tokens / token_budget.input_budget)
                if token_budget.input_budget
                else 0.0,
                utilization_after=(before_tokens / token_budget.input_budget)
                if token_budget.input_budget
                else 0.0,
                policy_used=policy_used,
                actions=[],
            ),
            cloned_protected_indexes,
        )

    reasoning_compacted, reasoning_trimmed, reasoning_protected_indexes = (
        _compact_message_reasoning(
            messages,
            keep_recent_reasoning_messages=keep_recent_reasoning_messages,
            protected_indexes=protected_indexes,
        )
    )
    tool_compacted, tool_results_trimmed, tool_protected_indexes = (
        _apply_selective_tool_result_compaction(
            reasoning_compacted,
            model_id=model_id,
            provider=provider,
            keep_recent_tool_results=keep_recent_tool_results,
            tool_result_compact_min_tokens=tool_result_compact_min_tokens,
            recent_raw_turns=recent_raw_turns,
            recent_tool_turns=recent_tool_turns,
            protected_indexes=reasoning_protected_indexes,
        )
    )
    (
        session_memory_messages,
        session_memory_compacted,
        session_memory_protected_indexes,
    ) = await _apply_session_memory_compaction(
        tool_compacted,
        conversation=conversation,
        model_id=model_id,
        provider=provider,
        recent_raw_turns=recent_raw_turns,
        recent_tool_turns=recent_tool_turns,
        protected_indexes=tool_protected_indexes,
        before_created_at=before_created_at,
    )
    after_tokens = _estimate_message_tokens(
        session_memory_messages,
        model_id=model_id,
        provider=provider,
    )

    actions: list[str] = []
    if reasoning_trimmed:
        actions.append("trim_reasoning")
    if tool_results_trimmed:
        actions.append("compact_old_tool_results")
    if session_memory_compacted:
        actions.append("session_memory_compact")

    stage: Literal["none", "micro"] = "micro" if actions else "none"
    utilization_before = (
        (before_tokens / token_budget.input_budget)
        if token_budget.input_budget
        else 0.0
    )
    utilization_after = (
        (after_tokens / token_budget.input_budget) if token_budget.input_budget else 0.0
    )
    return (
        session_memory_messages,
        CompressionMeta(
            stage=stage,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            input_budget=token_budget.input_budget,
            reasoning_trimmed=reasoning_trimmed,
            tool_results_trimmed=tool_results_trimmed,
            pressure_level=pressure_level,
            trigger_ratio=trigger_ratio,
            warning_ratio=warning_ratio,
            blocking_ratio=blocking_ratio,
            trigger_budget=trigger_budget or token_budget.input_budget,
            hard_budget=token_budget.input_budget,
            utilization_before=utilization_before,
            utilization_after=utilization_after,
            policy_used=policy_used,
            actions=actions,
            session_memory_compacted=session_memory_compacted,
        ),
        session_memory_protected_indexes,
    )


def extract_macro_summary_text(messages: Sequence[Message]) -> str | None:
    for message in messages:
        if message.role != MessageRole.ASSISTANT:
            continue
        content = _stringify_content(message.content).strip()
        if content.startswith(MACRO_SUMMARY_PREFIX):
            return content
    return None


async def persist_compacted_context_snapshot(
    *,
    conversation: Conversation,
    source_message_id: UUID,
    summary_text: str,
    model_id: str | None = None,
) -> None:
    from app.core.timezone import now_utc
    from app.llm.token_counter import count_tokens
    from app.models.agent import (
        ConversationSessionMemory,
        ConversationSessionMemoryStatus,
    )
    from app.services.session_memory import MACRO_COMPACTION_ORIGIN

    if not summary_text.strip():
        return

    snapshot = await ConversationSessionMemory.filter(
        conversation_id=conversation.id,
    ).first()
    if snapshot is None:
        snapshot = await ConversationSessionMemory.create(
            conversation_id=conversation.id,
        )

    snapshot.source_message_id = source_message_id
    snapshot.status = ConversationSessionMemoryStatus.READY
    snapshot.summary_text = summary_text
    snapshot.snapshot_payload = {
        "overview": summary_text,
        "origin": MACRO_COMPACTION_ORIGIN,
    }
    snapshot.token_estimate = count_tokens(summary_text, model_id=model_id or "gpt-4")
    snapshot.extractor_model = model_id
    snapshot.failure_count = 0
    snapshot.last_error = None  # type: ignore[assignment]
    snapshot.last_extracted_at = now_utc()
    await snapshot.save()


def _apply_budget_compaction(
    *,
    messages: Sequence[Message],
    model_id: str,
    provider: str | None,
    token_budget: TokenBudget,
    compression: CompressionMeta,
    file_content_trimmed: bool,
    aggressive: bool = False,
    pressure_level: Literal[
        "normal", "warning", "auto_compact", "blocking", "over_budget"
    ] = "normal",
    trigger_ratio: float = DEFAULT_AUTO_COMPACT_TRIGGER_RATIO,
    warning_ratio: float = DEFAULT_WARNING_RATIO,
    blocking_ratio: float = DEFAULT_BLOCKING_RATIO,
    policy_used: str = DEFAULT_COMPACTION_POLICY,
    trigger_budget: int | None = None,
    recent_raw_turns: int = DEFAULT_RECENT_RAW_TURNS,
    recent_tool_turns: int = DEFAULT_RECENT_TOOL_TURNS,
    summary_max_chars: int = DEFAULT_SUMMARY_MAX_CHARS,
    block_summary_chars: int = DEFAULT_BLOCK_SUMMARY_CHARS,
    protected_indexes: set[int] | None = None,
) -> tuple[list[Message], CompressionMeta, set[int]]:
    protected_indexes = protected_indexes or set()
    if (
        compression.after_tokens <= token_budget.input_budget
        and pressure_level != "blocking"
    ):
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, compression, cloned_protected_indexes

    (
        macro_messages,
        summary_turns,
        retained_recent_turns,
        retained_tool_turns,
        compacted_blocks,
        macro_protected_indexes,
    ) = _apply_macro_compaction(
        messages,
        model_id=model_id,
        provider=provider,
        recent_raw_turns=(
            recent_raw_turns
            if not aggressive
            else min(recent_raw_turns, AGGRESSIVE_RECENT_RAW_TURNS)
        ),
        recent_tool_turns=(
            recent_tool_turns
            if not aggressive
            else min(recent_tool_turns, AGGRESSIVE_RECENT_TOOL_TURNS)
        ),
        summary_max_chars=(
            summary_max_chars
            if not aggressive
            else min(summary_max_chars, AGGRESSIVE_SUMMARY_MAX_CHARS)
        ),
        block_summary_chars=(
            block_summary_chars if not aggressive else AGGRESSIVE_BLOCK_SUMMARY_CHARS
        ),
        protected_indexes=protected_indexes,
    )
    macro_after_tokens = _estimate_message_tokens(
        macro_messages,
        model_id=model_id,
        provider=provider,
    )
    if summary_turns <= 0:
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, compression, cloned_protected_indexes

    actions = list(compression.actions or [])
    if "macro_summary" not in actions:
        actions.append("macro_summary")
    utilization_after = (
        (macro_after_tokens / token_budget.input_budget)
        if token_budget.input_budget
        else 0.0
    )
    return (
        macro_messages,
        CompressionMeta(
            stage="macro",
            before_tokens=compression.before_tokens,
            after_tokens=macro_after_tokens,
            input_budget=token_budget.input_budget,
            reasoning_trimmed=compression.reasoning_trimmed,
            tool_results_trimmed=compression.tool_results_trimmed,
            file_content_trimmed=file_content_trimmed,
            summary_turns=summary_turns,
            pressure_level=pressure_level,
            trigger_ratio=trigger_ratio,
            warning_ratio=warning_ratio,
            blocking_ratio=blocking_ratio,
            trigger_budget=trigger_budget or token_budget.input_budget,
            hard_budget=token_budget.input_budget,
            utilization_before=compression.utilization_before,
            utilization_after=utilization_after,
            policy_used=policy_used,
            actions=actions,
            retained_recent_turns=retained_recent_turns,
            retained_tool_turns=retained_tool_turns,
            compacted_blocks=compacted_blocks,
            session_memory_compacted=compression.session_memory_compacted,
        ),
        macro_protected_indexes,
    )


async def build_model_messages(
    *,
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    file_content: str | None = None,
    user_locale: str | None = None,
    history_override: Sequence[Any] | None = None,
    current_images: Sequence[Any] | None = None,
    model_supports_vision: bool = False,
    current_user_message_id: UUID | None = None,
    include_current_user_message: bool = False,
    exclude_message_ids: Sequence[UUID] | None = None,
    history_before_message_created_at: datetime | None = None,
    tool_timeouts: dict[str, Any] | None = None,
    user: Any = None,
    protected_round_id: UUID | str | None = None,
) -> list[Message]:
    """Build model-ready messages for agent chat flows."""
    messages, _ = await _build_messages_with_file_content(
        agent=agent,
        conversation=conversation,
        user_message=user_message,
        file_content=file_content,
        user_locale=user_locale,
        history_override=history_override,
        current_images=current_images,
        model_supports_vision=model_supports_vision,
        current_user_message_id=current_user_message_id,
        include_current_user_message=include_current_user_message,
        exclude_message_ids=exclude_message_ids,
        history_before_message_created_at=history_before_message_created_at,
        tool_timeouts=tool_timeouts,
        user=user,
        protected_round_id=protected_round_id,
    )
    return messages


async def prepare_model_context(
    *,
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    model_id: str,
    model_context_limit: int | None,
    model_max_output_tokens: int | None,
    provider: str | None = None,
    file_content: str | None = None,
    user_locale: str | None = None,
    history_override: Sequence[Any] | None = None,
    current_images: Sequence[Any] | None = None,
    model_supports_vision: bool = False,
    current_user_message_id: UUID | None = None,
    include_current_user_message: bool = False,
    exclude_message_ids: Sequence[UUID] | None = None,
    history_before_message_created_at: datetime | None = None,
    tool_timeouts: dict[str, Any] | None = None,
    user: Any = None,
    aggressive: bool = False,
    protected_round_id: UUID | str | None = None,
) -> PreparedModelContext:
    compression_config = get_context_compression_config(agent)
    token_budget = _build_token_budget(
        context_limit=model_context_limit,
        model_max_output_tokens=model_max_output_tokens,
        output_token_reserve=int(
            compression_config.get("output_token_reserve", DEFAULT_OUTPUT_TOKEN_RESERVE)
        ),
        safety_margin_tokens=int(
            compression_config.get("safety_margin_tokens", DEFAULT_SAFETY_MARGIN_TOKENS)
        ),
    )

    warning_ratio = float(
        compression_config.get("warning_ratio", DEFAULT_WARNING_RATIO)
    )
    trigger_ratio = float(
        compression_config.get(
            "auto_compact_trigger_ratio", DEFAULT_AUTO_COMPACT_TRIGGER_RATIO
        )
    )
    blocking_ratio = float(
        compression_config.get("blocking_ratio", DEFAULT_BLOCKING_RATIO)
    )
    policy_used = str(
        compression_config.get("compaction_policy", DEFAULT_COMPACTION_POLICY)
    )
    macro_on_trigger = bool(compression_config.get("macro_on_trigger", False))
    keep_recent_tool_results = int(
        compression_config.get(
            "keep_recent_tool_results", DEFAULT_KEEP_RECENT_TOOL_RESULTS
        )
    )
    configured_recent_raw_turns = int(
        compression_config.get(
            "recent_raw_turns",
            DEFAULT_RECENT_RAW_TURNS if not aggressive else AGGRESSIVE_RECENT_RAW_TURNS,
        )
    )
    configured_recent_tool_turns = int(
        compression_config.get(
            "recent_tool_turns",
            DEFAULT_RECENT_TOOL_TURNS
            if not aggressive
            else AGGRESSIVE_RECENT_TOOL_TURNS,
        )
    )
    tool_result_compact_min_tokens = int(
        compression_config.get(
            "tool_result_compact_min_tokens",
            DEFAULT_TOOL_RESULT_COMPACT_MIN_TOKENS,
        )
    )
    thresholds = _build_compression_thresholds(
        token_budget=token_budget,
        warning_ratio=warning_ratio,
        trigger_ratio=trigger_ratio,
        blocking_ratio=blocking_ratio,
    )

    (
        untrimmed_messages,
        untrimmed_protected_indexes,
    ) = await _build_messages_with_file_content(
        agent=agent,
        conversation=conversation,
        user_message=user_message,
        file_content=file_content,
        user_locale=user_locale,
        history_override=history_override,
        current_images=current_images,
        model_supports_vision=model_supports_vision,
        current_user_message_id=current_user_message_id,
        include_current_user_message=include_current_user_message,
        exclude_message_ids=exclude_message_ids,
        history_before_message_created_at=history_before_message_created_at,
        tool_timeouts=tool_timeouts,
        user=user,
        protected_round_id=protected_round_id,
    )

    compression_enabled = bool(compression_config.get("enabled", True))
    preflight_guard_enabled = bool(
        compression_config.get("preflight_guard_enabled", True)
    )
    session_memory_compaction_kwargs = {
        "conversation": conversation,
        "model_id": model_id,
        "provider": provider,
        "recent_raw_turns": configured_recent_raw_turns,
        "recent_tool_turns": configured_recent_tool_turns,
        "before_created_at": history_before_message_created_at,
    }
    if compression_enabled and preflight_guard_enabled:
        (
            baseline_messages,
            baseline_session_memory_compacted,
            baseline_protected_indexes,
        ) = await _apply_session_memory_compaction(
            untrimmed_messages,
            protected_indexes=untrimmed_protected_indexes,
            **session_memory_compaction_kwargs,
        )
        if baseline_session_memory_compacted:
            untrimmed_messages = baseline_messages
            untrimmed_protected_indexes = baseline_protected_indexes

    untrimmed_tokens = _estimate_message_tokens(
        untrimmed_messages,
        model_id=model_id,
        provider=provider,
    )
    initial_pressure = _assess_context_pressure(
        before_tokens=untrimmed_tokens,
        token_budget=token_budget,
        thresholds=thresholds,
    )
    utilization_before = (
        untrimmed_tokens / token_budget.input_budget
        if token_budget.input_budget
        else 0.0
    )
    if not compression_enabled or not preflight_guard_enabled:
        return PreparedModelContext(
            messages=untrimmed_messages,
            token_budget=token_budget,
            compression=CompressionMeta(
                stage="none",
                before_tokens=untrimmed_tokens,
                after_tokens=untrimmed_tokens,
                input_budget=token_budget.input_budget,
                pressure_level=initial_pressure,
                trigger_ratio=trigger_ratio,
                warning_ratio=warning_ratio,
                blocking_ratio=blocking_ratio,
                trigger_budget=thresholds.trigger_input_budget,
                hard_budget=token_budget.input_budget,
                utilization_before=utilization_before,
                utilization_after=utilization_before,
                policy_used=policy_used,
                actions=[],
            ),
            protected_indexes=untrimmed_protected_indexes,
        )

    needs_file_trim = (
        bool(file_content) and untrimmed_tokens > thresholds.trigger_input_budget
    )
    effective_file_content = file_content
    file_content_trimmed = False
    if needs_file_trim:
        effective_file_content, file_content_trimmed = _trim_file_content(
            file_content,
            aggressive=aggressive,
        )

    if not file_content_trimmed:
        base_messages = untrimmed_messages
        base_protected_indexes = set(untrimmed_protected_indexes)
    else:
        base_messages, base_protected_indexes = await _build_messages_with_file_content(
            agent=agent,
            conversation=conversation,
            user_message=user_message,
            file_content=effective_file_content,
            user_locale=user_locale,
            history_override=history_override,
            current_images=current_images,
            model_supports_vision=model_supports_vision,
            current_user_message_id=current_user_message_id,
            include_current_user_message=include_current_user_message,
            exclude_message_ids=exclude_message_ids,
            history_before_message_created_at=history_before_message_created_at,
            tool_timeouts=tool_timeouts,
            user=user,
            protected_round_id=protected_round_id,
        )
        (
            base_messages,
            _,
            base_protected_indexes,
        ) = await _apply_session_memory_compaction(
            base_messages,
            protected_indexes=base_protected_indexes,
            **session_memory_compaction_kwargs,
        )

    base_tokens = _estimate_message_tokens(
        base_messages,
        model_id=model_id,
        provider=provider,
    )
    pressure_level = _assess_context_pressure(
        before_tokens=base_tokens,
        token_budget=token_budget,
        thresholds=thresholds,
    )

    compacted_messages = base_messages
    compacted_protected_indexes = set(base_protected_indexes)
    compression = CompressionMeta(
        stage="none",
        before_tokens=untrimmed_tokens,
        after_tokens=base_tokens,
        input_budget=token_budget.input_budget,
        file_content_trimmed=file_content_trimmed,
        pressure_level=pressure_level,
        trigger_ratio=trigger_ratio,
        warning_ratio=warning_ratio,
        blocking_ratio=blocking_ratio,
        trigger_budget=thresholds.trigger_input_budget,
        hard_budget=token_budget.input_budget,
        utilization_before=utilization_before,
        utilization_after=(base_tokens / token_budget.input_budget)
        if token_budget.input_budget
        else 0.0,
        policy_used=policy_used,
        actions=["trim_file_content"] if file_content_trimmed else [],
    )

    should_run_micro = pressure_level in {"auto_compact", "blocking", "over_budget"}
    if compression_config.get("micro_compaction_enabled", True) and should_run_micro:
        keep_recent_reasoning_messages = (
            DEFAULT_RECENT_REASONING_MESSAGES
            if not aggressive
            else AGGRESSIVE_RECENT_REASONING_MESSAGES
        )
        if not compression_config.get("drop_historical_reasoning_first", True):
            keep_recent_reasoning_messages = max(keep_recent_reasoning_messages, 9999)
        (
            compacted_messages,
            compression,
            compacted_protected_indexes,
        ) = await _apply_micro_compaction(
            messages=base_messages,
            conversation=conversation,
            model_id=model_id,
            provider=provider,
            token_budget=token_budget,
            keep_recent_reasoning_messages=keep_recent_reasoning_messages,
            keep_recent_tool_results=keep_recent_tool_results,
            tool_result_compact_min_tokens=tool_result_compact_min_tokens,
            recent_raw_turns=configured_recent_raw_turns,
            recent_tool_turns=configured_recent_tool_turns,
            pressure_level=pressure_level,
            trigger_ratio=trigger_ratio,
            warning_ratio=warning_ratio,
            blocking_ratio=blocking_ratio,
            policy_used=policy_used,
            trigger_budget=thresholds.trigger_input_budget,
            protected_indexes=base_protected_indexes,
            before_created_at=history_before_message_created_at,
        )
        compression.file_content_trimmed = file_content_trimmed
        if file_content_trimmed and "trim_file_content" not in (
            compression.actions or []
        ):
            compression.actions = [*(compression.actions or []), "trim_file_content"]

    should_run_macro = False
    if compression_config.get("macro_compaction_enabled", True):
        should_run_macro = pressure_level in {"blocking", "over_budget"}
        if (
            not should_run_macro
            and pressure_level == "auto_compact"
            and macro_on_trigger
        ):
            should_run_macro = True
        if compression.after_tokens > token_budget.input_budget:
            should_run_macro = True

    if should_run_macro:
        summary_max_chars = (
            int(
                compression_config.get("summary_max_tokens", DEFAULT_SUMMARY_MAX_TOKENS)
            )
            * 4
        )
        compacted_messages, compression, compacted_protected_indexes = (
            _apply_budget_compaction(
                messages=compacted_messages,
                model_id=model_id,
                provider=provider,
                token_budget=token_budget,
                compression=compression,
                file_content_trimmed=file_content_trimmed,
                aggressive=aggressive,
                pressure_level=pressure_level,
                trigger_ratio=trigger_ratio,
                warning_ratio=warning_ratio,
                blocking_ratio=blocking_ratio,
                policy_used=policy_used,
                trigger_budget=(
                    thresholds.blocking_input_budget
                    if pressure_level in {"blocking", "over_budget"}
                    else thresholds.trigger_input_budget
                ),
                recent_raw_turns=configured_recent_raw_turns,
                recent_tool_turns=configured_recent_tool_turns,
                summary_max_chars=(
                    summary_max_chars
                    if not aggressive
                    else min(summary_max_chars, AGGRESSIVE_SUMMARY_MAX_CHARS)
                ),
                block_summary_chars=(
                    DEFAULT_BLOCK_SUMMARY_CHARS
                    if not aggressive
                    else AGGRESSIVE_BLOCK_SUMMARY_CHARS
                ),
                protected_indexes=compacted_protected_indexes,
            )
        )

    if file_content_trimmed:
        compression.before_tokens = max(compression.before_tokens, untrimmed_tokens)
        if compression.stage == "none":
            compression.stage = "micro"

    compression.utilization_after = (
        compression.after_tokens / token_budget.input_budget
        if token_budget.input_budget
        else 0.0
    )

    if compression.after_tokens > token_budget.input_budget:
        # Emergency fallback: keep only system prompt and current user message
        logger.warning(
            "Context still exceeds budget after all compression (%d > %d tokens). "
            "Applying emergency fallback: keeping only system prompt and current user message.",
            compression.after_tokens,
            token_budget.input_budget,
        )
        emergency_messages: list[Message] = []
        emergency_protected_indexes: set[int] = set()
        current_round_messages = [
            compacted_messages[index].model_copy(deep=True)
            for index in sorted(compacted_protected_indexes)
            if 0 <= index < len(compacted_messages)
        ]
        if compacted_messages and compacted_messages[0].role == MessageRole.SYSTEM:
            _append_message(
                emergency_messages,
                emergency_protected_indexes,
                compacted_messages[0].model_copy(deep=True),
            )
        if current_round_messages:
            for message in current_round_messages:
                _append_message(
                    emergency_messages,
                    emergency_protected_indexes,
                    message,
                    protect=True,
                )
        elif compacted_messages and compacted_messages[-1].role == MessageRole.USER:
            _append_message(
                emergency_messages,
                emergency_protected_indexes,
                compacted_messages[-1].model_copy(deep=True),
            )

        emergency_tokens = _estimate_message_tokens(
            emergency_messages,
            model_id=model_id,
            provider=provider,
        )

        if emergency_tokens > token_budget.input_budget:
            # Even system + user is too large - this shouldn't happen but handle it
            raise ContextLengthError(
                message="Context length exceeded even with emergency fallback (system + user only)",
                max_tokens=token_budget.input_budget,
                actual_tokens=emergency_tokens,
                provider=provider,
                model=model_id,
            )

        emergency_actions = list(compression.actions or [])
        if "emergency_fallback" not in emergency_actions:
            emergency_actions.append("emergency_fallback")

        return PreparedModelContext(
            messages=emergency_messages,
            token_budget=token_budget,
            compression=CompressionMeta(
                stage="macro",
                before_tokens=compression.before_tokens,
                after_tokens=emergency_tokens,
                input_budget=token_budget.input_budget,
                reasoning_trimmed=compression.reasoning_trimmed,
                tool_results_trimmed=compression.tool_results_trimmed,
                file_content_trimmed=compression.file_content_trimmed,
                summary_turns=len(compacted_messages) - len(emergency_messages),
                pressure_level="over_budget",
                trigger_ratio=compression.trigger_ratio,
                warning_ratio=compression.warning_ratio,
                blocking_ratio=compression.blocking_ratio,
                trigger_budget=compression.trigger_budget,
                hard_budget=token_budget.input_budget,
                utilization_before=compression.utilization_before,
                utilization_after=(emergency_tokens / token_budget.input_budget)
                if token_budget.input_budget
                else 0.0,
                policy_used=compression.policy_used,
                actions=emergency_actions,
                retained_recent_turns=0,
                retained_tool_turns=0,
                compacted_blocks=compression.compacted_blocks,
                session_memory_compacted=compression.session_memory_compacted,
            ),
            protected_indexes=emergency_protected_indexes,
        )

    return PreparedModelContext(
        messages=compacted_messages,
        token_budget=token_budget,
        compression=compression,
        protected_indexes=compacted_protected_indexes,
    )


async def retry_prepare_model_context(
    *,
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    model_id: str,
    model_context_limit: int | None,
    model_max_output_tokens: int | None,
    provider: str | None = None,
    file_content: str | None = None,
    user_locale: str | None = None,
    history_override: Sequence[Any] | None = None,
    current_images: Sequence[Any] | None = None,
    model_supports_vision: bool = False,
    current_user_message_id: UUID | None = None,
    include_current_user_message: bool = False,
    exclude_message_ids: Sequence[UUID] | None = None,
    history_before_message_created_at: datetime | None = None,
    tool_timeouts: dict[str, Any] | None = None,
    user: Any = None,
    protected_round_id: UUID | str | None = None,
) -> PreparedModelContext:
    return await prepare_model_context(
        agent=agent,
        conversation=conversation,
        user_message=user_message,
        model_id=model_id,
        model_context_limit=model_context_limit,
        model_max_output_tokens=model_max_output_tokens,
        provider=provider,
        file_content=file_content,
        user_locale=user_locale,
        history_override=history_override,
        current_images=current_images,
        model_supports_vision=model_supports_vision,
        current_user_message_id=current_user_message_id,
        include_current_user_message=include_current_user_message,
        exclude_message_ids=exclude_message_ids,
        history_before_message_created_at=history_before_message_created_at,
        tool_timeouts=tool_timeouts,
        user=user,
        aggressive=True,
        protected_round_id=protected_round_id,
    )
