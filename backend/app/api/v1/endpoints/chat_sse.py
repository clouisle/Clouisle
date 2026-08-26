"""SSE event builders for chat streaming."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.agent import Agent

from app.api.v1.endpoints.chat_helpers.general import _safe_json_loads
from app.core.i18n import t

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


def build_tool_call_sse_event(
    *,
    tool_call_id: str,
    tool_name: str,
    tool_display_name: str,
    arguments: dict[str, Any],
) -> str:
    """构建工具调用 SSE 事件"""
    from app.schemas.agent import SSEEventType

    payload = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "tool_display_name": tool_display_name,
        "arguments": arguments,
    }
    return (
        f"event: {SSEEventType.TOOL_CALL}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


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


def build_compression_start_event(
    *,
    agent: "Agent",
    stage: str,
    trigger: str,
) -> str | None:
    """Build the compression-start SSE event when emission is enabled."""
    from app.schemas.agent import SSEEventType
    from app.services.chat_context import get_context_compression_config

    if not get_context_compression_config(agent).get("emit_sse_events", True):
        return None

    return (
        f"event: {SSEEventType.COMPRESSION_START}\n"
        f"data: {json.dumps({'stage': stage, 'trigger': trigger}, ensure_ascii=False)}\n\n"
    )


def build_compression_events(
    *,
    agent: "Agent",
    compression: Any,
    trigger: str,
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

    stage = compression.stage
    if stage == "none":
        return None, None

    note_parts = [t("chat_context_summary_applied")]

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
        "pressure_level": compression.pressure_level,
        "before_tokens": compression.before_tokens,
        "after_tokens": compression.after_tokens,
        "input_budget": compression.input_budget,
        "trigger_ratio": compression.trigger_ratio,
        "utilization_before": compression.utilization_before,
        "utilization_after": compression.utilization_after,
        "policy_used": compression.policy_used,
        "actions": compression.actions,
        "summary_turns": compression.summary_turns,
        "summary_source_tokens": getattr(compression, "summary_source_tokens", 0),
        "summary_result_tokens": getattr(compression, "summary_result_tokens", 0),
        "summary_saved_tokens": getattr(compression, "summary_saved_tokens", 0),
        "context_limit": compression.context_limit,
        "output_reserve": compression.output_reserve,
        "safety_margin": compression.safety_margin,
        "note": "; ".join(note_parts),
    }
    end_event = (
        f"event: {SSEEventType.COMPRESSION_END}\n"
        f"data: {json.dumps(end_payload, ensure_ascii=False)}\n\n"
    )

    return start_event, end_event
