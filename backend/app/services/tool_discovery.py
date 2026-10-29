"""Authorized on-demand tool discovery for Agent runs.

A large MCP/custom catalog makes every model turn pay for every tool schema.
This module keeps a compact *always visible* set and exposes two read-only
metadata tools instead:

``discover_tools``
    Search the catalog that the current Agent is already authorized to use.
``load_tools``
    Add exact tool names to the schema list sent on the next model turn.

Security invariants:

- The catalog is derived only from the tool definitions the existing loaders
  produced for this Agent. Discovery never loads a Tool row of its own, never
  widens the configured set, and never changes the execution boundary: a
  discovered call still goes through the same authorization and approval path
  as an always-visible call.
- Custom tools are re-checked with the canonical ``authorize_tool_context``
  before their metadata enters the catalog, so a schema whose execution would
  be denied is not exposed either.
- Names restored from a resumed run are re-validated against the freshly
  authorized catalog; anything that disappeared (config change, revoked share,
  disabled tool) is dropped instead of being re-exposed.

The state object is deliberately transport-agnostic: the durable Agent run
binds it to the loop's per-turn tool list, while ``AgentService`` (workflow
Agent nodes) can use the same object directly.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DISCOVER_TOOLS_TOOL = "discover_tools"
LOAD_TOOLS_TOOL = "load_tools"
UNLOAD_TOOLS_TOOL = "unload_tools"
DISCOVERY_TOOL_NAMES: frozenset[str] = frozenset(
    {DISCOVER_TOOLS_TOOL, LOAD_TOOLS_TOOL, UNLOAD_TOOLS_TOOL}
)

#: Fallback labels for event consumers; chat localizes these by internal name.
DISCOVERY_TOOL_DISPLAY_NAMES: dict[str, str] = {
    DISCOVER_TOOLS_TOOL: "Discover Tools",
    LOAD_TOOLS_TOOL: "Load Tools",
    UNLOAD_TOOLS_TOOL: "Unload Tools",
}

#: Keep configured interaction, retrieval, asset, and sandbox primitives visible.
#: All other authorized tools remain discoverable in large catalogs.
CORE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "ask_user",
        "knowledge_search",
        "read_tool_result",
        "list_assets",
        "inspect_asset",
        "read_asset",
        "search_asset",
        "materialize_asset",
        "view_asset",
        "read",
        "edit",
        "write",
        "bash",
    }
)

#: Discovery engages only when at least this many non-core tools exist, or the
#: serialized schema footprint exceeds ``DEFAULT_SCHEMA_TOKEN_BUDGET``.
DEFAULT_MIN_DISCOVERABLE_TOOLS = 20
DEFAULT_SCHEMA_TOKEN_BUDGET = 4096
DEFAULT_SEARCH_LIMIT = 8
MAX_SEARCH_LIMIT = 20
MAX_LOADED_TOOLS = 24
_DESCRIPTION_LIMIT = 180

#: Latin words/digits and CJK runs. Chinese queries are common, so tokenizing
#: must not drop CJK text; CJK runs are also expanded into bigrams for partial
#: substring matches (e.g. 「日历」 inside 「创建日历事件」).
_TERM_RE = re.compile(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_MAX_QUERY_TERMS = 24


def _schema_dict(tool: Any) -> dict[str, Any]:
    """Return an OpenAI tool schema for a dict or a ``ToolDefinition``."""
    if isinstance(tool, Mapping):
        return dict(tool)
    dump = getattr(tool, "model_dump", None)
    if callable(dump):
        value = dump()
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _function_dict(tool: Any) -> dict[str, Any]:
    function = _schema_dict(tool).get("function")
    return dict(function) if isinstance(function, Mapping) else {}


def _function_name(tool: Any) -> str:
    name = _function_dict(tool).get("name")
    return name if isinstance(name, str) else ""


def estimate_tool_schema_tokens(tools: Sequence[Any] | None) -> int:
    """Conservative size estimate used only for the activation decision."""
    if not tools:
        return 0
    payload = json.dumps(
        [_schema_dict(tool) for tool in tools],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (len(payload) + 3) // 4


def _short_description(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= _DESCRIPTION_LIMIT:
        return text
    return text[: _DESCRIPTION_LIMIT - 1].rstrip() + "…"


def _parameter_names(parameters: Any) -> list[str]:
    if not isinstance(parameters, Mapping):
        return []
    properties = parameters.get("properties")
    if not isinstance(properties, Mapping):
        return []
    required = parameters.get("required")
    required_names = (
        [str(item) for item in required] if isinstance(required, (list, tuple)) else []
    )
    ordered = [name for name in required_names if name in properties]
    ordered.extend(str(name) for name in properties if str(name) not in ordered)
    return ordered


def _source_label(name: str) -> str:
    if name.startswith("mcp_"):
        return "MCP"
    if name.startswith("custom_"):
        return "Custom"
    if name.startswith("skill_"):
        return "Skill"
    return "Builtin"


def _search_terms(query: str) -> tuple[list[str], list[str]]:
    """Split a query into match terms and the primary terms.

    Latin words and CJK runs are primary terms; CJK runs longer than two
    characters also contribute bigrams so a natural-language Chinese query
    (「创建日历事件」) matches a shorter tool description (「日历 事件」).
    """
    primary = _TERM_RE.findall(query.lower())
    expanded: list[str] = []
    seen: set[str] = set()
    for run in primary:
        candidates = [run]
        if not run[0].isascii() and len(run) > 2:
            candidates.extend(run[index : index + 2] for index in range(len(run) - 1))
        for term in candidates:
            if term and term not in seen:
                seen.add(term)
                expanded.append(term)
    return expanded[:_MAX_QUERY_TERMS], primary


def _name_words(name: str) -> list[str]:
    spaced = _CAMEL_SPLIT_RE.sub(" ", name)
    return _TERM_RE.findall(spaced.lower())


@dataclass(slots=True)
class ToolCatalogEntry:
    """One authorized tool that can be discovered and then loaded."""

    name: str
    description: str
    group: str
    required_parameters: list[str]
    raw: Any
    order: int

    def compact(self, *, loaded: bool) -> dict[str, Any]:
        return {
            "name": self.name,
            "group": self.group,
            "description": self.description,
            "parameters": self.required_parameters,
            "loaded": loaded,
        }


@dataclass(slots=True)
class ToolDiscoveryState:
    """Active discovery mode for one Agent round.

    ``tools_for_turn`` is the only thing the model loop needs; the discovery
    tools themselves are executed by :meth:`execute` through the caller's
    existing ``execute_tool_call`` wrapper.
    """

    catalog: dict[str, ToolCatalogEntry]
    core_names: tuple[str, ...]
    meta_tools: list[Any]
    loaded: list[str] = field(default_factory=list)
    max_loaded: int = MAX_LOADED_TOOLS
    #: Awaited after a load changes the visible set so the run can persist it.
    on_loaded_change: Callable[[list[str]], Awaitable[None]] | None = None

    @property
    def loaded_names(self) -> list[str]:
        return list(self.loaded)

    def handles(self, tool_name: str) -> bool:
        return tool_name in DISCOVERY_TOOL_NAMES

    def is_visible(self, tool_name: str) -> bool:
        """Whether this tool is currently declared to the model.

        Discovery mode must not become a shortcut: a call for an authorized but
        not-yet-loaded tool is rejected until ``load_tools`` exposes it. Core
        and discovery tools are always visible.
        """
        return (
            tool_name in DISCOVERY_TOOL_NAMES
            or tool_name in self.core_names
            or tool_name in self.loaded
        )

    def touch(self, tool_name: str) -> None:
        """Refresh a loaded tool's recency after it was actually called.

        Recency lives in ``loaded`` order and is persisted with the next
        selection change or pause snapshot, so a tool call never costs a
        database write while eviction still reflects real usage.
        """
        if tool_name in self.loaded:
            self.loaded.remove(tool_name)
            self.loaded.append(tool_name)

    async def reduce_for_retry(self) -> list[str]:
        """Shed optional tool schemas for a context-overflow retry.

        Only tools the model loaded on demand are removed; always-visible and
        discovery tools remain declared. Returns the exact removed names so a
        retry can report what changed. An empty list means no further schema
        reduction is available here — callers must not claim a reduction or
        retry on that basis.
        """
        removed = list(self.loaded)
        if not removed:
            return []
        self.loaded.clear()
        if self.on_loaded_change is not None:
            try:
                await self.on_loaded_change([])
            except Exception:
                # In-memory reduction still applies to the current attempt; a
                # resumed run revalidates the persisted selection.
                logger.warning(
                    "Failed to persist discovered tool selection",
                    exc_info=True,
                )
        return removed

    def undiscovered_error(self, tool_name: str) -> str:
        return json.dumps(
            {
                "error": (
                    f"Tool '{tool_name}' is not loaded. Call discover_tools "
                    "with capability keywords, then load_tools with the exact "
                    "name before calling it."
                ),
                "tool_name": tool_name,
                "success": False,
            },
            ensure_ascii=False,
        )

    def tools_for_turn(self) -> list[Any]:
        """Return the exact schema list for the next model call."""
        visible: list[Any] = list(self.meta_tools)
        for name in self.core_names:
            entry = self.catalog.get(name)
            if entry is not None:
                visible.append(entry.raw)
        for name in self.loaded:
            if name in self.core_names:
                continue
            entry = self.catalog.get(name)
            if entry is not None:
                visible.append(entry.raw)
        return visible

    # ------------------------------------------------------------------
    # discovery metadata tools
    # ------------------------------------------------------------------
    async def execute(self, tool_name: str, arguments: Any) -> str:
        """Execute a discovery tool. Returns a JSON tool-result string."""
        args = arguments if isinstance(arguments, Mapping) else {}
        if tool_name == DISCOVER_TOOLS_TOOL:
            return self._search(args)
        if tool_name == LOAD_TOOLS_TOOL:
            return await self._load(args)
        if tool_name == UNLOAD_TOOLS_TOOL:
            return await self._unload(args)
        return json.dumps(
            {"error": f"unsupported discovery tool: {tool_name}"},
            ensure_ascii=False,
        )

    def _search(self, args: Mapping[str, Any]) -> str:
        query = str(args.get("query") or "").strip()
        limit = _clamp_int(args.get("limit"), DEFAULT_SEARCH_LIMIT, 1, MAX_SEARCH_LIMIT)
        terms, primary_terms = _search_terms(query)
        loaded = set(self.loaded)
        ranked: list[tuple[int, ToolCatalogEntry]] = []
        for entry in self.catalog.values():
            if entry.name in self.core_names:
                continue
            score = _score_entry(entry, query, terms, primary_terms)
            # A non-empty query that matches nothing returns no candidates;
            # an empty query lists the whole catalog.
            if query and score <= 0:
                continue
            ranked.append((score, entry))
        ranked.sort(key=lambda item: (-item[0], item[1].order))
        total = len(ranked)
        # The offset is bounded by the result set, not a fixed number, so
        # catalogs larger than any arbitrary constant stay traversable.
        offset = _clamp_int(args.get("offset"), 0, 0, total)
        page = ranked[offset : offset + limit]
        consumed = offset + len(page)
        return json.dumps(
            {
                "tools": [
                    entry.compact(loaded=entry.name in loaded) for _, entry in page
                ],
                "total_matches": total,
                "offset": offset,
                "limit": limit,
                "next_offset": consumed if consumed < total else None,
                "discoverable_tools": len(self.catalog) - len(self.core_names),
                "note": (
                    "Call load_tools with exact names from this result before "
                    "calling them. Omit the query to page through the full "
                    "catalog; continue with next_offset while it is not null."
                ),
            },
            ensure_ascii=False,
        )

    def _normalize_names(self, args: Mapping[str, Any]) -> list[str]:
        raw_names = args.get("names")
        if isinstance(raw_names, str):
            candidates = [raw_names]
        elif isinstance(raw_names, Sequence) and not isinstance(
            raw_names, (bytes, bytearray)
        ):
            candidates = [str(item) for item in raw_names]
        else:
            candidates = []

        normalized: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            name = item.strip()
            if name and name not in seen:
                seen.add(name)
                normalized.append(name)
        return normalized

    async def _load(self, args: Mapping[str, Any]) -> str:
        added: list[str] = []
        already: list[str] = []
        unknown: list[str] = []
        evicted: list[str] = []
        deferred: list[str] = []

        requested: list[str] = []
        for name in self._normalize_names(args):
            if name in self.core_names or name in DISCOVERY_TOOL_NAMES:
                already.append(name)
                continue
            if name in self.loaded:
                already.append(name)
                self.touch(name)
                continue
            if name not in self.catalog:
                unknown.append(name)
                continue
            requested.append(name)

        # A single request larger than the cap keeps the requested order and
        # tools are evicted to make room for the requested batch.
        if len(requested) > self.max_loaded:
            deferred = requested[self.max_loaded :]
            requested = requested[: self.max_loaded]
        overflow = len(self.loaded) + len(requested) - self.max_loaded
        if overflow > 0:
            evicted = self.loaded[:overflow]
            del self.loaded[:overflow]
        self.loaded.extend(requested)
        added = requested

        if added and self.on_loaded_change is not None:
            try:
                await self.on_loaded_change(self.loaded_names)
            except Exception:
                # Persistence is best effort: the loaded schemas are still
                # valid for this run, and a rebuild revalidates them.
                logger.warning(
                    "Failed to persist discovered tool selection",
                    exc_info=True,
                )

        result: dict[str, Any] = {
            "loaded": added,
            "already_visible": already,
        }
        if unknown:
            result["unknown"] = unknown
        if evicted:
            result["evicted"] = evicted
        if deferred:
            result["not_loaded_limit_reached"] = deferred
        result["note"] = (
            "Loaded tools are callable on the next turn. Oldest loaded tools "
            "are evicted automatically when the limit is reached; call "
            "unload_tools to free space deliberately."
            if added
            else "No new tools were loaded."
        )
        return json.dumps(result, ensure_ascii=False)

    async def _unload(self, args: Mapping[str, Any]) -> str:
        unloaded: list[str] = []
        always_visible: list[str] = []
        not_loaded: list[str] = []
        for name in self._normalize_names(args):
            if name in self.core_names or name in DISCOVERY_TOOL_NAMES:
                always_visible.append(name)
                continue
            if name in self.loaded:
                self.loaded.remove(name)
                unloaded.append(name)
            else:
                not_loaded.append(name)
        if unloaded and self.on_loaded_change is not None:
            try:
                await self.on_loaded_change(self.loaded_names)
            except Exception:
                logger.warning(
                    "Failed to persist discovered tool selection",
                    exc_info=True,
                )
        result: dict[str, Any] = {"unloaded": unloaded}
        if always_visible:
            result["always_visible"] = always_visible
        if not_loaded:
            result["not_loaded"] = not_loaded
        result["note"] = (
            "Unloaded tools are no longer declared; load them again before "
            "calling them."
            if unloaded
            else "No tools were unloaded."
        )
        return json.dumps(result, ensure_ascii=False)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _score_entry(
    entry: ToolCatalogEntry,
    query: str,
    terms: list[str],
    primary_terms: list[str],
) -> int:
    if not terms:
        return 0
    query_lower = query.lower().strip()
    name_lower = entry.name.lower()
    if query_lower == name_lower:
        return 1000
    score = 0
    if query_lower and query_lower in name_lower:
        score += 50
    words = set(_name_words(entry.name))
    group_lower = entry.group.lower()
    description_lower = entry.description.lower()
    for term in terms:
        if term == name_lower:
            score += 100
        if term in name_lower:
            score += 10
            if term in words:
                score += 12
            elif any(word.startswith(term) for word in words):
                score += 6
            if name_lower.startswith(term):
                score += 8
        if term in group_lower:
            score += 4
        if term in description_lower:
            score += 2
    searchable = f"{name_lower} {group_lower} {description_lower}"
    hits = sum(1 for term in primary_terms if term in searchable)
    if primary_terms:
        if hits == len(primary_terms):
            score += 25
        elif hits * 2 >= len(primary_terms):
            score += 10
    return score


def _meta_tool_schema(discoverable: int, servers: int) -> dict[str, Any]:
    server_note = f" across {servers} tool sources" if servers else ""
    return {
        "type": "function",
        "function": {
            "name": DISCOVER_TOOLS_TOOL,
            "description": (
                "Search the tools this agent is authorized to use. "
                f"{discoverable} additional tools are available{server_note} "
                "beyond the always-visible ones. Use short capability keywords "
                "(for example 'calendar', 'issue tracker', 'send email'). "
                "Omit the query to list the full catalog page by page. Returns "
                "names, short descriptions and parameter names. Load matches "
                "with load_tools before calling them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Capability or tool keywords. Omit or leave empty "
                            "to list every discoverable tool."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Maximum results per page (1-{MAX_SEARCH_LIMIT}).",
                        "minimum": 1,
                        "maximum": MAX_SEARCH_LIMIT,
                    },
                    "offset": {
                        "type": "integer",
                        "description": (
                            "Pagination offset; continue with next_offset from "
                            "the previous result."
                        ),
                        "minimum": 0,
                    },
                },
                "required": [],
            },
        },
    }


def _load_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": LOAD_TOOLS_TOOL,
            "description": (
                "Load tools returned by discover_tools by exact name so they "
                "become callable on the next turn. Loading only exposes tools "
                "the agent was already authorized to use. When the loaded "
                "limit is reached, the least recently used tool is evicted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exact tool names from discover_tools.",
                    }
                },
                "required": ["names"],
            },
        },
    }


def _unload_tool_schema() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": UNLOAD_TOOLS_TOOL,
            "description": (
                "Unload loaded tools by exact name to free tool slots. "
                "Always-visible tools cannot be unloaded; unloaded tools must "
                "be loaded again before they can be called."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Loaded tool names to unload.",
                    }
                },
                "required": ["names"],
            },
        },
    }


async def _custom_tool_denials(agent: Any, user_id: Any) -> set[str]:
    """Schema names of configured custom tools the caller may not use.

    MCP definitions are already authorized while their tools are listed, but
    custom tools are listed straight from the Agent configuration. The same
    canonical boundary used before execution decides whether their metadata
    may enter the catalog. Unknown/disabled rows contribute no schema anyway.
    """
    if agent is None or not user_id:
        return set()
    configs = [
        config
        for config in (getattr(agent, "tools_config", None) or [])
        if isinstance(config, Mapping)
        and config.get("type") == "custom"
        and config.get("tool_id")
    ]
    if not configs:
        return set()

    from app.models.tool import Tool
    from app.models.user import User
    from app.schemas.response import BusinessError
    from app.services.tool_context import (
        coerce_execution_entrypoint,
        current_tool_identity,
    )
    from app.services.tool_execution import ToolCallContext, authorize_tool_context

    team_id = getattr(agent, "team_id", None)
    actor = await User.get_or_none(id=user_id)
    runtime = current_tool_identity()
    denied: set[str] = set()
    for config in configs:
        tool = await Tool.get_or_none(id=config["tool_id"], is_enabled=True)
        if tool is None:
            continue
        schema_name = f"custom_{tool.name}"
        if team_id is None or actor is None:
            # No team context means the execution boundary itself rejects the
            # call; keep the schema out of the prompt as well.
            denied.add(schema_name)
            continue
        context = ToolCallContext(
            actor=actor,
            team_id=team_id,
            entrypoint=coerce_execution_entrypoint(
                runtime.entrypoint if runtime else None
            ),
            entrypoint_id=runtime.entrypoint_id if runtime else None,
            interactive=bool(runtime.interactive) if runtime else False,
        )
        try:
            await authorize_tool_context(tool, context)
        except BusinessError:
            denied.add(schema_name)
        except Exception:
            logger.warning(
                "Custom tool authorization check failed for %s",
                schema_name,
                exc_info=True,
            )
            denied.add(schema_name)
    return denied


async def build_tool_discovery(
    tools: Sequence[Any] | None,
    *,
    loaded_names: Sequence[str] | None = None,
    factory: Callable[[dict[str, Any]], Any] | None = None,
    agent: Any = None,
    user_id: Any = None,
    min_discoverable: int = DEFAULT_MIN_DISCOVERABLE_TOOLS,
    schema_token_budget: int = DEFAULT_SCHEMA_TOKEN_BUDGET,
    enabled: bool = True,
) -> ToolDiscoveryState | None:
    """Build discovery state for an already-loaded authorized tool list.

    Returns ``None`` when discovery is disabled, the catalog is small enough
    that hiding schemas buys nothing, or a catalog tool would collide with a
    discovery tool name (fail closed instead of shadowing it).
    """
    if not enabled or not tools:
        return None

    entries: dict[str, ToolCatalogEntry] = {}
    for order, tool in enumerate(tools):
        name = _function_name(tool)
        if not name or name in entries:
            continue
        if name in DISCOVERY_TOOL_NAMES:
            logger.warning(
                "Tool discovery disabled: agent tool %s collides with a "
                "discovery tool name",
                name,
            )
            return None
        function = _function_dict(tool)
        description = _short_description(function.get("description"))
        group = _source_label(name)
        entries[name] = ToolCatalogEntry(
            name=name,
            description=description,
            group=group,
            required_parameters=_parameter_names(function.get("parameters")),
            raw=tool,
            order=order,
        )

    denied: set[str] = set()
    if agent is not None and user_id is not None:
        try:
            denied = await _custom_tool_denials(agent, user_id)
        except Exception:
            # A failed authorization check must not widen the catalog: hide
            # every configured custom schema rather than guess.
            logger.warning(
                "Custom tool authorization check failed; hiding custom tools",
                exc_info=True,
            )
            denied = {name for name in entries if name.startswith("custom_")}
        denied &= entries.keys()
        for name in denied:
            entries.pop(name, None)

    discoverable = [
        entry for name, entry in entries.items() if name not in CORE_TOOL_NAMES
    ]
    # A denied custom tool must never be exposed even if hiding it would drop
    # the catalog below the normal activation threshold: enter discovery mode
    # so the visible list is built from the filtered catalog.
    if (
        not denied
        and len(discoverable) <= min_discoverable
        and estimate_tool_schema_tokens(tools) <= schema_token_budget
    ):
        return None

    core_names = tuple(name for name in entries if name in CORE_TOOL_NAMES)
    resolved_factory = factory or (lambda schema: schema)
    meta_schemas = [
        _meta_tool_schema(len(discoverable), _source_count(discoverable)),
        _load_tool_schema(),
        _unload_tool_schema(),
    ]
    state = ToolDiscoveryState(
        catalog=entries,
        core_names=core_names,
        meta_tools=[resolved_factory(schema) for schema in meta_schemas],
    )

    seen: set[str] = set()
    for name in loaded_names or []:
        if not isinstance(name, str):
            continue
        candidate = name.strip()
        if (
            not candidate
            or candidate in seen
            or candidate in core_names
            or candidate not in entries
        ):
            continue
        if len(state.loaded) >= state.max_loaded:
            break
        seen.add(candidate)
        state.loaded.append(candidate)
    return state


def _source_count(discoverable: Sequence[ToolCatalogEntry]) -> int:
    return len({entry.group for entry in discoverable})
