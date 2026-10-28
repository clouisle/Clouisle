"""Separate complete tool data from concise model-readable output.

Display payloads stay structured and complete for the UI, citations and durable
replay. Only explicitly known tools are rendered as text (see
``tool_output_renderers``); everything else keeps its exact JSON contract.
Presentation never guesses which business fields of an unknown/custom tool are
expendable, and it never truncates content: producers bound their payloads and
publish cursors/log locations for continuation.
"""

from __future__ import annotations

import json
from typing import Any

#: Envelope written next to a display payload when a tool supplied a model
#: representation that the deterministic renderer cannot reproduce. It keeps
#: live and replayed model context identical without changing the display data.
PERSISTED_RESULT_KIND = "tool.result.persisted"
PERSISTED_RESULT_VERSION = 1

#: Tools whose payload schemas the renderers may format. Anything else is
#: returned verbatim so configured/custom/MCP/database/Skill payloads keep
#: their fields, types and original JSON formatting.
KNOWN_OUTPUT_TOOLS = frozenset(
    {
        "read_asset",
        "view_asset",
        "search_asset",
        "list_assets",
        "inspect_asset",
        "materialize_asset",
        "fetch_webpage",
        "markitdown",
        "web_search",
        "knowledge_search",
        "search_knowledge_base",
        "rss_feed_reader",
        "calculate",
        "unit_convert",
        "get_current_time",
        "format_datetime",
        "create_memory_entity",
        "create_memory_relation",
        "update_memory_entity",
        "search_memory",
        "get_memory_subgraph",
        "bash",
        "read",
        "edit",
        "write",
        "artifact",
    }
)

#: Read/search segments advertise how their line text was bounded.
_CLIPPED_MARKER = " [line clipped]"
_CONTINUATION_MARKER = " [line continues]"


class ToolExecutionResult(dict):
    """Full UI payload plus an explicit model representation."""

    def __init__(self, *, display_result: dict[str, Any], llm_result: str) -> None:
        super().__init__(display_result=display_result, llm_result=llm_result)

    @property
    def display_result(self) -> dict[str, Any]:
        return self["display_result"]

    @property
    def llm_result(self) -> str:
        return self["llm_result"]


def json_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def format_numbered_lines(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for segment in segments:
        suffix = ""
        if segment.get("continuation"):
            suffix = _CONTINUATION_MARKER
        elif segment.get("truncated"):
            suffix = _CLIPPED_MARKER
        lines.append(f"{segment['line']}│{segment.get('text', '')}{suffix}")
    return "\n".join(lines)


def format_continuation(payload: dict[str, Any]) -> str:
    cursor = payload.get("next_cursor")
    if cursor:
        # Cursors are opaque and version bound: never rewrite their characters.
        return f"Not finished; cursor={cursor}"
    if payload.get("eof") is True or payload.get("has_more") is False:
        return "End of results."
    return "More results available." if payload.get("has_more") else ""


def render_tool_output(tool_name: str | None, payload: Any) -> str:
    """Render one known payload for the model.

    Imported lazily so the rendering schemas can use the shared formatting
    helpers above without an import cycle.
    """
    from app.utils.tool_output_renderers import render_tool_output as render

    return render(tool_name, payload)


def persisted_tool_output_parts(content: str) -> tuple[Any, str] | None:
    """Return ``(display, llm_result)`` from a persisted envelope, else ``None``."""
    if not content or not content.lstrip().startswith("{"):
        return None
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != PERSISTED_RESULT_KIND:
        return None
    if payload.get("version") != PERSISTED_RESULT_VERSION:
        return None
    llm_result = payload.get("llm_result")
    if not isinstance(llm_result, str):
        return None
    return payload.get("display"), llm_result


def unwrap_persisted_display(content: str) -> str:
    """Return the display JSON for API clients, leaving other content untouched."""
    parts = persisted_tool_output_parts(content)
    if parts is None:
        return content
    display, _ = parts
    return json.dumps(display, ensure_ascii=False)


def persistable_model_result(
    tool_name: str | None,
    display_result: str,
    llm_result: str,
    *,
    explicit: bool,
) -> str | None:
    """Build a storage envelope only for an explicit, non-reproducible result.

    ``explicit`` is true only for :class:`ToolExecutionResult`: plain tool output
    has no separate model representation, and known deterministic renderers
    persist just the display JSON. Unknown/plain payloads therefore stay
    byte-identical.
    """
    if not explicit:
        return None
    try:
        payload = json.loads(display_result)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("kind") == PERSISTED_RESULT_KIND:
        return None
    if render_tool_output(tool_name, payload) == llm_result:
        return None
    return json.dumps(
        {
            "kind": PERSISTED_RESULT_KIND,
            "version": PERSISTED_RESULT_VERSION,
            "display": payload,
            "llm_result": llm_result,
        },
        ensure_ascii=False,
    )


def get_tool_execution_payloads(
    result: Any, tool_name: str | None = None
) -> tuple[str, str]:
    """Return the display JSON and the model-facing text for one tool result."""
    from app.core.i18n import t
    from app.llm.tools.interaction import ToolInteractionRequest

    if isinstance(result, ToolInteractionRequest):
        # A pause request is never a tool result: stringifying it would feed the
        # model a fake success. Callers must park or fail closed explicitly.
        display = json.dumps(
            {
                "error": t("tool_approval_unavailable"),
                "tool_name": result.tool_name,
                "success": False,
            },
            ensure_ascii=False,
        )
        return display, display

    # ``ToolExecutionResult`` and the native ``AssetViewResult`` marker both
    # expose these properties. Duck typing keeps the native marker protocol
    # out of this low-level module without changing its behaviour.
    display_result = getattr(result, "display_result", None)
    llm_result = getattr(result, "llm_result", None)
    if isinstance(display_result, dict) and isinstance(llm_result, str):
        return json.dumps(display_result, ensure_ascii=False), llm_result
    if isinstance(result, dict):
        display = json.dumps(result, ensure_ascii=False)
        if tool_name not in KNOWN_OUTPUT_TOOLS:
            # Unknown tools keep their original JSON contract and formatting.
            return display, display
        return display, render_tool_output(tool_name, result)
    text = str(result) if result is not None else ""
    if tool_name not in KNOWN_OUTPUT_TOOLS:
        return text, text
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return text, text
    return text, render_tool_output(tool_name, payload)
