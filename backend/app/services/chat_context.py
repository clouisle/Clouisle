"""Shared chat context preparation helpers for agent chat flows."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from app.llm.errors import ContextLengthError
from app.llm.adapters.media_utils import parse_image_data_url
from app.llm.token_counter import count_message_tokens
from app.services.context_compaction import (
    DEFAULT_ACTIVE_TOOL_RESULT_MAX_TOKENS,
    DEFAULT_ACTIVE_TOOL_SUMMARY_MAX_TOKENS,
    DEFAULT_ACTIVE_TOOL_TARGET_RATIO,
    DEFAULT_REASONING_MAX_TOKENS,
    compact_active_tool_messages,
    fit_tool_results_to_budget,
    normalize_message_content,
    truncate_text_to_tokens,
)
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
    ConversationContextCheckpoint,
    Message as ConversationMessage,
    MessageRole as ConversationMessageRole,
)
from app.services.message_branching import (
    get_visible_conversation_messages,
    get_visible_conversation_messages_after,
    is_message_on_active_branch,
)
from app.services.system_prompt import (
    CHAT_MODE,
    FILE_CONTENT_PLACEHOLDER,
    LANGUAGE_INSTRUCTIONS,
    MARKDOWN_IMAGE_DISPLAY_INSTRUCTION,
    MEMORY_SYSTEM_INSTRUCTION,
    SANDBOX_SYSTEM_INSTRUCTION,
    append_prompt_section as _append_prompt_section,
    build_system_prompt,
    build_system_prompt_with_language,
    get_language_instruction,
    get_user_input_request_instruction,
    has_sandbox_tools as _has_sandbox_tools,
)

# Re-exported from ``system_prompt`` so existing imports
# ``from app.services.chat_context import ...`` keep working.
__all__ = [
    "CHAT_MODE",
    "FILE_CONTENT_PLACEHOLDER",
    "LANGUAGE_INSTRUCTIONS",
    "MARKDOWN_IMAGE_DISPLAY_INSTRUCTION",
    "MEMORY_SYSTEM_INSTRUCTION",
    "SANDBOX_SYSTEM_INSTRUCTION",
    "_append_prompt_section",
    "_build_system_prompt",
    "_has_sandbox_tools",
    "build_system_prompt",
    "build_system_prompt_with_language",
    "get_language_instruction",
    "get_user_input_request_instruction",
]

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
DEFAULT_CHECKPOINT_TARGET_RATIO = 0.6
DEFAULT_CHECKPOINT_KEEP_RECENT_RATIO = 0.35
DEFAULT_CHECKPOINT_MIN_NEW_TURNS = 2
DEFAULT_AUTO_COMPACT_TRIGGER_RATIO = 0.8
DEFAULT_BLOCKING_RATIO = 0.92
DEFAULT_WARNING_RATIO = 0.7
DEFAULT_COMPACTION_POLICY = "staged"
DEFAULT_RETENTION_STRATEGY = "recent_raw_and_tool_first"
DEFAULT_KEEP_RECENT_TOOL_RESULTS = 2
DEFAULT_KEEP_RECENT_TOOL_RESULT_MINUTES = 20
DEFAULT_TOOL_RESULT_COMPACT_MIN_TOKENS = 256
DEFAULT_SESSION_MEMORY_MAX_TOKENS = 400
DEFAULT_SESSION_MEMORY_MIN_TURNS = 4
DEFAULT_SESSION_MEMORY_FAILURE_THRESHOLD = 3
DEFAULT_SESSION_MEMORY_COOLDOWN_SECONDS = 600
AGGRESSIVE_RECENT_REASONING_MESSAGES = 0
AGGRESSIVE_RECENT_RAW_TURNS = 2
AGGRESSIVE_RECENT_TOOL_TURNS = 1
AGGRESSIVE_SUMMARY_MAX_CHARS = 2400
DEFAULT_FILE_CONTENT_MAX_TOKENS = 6_000
AGGRESSIVE_BLOCK_SUMMARY_CHARS = 220
DEFAULT_FILE_CONTENT_HEAD_CHARS = 12000
DEFAULT_FILE_CONTENT_TAIL_CHARS = 4000
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
    "macro_on_trigger": False,
    "retention_strategy": DEFAULT_RETENTION_STRATEGY,
    "keep_recent_tool_results": DEFAULT_KEEP_RECENT_TOOL_RESULTS,
    "keep_recent_tool_result_minutes": DEFAULT_KEEP_RECENT_TOOL_RESULT_MINUTES,
    "tool_result_compact_min_tokens": DEFAULT_TOOL_RESULT_COMPACT_MIN_TOKENS,
    "active_tool_compaction_enabled": True,
    "file_content_max_tokens": DEFAULT_FILE_CONTENT_MAX_TOKENS,
    "checkpoint_keep_recent_ratio": DEFAULT_CHECKPOINT_KEEP_RECENT_RATIO,
    "reasoning_max_tokens": DEFAULT_REASONING_MAX_TOKENS,
    "active_tool_target_ratio": DEFAULT_ACTIVE_TOOL_TARGET_RATIO,
    "active_tool_result_max_tokens": DEFAULT_ACTIVE_TOOL_RESULT_MAX_TOKENS,
    "active_tool_summary_max_tokens": DEFAULT_ACTIVE_TOOL_SUMMARY_MAX_TOKENS,
    "checkpoint_summary_enabled": True,
    "checkpoint_target_ratio": DEFAULT_CHECKPOINT_TARGET_RATIO,
    "checkpoint_min_new_turns": DEFAULT_CHECKPOINT_MIN_NEW_TURNS,
    "session_memory_enabled": True,
    "session_memory_async_extract": True,
    "session_memory_max_tokens": DEFAULT_SESSION_MEMORY_MAX_TOKENS,
    "session_memory_min_turns": DEFAULT_SESSION_MEMORY_MIN_TURNS,
    "session_memory_failure_threshold": DEFAULT_SESSION_MEMORY_FAILURE_THRESHOLD,
    "session_memory_cooldown_seconds": DEFAULT_SESSION_MEMORY_COOLDOWN_SECONDS,
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
    context_limit: int = 0
    output_reserve: int = 0
    safety_margin: int = 0
    active_tool_tokens: int = 0
    target_budget: int = 0
    keep_recent_budget: int = 0
    segment_tokens: dict[str, int] = field(default_factory=dict)


def _merge_compression_meta(
    baseline: CompressionMeta,
    current: CompressionMeta,
) -> CompressionMeta:
    actions = list(dict.fromkeys([*(baseline.actions or []), *(current.actions or [])]))
    return replace(
        current,
        stage=(baseline.stage if current.stage == "none" else current.stage),
        before_tokens=max(baseline.before_tokens, current.before_tokens),
        reasoning_trimmed=baseline.reasoning_trimmed or current.reasoning_trimmed,
        tool_results_trimmed=(
            baseline.tool_results_trimmed or current.tool_results_trimmed
        ),
        file_content_trimmed=(
            baseline.file_content_trimmed or current.file_content_trimmed
        ),
        summary_turns=baseline.summary_turns + current.summary_turns,
        utilization_before=baseline.utilization_before,
        policy_used=current.policy_used or baseline.policy_used,
        actions=actions,
        context_limit=current.context_limit or baseline.context_limit,
        output_reserve=current.output_reserve or baseline.output_reserve,
        safety_margin=current.safety_margin or baseline.safety_margin,
        active_tool_tokens=max(baseline.active_tool_tokens, current.active_tool_tokens),
        target_budget=current.target_budget or baseline.target_budget,
        keep_recent_budget=current.keep_recent_budget or baseline.keep_recent_budget,
        segment_tokens=current.segment_tokens or baseline.segment_tokens,
        session_memory_compacted=(
            baseline.session_memory_compacted or current.session_memory_compacted
        ),
    )


def _history_override_is_active_delta(
    history_override: Sequence[Any] | None,
    protected_round_id: UUID | str | None,
) -> bool:
    return bool(
        history_override
        and protected_round_id is not None
        and not any(
            _normalize_override_role(_get_override_value(item, "role")) == "user"
            for item in history_override
        )
        and any(
            _matches_protected_round(
                _get_override_value(item, "round_id"), protected_round_id
            )
            for item in history_override
        )
    )


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


def _normalize_vision_image(data: str, image_format: str | None) -> tuple[str, str]:
    try:
        with Image.open(io.BytesIO(base64.b64decode(data))) as image:
            if max(image.size) <= 2048 and len(data) <= 1_000_000:
                return data, image_format or "png"

            image.thumbnail((2048, 2048))
            normalized_image: Image.Image = image
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image)
                normalized_image = background

            output = io.BytesIO()
            normalized_image.save(output, format="JPEG", quality=85, optimize=True)
            return base64.b64encode(output.getvalue()).decode(), "jpeg"
    except (OSError, ValueError, UnidentifiedImageError):
        return data, image_format or "png"


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
            data_part, image_format = _normalize_vision_image(*parsed_data_url)
            content_parts.append(
                ContentPart(
                    type=ContentType.IMAGE,
                    image=ImageContent(base64=data_part, format=image_format),
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


def _normalize_file_content_for_budget(
    file_content: str | None,
    *,
    max_tokens: int,
    model_id: str | None,
    provider: str | None,
) -> tuple[str | None, bool]:
    if not file_content:
        return file_content, False
    normalized, changed = truncate_text_to_tokens(
        file_content,
        max_tokens=max_tokens,
        model_id=model_id or "",
        provider=provider,
        marker="\n\n[... file content truncated for context budget ...]\n\n",
    )
    return normalized, changed


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


def _build_system_prompt(
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    user_locale: str | None,
) -> str:
    """Build the system prompt for the chat endpoint.

    Thin adapter over :func:`app.services.system_prompt.build_system_prompt`:
    extracts conversation template variables and fixes the invocation mode to
    chat. Kept so existing callers/tests keep their signature.
    """
    variables = getattr(conversation, "variables", None)
    return build_system_prompt(
        agent,
        variables=dict(variables) if variables else None,
        user_message=user_message,
        user_locale=user_locale,
        invocation_mode=CHAT_MODE,
    )


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


def _context_segment_tokens(
    messages: Sequence[Message],
    *,
    model_id: str,
    provider: str | None,
) -> dict[str, int]:
    """Return non-overlapping message token totals for budget diagnostics."""
    segments = {
        "system": 0,
        "checkpoint": 0,
        "historical": 0,
        "current_user": 0,
        "active_tool": 0,
        "other": 0,
        "total": _estimate_message_tokens(
            messages, model_id=model_id, provider=provider
        ),
    }
    last_user_index = max(
        (
            index
            for index, message in enumerate(messages)
            if message.role == MessageRole.USER
        ),
        default=-1,
    )
    for index, message in enumerate(messages):
        message_tokens = _estimate_message_tokens(
            [message], model_id=model_id, provider=provider
        )
        content = message.content if isinstance(message.content, str) else ""
        if message.role == MessageRole.SYSTEM:
            segment = "system"
        elif index == last_user_index and message.role == MessageRole.USER:
            segment = "current_user"
        elif index > last_user_index and message.role in {
            MessageRole.ASSISTANT,
            MessageRole.TOOL,
        }:
            segment = "active_tool"
        elif content.startswith(
            ("Context checkpoint summary:", "Compressed earlier conversation summary:")
        ):
            segment = "checkpoint"
        elif index < last_user_index:
            segment = "historical"
        else:
            segment = "other"
        segments[segment] += message_tokens
    return segments


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
        protect=True,
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

    if _estimate_message_tokens(
        compacted, model_id=model_id, provider=provider
    ) >= _estimate_message_tokens(messages, model_id=model_id, provider=provider):
        cloned_messages, cloned_protected_indexes = _clone_messages(
            messages, protected_indexes
        )
        return cloned_messages, False, cloned_protected_indexes

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
    context_checkpoint: ConversationContextCheckpoint | None = None,
) -> tuple[list[Message], set[int]]:
    active_round_delta = _history_override_is_active_delta(
        history_override, protected_round_id
    )
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
    if (
        (history_override is None or active_round_delta)
        and context_checkpoint
        and context_checkpoint.summary_text
    ):
        _append_message(
            messages,
            protected_indexes,
            Message(
                role=MessageRole.ASSISTANT,
                content=context_checkpoint.summary_text,
            ),
            protect=True,
        )

    current_content = _append_file_content_to_user_content(
        _build_current_user_content(
            user_message=user_message,
            current_images=current_images,
            model_supports_vision=model_supports_vision,
        ),
        file_content,
    )

    if history_override is not None and not active_round_delta:
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

    if context_checkpoint and context_checkpoint.covered_through_message_id:
        checkpoint_history = await get_visible_conversation_messages_after(
            conversation.id,
            after_message_id=context_checkpoint.covered_through_message_id,
            before_created_at=history_before_message_created_at,
            exclude_message_ids=exclude_message_ids,
        )
        history = (
            checkpoint_history
            if checkpoint_history is not None
            else await get_visible_conversation_messages(
                conversation.id,
                before_created_at=history_before_message_created_at,
                exclude_message_ids=exclude_message_ids,
            )
        )
    else:
        history = await get_visible_conversation_messages(
            conversation.id,
            before_created_at=history_before_message_created_at,
            exclude_message_ids=exclude_message_ids,
        )
    if active_round_delta:
        history = [
            message
            for message in history
            if not _matches_protected_round(message.round_id, protected_round_id)
        ]
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

    current_user_inserted = False
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
                    current_user_inserted = True
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
    if (
        active_round_delta
        and include_current_user_message
        and not current_user_inserted
    ):
        _append_message(
            messages,
            protected_indexes,
            Message(role=MessageRole.USER, content=current_content),
            protect=True,
        )

    if not include_current_user_message:
        _append_message(
            messages,
            protected_indexes,
            Message(role=MessageRole.USER, content=current_content),
            protect=protected_round_id is not None,
        )
    if active_round_delta:
        for hist_msg in history_override or ():
            role = _normalize_override_role(_get_override_value(hist_msg, "role"))
            if role == "user":
                continue
            protect = _matches_protected_round(
                _get_override_value(hist_msg, "round_id"), protected_round_id
            )
            content = _get_override_value(hist_msg, "content") or ""
            if role == "assistant":
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
                            hist_msg, "reasoning_content"
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
                                content,
                            ),
                            tool_call_id=tool_call_id,
                        ),
                        protect=protect,
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
    skip_session_memory: bool = False,
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
    if skip_session_memory:
        session_memory_messages = tool_compacted
        session_memory_compacted = False
        session_memory_protected_indexes = tool_protected_indexes
    else:
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
    target_budget: int | None = None,
) -> tuple[list[Message], CompressionMeta, set[int]]:
    protected_indexes = protected_indexes or set()
    required_budget = target_budget or token_budget.input_budget
    if compression.after_tokens <= required_budget and pressure_level != "blocking":
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
    context_checkpoint = None
    if (
        history_override is None
        or _history_override_is_active_delta(history_override, protected_round_id)
    ) and get_context_compression_config(agent).get("checkpoint_summary_enabled", True):
        from app.services.context_checkpoint import get_valid_context_checkpoint

        context_checkpoint = await get_valid_context_checkpoint(
            conversation.id,
            before_created_at=history_before_message_created_at,
        )

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
        context_checkpoint=context_checkpoint,
    )
    return messages


async def prepare_model_context(
    *,
    agent: Agent,
    conversation: Conversation,
    user_message: str,
    model_id: str,
    tokenizer_model_id: str | None = None,
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
    compression_enabled = bool(compression_config.get("enabled", True))
    checkpoint_summary_enabled = bool(
        compression_config.get("checkpoint_summary_enabled", True)
    )
    active_round_delta = _history_override_is_active_delta(
        history_override, protected_round_id
    )
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
    checkpoint_target_ratio = float(
        compression_config.get(
            "checkpoint_target_ratio", DEFAULT_CHECKPOINT_TARGET_RATIO
        )
    )
    checkpoint_keep_recent_ratio = float(
        compression_config.get(
            "checkpoint_keep_recent_ratio", DEFAULT_CHECKPOINT_KEEP_RECENT_RATIO
        )
    )
    if checkpoint_target_ratio >= trigger_ratio:
        checkpoint_target_ratio = max(trigger_ratio * 0.75, 0.01)
    checkpoint_min_new_turns = int(
        compression_config.get(
            "checkpoint_min_new_turns", DEFAULT_CHECKPOINT_MIN_NEW_TURNS
        )
    )
    policy_used = DEFAULT_COMPACTION_POLICY
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
    active_tool_compaction_enabled = bool(
        compression_config.get("active_tool_compaction_enabled", True)
    )
    active_tool_target_ratio = float(
        compression_config.get(
            "active_tool_target_ratio", DEFAULT_ACTIVE_TOOL_TARGET_RATIO
        )
    )
    active_tool_result_max_tokens = int(
        compression_config.get(
            "active_tool_result_max_tokens", DEFAULT_ACTIVE_TOOL_RESULT_MAX_TOKENS
        )
    )
    active_tool_summary_max_tokens = int(
        compression_config.get(
            "active_tool_summary_max_tokens", DEFAULT_ACTIVE_TOOL_SUMMARY_MAX_TOKENS
        )
    )
    normalized_file_max_tokens = min(
        int(
            compression_config.get(
                "file_content_max_tokens", DEFAULT_FILE_CONTENT_MAX_TOKENS
            )
        ),
        max(token_budget.input_budget // 3, 128),
    )
    reasoning_max_tokens = int(
        compression_config.get("reasoning_max_tokens", DEFAULT_REASONING_MAX_TOKENS)
    )
    thresholds = _build_compression_thresholds(
        token_budget=token_budget,
        warning_ratio=warning_ratio,
        trigger_ratio=trigger_ratio,
        blocking_ratio=blocking_ratio,
    )
    file_content, file_content_bounded = _normalize_file_content_for_budget(
        file_content,
        max_tokens=normalized_file_max_tokens,
        model_id=tokenizer_model_id or model_id,
        provider=provider,
    )
    context_checkpoint = None
    if (
        compression_enabled
        and checkpoint_summary_enabled
        and (history_override is None or active_round_delta)
    ):
        from app.services.context_checkpoint import get_valid_context_checkpoint

        context_checkpoint = await get_valid_context_checkpoint(
            conversation.id,
            before_created_at=history_before_message_created_at,
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
        context_checkpoint=context_checkpoint,
    )
    source_tokens = _estimate_message_tokens(
        untrimmed_messages,
        model_id=tokenizer_model_id,
        provider=provider,
    )
    if not compression_enabled:
        source_pressure = _assess_context_pressure(
            before_tokens=source_tokens,
            token_budget=token_budget,
            thresholds=thresholds,
        )
        disabled_segments = {
            "system": 0,
            "checkpoint": 0,
            "historical": 0,
            "current_user": 0,
            "active_tool": 0,
            "other": 0,
            "total": source_tokens,
        }
        return PreparedModelContext(
            messages=untrimmed_messages,
            token_budget=token_budget,
            compression=CompressionMeta(
                stage="none",
                before_tokens=source_tokens,
                after_tokens=source_tokens,
                input_budget=token_budget.input_budget,
                file_content_trimmed=file_content_bounded,
                pressure_level=source_pressure,
                trigger_ratio=trigger_ratio,
                warning_ratio=warning_ratio,
                blocking_ratio=blocking_ratio,
                trigger_budget=thresholds.trigger_input_budget,
                hard_budget=token_budget.input_budget,
                utilization_before=(
                    source_tokens / token_budget.input_budget
                    if token_budget.input_budget
                    else 0.0
                ),
                utilization_after=(
                    source_tokens / token_budget.input_budget
                    if token_budget.input_budget
                    else 0.0
                ),
                policy_used=policy_used,
                actions=["bound_file_content"] if file_content_bounded else [],
                context_limit=token_budget.context_limit,
                output_reserve=token_budget.output_reserve,
                safety_margin=token_budget.safety_margin,
                target_budget=thresholds.trigger_input_budget,
                keep_recent_budget=max(
                    int(token_budget.input_budget * checkpoint_target_ratio), 1
                ),
                segment_tokens=disabled_segments,
            ),
            protected_indexes=untrimmed_protected_indexes,
        )
    normalized_content = normalize_message_content(
        untrimmed_messages,
        protected_indexes=untrimmed_protected_indexes,
        model_id=tokenizer_model_id or model_id,
        provider=provider,
        max_tool_result_tokens=active_tool_result_max_tokens,
        max_reasoning_tokens=reasoning_max_tokens,
    )
    untrimmed_messages = normalized_content.messages
    untrimmed_protected_indexes = normalized_content.protected_indexes
    normalized_source_tokens = _estimate_message_tokens(
        untrimmed_messages,
        model_id=tokenizer_model_id,
        provider=provider,
    )
    source_pressure = _assess_context_pressure(
        before_tokens=normalized_source_tokens,
        token_budget=token_budget,
        thresholds=thresholds,
    )
    normalization_actions = list(normalized_content.actions or [])
    normalization_tool_results_trimmed = normalized_content.tool_results_trimmed
    normalization_reasoning_trimmed = normalized_content.reasoning_trimmed
    if file_content_bounded:
        normalization_actions.append("bound_file_content")

    preflight_guard_enabled = bool(
        compression_config.get("preflight_guard_enabled", True)
    )
    if not compression_enabled or not preflight_guard_enabled:
        utilization_before = (
            source_tokens / token_budget.input_budget
            if token_budget.input_budget
            else 0.0
        )
        disabled_segments = _context_segment_tokens(
            untrimmed_messages,
            model_id=tokenizer_model_id,
            provider=provider,
        )
        return PreparedModelContext(
            messages=untrimmed_messages,
            token_budget=token_budget,
            compression=CompressionMeta(
                stage="none",
                before_tokens=source_tokens,
                after_tokens=normalized_source_tokens,
                input_budget=token_budget.input_budget,
                reasoning_trimmed=normalization_reasoning_trimmed,
                tool_results_trimmed=normalization_tool_results_trimmed,
                file_content_trimmed=file_content_bounded,
                pressure_level=source_pressure,
                trigger_ratio=trigger_ratio,
                warning_ratio=warning_ratio,
                blocking_ratio=blocking_ratio,
                trigger_budget=thresholds.trigger_input_budget,
                hard_budget=token_budget.input_budget,
                utilization_before=utilization_before,
                utilization_after=(
                    normalized_source_tokens / token_budget.input_budget
                    if token_budget.input_budget
                    else 0.0
                ),
                policy_used=policy_used,
                actions=list(dict.fromkeys(normalization_actions)),
                context_limit=token_budget.context_limit,
                output_reserve=token_budget.output_reserve,
                safety_margin=token_budget.safety_margin,
                active_tool_tokens=disabled_segments["active_tool"],
                target_budget=thresholds.trigger_input_budget,
                keep_recent_budget=max(
                    int(token_budget.input_budget * checkpoint_target_ratio), 1
                ),
                segment_tokens=disabled_segments,
            ),
            protected_indexes=untrimmed_protected_indexes,
        )
    if compression_enabled and preflight_guard_enabled:
        (
            baseline_messages,
            baseline_session_memory_compacted,
            baseline_protected_indexes,
        ) = await _apply_session_memory_compaction(
            untrimmed_messages,
            conversation=conversation,
            model_id=tokenizer_model_id,
            provider=provider,
            recent_raw_turns=configured_recent_raw_turns,
            recent_tool_turns=configured_recent_tool_turns,
            protected_indexes=untrimmed_protected_indexes,
            before_created_at=history_before_message_created_at,
        )
        if baseline_session_memory_compacted:
            untrimmed_messages = baseline_messages
            untrimmed_protected_indexes = baseline_protected_indexes

    untrimmed_tokens = _estimate_message_tokens(
        untrimmed_messages,
        model_id=tokenizer_model_id,
        provider=provider,
    )
    utilization_before = (
        untrimmed_tokens / token_budget.input_budget
        if token_budget.input_budget
        else 0.0
    )
    needs_file_trim = (
        bool(file_content) and untrimmed_tokens > thresholds.trigger_input_budget
    )
    effective_file_content = file_content
    additional_file_trimmed = False
    if needs_file_trim:
        effective_file_content, additional_file_trimmed = _trim_file_content(
            file_content,
            aggressive=aggressive,
        )
    file_content_trimmed = file_content_bounded or additional_file_trimmed

    if not additional_file_trimmed:
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
            context_checkpoint=context_checkpoint,
        )
        (
            base_messages,
            _,
            base_protected_indexes,
        ) = await _apply_session_memory_compaction(
            base_messages,
            conversation=conversation,
            model_id=tokenizer_model_id,
            provider=provider,
            recent_raw_turns=configured_recent_raw_turns,
            recent_tool_turns=configured_recent_tool_turns,
            protected_indexes=base_protected_indexes,
            before_created_at=history_before_message_created_at,
        )
        rebuilt_normalization = normalize_message_content(
            base_messages,
            protected_indexes=base_protected_indexes,
            model_id=tokenizer_model_id or model_id,
            provider=provider,
            max_tool_result_tokens=active_tool_result_max_tokens,
            max_reasoning_tokens=reasoning_max_tokens,
        )
        base_messages = rebuilt_normalization.messages
        base_protected_indexes = rebuilt_normalization.protected_indexes
        normalization_actions.extend(rebuilt_normalization.actions or [])
        normalization_tool_results_trimmed = (
            normalization_tool_results_trimmed
            or rebuilt_normalization.tool_results_trimmed
        )
        normalization_reasoning_trimmed = (
            normalization_reasoning_trimmed or rebuilt_normalization.reasoning_trimmed
        )

    base_tokens = _estimate_message_tokens(
        base_messages,
        model_id=tokenizer_model_id,
        provider=provider,
    )
    pressure_level = _assess_context_pressure(
        before_tokens=base_tokens,
        token_budget=token_budget,
        thresholds=thresholds,
    )

    compacted_messages = base_messages
    compacted_protected_indexes = set(base_protected_indexes)
    base_segments = _context_segment_tokens(
        base_messages,
        model_id=tokenizer_model_id,
        provider=provider,
    )
    compression = CompressionMeta(
        stage="none",
        before_tokens=untrimmed_tokens,
        after_tokens=base_tokens,
        input_budget=token_budget.input_budget,
        reasoning_trimmed=normalization_reasoning_trimmed,
        tool_results_trimmed=normalization_tool_results_trimmed,
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
        actions=list(
            dict.fromkeys(
                [*normalization_actions]
                + (["trim_file_content"] if file_content_trimmed else [])
            )
        ),
        context_limit=token_budget.context_limit,
        output_reserve=token_budget.output_reserve,
        safety_margin=token_budget.safety_margin,
        active_tool_tokens=base_segments["active_tool"],
        target_budget=thresholds.trigger_input_budget,
        keep_recent_budget=max(
            int(token_budget.input_budget * checkpoint_target_ratio), 1
        ),
        segment_tokens=base_segments,
    )
    compression_baseline = compression

    checkpoint_created = False
    checkpoint_fallback_required = False
    checkpoint_target_budget = max(
        int(token_budget.input_budget * checkpoint_target_ratio), 1
    )
    if (
        checkpoint_summary_enabled
        and history_override is None
        and source_pressure in {"auto_compact", "blocking", "over_budget"}
    ):
        from app.services.context_checkpoint import create_context_checkpoint

        checkpoint_exclude_ids = set(exclude_message_ids or ())
        if current_user_message_id:
            checkpoint_exclude_ids.add(current_user_message_id)
        checkpoint_source_messages = None
        try:
            if context_checkpoint and context_checkpoint.covered_through_message_id:
                checkpoint_source_messages = (
                    await get_visible_conversation_messages_after(
                        conversation.id,
                        after_message_id=context_checkpoint.covered_through_message_id,
                        before_created_at=history_before_message_created_at,
                        exclude_message_ids=checkpoint_exclude_ids,
                    )
                )
            if checkpoint_source_messages is None:
                checkpoint_source_messages = await get_visible_conversation_messages(
                    conversation.id,
                    before_created_at=history_before_message_created_at,
                    exclude_message_ids=checkpoint_exclude_ids,
                )
        except Exception:
            logger.warning(
                "Skipping context checkpoint because history could not be loaded for %s",
                conversation.id,
                exc_info=True,
            )
            checkpoint_source_messages = []
        checkpoint_result = await create_context_checkpoint(
            agent=agent,
            conversation=conversation,
            messages=checkpoint_source_messages,
            previous_checkpoint=context_checkpoint,
            model_id=model_id,
            tokenizer_model_id=tokenizer_model_id,
            provider=provider,
            summary_max_tokens=int(
                compression_config.get("summary_max_tokens", DEFAULT_SUMMARY_MAX_TOKENS)
            ),
            recent_raw_turns=configured_recent_raw_turns,
            recent_tool_turns=configured_recent_tool_turns,
            min_new_turns=checkpoint_min_new_turns,
            input_budget=token_budget.input_budget,
            keep_recent_tokens=max(
                int(token_budget.input_budget * checkpoint_keep_recent_ratio), 1
            ),
        )
        if checkpoint_result.created and checkpoint_result.checkpoint:
            context_checkpoint = checkpoint_result.checkpoint
            (
                base_messages,
                base_protected_indexes,
            ) = await _build_messages_with_file_content(
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
                context_checkpoint=context_checkpoint,
            )
            checkpoint_normalization = normalize_message_content(
                base_messages,
                protected_indexes=base_protected_indexes,
                model_id=tokenizer_model_id or model_id,
                provider=provider,
                max_tool_result_tokens=active_tool_result_max_tokens,
                max_reasoning_tokens=reasoning_max_tokens,
            )
            base_messages = checkpoint_normalization.messages
            base_protected_indexes = checkpoint_normalization.protected_indexes
            normalization_actions.extend(checkpoint_normalization.actions or [])
            normalization_tool_results_trimmed = (
                normalization_tool_results_trimmed
                or checkpoint_normalization.tool_results_trimmed
            )
            normalization_reasoning_trimmed = (
                normalization_reasoning_trimmed
                or checkpoint_normalization.reasoning_trimmed
            )
            base_tokens = _estimate_message_tokens(
                base_messages,
                model_id=tokenizer_model_id,
                provider=provider,
            )
            pressure_level = _assess_context_pressure(
                before_tokens=base_tokens,
                token_budget=token_budget,
                thresholds=thresholds,
            )
            compacted_messages = base_messages
            compacted_protected_indexes = set(base_protected_indexes)
            checkpoint_created = True
            checkpoint_actions = ["checkpoint_summary"]
            if file_content_trimmed:
                checkpoint_actions.insert(0, "trim_file_content")
            checkpoint_segments = _context_segment_tokens(
                base_messages,
                model_id=tokenizer_model_id,
                provider=provider,
            )
            compression = CompressionMeta(
                stage="macro",
                before_tokens=untrimmed_tokens,
                after_tokens=base_tokens,
                input_budget=token_budget.input_budget,
                reasoning_trimmed=normalization_reasoning_trimmed,
                tool_results_trimmed=normalization_tool_results_trimmed,
                file_content_trimmed=file_content_trimmed,
                summary_turns=checkpoint_result.covered_turns,
                pressure_level=pressure_level,
                trigger_ratio=trigger_ratio,
                warning_ratio=warning_ratio,
                blocking_ratio=blocking_ratio,
                trigger_budget=thresholds.trigger_input_budget,
                hard_budget=token_budget.input_budget,
                utilization_before=(
                    source_tokens / token_budget.input_budget
                    if token_budget.input_budget
                    else 0.0
                ),
                utilization_after=(
                    base_tokens / token_budget.input_budget
                    if token_budget.input_budget
                    else 0.0
                ),
                policy_used=policy_used,
                actions=list(
                    dict.fromkeys([*normalization_actions, *checkpoint_actions])
                ),
                retained_recent_turns=checkpoint_result.retained_turns,
                compacted_blocks=checkpoint_result.covered_turns,
                context_limit=token_budget.context_limit,
                output_reserve=token_budget.output_reserve,
                safety_margin=token_budget.safety_margin,
                active_tool_tokens=checkpoint_segments["active_tool"],
                target_budget=thresholds.trigger_input_budget,
                keep_recent_budget=checkpoint_target_budget,
                segment_tokens=checkpoint_segments,
            )
            compression_baseline = compression
        else:
            checkpoint_fallback_required = True
    should_run_micro = not checkpoint_created and pressure_level in {
        "auto_compact",
        "blocking",
        "over_budget",
    }
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
            model_id=tokenizer_model_id,
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
            # Preflight has already checked the same base context for a ready snapshot.
            skip_session_memory=True,
        )
        compression.file_content_trimmed = file_content_trimmed
        if file_content_trimmed and "trim_file_content" not in (
            compression.actions or []
        ):
            compression.actions = [*(compression.actions or []), "trim_file_content"]
        compression = _merge_compression_meta(compression_baseline, compression)
        compression_baseline = compression

    should_run_macro = False
    if compression_config.get("macro_compaction_enabled", True):
        should_run_macro = pressure_level in {"blocking", "over_budget"}
        if (
            not should_run_macro
            and pressure_level == "auto_compact"
            and (macro_on_trigger or checkpoint_fallback_required)
        ):
            should_run_macro = True
        if compression.after_tokens > token_budget.input_budget:
            should_run_macro = True
        if checkpoint_created and compression.after_tokens > checkpoint_target_budget:
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
                model_id=tokenizer_model_id,
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
                target_budget=(
                    checkpoint_target_budget if checkpoint_created else None
                ),
            )
        )
    if should_run_macro:
        compression = _merge_compression_meta(compression_baseline, compression)
        compression_baseline = compression
    if compression_enabled and active_tool_compaction_enabled:
        active_compaction = compact_active_tool_messages(
            compacted_messages,
            protected_indexes=compacted_protected_indexes,
            model_id=tokenizer_model_id,
            provider=provider,
            input_budget=token_budget.input_budget,
            target_ratio=active_tool_target_ratio,
            max_tool_result_tokens=active_tool_result_max_tokens,
            summary_max_tokens=active_tool_summary_max_tokens,
        )
        if active_compaction.changed:
            compacted_messages = active_compaction.messages
            compacted_protected_indexes = active_compaction.protected_indexes
            base_messages = compacted_messages
            base_protected_indexes = set(compacted_protected_indexes)
            base_tokens = _estimate_message_tokens(
                base_messages,
                model_id=tokenizer_model_id,
                provider=provider,
            )
            pressure_level = _assess_context_pressure(
                before_tokens=base_tokens,
                token_budget=token_budget,
                thresholds=thresholds,
            )
            compression.after_tokens = base_tokens
            compression.pressure_level = pressure_level
            if compression.stage == "none":
                compression.stage = "micro"
            compression.tool_results_trimmed = (
                compression.tool_results_trimmed
                or active_compaction.tool_results_trimmed
            )
            compression.actions = [
                *(compression.actions or []),
                *(active_compaction.actions or []),
            ]
            compression.active_tool_tokens = sum(
                _estimate_message_tokens(
                    [message], model_id=tokenizer_model_id, provider=provider
                )
                for message in compacted_messages
                if message.role == MessageRole.TOOL
            )

    if compression_enabled and compression.after_tokens > token_budget.input_budget:
        fit_result = fit_tool_results_to_budget(
            compacted_messages,
            protected_indexes=compacted_protected_indexes,
            model_id=tokenizer_model_id,
            provider=provider,
            input_budget=token_budget.input_budget,
        )
        if fit_result.changed:
            compacted_messages = fit_result.messages
            compacted_protected_indexes = fit_result.protected_indexes
            compression.tool_results_trimmed = True
            compression.actions = [
                *(compression.actions or []),
                *(fit_result.actions or []),
            ]
            compression.after_tokens = _estimate_message_tokens(
                compacted_messages,
                model_id=tokenizer_model_id,
                provider=provider,
            )
            compression.stage = "reactive_retry"
            compression.pressure_level = (
                "over_budget"
                if compression.after_tokens > token_budget.input_budget
                else compression.pressure_level
            )
    final_segments = _context_segment_tokens(
        compacted_messages,
        model_id=tokenizer_model_id,
        provider=provider,
    )
    compression.segment_tokens = final_segments
    compression.active_tool_tokens = final_segments["active_tool"]
    compression.context_limit = token_budget.context_limit
    compression.output_reserve = token_budget.output_reserve
    compression.safety_margin = token_budget.safety_margin
    compression.target_budget = thresholds.trigger_input_budget
    compression.keep_recent_budget = checkpoint_target_budget
    compression.actions = list(dict.fromkeys(compression.actions or []))
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
        current_user_message = next(
            (
                compacted_messages[index].model_copy(deep=True)
                for index in range(len(compacted_messages) - 1, -1, -1)
                if index in compacted_protected_indexes
                and compacted_messages[index].role == MessageRole.USER
            ),
            None,
        ) or next(
            (
                compacted_messages[index].model_copy(deep=True)
                for index in range(len(compacted_messages) - 1, -1, -1)
                if compacted_messages[index].role == MessageRole.USER
            ),
            None,
        )
        if compacted_messages and compacted_messages[0].role == MessageRole.SYSTEM:
            _append_message(
                emergency_messages,
                emergency_protected_indexes,
                compacted_messages[0].model_copy(deep=True),
            )
        if current_user_message is not None:
            _append_message(
                emergency_messages,
                emergency_protected_indexes,
                current_user_message,
                protect=True,
            )

        emergency_tokens = _estimate_message_tokens(
            emergency_messages,
            model_id=tokenizer_model_id,
            provider=provider,
        )
        emergency_segments = _context_segment_tokens(
            emergency_messages,
            model_id=tokenizer_model_id,
            provider=provider,
        )
        if emergency_tokens > token_budget.input_budget:
            raise ContextLengthError(
                message="Context length exceeded even with emergency fallback (system + user only)",
                max_tokens=token_budget.input_budget,
                actual_tokens=emergency_tokens,
                provider=provider,
                model=model_id,
                details={
                    "retryable": False,
                    "reason": "system_and_user_exceed_input_budget",
                    "context_limit": token_budget.context_limit,
                    "output_reserve": token_budget.output_reserve,
                    "safety_margin": token_budget.safety_margin,
                    "segment_tokens": emergency_segments,
                    "reduction_actions": list(compression.actions or []),
                },
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
                input_budget=token_budget.input_budget,
                after_tokens=emergency_tokens,
                reasoning_trimmed=compression.reasoning_trimmed,
                tool_results_trimmed=compression.tool_results_trimmed,
                file_content_trimmed=compression.file_content_trimmed,
                summary_turns=max(len(compacted_messages) - len(emergency_messages), 0),
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
                context_limit=token_budget.context_limit,
                output_reserve=token_budget.output_reserve,
                safety_margin=token_budget.safety_margin,
                active_tool_tokens=emergency_segments["active_tool"],
                target_budget=thresholds.trigger_input_budget,
                keep_recent_budget=checkpoint_target_budget,
                segment_tokens=emergency_segments,
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
    tokenizer_model_id: str | None = None,
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
        tokenizer_model_id=tokenizer_model_id,
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
