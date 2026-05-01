"""General helper functions for chat endpoints."""

from __future__ import annotations

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
    """Parse user_input_request XML from content."""
    from xml.etree import ElementTree as ET

    pattern = r"<user_input_request>(.*?)</user_input_request>"
    match = re.search(pattern, content, re.DOTALL)
    if not match:
        return None, content

    xml_block = match.group(0)
    xml_content = match.group(1)

    try:
        logger.info("Parsing user_input_request XML: %s", xml_content[:200])
        root = ET.fromstring(f"<root>{xml_content}</root>")
        question_elem = root.find("question")
        if question_elem is None or not question_elem.text:
            return None, content
        question = question_elem.text.strip()

        options_elem = root.find("options")
        if options_elem is None:
            return None, content

        options = []
        for opt in options_elem.findall("option"):
            if opt.text:
                option_text = opt.text.strip()
                if option_text and len(option_text) <= 200:
                    options.append(option_text)

        if len(options) < 2:
            return None, content

        remaining_content = content.replace(xml_block, "").strip()
        logger.info(
            "Successfully parsed user_input_request: question=%s, options_count=%s",
            question[:50],
            len(options),
        )
        return {"question": question[:500], "options": options}, remaining_content

    except ET.ParseError as e:
        logger.error("Failed to parse user_input_request XML: %s", e)
        return None, content


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
