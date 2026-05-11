"""SSE event builders for chat streaming."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.agent import Agent

from app.api.v1.endpoints.chat_helpers.general import _safe_json_loads

logger = logging.getLogger(__name__)

MEDIA_TOOL_KINDS = {"media.image", "media.video"}


def infer_tool_result_is_error(display_result: str) -> bool:
    """判断工具结果是否为错误"""
    payload = _safe_json_loads(display_result)
    if not payload:
        return False

    if payload.get("success") is False:
        return True

    error = payload.get("error")
    return isinstance(error, str) and bool(error.strip())


def build_tool_result_sse_event(
    *,
    tool_call_id: str,
    tool_name: str,
    tool_display_name: str,
    display_result: str,
) -> str:
    """构建工具结果 SSE 事件"""
    from app.schemas.agent import SSEEventType

    payload = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_display_name": tool_display_name,
        "result": display_result,
        "is_error": infer_tool_result_is_error(display_result),
    }
    return (
        f"event: {SSEEventType.TOOL_RESULT}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def build_media_result_sse_event(display_result: str) -> str | None:
    """构建媒体结果 SSE 事件"""
    from app.schemas.agent import SSEEventType

    media_payload = extract_media_display_payload(display_result)
    if not media_payload:
        return None
    return (
        f"event: {SSEEventType.MEDIA_RESULT}\n"
        f"data: {json.dumps(media_payload, ensure_ascii=False)}\n\n"
    )


def extract_media_display_payload(display_result: str) -> dict[str, Any] | None:
    """从显示结果中提取媒体负载"""
    payload = _safe_json_loads(display_result)
    if not payload:
        return None
    if payload.get("kind") not in MEDIA_TOOL_KINDS:
        return None
    return payload


def build_compression_events(
    *,
    agent: "Agent",
    compression: Any,
    trigger: str,
    retry_index: int = 0,
    stage_override: str | None = None,
) -> tuple[str | None, str | None]:
    """Build SSE compression start and end event payloads when compression should be surfaced.

    Returns:
        Tuple of (start_event, end_event). Either or both may be None if events should not be emitted.
    """
    from app.schemas.agent import SSEEventType
    from app.services.chat_context import get_context_compression_config

    config = get_context_compression_config(agent)
    if not config.get("emit_sse_events", True):
        return None, None

    stage = stage_override or compression.stage
    if stage == "none":
        return None, None

    note_parts: list[str] = []
    if trigger == "context_length_error" or stage == "reactive_retry":
        note_parts.append("Retried with more aggressive context compaction")
    elif trigger == "blocking_threshold":
        note_parts.append(
            "Applied blocking-level compaction before the next model call"
        )
    else:
        note_parts.append(
            "Applied proactive context compaction before the next model call"
        )
    if compression.summary_turns:
        note_parts.append(f"summarized {compression.summary_turns} older turns")
    if compression.reasoning_trimmed:
        note_parts.append("trimmed historical reasoning")
    if compression.tool_results_trimmed:
        note_parts.append("compacted older tool results")
    if compression.file_content_trimmed:
        note_parts.append("trimmed file content")

    # Start event - minimal info
    start_payload = {
        "stage": stage,
        "trigger": trigger,
    }
    start_event = (
        f"event: {SSEEventType.COMPRESSION_START}\n"
        f"data: {json.dumps(start_payload, ensure_ascii=False)}\n\n"
    )

    # End event - full compression details
    end_payload = {
        "stage": stage,
        "trigger": trigger,
        "pressure_level": getattr(compression, "pressure_level", None),
        "before_tokens": compression.before_tokens,
        "after_tokens": compression.after_tokens,
        "input_budget": compression.input_budget,
        "trigger_ratio": getattr(compression, "trigger_ratio", None),
        "warning_ratio": getattr(compression, "warning_ratio", None),
        "blocking_ratio": getattr(compression, "blocking_ratio", None),
        "trigger_budget": getattr(compression, "trigger_budget", None),
        "hard_budget": getattr(compression, "hard_budget", compression.input_budget),
        "utilization_before": getattr(compression, "utilization_before", None),
        "utilization_after": getattr(compression, "utilization_after", None),
        "policy_used": getattr(compression, "policy_used", None),
        "actions": getattr(compression, "actions", None),
        "retained_recent_turns": getattr(compression, "retained_recent_turns", None),
        "retained_tool_turns": getattr(compression, "retained_tool_turns", None),
        "compacted_blocks": getattr(compression, "compacted_blocks", None),
        "summary_turns": compression.summary_turns,
        "reasoning_dropped": compression.reasoning_trimmed,
        "tool_results_trimmed": compression.tool_results_trimmed,
        "file_content_trimmed": compression.file_content_trimmed,
        "retry_index": retry_index,
        "note": "; ".join(note_parts),
    }
    end_event = (
        f"event: {SSEEventType.COMPRESSION_END}\n"
        f"data: {json.dumps(end_payload, ensure_ascii=False)}\n\n"
    )

    return start_event, end_event
