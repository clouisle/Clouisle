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
DEFAULT_SUMMARY_RESERVE_RATIO = 0.15
DEFAULT_RECENT_TAIL_TOKENS = 20000
# Minimum tokens kept verbatim after the summary when the window is small.
MIN_RECENT_TAIL_TOKENS = 0
CONTEXT_SUMMARY_TIMEOUT_SECONDS = 180.0
CONTEXT_SUMMARY_MAX_ATTEMPTS = 3
CONTEXT_SUMMARY_RETRY_DELAY_SECONDS = 2.0
CONTEXT_SUMMARY_PREFIX = (
    "Earlier conversation summary (older history was replaced by this summary):"
)
DEFAULT_CONTEXT_COMPRESSION_CONFIG = {
    "enabled": True,
    "summary_max_tokens": DEFAULT_SUMMARY_MAX_TOKENS,
    "emit_sse_events": True,
}


@dataclass(slots=True)
class TokenBudget:
    context_limit: int
    output_reserve: int
    safety_margin: int
    input_budget: int


@dataclass(slots=True)
class PreparedModelContext:
    messages: list[Message]
    token_budget: TokenBudget
    compression: CompressionMeta
    protected_indexes: set[int] = field(default_factory=set)


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
    summary_source_tokens: int = 0
    summary_result_tokens: int = 0
    summary_saved_tokens: int = 0


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
    meta: list[dict[str, Any]] | None = None,
    round_id: UUID | str | None = None,
    round_role: str | None = None,
    is_round_canonical: bool | None = None,
    tool_call_id: str | None = None,
    tool_calls: Any = None,
    source_role: str | None = None,
    source_message_id: Any = None,
    **extra: Any,
) -> None:
    """Append a flattened message.

    When ``meta`` is provided it records round/protocol metadata (parallel to
    ``messages``) that turn-aware compaction uses to select safe cut points.
    """
    messages.append(message)
    index = len(messages) - 1
    if protect:
        protected_indexes.add(index)
    if meta is not None:
        entry: dict[str, Any] = {
            "index": index,
            "role": message.role.value
            if hasattr(message.role, "value")
            else str(message.role),
            "round_id": round_id,
            "round_role": round_role,
            "is_round_canonical": is_round_canonical,
            "tool_call_id": tool_call_id,
            "tool_calls": tool_calls,
            "source_role": source_role,
            "source_message_id": source_message_id,
        }
        entry.update(extra)
        meta.append(entry)


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
    raw_config = getattr(agent, "context_compression_config", None) or {}
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
) -> tuple[list[Message], set[int], list[dict[str, Any]]]:
    """Build the model-ready message list plus parallel round metadata.

    The third return value is a ``meta`` list aligned with ``messages``; each
    entry records the source round/protocol fields (round_id, round_role,
    canonical flag, tool_call_id, source message id) needed by turn-aware
    compaction to select cut points at complete round boundaries.
    """
    active_round_delta = _history_override_is_active_delta(
        history_override, protected_round_id
    )
    messages: list[Message] = []
    protected_indexes: set[int] = set()
    meta: list[dict[str, Any]] = []
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
        meta=meta,
    )
    if context_summary_text:
        _append_message(
            messages,
            protected_indexes,
            Message(
                role=MessageRole.USER,
                content=f"{CONTEXT_SUMMARY_PREFIX}\n\n{context_summary_text}",
            ),
            meta=meta,
            source_role="summary",
        )

    current_content = _append_file_content_to_user_content(
        _build_current_user_content(
            user_message=user_message,
            current_images=current_images,
            model_supports_vision=model_supports_vision,
        ),
        file_content,
    )

    def _override_meta(hist_msg: Any, *, tool_calls: Any = None) -> dict[str, Any]:
        return {
            "round_id": _get_override_value(hist_msg, "round_id"),
            "round_role": _get_override_value(hist_msg, "round_role"),
            "is_round_canonical": _get_override_value(hist_msg, "is_round_canonical"),
            "tool_call_id": _get_override_value(hist_msg, "tool_call_id")
            or (_get_override_value(hist_msg, "id") if False else None),
            "tool_calls": tool_calls,
            "source_role": _normalize_override_role(
                _get_override_value(hist_msg, "role")
            ),
            "source_message_id": None,
        }

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
                    meta=meta,
                    **{
                        "round_id": _get_override_value(hist_msg, "round_id"),
                        "round_role": "user_input",
                        "is_round_canonical": True,
                        "source_role": "user",
                        "source_message_id": None,
                    },
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
                    meta=meta,
                    **{
                        "round_id": _get_override_value(hist_msg, "round_id"),
                        "round_role": _get_override_value(hist_msg, "round_role"),
                        "is_round_canonical": _get_override_value(
                            hist_msg, "is_round_canonical"
                        ),
                        "source_role": "user",
                        "source_message_id": None,
                    },
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
                    meta=meta,
                    **{
                        "round_id": _get_override_value(hist_msg, "round_id"),
                        "round_role": _get_override_value(hist_msg, "round_role"),
                        "is_round_canonical": _get_override_value(
                            hist_msg, "is_round_canonical"
                        ),
                        "tool_calls": tool_calls,
                        "source_role": "assistant",
                        "source_message_id": None,
                    },
                )
            elif role == "tool":
                tool_call_id = _get_override_value(hist_msg, "tool_call_id")
                if tool_call_id and tool_call_id in valid_tool_call_ids:
                    _append_message(
                        messages,
                        protected_indexes,
                        Message(
                            role=MessageRole.TOOL,
                            name=_get_override_value(hist_msg, "tool_name"),
                            content=summarize_tool_result_for_llm(
                                _get_override_value(hist_msg, "tool_name"),
                                content or "",
                            ),
                            tool_call_id=tool_call_id,
                        ),
                        protect=protect,
                        meta=meta,
                        **{
                            "round_id": _get_override_value(hist_msg, "round_id"),
                            "round_role": _get_override_value(hist_msg, "round_role"),
                            "is_round_canonical": _get_override_value(
                                hist_msg, "is_round_canonical"
                            ),
                            "tool_call_id": tool_call_id,
                            "source_role": "tool",
                            "source_message_id": None,
                        },
                    )
        if not current_user_inserted and not has_current_round_user_in_override:
            _append_message(
                messages,
                protected_indexes,
                Message(role=MessageRole.USER, content=current_content),
                protect=protected_round_id is not None,
                meta=meta,
                round_role="user_input",
                is_round_canonical=True,
                source_role="user",
            )
        return messages, protected_indexes, meta

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
                        meta=meta,
                        round_id=msg.round_id,
                        round_role=(
                            msg.round_role.value if msg.round_role else "user_input"
                        ),
                        is_round_canonical=True,
                        source_role="user",
                        source_message_id=msg.id,
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
                meta=meta,
                round_id=msg.round_id,
                round_role=(msg.round_role.value if msg.round_role else "user_input"),
                is_round_canonical=True,
                source_role="user",
                source_message_id=msg.id,
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
                meta=meta,
                round_id=msg.round_id,
                round_role=(msg.round_role.value if msg.round_role else None),
                is_round_canonical=msg.is_round_canonical,
                tool_calls=tool_calls,
                source_role="assistant",
                source_message_id=msg.id,
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
                    name=msg.tool_name,
                    content=summarize_tool_result_for_llm(msg.tool_name, msg.content),
                    tool_call_id=msg.tool_call_id,
                ),
                protect=protect,
                meta=meta,
                round_id=msg.round_id,
                round_role=(msg.round_role.value if msg.round_role else "tool_result"),
                is_round_canonical=msg.is_round_canonical,
                tool_call_id=msg.tool_call_id,
                source_role="tool",
                source_message_id=msg.id,
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
            meta=meta,
            round_role="user_input",
            is_round_canonical=True,
            source_role="user",
        )

    if not include_current_user_message:
        _append_message(
            messages,
            protected_indexes,
            Message(role=MessageRole.USER, content=current_content),
            protect=protected_round_id is not None,
            meta=meta,
            round_role="user_input",
            is_round_canonical=True,
            source_role="user",
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
                    meta=meta,
                    **{
                        "round_id": _get_override_value(hist_msg, "round_id"),
                        "round_role": _get_override_value(hist_msg, "round_role"),
                        "is_round_canonical": _get_override_value(
                            hist_msg, "is_round_canonical"
                        ),
                        "tool_calls": tool_calls,
                        "source_role": "assistant",
                        "source_message_id": None,
                    },
                )
            elif role == "tool":
                tool_call_id = _get_override_value(hist_msg, "tool_call_id")
                if tool_call_id and tool_call_id in valid_tool_call_ids:
                    _append_message(
                        messages,
                        protected_indexes,
                        Message(
                            role=MessageRole.TOOL,
                            name=_get_override_value(hist_msg, "tool_name"),
                            content=summarize_tool_result_for_llm(
                                _get_override_value(hist_msg, "tool_name"),
                                content,
                            ),
                            tool_call_id=tool_call_id,
                        ),
                        protect=protect,
                        meta=meta,
                        **{
                            "round_id": _get_override_value(hist_msg, "round_id"),
                            "round_role": _get_override_value(hist_msg, "round_role"),
                            "is_round_canonical": _get_override_value(
                                hist_msg, "is_round_canonical"
                            ),
                            "tool_call_id": tool_call_id,
                            "source_role": "tool",
                            "source_message_id": None,
                        },
                    )

    return messages, protected_indexes, meta


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
    messages, _, _meta = await _build_messages_with_file_content(
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
            tool_name = getattr(message, "tool_name", None) or getattr(
                message, "name", None
            )
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


def _is_context_summary_message(message: Message) -> bool:
    return isinstance(message.content, str) and message.content.startswith(
        CONTEXT_SUMMARY_PREFIX
    )


SUMMARY_SYSTEM_INSTRUCTION = (
    "You compress an agent conversation history into a durable summary so the "
    "conversation can continue seamlessly with the summary replacing the older "
    "history. Always write the summary in concise English, regardless of the "
    "transcript language or the user's locale. Return ONLY the summary text. "
    "Include, in this order:\n"
    "1. Task: the user's overall goal and the latest request.\n"
    "2. Completed actions and results: what was already done, key outcomes, and "
    "exact identifiers, file paths, names, and numbers.\n"
    "3. Pending work: what remains, including the immediate next step.\n"
    "4. Constraints and decisions: rules, preferences, and choices that bind "
    "later work.\n"
    "Be concise and factual. Never invent information. Omit small talk and filler."
)


def _select_summary_cut_index(
    messages: Sequence[Message],
    meta: Sequence[dict[str, Any]] | None,
    current_user_index: int,
    tail_tokens: int,
    *,
    tokenizer_model_id: str | None,
    provider: str | None,
) -> int:
    """Pick the first index of the recent verbatim tail.

    History (indices ``[1, current_user_index)``) is grouped into consecutive
    round blocks via the parallel ``meta`` sidecar. Blocks are kept verbatim
    from the newest backward while they fit the tail budget; the first block
    that does not fit (and everything older) is eligible for summarization.
    Incomplete rounds (assistant tool calls without matching tool results) are
    never cut; the newest block is always retained even when oversized so a
    recent single turn is preserved intact. Returns the index where the
    retained tail starts; ``current_user_index`` means nothing old is kept raw
    (and nothing old is summarized by the caller).
    """
    if current_user_index <= 1:
        return current_user_index
    metas = list(meta or [])
    # consecutive round blocks over history only: [1, current_user_index)
    blocks: list[tuple[int, int]] = []
    block_start = 1
    for idx in range(2, current_user_index + 1):
        prev_rid = metas[idx - 1].get("round_id") if idx - 1 < len(metas) else None
        cur_rid = metas[idx].get("round_id") if idx < len(metas) else None
        if prev_rid is not None and cur_rid != prev_rid:
            blocks.append((block_start, idx))
            block_start = idx
    if block_start < current_user_index:
        blocks.append((block_start, current_user_index))
    if not blocks:
        return current_user_index

    retained_start = current_user_index
    budget = tail_tokens
    for start, end in reversed(blocks):
        block_tokens = _estimate_message_tokens(
            messages[start:end],
            model_id=tokenizer_model_id,
            provider=provider,
        )
        if not _round_is_complete(metas[start:end]):
            # active/incomplete protocol: never cut into it
            retained_start = start
            break
        if budget >= block_tokens:
            retained_start = start
            budget -= block_tokens
            continue
        # The newest block that does not fit is summarized (with everything
        # older); an oversized single completed turn is prefix-compacted by
        # the summarizer transcript bound rather than preserved whole.
        break
    return retained_start


def _round_is_complete(block_meta: Sequence[dict[str, Any]]) -> bool:
    """A retained round block is complete when every assistant tool call has a
    matching tool result inside the block, or the assistant made no calls."""
    assistant_call_ids: set[str] = set()
    tool_result_ids: set[str] = set()
    for entry in block_meta:
        role = entry.get("role") or entry.get("source_role")
        if role == "assistant":
            calls = entry.get("tool_calls") or ()
            for call in calls:
                call_id = (
                    call.get("id")
                    if isinstance(call, dict)
                    else getattr(call, "id", None)
                )
                if call_id:
                    assistant_call_ids.add(str(call_id))
        elif role == "tool":
            call_id = entry.get("tool_call_id")
            if call_id:
                tool_result_ids.add(str(call_id))
    if not assistant_call_ids:
        return True
    return bool(tool_result_ids) and assistant_call_ids.issubset(tool_result_ids)


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
    previous_summary: str | None = None,
) -> str | None:
    transcript = _render_summary_transcript(messages_to_summarize)
    transcript, _ = truncate_text_to_tokens(
        transcript,
        max_tokens=max(max_transcript_tokens, 1),
        model_id=tokenizer_model_id or model_id,
        provider=provider,
    )
    if not transcript.strip() and not previous_summary:
        return None
    if previous_summary:
        transcript = (
            "Previous summary:\n"
            f"{previous_summary}\n\n"
            "New conversation transcript:\n"
            f"{transcript}"
        )
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
                "Context summarization attempt %d/%d failed for conversation %s "
                "(%s: %r)",
                attempt,
                CONTEXT_SUMMARY_MAX_ATTEMPTS,
                conversation.id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
        if attempt < CONTEXT_SUMMARY_MAX_ATTEMPTS:
            await asyncio.sleep(CONTEXT_SUMMARY_RETRY_DELAY_SECONDS)
    if response is None:
        logger.error(
            "Context summarization failed after %d attempts for conversation %s "
            "(%s: %r)",
            CONTEXT_SUMMARY_MAX_ATTEMPTS,
            conversation.id,
            type(last_error).__name__ if last_error else "unknown",
            last_error,
            exc_info=(
                type(last_error),
                last_error,
                last_error.__traceback__,
            )
            if last_error
            else None,
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
    watermark_message_id: UUID | None = None,
) -> None:
    """Persist a summary and advance the watermark to the last message it
    covers.

    With turn-aware compaction the summary covers only the newly summarized
    old turns; the recent verbatim tail stays raw, so the watermark must point
    at the last summarized message (not the last visible history message).
    """
    try:
        if watermark_message_id is not None:
            await Conversation.filter(id=conversation.id).update(
                context_summary_text=summary_text,
                context_summary_watermark_id=watermark_message_id,
            )
            conversation.context_summary_text = summary_text
            conversation.context_summary_watermark_id = watermark_message_id
            return
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
        await Conversation.filter(id=conversation.id).update(
            context_summary_text=summary_text,
            context_summary_watermark_id=history[-1].id,
        )
        # The next tool iteration reuses this loaded Conversation instance.
        # Keep it in sync with the persisted watermark so that the same
        # request does not rebuild and summarize the covered history again.
        conversation.context_summary_text = summary_text
        conversation.context_summary_watermark_id = history[-1].id
    except Exception:
        logger.warning(
            "Failed to persist context summary for conversation %s",
            conversation.id,
            exc_info=True,
        )


@dataclass(slots=True)
class ContextPlan:
    """Built context plus the single preflight summary decision."""

    agent: Agent
    conversation: Conversation
    messages: list[Message]
    protected_indexes: set[int]
    token_budget: TokenBudget
    compression: CompressionMeta
    compression_config: dict[str, Any]
    compression_enabled: bool
    trigger_budget: int
    current_user_index: int
    tail_start_index: int
    summarized: list[Message]
    previous_summary_text: str | None
    meta: list[dict[str, Any]]
    will_summarize: bool
    model_id: str
    tokenizer_model_id: str | None
    provider: str | None
    tool_definition_tokens: int
    history_override_is_none: bool
    current_user_message_id: UUID | None
    exclude_message_ids: Sequence[UUID] | None
    history_before_message_created_at: datetime | None

    @property
    def _new_watermark_id(self) -> UUID | None:
        """Last newly covered source message id (advances the watermark past
        only the summarized old turns; the retained tail stays raw)."""
        if not self.summarized:
            return None
        for entry in reversed(self.meta[: self.tail_start_index]):
            source_id = entry.get("source_message_id")
            if source_id is not None:
                return source_id
        return None

    async def finalize(self) -> PreparedModelContext:
        """Summarize old history when needed and return the provider context."""
        messages = self.messages
        protected_indexes = self.protected_indexes
        compression = self.compression
        token_budget = self.token_budget
        preserved_suffix = (
            self.messages[self.tail_start_index :]
            if self.tail_start_index > 0
            else self.messages[self.current_user_index :]
        )
        protected_payload_tokens = _estimate_message_tokens(
            [self.messages[0], *preserved_suffix],
            model_id=self.tokenizer_model_id,
            provider=self.provider,
        ) + max(self.tool_definition_tokens, 0)
        if protected_payload_tokens > token_budget.input_budget:
            # The protected content alone (system + retained tail + current
            # turn + tool definitions) cannot fit; no summary can help.
            raise ContextLengthError(
                message="Context length exceeded: protected payload over budget",
                max_tokens=token_budget.input_budget,
                actual_tokens=protected_payload_tokens,
                provider=self.provider,
                model=self.model_id,
                details={
                    "retryable": False,
                    "reason": "protected_payload_over_budget",
                    "context_limit": token_budget.context_limit,
                },
            )
        fixed_messages = [self.messages[0], *preserved_suffix]
        fixed_context_tokens = _estimate_message_tokens(
            fixed_messages,
            model_id=self.tokenizer_model_id,
            provider=self.provider,
        )
        configured_summary_tokens = max(
            int(
                self.compression_config.get(
                    "summary_max_tokens", DEFAULT_SUMMARY_MAX_TOKENS
                )
            ),
            1,
        )
        summary_message_overhead = _estimate_message_tokens(
            [
                Message(
                    role=MessageRole.USER,
                    content=f"{CONTEXT_SUMMARY_PREFIX}\n\n",
                )
            ],
            model_id=self.tokenizer_model_id,
            provider=self.provider,
        )
        summary_max_tokens = min(
            configured_summary_tokens,
            max(
                token_budget.input_budget
                - self.tool_definition_tokens
                - fixed_context_tokens
                - summary_message_overhead,
                1,
            ),
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
            token_budget.input_budget - summary_prompt_overhead - summary_max_tokens,
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
                previous_summary=self.previous_summary_text,
            )
            if summary_text:
                summary_message = Message(
                    role=MessageRole.USER,
                    content=f"{CONTEXT_SUMMARY_PREFIX}\n\n{summary_text}",
                )
                source_tokens = _estimate_message_tokens(
                    self.summarized,
                    model_id=self.tokenizer_model_id,
                    provider=self.provider,
                )
                result_tokens = _estimate_message_tokens(
                    [summary_message],
                    model_id=self.tokenizer_model_id,
                    provider=self.provider,
                )
                compression.summary_source_tokens = source_tokens
                compression.summary_result_tokens = result_tokens
                compression.summary_saved_tokens = max(source_tokens - result_tokens, 0)
                messages = [self.messages[0], summary_message, *preserved_suffix]
                protected_indexes = set(range(len(messages)))
                compression.stage = "macro"
                compression.summary_turns = sum(
                    1
                    for message in self.summarized
                    if message.role == MessageRole.USER
                    and not _is_context_summary_message(message)
                )
                compression.actions = list(
                    dict.fromkeys([*(compression.actions or []), "context_summary"])
                )
                if self.history_override_is_none:
                    await _persist_context_summary(
                        conversation=self.conversation,
                        summary_text=summary_text,
                        current_user_message_id=self.current_user_message_id,
                        exclude_message_ids=self.exclude_message_ids,
                        history_before_message_created_at=(
                            self.history_before_message_created_at
                        ),
                        watermark_message_id=self._new_watermark_id,
                    )

        compression.after_tokens = _estimate_message_tokens(
            messages,
            model_id=self.tokenizer_model_id,
            provider=self.provider,
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
            raise ContextLengthError(
                message="Context length exceeded after context summary",
                max_tokens=token_budget.input_budget,
                actual_tokens=compression.after_tokens,
                provider=self.provider,
                model=self.model_id,
                details={
                    "retryable": False,
                    "reason": "context_summary_did_not_fit",
                    "context_limit": token_budget.context_limit,
                },
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
    """Build the request and decide whether the full history needs a summary."""
    compression_config = get_context_compression_config(agent)
    compression_enabled = bool(compression_config.get("enabled", True))
    token_budget = _build_token_budget(
        context_limit=model_context_limit,
        model_max_output_tokens=model_max_output_tokens,
        output_token_reserve=DEFAULT_OUTPUT_TOKEN_RESERVE,
        safety_margin_tokens=DEFAULT_SAFETY_MARGIN_TOKENS,
    )
    trigger_ratio = DEFAULT_SUMMARY_TRIGGER_RATIO
    # Reserve-aware trigger: compress before the payload reaches
    # context - max(15% of context, model output reserve) so a summary + recent
    # tail + current turn can always fit above the false-90% boundary.
    effective_reserve = max(
        int(token_budget.context_limit * DEFAULT_SUMMARY_RESERVE_RATIO),
        token_budget.output_reserve,
    )
    trigger_budget = min(
        max(token_budget.context_limit - effective_reserve, 1),
        token_budget.input_budget,
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

    messages, protected_indexes, _meta = await _build_messages_with_file_content(
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
        actions=[],
        context_limit=token_budget.context_limit,
        output_reserve=token_budget.output_reserve,
        safety_margin=token_budget.safety_margin,
    )

    current_user_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].role == MessageRole.USER
            and not _is_context_summary_message(messages[index])
        ),
        -1,
    )

    # Recent verbatim tail: retain a bounded raw-history target,
    # clamped so system + summary + current/active turn + output reserve fit.
    system_tokens = _estimate_message_tokens(
        messages[:1], model_id=tokenizer_model_id, provider=provider
    )
    current_tokens = _estimate_message_tokens(
        messages[current_user_index:],
        model_id=tokenizer_model_id,
        provider=provider,
    )
    configured_summary_tokens = max(
        int(compression_config.get("summary_max_tokens", DEFAULT_SUMMARY_MAX_TOKENS)),
        1,
    )
    summary_overhead = _estimate_message_tokens(
        [
            Message(
                role=MessageRole.USER,
                content=f"{CONTEXT_SUMMARY_PREFIX}\n\n",
            )
        ],
        model_id=tokenizer_model_id,
        provider=provider,
    )
    tail_tokens = min(
        DEFAULT_RECENT_TAIL_TOKENS,
        max(
            token_budget.input_budget
            - system_tokens
            - current_tokens
            - max(tool_definition_tokens, 0)
            - configured_summary_tokens
            - summary_overhead,
            MIN_RECENT_TAIL_TOKENS,
        ),
    )

    previous_summary_text: str | None = context_summary_text
    _meta = list(_meta or [])
    # Summarizable range starts right after the previous summary (index 1).
    summarize_from = 2 if previous_summary_text else 1
    if not _meta:
        # No round metadata (e.g. mocked builds): fall back to summarizing all
        # old turns between the previous summary and the current user.
        tail_start_index = current_user_index
        summarized = (
            [
                message
                for index, message in enumerate(messages)
                if summarize_from <= index < current_user_index
                and not _is_context_summary_message(message)
            ]
            if compression_enabled
            and before_tokens > trigger_budget
            and current_user_index > summarize_from
            else []
        )
    else:
        tail_start_index = _select_summary_cut_index(
            messages,
            _meta,
            current_user_index,
            tail_tokens,
            tokenizer_model_id=tokenizer_model_id,
            provider=provider,
        )
        summarized = (
            [
                message
                for index, message in enumerate(messages)
                if summarize_from <= index < tail_start_index
                and not _is_context_summary_message(message)
            ]
            if compression_enabled
            and before_tokens > trigger_budget
            and tail_start_index > summarize_from
            else []
        )

    return ContextPlan(
        agent=agent,
        conversation=conversation,
        messages=messages,
        protected_indexes=protected_indexes,
        meta=_meta,
        token_budget=token_budget,
        compression=compression,
        compression_config=compression_config,
        compression_enabled=compression_enabled,
        trigger_budget=trigger_budget,
        current_user_index=current_user_index,
        tail_start_index=tail_start_index,
        summarized=summarized,
        previous_summary_text=previous_summary_text,
        will_summarize=bool(summarized),
        model_id=model_id,
        tokenizer_model_id=tokenizer_model_id,
        provider=provider,
        tool_definition_tokens=tool_definition_tokens,
        history_override_is_none=history_override is None,
        current_user_message_id=current_user_message_id,
        exclude_message_ids=exclude_message_ids,
        history_before_message_created_at=history_before_message_created_at,
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
