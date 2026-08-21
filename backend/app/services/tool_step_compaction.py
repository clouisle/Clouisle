"""Deterministic compaction for in-round agent tool steps.

Long tool loops accumulate hundreds of assistant tool-call / tool-result
messages inside a single conversation round. This module bounds that growth
without any model call: completed tool-call/result pairs older than a
verbatim tail are replaced by ONE rule-generated progress-summary assistant
message. Compaction is recomputed from the raw step list on every call, so
repeated application is idempotent and never compounds loss.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.llm.types import Message, MessageRole

TOOL_PROGRESS_SUMMARY_PREFIX = "[工具进度摘要]"

# 单条进度行与单条结果的字符截断上限
_MAX_ARGS_CHARS = 80
_MAX_RESULT_CHARS = 120
# 进度摘要最大行数；超出时最旧的行折叠为一行计数说明
_MAX_SUMMARY_LINES = 80


@dataclass(slots=True)
class RoundStepCompactionResult:
    """Outcome of a deterministic round-step compaction pass."""

    messages: list[Message]
    changed: bool
    compacted_messages: int = 0
    # 压缩摘要消息在新列表中的相对下标（未压缩时为 None）
    summary_rel: int | None = None
    # 原样保留尾部在新列表中的起始相对下标（未压缩时为 None）
    tail_start_rel: int | None = None


def _role_value(message: Message) -> str:
    role = message.role
    return role.value if hasattr(role, "value") else str(role)


def _truncate(value: str, max_chars: int) -> str:
    value = " ".join((value or "").split())
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def _tool_call_ids(message: Message) -> set[str]:
    ids: set[str] = set()
    for call in message.tool_calls or []:
        if call.id:
            ids.add(call.id)
    return ids


def _is_progress_summary(message: Message) -> bool:
    return (
        _role_value(message) == MessageRole.ASSISTANT.value
        and isinstance(message.content, str)
        and message.content.startswith(TOOL_PROGRESS_SUMMARY_PREFIX)
    )


def _split_groups(steps: Sequence[Message]) -> list[list[tuple[int, Message]]]:
    """Group steps: an assistant message opens a group; tool results attach
    to the current group. Any other message opens its own group."""
    groups: list[list[tuple[int, Message]]] = []
    for rel, message in enumerate(steps):
        if _role_value(message) == MessageRole.TOOL.value and groups:
            groups[-1].append((rel, message))
            continue
        groups.append([(rel, message)])
    return groups


def _group_is_complete(group: Sequence[tuple[int, Message]]) -> bool:
    if not group:
        return False
    head = group[0][1]
    head_role = _role_value(head)
    if head_role != MessageRole.ASSISTANT.value:
        return False
    if not head.tool_calls:
        return True
    pending = _tool_call_ids(head)
    for _, message in group[1:]:
        pending.discard(message.tool_call_id)
    return not pending


def _summarize_group(
    group: Sequence[tuple[int, Message]],
    counter: list[int],
    lines: list[str],
) -> None:
    for _, message in group:
        if _role_value(message) != MessageRole.ASSISTANT.value:
            continue
        text = message.content if isinstance(message.content, str) else ""
        if not message.tool_calls:
            counter[0] += 1
            lines.append(
                f"{counter[0]}. [assistant] {_truncate(text, _MAX_RESULT_CHARS)}"
            )
            continue
        results: dict[str, str] = {}
        for _, member in group:
            if _role_value(member) == MessageRole.TOOL.value and member.tool_call_id:
                results[member.tool_call_id] = _truncate(
                    member.content or "", _MAX_RESULT_CHARS
                )
        for call in message.tool_calls:
            counter[0] += 1
            args = call.function.arguments if call.function else ""
            name = call.function.name if call.function else "unknown"
            result_text = results.get(call.id or "", "(无结果)")
            lines.append(
                f"{counter[0]}. {name}({_truncate(args or '', _MAX_ARGS_CHARS)})"
                f" → {result_text}"
            )


def compact_round_tool_steps(
    steps: Sequence[Message],
    *,
    keep_recent_steps: int,
) -> RoundStepCompactionResult:
    """Compact older completed tool interactions inside one round.

    The last ``keep_recent_steps`` messages are always kept verbatim; an
    incomplete trailing tool-call group and existing progress summaries are
    never touched. Everything older collapses into a single progress-summary
    assistant message.
    """
    keep_recent_steps = max(keep_recent_steps, 0)
    groups = _split_groups(steps)
    tail_cut = max(len(steps) - keep_recent_steps, 0)

    def _kept(group: list[tuple[int, Message]]) -> bool:
        is_last = group is groups[-1]
        return (
            group[-1][0] >= tail_cut
            or is_last
            or not _group_is_complete(group)
            or _is_progress_summary(group[0][1])
        )

    compacted_groups: list[list[tuple[int, Message]]] = []
    first_compact_rel: int | None = None
    tail_start_rel: int | None = None
    for group in groups:
        if _kept(group):
            if tail_start_rel is None:
                tail_start_rel = group[0][0]
            continue
        if first_compact_rel is None:
            first_compact_rel = group[0][0]
        compacted_groups.append(group)

    if first_compact_rel is None:
        return RoundStepCompactionResult(messages=list(steps), changed=False)

    counter = [0]
    lines: list[str] = []
    for group in compacted_groups:
        _summarize_group(group, counter, lines)

    if len(lines) > _MAX_SUMMARY_LINES:
        omitted = len(lines) - _MAX_SUMMARY_LINES + 1
        lines = [f"1. …另有 {omitted} 次更早的工具交互（略）"] + lines[
            -(_MAX_SUMMARY_LINES - 1) :
        ]

    summary_text = (
        f"{TOOL_PROGRESS_SUMMARY_PREFIX} 本轮前 {counter[0]} 条消息已完成，"
        "按序摘要如下：\n" + "\n".join(lines)
    )

    result: list[Message] = [
        message for rel, message in enumerate(steps) if rel < first_compact_rel
    ]
    summary_rel = len(result)
    result.append(Message(role=MessageRole.ASSISTANT, content=summary_text))
    result.extend(
        message
        for rel, message in enumerate(steps)
        if rel >= (tail_start_rel or len(steps))
    )
    compacted_count = sum(len(group) for group in compacted_groups)
    return RoundStepCompactionResult(
        messages=result,
        changed=True,
        compacted_messages=compacted_count,
        summary_rel=summary_rel,
        tail_start_rel=summary_rel + 1,
    )
