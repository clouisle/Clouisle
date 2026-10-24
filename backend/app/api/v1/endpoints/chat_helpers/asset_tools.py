"""Shared Asset tool schemas for every Agent dispatch path.

Both the conversation chat tool registry (``endpoints/chat.py``) and the
Workflow Agent runtime (``services/agent.py``) build their attachment tool
sets from here, so the model sees one contract: list/view/inspect plus the
bounded ``read_asset`` / ``search_asset`` document reader.
"""

from __future__ import annotations

from app.core.i18n import t

ASSET_TOOL_NAMES = (
    "list_assets",
    "view_asset",
    "inspect_asset",
    "read_asset",
    "search_asset",
    "materialize_asset",
)

_ASSET_TOOL_DISPLAY_NAME_KEYS = {
    "list_assets": "asset_tool_list",
    "view_asset": "asset_tool_view",
    "inspect_asset": "asset_tool_inspect",
    "read_asset": "asset_tool_read",
    "search_asset": "asset_tool_search",
    "materialize_asset": "asset_tool_materialize",
}


def asset_tool_display_names(user_locale: str | None = None) -> dict[str, str]:
    """Localized display names for every registered Asset tool."""
    return {
        name: t(key, lang=user_locale)
        for name, key in _ASSET_TOOL_DISPLAY_NAME_KEYS.items()
    }


def asset_tool_names_for_agent(agent: object) -> tuple[str, ...]:
    """Keep persisted web documents readable even without file uploads."""
    if getattr(agent, "enable_attachments", False):
        return ASSET_TOOL_NAMES
    configured = getattr(agent, "tools_config", None) or []
    if any(
        isinstance(config, dict)
        and config.get("type") == "builtin"
        and config.get("name") in {"fetch_webpage", "markitdown"}
        for config in configured
    ):
        return ("list_assets", "inspect_asset", "read_asset", "search_asset")
    return ()


def describe_attachment_references(items: list[object] | None) -> list[dict]:
    """Bounded attachment metadata; never inlines extracted document text."""
    documents: list[dict] = []
    for item in items or []:
        if isinstance(item, dict):
            ref = item.get("asset_ref") or item.get("ref")
            filename = item.get("filename") or item.get("name")
            mime_type = item.get("mime_type") or item.get("content_type")
            url = item.get("url")
            size = item.get("size")
        elif isinstance(item, str):
            ref = None
            filename = None
            mime_type = None
            url = item
            size = None
        else:
            ref = getattr(item, "asset_ref", None) or getattr(item, "ref", None)
            filename = getattr(item, "filename", None) or getattr(item, "name", None)
            mime_type = getattr(item, "mime_type", None) or getattr(
                item, "content_type", None
            )
            url = getattr(item, "url", None)
            size = getattr(item, "size", None)
        if not filename and isinstance(url, str):
            filename = url.rsplit("/", 1)[-1].split("?", 1)[0]
        document: dict = {}
        if isinstance(ref, str) and ref:
            document["ref"] = ref
        if isinstance(filename, str) and filename:
            document["filename"] = filename
        if isinstance(mime_type, str) and mime_type:
            document["mime_type"] = mime_type
        if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
            document["size"] = size
        if not document:
            continue
        document["reading"] = (
            "Use list_assets to discover a ref, then read_asset for bounded lines "
            "and search_asset to locate text; continue until eof."
        )
        documents.append(document)
    return documents


def build_asset_tools() -> list[dict]:
    """OpenAI-format function schemas for the Asset tool family."""
    ref_property = {
        "type": "string",
        "pattern": "^[0-9a-f]{4}$",
        "description": t("asset_tool_ref_description"),
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "list_assets",
                "description": (
                    "Discover assets in the current scope before viewing them. "
                    "Search filenames with query, filter kind, and follow "
                    "next_cursor until has_more is false. Returned refs work "
                    "with view_asset and other asset tools. Keep query and kind "
                    "unchanged when paging."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "maxLength": 200,
                            "description": (
                                "Case-insensitive filename substring; omit to list all."
                            ),
                        },
                        "kind": {
                            "type": "string",
                            "enum": ["image", "audio", "video", "file"],
                        },
                        "cursor": {
                            "type": "string",
                            "pattern": "^[0-9a-f]{4}$",
                            "description": "next_cursor from the previous page.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                            "default": 10,
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "view_asset",
                "description": (
                    "View an authorized attachment as native multimodal model "
                    "input when supported. PDFs require an explicit page "
                    "selection; use read_asset or search_asset for document "
                    "text instead of whole-file uploads."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ref": ref_property,
                        "extracted_text": {"type": "boolean", "default": False},
                        "selection": {
                            "type": "object",
                            "properties": {
                                "start_seconds": {"type": "number", "minimum": 0},
                                "end_seconds": {"type": "number", "minimum": 0},
                                "page_start": {"type": "integer", "minimum": 1},
                                "page_end": {"type": "integer", "minimum": 1},
                            },
                        },
                    },
                    "required": ["ref"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "inspect_asset",
                "description": t("asset_tool_inspect_description"),
                "parameters": {
                    "type": "object",
                    "properties": {"ref": ref_property},
                    "required": ["ref"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_asset",
                "description": t("asset_tool_read_description"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ref": ref_property,
                        "start_line": {
                            "type": "integer",
                            "minimum": 1,
                            "default": 1,
                            "description": t("asset_tool_start_line_description"),
                        },
                        "line_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 500,
                            "default": 100,
                            "description": t("asset_tool_line_count_description"),
                        },
                        "cursor": {
                            "type": "string",
                            "description": t("asset_tool_cursor_description"),
                        },
                    },
                    "required": ["ref"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_asset",
                "description": t("asset_tool_search_description"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ref": ref_property,
                        "query": {
                            "type": "string",
                            "description": t("asset_tool_query_description"),
                        },
                        "context_lines": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 10,
                            "default": 2,
                            "description": t("asset_tool_context_lines_description"),
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 20,
                            "description": t("asset_tool_limit_description"),
                        },
                        "cursor": {
                            "type": "string",
                            "description": t("asset_tool_cursor_description"),
                        },
                    },
                    "required": ["ref", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "materialize_asset",
                "description": t("asset_tool_materialize_description"),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ref": ref_property,
                        "path": {
                            "type": "string",
                            "description": t("asset_tool_materialize_path_description"),
                        },
                    },
                    "required": ["ref", "path"],
                },
            },
        },
    ]
