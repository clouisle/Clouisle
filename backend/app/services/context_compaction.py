"""Request-local active tool-loop context compaction helpers.

This module deliberately operates on model-ready ``Message`` objects.  Historical
checkpoint persistence belongs to ``context_checkpoint.py``; these helpers only
bound and compact the currently executing tool loop before the next provider call.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.llm.token_counter import count_message_tokens, get_encoding_for_model
from app.llm.types import Message, MessageRole

DEFAULT_ACTIVE_TOOL_RESULT_MAX_TOKENS = 1_500
DEFAULT_ACTIVE_TOOL_TARGET_RATIO = 0.80
DEFAULT_ACTIVE_TOOL_SUMMARY_MAX_TOKENS = 512
DEFAULT_REASONING_MAX_TOKENS = 1_500
ACTIVE_TOOL_SUMMARY_PREFIX = "Active tool progress summary:"


@dataclass(slots=True)
class ActiveToolCompactionResult:
    messages: list[Message]
    protected_indexes: set[int]
    changed: bool = False
    tool_results_trimmed: bool = False
    summary_created: bool = False
    reasoning_trimmed: bool = False
    actions: list[str] | None = None


def _estimate_messages(
    messages: Sequence[Message], *, model_id: str, provider: str | None
) -> int:
    payload = [
        message.model_dump(exclude_none=True, mode="json") for message in messages
    ]
    return count_message_tokens(payload, model_id=model_id, provider=provider)


def _role_value(message: Message) -> str:
    role = getattr(message, "role", "")
    return role.value if hasattr(role, "value") else str(role)


def _token_count(text: str, *, model_id: str, provider: str | None) -> int:
    if not text:
        return 0
    try:
        encoding = get_encoding_for_model(model_id, provider)
        return len(encoding.encode(text))
    except Exception:
        return max(len(text) // 4, 1)


def truncate_text_to_tokens(
    text: str,
    *,
    max_tokens: int,
    model_id: str,
    provider: str | None,
    marker: str = "\n...[content truncated for context budget]...\n",
) -> tuple[str, bool]:
    """Keep the head and tail of text within a model-token limit."""
    if not text or max_tokens <= 0:
        return "", bool(text)

    try:
        encoding = get_encoding_for_model(model_id, provider)
        token_ids = encoding.encode(text)
        if len(token_ids) <= max_tokens:
            return text, False
        marker_ids = encoding.encode(marker)
        if max_tokens <= len(marker_ids) + 2:
            return encoding.decode(token_ids[:max_tokens]), True
        available = max_tokens - len(marker_ids)
        head_count = max(available * 2 // 3, 1)
        tail_count = max(available - head_count, 0)
        head = encoding.decode(token_ids[:head_count]).rstrip()
        tail = encoding.decode(token_ids[-tail_count:]).lstrip() if tail_count else ""
        return f"{head}{marker}{tail}", True
    except Exception:
        # Conservative fallback for an unavailable tokenizer.
        max_chars = max(max_tokens * 2, 1)
        if len(text) <= max_chars:
            return text, False
        head_chars = max(max_chars * 2 // 3, 1)
        tail_chars = max(max_chars - head_chars, 0)
        tail = text[-tail_chars:] if tail_chars else ""
        return f"{text[:head_chars]}{marker}{tail}", True


def _has_tool_calls(message: Message) -> bool:
    return _role_value(message) == MessageRole.ASSISTANT.value and bool(
        getattr(message, "tool_calls", None)
    )


def _group_active_iterations(
    messages: Sequence[Message], start_index: int
) -> list[list[tuple[int, Message]]]:
    groups: list[list[tuple[int, Message]]] = []
    current: list[tuple[int, Message]] = []
    for index in range(start_index, len(messages)):
        message = messages[index]
        if _has_tool_calls(message) and current:
            groups.append(current)
            current = []
        current.append((index, message))
    if current:
        groups.append(current)
    return groups


def _group_is_complete(group: Sequence[tuple[int, Message]]) -> bool:
    if not group or not _has_tool_calls(group[0][1]):
        return False
    assistant = group[0][1]
    call_ids = {
        str(getattr(tool_call, "id", ""))
        for tool_call in (assistant.tool_calls or [])
        if getattr(tool_call, "id", None)
    }
    result_ids = {
        str(message.tool_call_id)
        for _, message in group[1:]
        if _role_value(message) == MessageRole.TOOL.value and message.tool_call_id
    }
    return bool(call_ids) and call_ids.issubset(result_ids)


def _group_tokens(
    group: Sequence[tuple[int, Message]], *, model_id: str, provider: str | None
) -> int:
    return _estimate_messages(
        [message for _, message in group], model_id=model_id, provider=provider
    )


def _summary_for_groups(
    groups: Sequence[Sequence[tuple[int, Message]]],
    *,
    model_id: str,
    provider: str | None,
    max_tokens: int,
) -> Message:
    lines = [ACTIVE_TOOL_SUMMARY_PREFIX]
    for index, group in enumerate(groups, start=1):
        tool_names: list[str] = []
        result_snippets: list[str] = []
        for _, message in group:
            if _has_tool_calls(message):
                tool_names.extend(
                    str(getattr(getattr(call, "function", None), "name", "tool"))
                    for call in (message.tool_calls or [])
                )
            elif _role_value(message) == MessageRole.TOOL.value:
                content = message.content if isinstance(message.content, str) else ""
                normalized = " ".join(content.split())
                if normalized:
                    result_snippets.append(normalized[:360])
        name_text = ", ".join(dict.fromkeys(tool_names)) or "tool"
        line = f"- Iteration {index}: {name_text}"
        if result_snippets:
            line += f"; findings: {' | '.join(result_snippets)}"
        lines.append(line)

    text = "\n".join(lines)
    text, _ = truncate_text_to_tokens(
        text,
        max_tokens=max_tokens,
        model_id=model_id,
        provider=provider,
        marker="\n...[older tool progress omitted]...\n",
    )
    return Message(role=MessageRole.ASSISTANT, content=text)


def _bound_tool_results(
    messages: Sequence[Message],
    *,
    start_index: int,
    max_tokens: int,
    model_id: str,
    provider: str | None,
) -> tuple[list[Message], bool]:
    bounded: list[Message] = []
    changed = False
    for index, message in enumerate(messages):
        copied = message.model_copy(deep=True)
        if (
            index >= start_index
            and _role_value(copied) == MessageRole.TOOL.value
            and isinstance(copied.content, str)
        ):
            copied.content, did_change = truncate_text_to_tokens(
                copied.content,
                max_tokens=max_tokens,
                model_id=model_id,
                provider=provider,
            )
            changed = changed or did_change
        bounded.append(copied)
    return bounded, changed


def normalize_message_content(
    messages: Sequence[Message],
    *,
    protected_indexes: set[int] | None,
    model_id: str,
    provider: str | None,
    max_tool_result_tokens: int = DEFAULT_ACTIVE_TOOL_RESULT_MAX_TOKENS,
    max_reasoning_tokens: int = DEFAULT_REASONING_MAX_TOKENS,
) -> ActiveToolCompactionResult:
    """Bound replay-only tool and reasoning payloads without changing protocol fields."""
    normalized: list[Message] = []
    tool_results_trimmed = False
    reasoning_trimmed = False
    for message in messages:
        copied = message.model_copy(deep=True)
        if _role_value(copied) == MessageRole.TOOL.value and isinstance(
            copied.content, str
        ):
            copied.content, did_change = truncate_text_to_tokens(
                copied.content,
                max_tokens=max_tool_result_tokens,
                model_id=model_id,
                provider=provider,
            )
            tool_results_trimmed = tool_results_trimmed or did_change
        if _role_value(copied) == MessageRole.ASSISTANT.value and isinstance(
            copied.reasoning_content, str
        ):
            copied.reasoning_content, did_change = truncate_text_to_tokens(
                copied.reasoning_content,
                max_tokens=max_reasoning_tokens,
                model_id=model_id,
                provider=provider,
                marker="\n...[reasoning omitted for context budget]...\n",
            )
            reasoning_trimmed = reasoning_trimmed or did_change
        normalized.append(copied)

    actions: list[str] = []
    if tool_results_trimmed:
        actions.append("bound_tool_results")
    if reasoning_trimmed:
        actions.append("bound_reasoning")
    return ActiveToolCompactionResult(
        messages=normalized,
        protected_indexes=set(protected_indexes or ()),
        changed=tool_results_trimmed or reasoning_trimmed,
        tool_results_trimmed=tool_results_trimmed,
        reasoning_trimmed=reasoning_trimmed,
        actions=actions,
    )


def compact_active_tool_messages(
    messages: Sequence[Message],
    *,
    protected_indexes: set[int] | None,
    model_id: str,
    provider: str | None,
    input_budget: int,
    target_ratio: float = DEFAULT_ACTIVE_TOOL_TARGET_RATIO,
    max_tool_result_tokens: int = DEFAULT_ACTIVE_TOOL_RESULT_MAX_TOKENS,
    summary_max_tokens: int = DEFAULT_ACTIVE_TOOL_SUMMARY_MAX_TOKENS,
) -> ActiveToolCompactionResult:
    """Bound and compact completed tool iterations after the latest user turn."""
    protected_indexes = protected_indexes or set()
    last_user_index = max(
        (
            index
            for index, message in enumerate(messages)
            if _role_value(message) == MessageRole.USER.value
        ),
        default=-1,
    )
    if last_user_index < 0:
        return ActiveToolCompactionResult(
            messages=[message.model_copy(deep=True) for message in messages],
            protected_indexes=set(protected_indexes),
        )

    bounded, tool_results_trimmed = _bound_tool_results(
        messages,
        start_index=last_user_index + 1,
        max_tokens=max_tool_result_tokens,
        model_id=model_id,
        provider=provider,
    )
    target_budget = min(
        input_budget,
        max(int(input_budget * max(target_ratio, 0.5)), 1),
    )
    before_tokens = _estimate_messages(bounded, model_id=model_id, provider=provider)
    groups = _group_active_iterations(bounded, last_user_index + 1)
    complete_groups = [group for group in groups if _group_is_complete(group)]

    if before_tokens <= target_budget or len(complete_groups) <= 1:
        return ActiveToolCompactionResult(
            messages=bounded,
            protected_indexes=set(protected_indexes),
            changed=tool_results_trimmed,
            tool_results_trimmed=tool_results_trimmed,
            actions=["bound_tool_results"] if tool_results_trimmed else [],
        )

    prefix = bounded[: last_user_index + 1]
    prefix_tokens = _estimate_messages(prefix, model_id=model_id, provider=provider)
    kept_groups: list[list[tuple[int, Message]]] = []
    summarized_groups: list[list[tuple[int, Message]]] = []
    running_tokens = prefix_tokens

    for group in reversed(groups):
        group_token_count = _group_tokens(group, model_id=model_id, provider=provider)
        # An unfinished call/result sequence must remain raw; summarizing it
        # would either orphan a call or hide the result needed by the provider.
        if not _group_is_complete(group):
            kept_groups.insert(0, group)
            running_tokens += group_token_count
        elif not kept_groups or running_tokens + group_token_count <= target_budget:
            kept_groups.insert(0, group)
            running_tokens += group_token_count
        else:
            summarized_groups.insert(0, group)

    if not summarized_groups:
        return ActiveToolCompactionResult(
            messages=bounded,
            protected_indexes=set(protected_indexes),
            changed=tool_results_trimmed,
            tool_results_trimmed=tool_results_trimmed,
            actions=["bound_tool_results"] if tool_results_trimmed else [],
        )

    summary_budget = max(
        min(summary_max_tokens, max((target_budget - prefix_tokens) // 4, 64)),
        64,
    )
    summary = _summary_for_groups(
        summarized_groups,
        model_id=model_id,
        provider=provider,
        max_tokens=summary_budget,
    )
    compacted = [message.model_copy(deep=True) for message in prefix]
    compacted.append(summary)
    summary_index = len(compacted) - 1
    new_protected_indexes = {
        index for index in protected_indexes if index < len(prefix)
    }
    new_protected_indexes.add(summary_index)

    for group in kept_groups:
        for original_index, message in group:
            new_index = len(compacted)
            compacted.append(message.model_copy(deep=True))
            if original_index in protected_indexes:
                new_protected_indexes.add(new_index)

    actions = ["active_tool_summary"]
    if tool_results_trimmed:
        actions.insert(0, "bound_tool_results")
    return ActiveToolCompactionResult(
        messages=compacted,
        protected_indexes=new_protected_indexes,
        changed=True,
        tool_results_trimmed=tool_results_trimmed,
        summary_created=True,
        actions=actions,
    )


def fit_tool_results_to_budget(
    messages: Sequence[Message],
    *,
    protected_indexes: set[int] | None,
    model_id: str,
    provider: str | None,
    input_budget: int,
) -> ActiveToolCompactionResult:
    """Last deterministic fit pass; shrink tool content without breaking pairing."""
    protected_indexes = protected_indexes or set()
    fitted = [message.model_copy(deep=True) for message in messages]
    total = _estimate_messages(fitted, model_id=model_id, provider=provider)
    if total <= input_budget:
        return ActiveToolCompactionResult(
            messages=fitted,
            protected_indexes=set(protected_indexes),
        )

    tool_indexes = [
        index
        for index, message in enumerate(fitted)
        if _role_value(message) == MessageRole.TOOL.value
        and isinstance(message.content, str)
    ]
    if not tool_indexes:
        return ActiveToolCompactionResult(
            messages=fitted,
            protected_indexes=set(protected_indexes),
        )

    fixed = [message.model_copy(deep=True) for message in fitted]
    for index in tool_indexes:
        fixed[index].content = ""
    fixed_tokens = _estimate_messages(fixed, model_id=model_id, provider=provider)
    available = max(input_budget - fixed_tokens, 0)
    changed = False

    for offset, index in enumerate(reversed(tool_indexes)):
        remaining = len(tool_indexes) - offset
        allocation = available // remaining if remaining else 0
        content = (
            fitted[index].content if isinstance(fitted[index].content, str) else ""
        )
        bounded, did_change = truncate_text_to_tokens(
            content,
            max_tokens=allocation,
            model_id=model_id,
            provider=provider,
            marker="\n...[tool result omitted for context budget]...\n",
        )
        fitted[index].content = bounded
        changed = changed or did_change or bounded != content
        used = _token_count(bounded, model_id=model_id, provider=provider)
        available = max(available - used, 0)

    return ActiveToolCompactionResult(
        messages=fitted,
        protected_indexes=set(protected_indexes),
        changed=changed,
        tool_results_trimmed=changed,
        actions=["fit_tool_results_to_budget"] if changed else [],
    )
