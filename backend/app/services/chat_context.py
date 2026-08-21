"""Shared chat context preparation helpers for agent chat flows."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from app.llm.errors import ContextLengthError
from app.llm.adapters.media_utils import parse_image_data_url
from app.llm.token_counter import count_message_tokens, count_tokens
from app.schemas.response import BusinessError
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
from app.services.tool_step_compaction import compact_round_tool_steps

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
DEFAULT_SUMMARY_MAX_TOKENS = 1000
DEFAULT_SUMMARY_TRIGGER_RATIO = 0.9
DEFAULT_SUMMARY_KEEP_RECENT_TURNS = 3
DEFAULT_SUMMARY_KEEP_BUDGET_RATIO = 0.15
DEFAULT_SUMMARY_KEEP_RECENT_STEPS = 12
DEFAULT_FILE_CONTENT_MAX_TOKENS = 6_000
CONTEXT_SUMMARY_TIMEOUT_SECONDS = 180.0
CONTEXT_SUMMARY_MAX_ATTEMPTS = 3
CONTEXT_SUMMARY_RETRY_DELAY_SECONDS = 2.0
CONTEXT_SUMMARY_PREFIX = (
    "Earlier conversation summary (older history was replaced by this summary):"
)
DEFAULT_CONTEXT_COMPRESSION_CONFIG = {
    "enabled": True,
    "summary_trigger_ratio": DEFAULT_SUMMARY_TRIGGER_RATIO,
    "summary_max_tokens": DEFAULT_SUMMARY_MAX_TOKENS,
    "summary_keep_recent_turns": DEFAULT_SUMMARY_KEEP_RECENT_TURNS,
    "summary_keep_budget_ratio": DEFAULT_SUMMARY_KEEP_BUDGET_RATIO,
    "summary_keep_recent_steps": DEFAULT_SUMMARY_KEEP_RECENT_STEPS,
    "output_token_reserve": DEFAULT_OUTPUT_TOKEN_RESERVE,
    "safety_margin_tokens": DEFAULT_SAFETY_MARGIN_TOKENS,
    "file_content_max_tokens": DEFAULT_FILE_CONTENT_MAX_TOKENS,
    "emit_sse_events": True,
}


@dataclass(slots=True)
class TokenBudget:
    context_limit: int
    output_reserve: int
    safety_margin: int
    input_budget: int


@dataclass(slots=True)
class CompressionMeta:
    stage: Literal["none", "macro"]
    before_tokens: int
    after_tokens: int
    input_budget: int
    summary_turns: int = 0
    pressure_level: Literal[
        "normal", "warning", "auto_compact", "blocking", "over_budget"
    ] = "normal"
    trigger_ratio: float = DEFAULT_SUMMARY_TRIGGER_RATIO
    utilization_before: float = 0.0
    utilization_after: float = 0.0
    policy_used: str = "preflight_summary"
    actions: list[str] | None = None
    context_limit: int = 0
    output_reserve: int = 0
    safety_margin: int = 0


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
    messages: Sequence[Message], model_id: str | None, provider: str | None
) -> int:
    payload = [_message_to_token_payload(message) for message in messages]
    return count_message_tokens(
        payload,
        model_id=model_id,
        provider=provider,
        include_tool_calls=True,
    )


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
    context_summary_text: str | None = None,
    history_after_message_id: UUID | None = None,
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
    if context_summary_text:
        _append_message(
            messages,
            protected_indexes,
            Message(
                role=MessageRole.USER,
                content=f"{CONTEXT_SUMMARY_PREFIX}\n\n{context_summary_text}",
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

    if history_after_message_id:
        after_history = await get_visible_conversation_messages_after(
            conversation.id,
            after_message_id=history_after_message_id,
            before_created_at=history_before_message_created_at,
            exclude_message_ids=exclude_message_ids,
        )
        history = (
            after_history
            if after_history is not None
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


def truncate_text_to_tokens(
    text: str,
    *,
    max_tokens: int,
    model_id: str | None = None,
    provider: str | None = None,
    marker: str = "\n...[truncated]...\n",
) -> tuple[str, bool]:
    """Keep the head and tail of text within a model-token limit."""
    if not text:
        return "", False
    token_count = count_tokens(text, model_id=model_id, provider=provider)
    if token_count <= max_tokens:
        return text, False
    chars_per_token = max(len(text) / token_count, 1)
    budget_chars = max(int(max_tokens * chars_per_token), 1)
    head_chars = max(int(budget_chars * 0.7), 1)
    tail_chars = max(budget_chars - head_chars, 0)
    marker = "\n...[truncated]...\n"
    return f"{text[:head_chars]}{marker}{text[len(text) - tail_chars :]}", True


def _fit_message_contents_to_budget(
    messages: Sequence[Message],
    *,
    input_budget: int,
    tool_definition_tokens: int,
    model_id: str | None,
    provider: str | None,
    protected_indexes: set[int] | None = None,
) -> tuple[list[Message], bool]:
    """Trim eligible text payloads without breaking tool-call protocol.

    Deterministic round compaction removes completed groups, but the newest
    tool result may itself be larger than the remaining input budget. Shrink
    tool-result content and only unprotected assistant prose; never alter
    protected assistant messages, tool-call arguments, roles, IDs, system
    prompts, or user requests.
    """
    total = _estimate_message_tokens(messages, model_id, provider) + max(
        tool_definition_tokens, 0
    )
    if total <= input_budget:
        return list(messages), False

    fitted = [message.model_copy(deep=True) for message in messages]
    changed = False
    for _ in range(max(len(fitted) * 8, 8)):
        total = _estimate_message_tokens(fitted, model_id, provider) + max(
            tool_definition_tokens, 0
        )
        candidates = [
            index
            for index, message in enumerate(fitted)
            if (
                message.role == MessageRole.TOOL
                or (
                    message.role == MessageRole.ASSISTANT
                    and index not in (protected_indexes or set())
                )
            )
            and isinstance(message.content, str)
            and message.content
        ]
        candidates.sort(
            key=lambda index: count_tokens(
                fitted[index].content or "", model_id=model_id, provider=provider
            ),
            reverse=True,
        )
        reduced = False
        for index in candidates:
            message = fitted[index]
            current_tokens = count_tokens(
                message.content or "", model_id=model_id, provider=provider
            )
            if current_tokens <= 128:
                continue
            target_tokens = max(128, int(current_tokens * 0.65))
            content, content_changed = truncate_text_to_tokens(
                message.content or "",
                max_tokens=target_tokens,
                model_id=model_id,
                provider=provider,
                marker="\n...[message content truncated for context budget]...\n",
            )
            if content_changed and len(content) < len(message.content or ""):
                fitted[index] = message.model_copy(update={"content": content})
                changed = True
                reduced = True
                break
        if not reduced:
            break
    return fitted, changed


def _assess_pressure(
    tokens: int,
    *,
    trigger_budget: int,
    input_budget: int,
) -> Literal["normal", "warning", "auto_compact", "blocking", "over_budget"]:
    if tokens > input_budget:
        return "over_budget"
    if tokens > trigger_budget:
        return "auto_compact"
    return "normal"


def _render_summary_transcript(messages: Sequence[Message]) -> str:
    lines: list[str] = []
    for message in messages:
        role = (
            message.role.value if hasattr(message.role, "value") else str(message.role)
        )
        text = _stringify_content(message.content)
        if role == "tool":
            header = "TOOL result"
            tool_name = getattr(message, "tool_name", None)
            if tool_name:
                header += f" for {tool_name}"
            lines.append(f"{header}:\n{text or '(empty)'}")
            continue
        if message.tool_calls:
            calls = "; ".join(
                f"{tool_call.function.name}({tool_call.function.arguments})"
                for tool_call in message.tool_calls
                if tool_call.function
            )
            rendered = f"ASSISTANT tool calls: {calls}"
            if text:
                rendered += f"\n{text}"
            lines.append(rendered)
            continue
        lines.append(f"{role.upper()}:\n{text or '(empty)'}")
    return "\n\n".join(lines)


SUMMARY_SYSTEM_INSTRUCTION = (
    "You compress an agent conversation history into a durable summary so the "
    "conversation can continue seamlessly with the summary replacing the older "
    "history. Return ONLY the summary text. Include, in this order:\n"
    "1. Task: the user's overall goal and the latest request.\n"
    "2. Completed actions and results: what was already done, key outcomes, and "
    "exact identifiers, file paths, names, and numbers.\n"
    "3. Pending work: what remains, including the immediate next step.\n"
    "4. Constraints and decisions: rules, preferences, and choices that bind "
    "later work.\n"
    "Be concise and factual. Never invent information. Omit small talk and filler."
)


def _turn_user_starts(
    messages: Sequence[Message],
    *,
    current_user_index: int,
) -> list[int]:
    """Return the start indexes of conversation turns before the current one.

    Turns are delimited by user messages; an injected persistent-summary
    message never starts a turn. The system prompt (index 0) is excluded.
    """
    return [
        index
        for index in range(1, current_user_index)
        if messages[index].role == MessageRole.USER
        and not (
            isinstance(messages[index].content, str)
            and messages[index].content.startswith(CONTEXT_SUMMARY_PREFIX)
        )
    ]


async def _summarize_context(
    *,
    agent: Agent,
    conversation: Conversation,
    messages_to_summarize: Sequence[Message],
    model_id: str,
    tokenizer_model_id: str | None,
    provider: str | None,
    max_tokens: int,
    max_transcript_tokens: int,
) -> str | None:
    transcript = _render_summary_transcript(messages_to_summarize)
    transcript, _ = truncate_text_to_tokens(
        transcript,
        max_tokens=max(max_transcript_tokens, 1),
        model_id=tokenizer_model_id or model_id,
        provider=provider,
    )
    if not transcript.strip():
        return None
    response = None
    last_error: Exception | None = None
    for attempt in range(1, CONTEXT_SUMMARY_MAX_ATTEMPTS + 1):
        try:
            from app.llm import model_manager

            response = await asyncio.wait_for(
                model_manager.team_chat(
                    team_id=str(agent.team_id),
                    model_id=model_id,
                    messages=[
                        Message(
                            role=MessageRole.SYSTEM,
                            content=SUMMARY_SYSTEM_INSTRUCTION,
                        ),
                        Message(
                            role=MessageRole.USER,
                            content=(
                                "Conversation transcript:\n\n"
                                f"{transcript}\n\nWrite the summary now."
                            ),
                        ),
                    ],
                ),
                timeout=CONTEXT_SUMMARY_TIMEOUT_SECONDS,
            )
            if (response.content or "").strip():
                break
            response = None
            last_error = ValueError("summarizer returned an empty response")
            logger.warning(
                "Context summarization attempt %d/%d returned empty content "
                "for conversation %s",
                attempt,
                CONTEXT_SUMMARY_MAX_ATTEMPTS,
                conversation.id,
            )
        except Exception as exc:
            response = None
            last_error = exc
            logger.warning(
                "Context summarization attempt %d/%d failed for conversation %s: %s",
                attempt,
                CONTEXT_SUMMARY_MAX_ATTEMPTS,
                conversation.id,
                exc,
            )
        if attempt < CONTEXT_SUMMARY_MAX_ATTEMPTS:
            await asyncio.sleep(CONTEXT_SUMMARY_RETRY_DELAY_SECONDS)
    if response is None:
        logger.error(
            "Context summarization failed after %d attempts for conversation %s: %s",
            CONTEXT_SUMMARY_MAX_ATTEMPTS,
            conversation.id,
            last_error,
        )
        raise BusinessError(msg_key="context_summarization_failed")
    fitted, _ = truncate_text_to_tokens(
        (response.content or "").strip(),
        max_tokens=max_tokens,
        model_id=tokenizer_model_id or "",
        provider=provider,
    )
    return fitted or None


async def _persist_context_summary(
    *,
    conversation: Conversation,
    summary_text: str,
    current_user_message_id: UUID | None,
    exclude_message_ids: Sequence[UUID] | None,
    history_before_message_created_at: datetime | None,
    keep_recent_turns: int,
) -> None:
    """Persist the summary and advance its watermark past covered turns.

    Turns are delimited by user messages. The watermark stops before the
    most recent ``keep_recent_turns`` turns so they remain raw history in
    later requests until they eventually roll into a future summary.
    """
    try:
        excludes = [*(exclude_message_ids or [])]
        if current_user_message_id:
            excludes.append(current_user_message_id)
        history = await get_visible_conversation_messages(
            conversation.id,
            before_created_at=history_before_message_created_at,
            exclude_message_ids=excludes,
        )
        if not history:
            return
        blocks: list[list] = []
        for message in history:
            if not blocks or message.role == ConversationMessageRole.USER:
                blocks.append([message])
            else:
                blocks[-1].append(message)
        if len(blocks) <= max(keep_recent_turns, 0):
            return
        covered_blocks = (
            blocks[:-keep_recent_turns] if keep_recent_turns > 0 else blocks
        )
        await Conversation.filter(id=conversation.id).update(
            context_summary_text=summary_text,
            context_summary_watermark_id=covered_blocks[-1][-1].id,
        )
    except Exception:
        logger.warning(
            "Failed to persist context summary for conversation %s",
            conversation.id,
            exc_info=True,
        )


@dataclass(slots=True)
class ContextPlan:
    """First-phase result: the built context plus the summarization decision.

    ``build_context_plan`` never performs a model call, so streaming
    endpoints can emit a compression-start event before awaiting
    :meth:`finalize` (which may run the summarizer).
    """

    agent: Agent
    conversation: Conversation
    messages: list[Message]
    protected_indexes: set[int]
    token_budget: TokenBudget
    compression: CompressionMeta
    compression_config: dict[str, Any]
    compression_enabled: bool
    trigger_budget: int
    keep_start: int
    current_user_index: int
    summarized: list[Message]
    will_summarize: bool
    model_id: str
    tokenizer_model_id: str | None
    provider: str | None
    tool_definition_tokens: int
    keep_recent_turns: int
    keep_recent_steps: int
    history_override_is_none: bool
    current_user_message_id: UUID | None
    exclude_message_ids: Sequence[UUID] | None
    history_before_message_created_at: datetime | None
    persisted_summary_text: str | None

    async def finalize(self) -> PreparedModelContext:
        """Run the summarizer (if planned), bound in-loop growth, and return."""
        messages = self.messages
        protected_indexes = self.protected_indexes
        compression = self.compression
        token_budget = self.token_budget
        summary_max_tokens = int(
            self.compression_config.get(
                "summary_max_tokens", DEFAULT_SUMMARY_MAX_TOKENS
            )
        )
        summary_prompt_overhead = _estimate_message_tokens(
            [
                Message(
                    role=MessageRole.SYSTEM,
                    content=SUMMARY_SYSTEM_INSTRUCTION,
                ),
                Message(
                    role=MessageRole.USER,
                    content="Conversation transcript:\n\n\n\nWrite the summary now.",
                ),
            ],
            model_id=self.tokenizer_model_id,
            provider=self.provider,
        )
        max_transcript_tokens = max(
            min(
                int(token_budget.input_budget * 0.8),
                token_budget.input_budget
                - token_budget.safety_margin
                - summary_max_tokens
                - summary_prompt_overhead,
            ),
            1,
        )

        if self.will_summarize:
            summary_text = await _summarize_context(
                agent=self.agent,
                conversation=self.conversation,
                messages_to_summarize=self.summarized,
                model_id=self.model_id,
                tokenizer_model_id=self.tokenizer_model_id,
                provider=self.provider,
                max_tokens=summary_max_tokens,
                max_transcript_tokens=max_transcript_tokens,
            )
            if summary_text:
                keep_start = self.keep_start
                kept_messages = messages[keep_start:]
                messages = [
                    messages[0],
                    Message(
                        role=MessageRole.USER,
                        content=f"{CONTEXT_SUMMARY_PREFIX}\n\n{summary_text}",
                    ),
                    *kept_messages,
                ]
                protected_indexes = {0, 1} | {
                    2 + (index - keep_start)
                    for index in protected_indexes
                    if index >= keep_start
                }
                compression.stage = "macro"
                compression.summary_turns = len(self.summarized)
                compression.actions = list(
                    dict.fromkeys([*(compression.actions or []), "context_summary"])
                )
                if self.history_override_is_none:
                    retained_turns = sum(
                        1
                        for message in self.messages[
                            self.keep_start : self.current_user_index
                        ]
                        if message.role == MessageRole.USER
                        and not (
                            isinstance(message.content, str)
                            and message.content.startswith(CONTEXT_SUMMARY_PREFIX)
                        )
                    )
                    await _persist_context_summary(
                        conversation=self.conversation,
                        summary_text=summary_text,
                        current_user_message_id=self.current_user_message_id,
                        exclude_message_ids=self.exclude_message_ids,
                        history_before_message_created_at=(
                            self.history_before_message_created_at
                        ),
                        keep_recent_turns=retained_turns,
                    )

        if self.compression_enabled and compression.after_tokens > self.trigger_budget:
            current_user_index = next(
                (
                    index
                    for index in range(len(messages) - 1, -1, -1)
                    if messages[index].role == MessageRole.USER
                ),
                None,
            )
            if current_user_index is not None and current_user_index + 1 < len(
                messages
            ):
                region_start = current_user_index + 1
                region = messages[region_start:]
                selected_messages: list[Message] | None = None
                selected_protected: set[int] | None = None
                selected_tokens = 0
                selected_compacted = False
                max_recent_steps = max(self.keep_recent_steps, 0)
                for keep_steps in range(max_recent_steps, -1, -1):
                    compaction = compact_round_tool_steps(
                        region,
                        keep_recent_steps=keep_steps,
                    )
                    candidate_messages = (
                        [*messages[:region_start], *compaction.messages]
                        if compaction.changed
                        else messages
                    )
                    candidate_tokens = _estimate_message_tokens(
                        candidate_messages,
                        model_id=self.tokenizer_model_id,
                        provider=self.provider,
                    ) + max(self.tool_definition_tokens, 0)
                    if compaction.changed:
                        candidate_protected = {
                            index for index in protected_indexes if index < region_start
                        }
                        if compaction.summary_rel is not None:
                            candidate_protected.add(
                                region_start + compaction.summary_rel
                            )
                        if compaction.tail_start_rel is not None:
                            candidate_protected.update(
                                region_start + rel
                                for rel in range(
                                    compaction.tail_start_rel,
                                    len(compaction.messages),
                                )
                            )
                    else:
                        candidate_protected = protected_indexes
                    selected_messages = candidate_messages
                    selected_protected = candidate_protected
                    selected_tokens = candidate_tokens
                    selected_compacted = bool(compaction.changed)
                    if candidate_tokens <= token_budget.input_budget or keep_steps == 0:
                        break
                if selected_messages is not None:
                    messages = selected_messages
                    protected_indexes = selected_protected or set()
                    compression.after_tokens = selected_tokens
                    if selected_compacted:
                        if compression.stage == "none":
                            compression.stage = "macro"
                        compression.actions = list(
                            dict.fromkeys(
                                [*(compression.actions or []), "compact_round_steps"]
                            )
                        )

        if compression.after_tokens > token_budget.input_budget:
            bounded_messages, content_bounded = _fit_message_contents_to_budget(
                messages,
                input_budget=token_budget.input_budget,
                tool_definition_tokens=self.tool_definition_tokens,
                model_id=self.tokenizer_model_id,
                provider=self.provider,
                protected_indexes=protected_indexes,
            )
            if content_bounded:
                messages = bounded_messages
                compression.stage = "macro"
                compression.actions = list(
                    dict.fromkeys(
                        [*(compression.actions or []), "bound_message_content"]
                    )
                )
                compression.after_tokens = _estimate_message_tokens(
                    messages,
                    model_id=self.tokenizer_model_id,
                    provider=self.provider,
                ) + max(self.tool_definition_tokens, 0)
        compression.after_tokens = _estimate_message_tokens(
            messages, model_id=self.tokenizer_model_id, provider=self.provider
        ) + max(self.tool_definition_tokens, 0)
        compression.pressure_level = _assess_pressure(
            compression.after_tokens,
            trigger_budget=self.trigger_budget,
            input_budget=token_budget.input_budget,
        )
        compression.utilization_after = (
            compression.after_tokens / token_budget.context_limit
            if token_budget.context_limit
            else 0.0
        )

        if compression.after_tokens > token_budget.input_budget:
            # Emergency fallback: system + latest persisted summary + current
            # request, so the model never restarts from a blank slate.
            current_user_message = next(
                (
                    messages[index]
                    for index in range(len(messages) - 1, -1, -1)
                    if messages[index].role == MessageRole.USER
                ),
                None,
            )
            emergency_messages: list[Message] = []
            if messages and messages[0].role == MessageRole.SYSTEM:
                emergency_messages.append(messages[0])
            if self.persisted_summary_text:
                emergency_messages.append(
                    Message(
                        role=MessageRole.USER,
                        content=(
                            f"{CONTEXT_SUMMARY_PREFIX}\n\n{self.persisted_summary_text}"
                        ),
                    )
                )
            if current_user_message is not None:
                emergency_messages.append(current_user_message)
            emergency_tokens = _estimate_message_tokens(
                emergency_messages,
                model_id=self.tokenizer_model_id,
                provider=self.provider,
            ) + max(self.tool_definition_tokens, 0)
            if emergency_tokens > token_budget.input_budget:
                raise ContextLengthError(
                    message="Context length exceeded even with emergency fallback",
                    max_tokens=token_budget.input_budget,
                    actual_tokens=emergency_tokens,
                    provider=self.provider,
                    model=self.model_id,
                    details={
                        "retryable": False,
                        "reason": "system_and_user_exceed_input_budget",
                        "context_limit": token_budget.context_limit,
                        "output_reserve": token_budget.output_reserve,
                        "safety_margin": token_budget.safety_margin,
                    },
                )
            messages = emergency_messages
            protected_indexes = set(range(len(emergency_messages)))
            compression.stage = "macro"
            compression.after_tokens = emergency_tokens
            compression.pressure_level = "over_budget"
            compression.actions = list(
                dict.fromkeys([*(compression.actions or []), "emergency_fallback"])
            )
            compression.utilization_after = (
                emergency_tokens / token_budget.context_limit
                if token_budget.context_limit
                else 0.0
            )

        return PreparedModelContext(
            messages=messages,
            token_budget=token_budget,
            compression=compression,
            protected_indexes=protected_indexes,
        )


async def build_context_plan(
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
    tool_definition_tokens: int = 0,
) -> ContextPlan:
    """Build the full context and decide whether summarization is needed.

    Never performs a model call; call :meth:`ContextPlan.finalize` to run
    the planned summarization and bounding passes.
    """
    compression_config = get_context_compression_config(agent)
    compression_enabled = bool(compression_config.get("enabled", True))
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
    trigger_ratio = float(
        compression_config.get("summary_trigger_ratio", DEFAULT_SUMMARY_TRIGGER_RATIO)
    )
    trigger_budget = max(
        min(
            int(token_budget.context_limit * trigger_ratio),
            token_budget.input_budget,
        ),
        1,
    )

    file_content, file_content_bounded = _normalize_file_content_for_budget(
        file_content,
        max_tokens=min(
            int(
                compression_config.get(
                    "file_content_max_tokens", DEFAULT_FILE_CONTENT_MAX_TOKENS
                )
            ),
            max(token_budget.input_budget // 3, 128),
        ),
        model_id=tokenizer_model_id or model_id,
        provider=provider,
    )
    context_summary_text: str | None = None
    history_after_message_id: UUID | None = None
    if compression_enabled and (
        history_override is None
        or _history_override_is_active_delta(history_override, protected_round_id)
    ):
        stored_summary = getattr(conversation, "context_summary_text", None)
        watermark_id = getattr(conversation, "context_summary_watermark_id", None)
        if stored_summary and watermark_id:
            try:
                watermark_active = await is_message_on_active_branch(
                    conversation.id,
                    watermark_id,
                    before_created_at=history_before_message_created_at,
                )
            except Exception:
                logger.warning(
                    "Failed to validate context summary watermark for %s",
                    conversation.id,
                    exc_info=True,
                )
                watermark_active = False
            if watermark_active:
                context_summary_text = stored_summary
                history_after_message_id = watermark_id

    messages, protected_indexes = await _build_messages_with_file_content(
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
        context_summary_text=context_summary_text,
        history_after_message_id=history_after_message_id,
    )
    before_tokens = _estimate_message_tokens(
        messages, model_id=tokenizer_model_id, provider=provider
    ) + max(tool_definition_tokens, 0)
    compression = CompressionMeta(
        stage="none",
        before_tokens=before_tokens,
        after_tokens=before_tokens,
        input_budget=token_budget.input_budget,
        pressure_level=_assess_pressure(
            before_tokens,
            trigger_budget=trigger_budget,
            input_budget=token_budget.input_budget,
        ),
        trigger_ratio=trigger_ratio,
        utilization_before=(
            before_tokens / token_budget.context_limit
            if token_budget.context_limit
            else 0.0
        ),
        actions=["bound_file_content"] if file_content_bounded else [],
        context_limit=token_budget.context_limit,
        output_reserve=token_budget.output_reserve,
        safety_margin=token_budget.safety_margin,
    )

    keep_start = 1
    current_user_index = -1
    summarized: list[Message] = []
    keep_recent_turns = int(
        compression_config.get(
            "summary_keep_recent_turns", DEFAULT_SUMMARY_KEEP_RECENT_TURNS
        )
    )
    if compression_enabled and before_tokens > trigger_budget:
        current_user_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if messages[index].role == MessageRole.USER
            ),
            -1,
        )
        if current_user_index > 0:
            turn_starts = _turn_user_starts(
                messages, current_user_index=current_user_index
            )
            keep_start = (
                current_user_index
                if keep_recent_turns <= 0
                else (
                    turn_starts[-keep_recent_turns]
                    if len(turn_starts) > keep_recent_turns
                    else 1
                )
            )
            # 轮数只是优先级，token 预算是硬约束。单轮可能本身极长；
            # 若最后一轮也放不进保留区，就把整轮交给摘要，不保留超预算原文。
            keep_budget = int(
                token_budget.input_budget
                * float(
                    compression_config.get(
                        "summary_keep_budget_ratio",
                        DEFAULT_SUMMARY_KEEP_BUDGET_RATIO,
                    )
                )
            )
            while True:
                kept_tokens = _estimate_message_tokens(
                    messages[keep_start:current_user_index],
                    model_id=tokenizer_model_id,
                    provider=provider,
                )
                if kept_tokens <= keep_budget:
                    break
                next_start = next(
                    (index for index in turn_starts if index > keep_start), None
                )
                if next_start is None:
                    keep_start = current_user_index
                    break
                keep_start = next_start
            summarized = [
                message
                for index, message in enumerate(messages)
                if 0 < index < keep_start and index not in protected_indexes
            ]
        else:
            logger.warning(
                "Skipping context summarization for conversation %s: "
                "no separable user message found",
                conversation.id,
            )

    return ContextPlan(
        agent=agent,
        conversation=conversation,
        messages=messages,
        protected_indexes=protected_indexes,
        token_budget=token_budget,
        compression=compression,
        compression_config=compression_config,
        compression_enabled=compression_enabled,
        trigger_budget=trigger_budget,
        keep_start=keep_start,
        current_user_index=current_user_index,
        summarized=summarized,
        will_summarize=bool(summarized),
        model_id=model_id,
        tokenizer_model_id=tokenizer_model_id,
        provider=provider,
        tool_definition_tokens=tool_definition_tokens,
        keep_recent_turns=keep_recent_turns,
        keep_recent_steps=int(
            compression_config.get(
                "summary_keep_recent_steps", DEFAULT_SUMMARY_KEEP_RECENT_STEPS
            )
        ),
        history_override_is_none=history_override is None,
        current_user_message_id=current_user_message_id,
        exclude_message_ids=exclude_message_ids,
        history_before_message_created_at=history_before_message_created_at,
        persisted_summary_text=context_summary_text,
    )


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
    protected_round_id: UUID | str | None = None,
    tool_definition_tokens: int = 0,
) -> PreparedModelContext:
    """Build, summarize, and bound the model request context."""
    plan = await build_context_plan(
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
        protected_round_id=protected_round_id,
        tool_definition_tokens=tool_definition_tokens,
    )
    return await plan.finalize()
