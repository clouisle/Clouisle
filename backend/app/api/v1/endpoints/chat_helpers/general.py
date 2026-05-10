"""General helper functions for chat endpoints."""

from __future__ import annotations

import html
import json
import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.agent import Agent

logger = logging.getLogger(__name__)


def get_item_value(item: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object by key."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _safe_json_loads(value: str | None) -> dict[str, Any] | None:
    """Safely parse JSON string."""
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_user_input_request(content: str) -> tuple[dict | None, str]:
    """Parse user_input_request tags from content."""
    match = re.search(
        r"<user_input_request>(.*?)</user_input_request>", content, re.DOTALL
    )
    if not match:
        return None, content

    xml_block = match.group(0)
    xml_content = match.group(1)
    question_match = re.search(r"<question>(.*?)</question>", xml_content, re.DOTALL)
    options_match = re.search(r"<options>(.*?)</options>", xml_content, re.DOTALL)
    if not question_match or not options_match:
        return None, content

    question = html.unescape(question_match.group(1)).strip()
    if not question:
        return None, content

    options = []
    for option_match in re.finditer(
        r"<option>(.*?)</option>", options_match.group(1), re.DOTALL
    ):
        option_text = html.unescape(option_match.group(1)).strip()
        if option_text and len(option_text) <= 200:
            options.append(option_text)

    if len(options) < 2:
        return None, content

    remaining_content = content.replace(xml_block, "").strip()
    logger.info(
        "Successfully parsed user_input_request: question_length=%s, options_count=%s",
        len(question),
        len(options),
    )
    return {"question": question[:500], "options": options}, remaining_content


def get_tool_execution_payloads(result: Any) -> tuple[str, str]:
    """Build display and LLM payloads from tool execution result."""
    from app.llm.tools.builtin.media import ToolExecutionResult

    if isinstance(result, ToolExecutionResult):
        display_result = json.dumps(result.display_result, ensure_ascii=False)
        return display_result, result.llm_result
    if isinstance(result, dict):
        payload = json.dumps(result, ensure_ascii=False)
        return payload, payload
    stringified = str(result) if result is not None else ""
    return stringified, stringified


def should_retry_context_length(agent: "Agent") -> bool:
    """Whether reactive context-length retry is enabled for the agent."""
    from app.services.chat_context import get_context_compression_config

    return bool(
        get_context_compression_config(agent).get("reactive_retry_enabled", True)
    )


def get_compression_trigger(compression: Any) -> str:
    """Determine compression trigger type based on compression state."""
    pressure_level = getattr(compression, "pressure_level", None)
    if (
        pressure_level in {"blocking", "over_budget"}
        or getattr(compression, "stage", None) == "macro"
    ):
        return "blocking_threshold"
    return "proactive_threshold"
