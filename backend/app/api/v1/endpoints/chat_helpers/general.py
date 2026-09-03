"""General helper functions for chat endpoints."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from app.models.agent import Message

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


def _has_image_source(image: Any) -> bool:
    source = image.get("image", image) if isinstance(image, dict) else image
    return bool(
        get_item_value(source, "url")
        or get_item_value(source, "base64")
        or get_item_value(source, "file_path")
    )


def append_generated_images(
    images: list[Any],
    inventory: list[dict[str, str]],
    display_result: Any,
) -> None:
    payload = (
        display_result
        if isinstance(display_result, dict)
        else _safe_json_loads(display_result)
    )
    if (
        not payload
        or payload.get("kind") != "media.image"
        or not payload.get("success")
    ):
        return

    prompt = str(payload.get("prompt") or "").strip().replace("\n", " ")[:120]
    for generated in payload.get("images") or []:
        image = generated.get("image") if isinstance(generated, dict) else None
        if not isinstance(image, dict) or not _has_image_source(image):
            continue
        images.append(image)
        inventory.append({"origin": "generated", "context": prompt})


def collect_conversation_images(
    messages: Sequence["Message"],
    *,
    current_message_id: UUID | None = None,
    current_images: Sequence[Any] | None = None,
) -> tuple[list[Any], list[dict[str, str]]]:
    images: list[Any] = []
    inventory: list[dict[str, str]] = []

    for message in messages:
        role = get_item_value(message, "role")
        role_value = role.value if hasattr(role, "value") else str(role)
        if role_value == "user":
            message_images = get_item_value(message, "images") or []
            context = str(get_item_value(message, "content", ""))
            for image in message_images:
                if _has_image_source(image):
                    images.append(image)
                    inventory.append(
                        {
                            "origin": "uploaded",
                            "context": context.strip().replace("\n", " ")[:120],
                        }
                    )
        elif role_value == "tool":
            append_generated_images(
                images,
                inventory,
                get_item_value(message, "content", ""),
            )

    message_ids = {get_item_value(message, "id") for message in messages}
    if current_images and (
        current_message_id is None or current_message_id not in message_ids
    ):
        for image in current_images:
            if _has_image_source(image):
                images.append(image)
                inventory.append({"origin": "uploaded", "context": "current message"})

    return images, inventory


def build_conversation_image_inventory(
    inventory: Sequence[dict[str, str]],
) -> str | None:
    if not inventory:
        return None

    lines = [
        "<available_conversation_images>",
        "Use these 1-based indexes with reference_image_indexes or start_image_index:",
    ]
    for index, item in enumerate(inventory, start=1):
        context = item.get("context") or "no context"
        lines.append(f"{index}. {item['origin']}: {context}")
    lines.append("</available_conversation_images>")
    return "\n".join(lines)


def append_conversation_image_inventory(
    user_message: str,
    inventory: Sequence[dict[str, str]],
) -> str:
    image_inventory = build_conversation_image_inventory(inventory)
    if not image_inventory:
        return user_message
    return f"{user_message}\n\n{image_inventory}" if user_message else image_inventory


def get_compression_trigger(compression: Any) -> str:
    """Return the stable SSE trigger for model-generated context summaries."""
    return "proactive_threshold"
