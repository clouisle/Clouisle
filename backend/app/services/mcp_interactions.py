"""Bridge MCP server-initiated requests to durable, human-authorized records.

The adapter (``app.llm.tools.mcp_client``) answers ``sampling/createMessage``,
``elicitation/create`` and ``roots/list`` only while a live session exists.
This module supplies those handlers:

* **sampling** is never auto-answered. The server's request is reduced to a
  bounded preview, stored as a pending :class:`InteractionRequest`, and a
  member of its explicit audience must approve it. Approval then calls the
  existing team model manager (same team quota and user identity) with no
  tools and no MCP connection, so a sampling request cannot elevate access or
  recursively invoke tools.
* **elicitation** stores a form schema or an allowlisted HTTPS URL and waits
  for an authorized human answer. Form answers are schema-validated and
  credential-like fields are refused; URL mode only accepts exact configured
  hosts.
* **roots** are returned from the explicitly configured ``mcp_config.roots``
  allowlist. Nothing is derived from the host filesystem.

Capabilities are advertised only when the tool explicitly enables them
(``enable_sampling`` / ``enable_elicitation``) and roots are configured, so a
server never sees a capability this bridge cannot honour.

Durability boundary: callbacks await the database row for a bounded time.
``run_with_mcp_callbacks`` owns exactly one process-local session handle; when
the scope exits (success, error or session loss) still-pending rows become
``connection_lost``. No outer tool call is ever replayed to "continue" a dead
JSON-RPC request.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import mcp.types as types

from app.core.config import settings
from app.llm.tools.mcp_client import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ElicitationHandler,
    McpCallbackPolicy,
    McpCallbacks,
    McpRoot,
    SamplingHandler,
)
from app.models.tool import Tool
from app.models.tool_interaction import (
    InteractionKind,
    InteractionOutcome,
    InteractionRequest,
    InteractionStatus,
)
from app.services import mcp_session_runtime, tool_interactions
from app.services.mcp_session_runtime import (
    ManagedMcpSession,
    McpSessionTerminalReason,
)
from app.services.tool_context import current_execution_id
from app.services.tool_execution import ToolCallContext

logger = logging.getLogger(__name__)

MAX_SAMPLING_REQUESTS = 20
MAX_SAMPLING_TOKENS = 8192
MAX_CALLBACK_REQUESTS_DEFAULT = 4
MIN_CALLBACK_SECONDS = 10.0
# The live callback lives inside the outer MCP request; it must end before
# that request's budget expires so the worker can persist a terminal decision
# instead of being killed mid-wait. Five seconds pays for the model/tool
# response path after the human answer.
MCP_CALL_RESERVE_SECONDS = 5.0
DEFAULT_CALLBACK_TIMEOUT_SECONDS = 120.0
MAX_PREVIEW_MESSAGES = 20
MAX_PREVIEW_MESSAGE_CHARS = 4000
MAX_PREVIEW_TOTAL_CHARS = 32000
MAX_ELICITATION_MESSAGE_CHARS = 4000


# ---------------------------------------------------------------------------
# Configuration parsing (mcp_config is admin-reviewed, non-secret here)
# ---------------------------------------------------------------------------


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _bool_flag(config: Mapping[str, Any], key: str) -> bool:
    return config.get(key) is True


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _requested_callback_timeout(tool: Tool) -> float:
    """The configured approval window, independent of the outer call budget."""
    config = _mapping(tool.mcp_config)
    try:
        requested = float(config.get("callback_timeout_seconds"))
    except (TypeError, ValueError):
        requested = DEFAULT_CALLBACK_TIMEOUT_SECONDS
    ceiling = float(settings.MCP_INTERACTION_TTL_SECONDS)
    return max(MIN_CALLBACK_SECONDS, min(ceiling, requested))


def _callback_timeout(tool: Tool, call_timeout_seconds: float | None = None) -> float:
    """Explicit ladder: callback budget = outer MCP call budget - reserve.

    A live callback cannot outlive the request that carries it. With the
    adapter's default 60s request budget the approval window is 55s; callers
    that pass a larger ``execute_mcp_tool`` timeout must pass the same value
    here (``mcp_call_timeout_seconds`` returns the matching pair).
    """
    outer = (
        float(call_timeout_seconds)
        if call_timeout_seconds is not None
        else float(DEFAULT_REQUEST_TIMEOUT_SECONDS)
    )
    ceiling = min(
        float(settings.MCP_INTERACTION_TTL_SECONDS),
        max(MIN_CALLBACK_SECONDS, outer - MCP_CALL_RESERVE_SECONDS),
    )
    requested = _requested_callback_timeout(tool)
    effective = max(MIN_CALLBACK_SECONDS, min(ceiling, requested))
    if requested > effective:
        logger.info(
            "Capping MCP callback budget for tool %s from %.1fs to %.1fs "
            "(outer call %.1fs)",
            tool.id,
            requested,
            effective,
            outer,
        )
    return effective


def mcp_call_timeout_seconds(tool: Tool) -> float:
    """Outer MCP request budget that matches the configured callback window.

    Pass this to ``execute_mcp_tool(timeout=...)`` and the same value as
    ``call_timeout_seconds`` to :func:`run_with_mcp_callbacks` so the approval
    window and the request budget cannot disagree.
    """
    budget = _requested_callback_timeout(tool)
    return max(
        float(DEFAULT_REQUEST_TIMEOUT_SECONDS),
        budget + MCP_CALL_RESERVE_SECONDS,
    )


def _configured_roots(tool: Tool) -> tuple[tuple[McpRoot, ...], tuple[str, ...]]:
    config = _mapping(tool.mcp_config)
    roots: list[McpRoot] = []
    raw_roots = config.get("roots")
    if isinstance(raw_roots, list):
        for item in raw_roots:
            if not isinstance(item, Mapping):
                continue
            uri = item.get("uri")
            if not isinstance(uri, str) or not uri.startswith("file://"):
                logger.warning(
                    "Dropping MCP root for tool %s: only file:// URIs are sent",
                    tool.id,
                )
                continue
            name = item.get("name")
            roots.append(
                McpRoot(
                    uri=uri,
                    name=str(name)[:200] if isinstance(name, str) and name else None,
                )
            )
    raw_allowlist = config.get("roots_allowlist")
    allowlist: list[str] = []
    if isinstance(raw_allowlist, list):
        for item in raw_allowlist:
            if isinstance(item, str) and item.startswith("file://"):
                allowlist.append(item)
    return tuple(roots), tuple(allowlist)


def _configured_url_hosts(tool: Tool) -> frozenset[str]:
    config = _mapping(tool.mcp_config)
    raw = config.get("elicitation_url_hosts")
    if not isinstance(raw, list):
        return frozenset()
    hosts: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        host = item.strip().lower()
        if host and "/" not in host and ":" not in host:
            hosts.add(host)
    return frozenset(hosts)


def _callback_policy(
    tool: Tool, call_timeout_seconds: float | None = None
) -> McpCallbackPolicy:
    config = _mapping(tool.mcp_config)
    url_hosts = _configured_url_hosts(tool)
    roots, allowlist = _configured_roots(tool)
    modes = {"form"}
    if url_hosts:
        modes.add("url")
    return McpCallbackPolicy(
        max_sampling_requests=_bounded_int(
            config.get("max_sampling_requests"),
            default=MAX_CALLBACK_REQUESTS_DEFAULT,
            minimum=0,
            maximum=MAX_SAMPLING_REQUESTS,
        ),
        sampling_max_tokens=_bounded_int(
            config.get("sampling_max_tokens"),
            default=1024,
            minimum=1,
            maximum=MAX_SAMPLING_TOKENS,
        ),
        sampling_tools=False,
        max_elicitation_requests=_bounded_int(
            config.get("max_elicitation_requests"),
            default=MAX_CALLBACK_REQUESTS_DEFAULT,
            minimum=0,
            maximum=MAX_SAMPLING_REQUESTS,
        ),
        elicitation_modes=frozenset(modes),
        elicitation_url_hosts=url_hosts,
        max_callback_seconds=_callback_timeout(tool, call_timeout_seconds),
        roots=roots,
        roots_allowlist=allowlist,
    )


# ---------------------------------------------------------------------------
# Audience resolution
# ---------------------------------------------------------------------------


def _run_kind_value(context: ToolCallContext) -> str | None:
    value = getattr(context.run_kind, "value", context.run_kind)
    return str(value) if value is not None else None


async def _run_owner_user_id(context: ToolCallContext) -> UUID | None:
    """The durable run's responsible human, if the run still exists."""
    if context.run_id is None:
        return None
    kind = _run_kind_value(context)
    try:
        if kind == "agent":
            from app.models.agent_run import AgentRun

            run = await AgentRun.filter(id=context.run_id).first()
            return run.user_id if run is not None else None
        if kind == "workflow":
            from app.models.workflow import WorkflowRun

            run = await WorkflowRun.filter(id=context.run_id).first()
            return run.triggered_by_id if run is not None else None
    except Exception:  # pragma: no cover - database safety
        logger.warning(
            "Unable to resolve interaction audience for %s run %s",
            kind,
            context.run_id,
            exc_info=True,
        )
    return None


async def _resolve_audience(context: ToolCallContext) -> dict[str, list[str]]:
    user_ids: list[Any] = []
    actor_id = getattr(context.actor, "id", None)
    if actor_id:
        user_ids.append(actor_id)
    owner_id = await _run_owner_user_id(context)
    if owner_id:
        user_ids.append(owner_id)
    return {"user_ids": [str(item) for item in user_ids], "roles": []}


# ---------------------------------------------------------------------------
# Sampling preview and model call
# ---------------------------------------------------------------------------


class _UnsupportedSamplingContent(Exception):
    """The server sent sampling content this platform cannot faithfully forward."""


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    direct = getattr(content, "text", None)
    if isinstance(direct, str):
        return direct
    if isinstance(content, Mapping):
        text = content.get("text")
        if isinstance(text, str):
            return text
        return None
    if isinstance(content, Sequence):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, Mapping):
                text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
        return "\n".join(parts) if parts else None
    return None


def _sampling_messages(params: Any) -> tuple[list[dict[str, str]], bool]:
    """Extract bounded text messages from sampling params.

    Returns ``(messages, truncated)``. Non-text content is dropped from the
    preview and rejected before a model call, so media is never silently
    replaced by a placeholder answer.
    """
    messages: list[dict[str, str]] = []
    total = 0
    truncated = False
    raw_messages = getattr(params, "messages", None) or []
    for raw in list(raw_messages)[:MAX_PREVIEW_MESSAGES]:
        role = getattr(raw, "role", None)
        if role is None and isinstance(raw, Mapping):
            role = raw.get("role")
        content = getattr(raw, "content", None)
        if content is None and isinstance(raw, Mapping):
            content = raw.get("content")
        text = _content_text(content)
        if text is None:
            raise _UnsupportedSamplingContent()
        if len(text) > MAX_PREVIEW_MESSAGE_CHARS:
            text = text[:MAX_PREVIEW_MESSAGE_CHARS] + "…"
            truncated = True
        if total + len(text) > MAX_PREVIEW_TOTAL_CHARS:
            remaining = max(MAX_PREVIEW_TOTAL_CHARS - total, 0)
            text = text[:remaining]
            truncated = True
        total += len(text)
        messages.append(
            {
                "role": str(role) if role in {"user", "assistant"} else "user",
                "content": text,
            }
        )
    if len(list(raw_messages)) > MAX_PREVIEW_MESSAGES:
        truncated = True
    if not messages:
        raise _UnsupportedSamplingContent()
    return messages, truncated


def _model_preferences(params: Any) -> dict[str, Any] | None:
    preferences = getattr(params, "model_preferences", None)
    if preferences is None:
        preferences = getattr(params, "modelPreferences", None)
    if not isinstance(preferences, Mapping) and not hasattr(preferences, "model_dump"):
        return None
    try:
        raw = (
            preferences.model_dump(mode="json", exclude_none=True)
            if hasattr(preferences, "model_dump")
            else dict(preferences)
        )
    except Exception:  # pragma: no cover - defensive
        return None
    hints: list[str] = []
    raw_hints = raw.get("hints")
    if isinstance(raw_hints, list):
        for hint in raw_hints[:8]:
            name = hint.get("name") if isinstance(hint, Mapping) else None
            if isinstance(name, str) and name:
                hints.append(name[:200])
    kept: dict[str, Any] = {}
    if hints:
        kept["hints"] = hints
    for key, field in (
        ("costPriority", "cost_priority"),
        ("speedPriority", "speed_priority"),
        ("intelligencePriority", "intelligence_priority"),
    ):
        value = raw.get(key, raw.get(field))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            kept[key] = max(0.0, min(1.0, float(value)))
    return kept or None


def _sampling_payload(params: Any, policy: McpCallbackPolicy) -> dict[str, Any]:
    messages, truncated = _sampling_messages(params)
    system_prompt = getattr(params, "system_prompt", None) or getattr(
        params, "systemPrompt", None
    )
    if isinstance(system_prompt, str):
        if len(system_prompt) > MAX_PREVIEW_MESSAGE_CHARS:
            system_prompt = system_prompt[:MAX_PREVIEW_MESSAGE_CHARS] + "…"
            truncated = True
    else:
        system_prompt = None
    requested_tokens = getattr(params, "max_tokens", None) or getattr(
        params, "maxTokens", None
    )
    if isinstance(requested_tokens, bool) or not isinstance(requested_tokens, int):
        requested_tokens = policy.sampling_max_tokens
    max_tokens = max(1, min(policy.sampling_max_tokens, requested_tokens))
    include_context = getattr(params, "include_context", None) or getattr(
        params, "includeContext", None
    )
    return {
        "mode": "sampling",
        "system_prompt": system_prompt,
        "messages": messages,
        "max_tokens": max_tokens,
        "model_preferences": _model_preferences(params),
        "include_context": (
            str(include_context) if isinstance(include_context, str) else None
        ),
        "truncated": truncated,
    }


def _cap_sampling_output(
    text: str, max_tokens: int, model_id: str | None
) -> tuple[str, str]:
    """Bound generated text to the approved token budget."""
    from app.llm.token_counter import count_tokens, get_encoding_for_model

    if count_tokens(text, model_id) <= max_tokens:
        return text, "endTurn"
    try:
        encoding = get_encoding_for_model(model_id)
        capped = encoding.decode(encoding.encode(text)[:max_tokens])
    except Exception:  # pragma: no cover - tokenizer safety
        capped = text[: max_tokens * 2]
    return capped, "maxTokens"


async def _run_approved_sampling(
    context: ToolCallContext, payload: Mapping[str, Any]
) -> tuple[str, str, str]:
    """Call the existing team model manager with the run's identity/quota."""
    from app.llm import model_manager
    from app.llm.types import Message, MessageRole

    messages: list[Message] = []
    system_prompt = payload.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt:
        messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
    for item in payload.get("messages") or []:
        if not isinstance(item, Mapping):
            continue
        role = (
            MessageRole.ASSISTANT
            if item.get("role") == "assistant"
            else MessageRole.USER
        )
        messages.append(Message(role=role, content=str(item.get("content") or "")))
    if not messages:
        raise ValueError("Sampling request had no forwardable messages")

    response = await model_manager.team_chat(
        team_id=str(context.team_id),
        messages=messages,
        model_id=None,
        tools=None,
        user_id=str(getattr(context.actor, "id", "")),
    )
    text = response.content or ""
    max_tokens = int(payload.get("max_tokens") or 1)
    capped, stop_reason = _cap_sampling_output(text, max_tokens, response.model)
    return capped, stop_reason, response.model


# ---------------------------------------------------------------------------
# Elicitation helpers
# ---------------------------------------------------------------------------


def _elicitation_url_allowed(url: Any, hosts: frozenset[str]) -> bool:
    from urllib.parse import urlsplit

    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    return parsed.hostname.lower() in hosts


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class _McpInteractionBridge:
    """Handlers bound to one tool call, audience and owned session."""

    def __init__(
        self,
        *,
        tool: Tool,
        context: ToolCallContext,
        execution_id: UUID | None,
        session: ManagedMcpSession | None,
        policy: McpCallbackPolicy,
    ) -> None:
        self.tool = tool
        self.context = context
        self.execution_id = execution_id
        self.session = session
        self.policy = policy
        self.timeout = float(policy.max_callback_seconds)

    def _session_status(self) -> InteractionStatus | None:
        """Terminal status to adopt if the owned session is already gone."""
        if self.session is None:
            return None
        return self.session.terminal_interaction_status()

    def _origin(self) -> dict[str, Any]:
        return {
            "run_kind": _run_kind_value(self.context),
            "run_id": self.context.run_id,
            "execution_id": self.execution_id,
            "session_key": self.session.key if self.session is not None else None,
            "tool_id": self.tool.id,
            "tool_name": self.tool.name,
            "tool_call_id": self.context.tool_call_id,
            "team_id": self.context.team_id,
        }

    async def _new_request(
        self, *, kind: InteractionKind, payload: dict[str, Any]
    ) -> InteractionRequest:
        origin = self._origin()
        return await tool_interactions.create_interaction(
            kind=kind,
            actor=self.context.actor,
            team_id=origin["team_id"],
            payload=payload,
            audience=await _resolve_audience(self.context),
            ttl_seconds=self.timeout,
            run_kind=origin["run_kind"],
            run_id=origin["run_id"],
            execution_id=origin["execution_id"],
            session_key=origin["session_key"],
            tool_id=origin["tool_id"],
            tool_name=origin["tool_name"],
            tool_call_id=origin["tool_call_id"],
        )

    async def _await(self, interaction: InteractionRequest) -> InteractionRequest:
        try:
            return await tool_interactions.wait_for_response(
                interaction.id,
                deadline_seconds=self.timeout,
                session_check=self._session_status,
            )
        except BaseException:
            # The adapter/worker cancelled its own call: no live request can
            # ever be answered, so make the row terminal instead of leaving a
            # phantom pending item until the reaper runs.
            try:
                await tool_interactions.close_interaction(
                    interaction.id, InteractionStatus.CANCELLED
                )
            except Exception:  # pragma: no cover - cancellation safety
                logger.warning(
                    "Unable to cancel interaction %s after caller cancellation",
                    interaction.id,
                    exc_info=True,
                )
            raise

    # -- sampling -------------------------------------------------------

    async def sampling(self, _context: Any, params: Any) -> Any:
        try:
            payload = _sampling_payload(params, self.policy)
        except _UnsupportedSamplingContent:
            logger.warning(
                "Refusing MCP sampling with non-text content from tool %s",
                self.tool.id,
            )
            return types.ErrorData(
                code=types.INVALID_REQUEST,
                message="Sampling content includes unsupported media",
            )
        except Exception:
            logger.exception("Unable to build MCP sampling preview")
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Sampling request could not be previewed",
            )

        try:
            interaction = await self._new_request(
                kind=InteractionKind.SAMPLING, payload=payload
            )
        except Exception as exc:
            logger.warning(
                "Unable to persist MCP sampling approval: %s", type(exc).__name__
            )
            return types.ErrorData(
                code=types.INVALID_REQUEST,
                message="Sampling is not available for this execution",
            )

        resolved = await self._await(interaction)
        if resolved.status != InteractionStatus.RESPONDED:
            return types.ErrorData(
                code=types.INVALID_REQUEST,
                message="Sampling request ended without approval",
            )
        if resolved.outcome != InteractionOutcome.ACCEPT:
            return types.ErrorData(
                code=types.INVALID_REQUEST,
                message="Sampling request was declined by the user",
            )

        try:
            text, stop_reason, model = await _run_approved_sampling(
                self.context, payload
            )
        except Exception as exc:
            from app.services.usage_tracker import QuotaExceededError

            if isinstance(exc, QuotaExceededError):
                logger.warning("MCP sampling denied by team quota: %s", exc)
                return types.ErrorData(
                    code=types.INTERNAL_ERROR,
                    message="The team model quota does not allow this sampling request",
                )
            logger.exception("Approved MCP sampling model call failed")
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message="Sampling model call failed",
            )
        return types.CreateMessageResult(
            role="assistant",
            content=types.TextContent(type="text", text=text),
            model=model,
            stopReason=stop_reason,
        )

    # -- elicitation ----------------------------------------------------

    async def elicitation(self, _context: Any, params: Any) -> Any:
        mode = getattr(params, "mode", None) or "form"
        message = getattr(params, "message", None)
        message = (
            message[:MAX_ELICITATION_MESSAGE_CHARS] if isinstance(message, str) else ""
        )

        if mode == "url":
            url = getattr(params, "url", None)
            if not _elicitation_url_allowed(url, self.policy.elicitation_url_hosts):
                logger.warning(
                    "Declining MCP URL elicitation outside the configured hosts"
                )
                return types.ElicitResult(action="decline")
            payload = {"mode": "url", "message": message, "url": url}
        elif mode == "form":
            schema = getattr(params, "requested_schema", None) or getattr(
                params, "requestedSchema", None
            )
            if not isinstance(schema, Mapping):
                return types.ElicitResult(action="decline")
            if not tool_interactions.form_schema_supported(schema):
                logger.warning(
                    "Declining MCP elicitation with an unsupported form schema"
                )
                return types.ElicitResult(action="decline")
            if tool_interactions.schema_requests_secrets(schema):
                logger.warning("Declining MCP elicitation that requests credentials")
                return types.ElicitResult(action="decline")
            payload = {
                "mode": "form",
                "message": message,
                "requested_schema": dict(schema),
            }
        else:
            logger.warning("Refusing unknown MCP elicitation mode %r", mode)
            return types.ElicitResult(action="decline")

        try:
            interaction = await self._new_request(
                kind=InteractionKind.ELICITATION, payload=payload
            )
        except Exception as exc:
            logger.warning("Unable to persist MCP elicitation: %s", type(exc).__name__)
            return types.ElicitResult(action="decline")

        resolved = await self._await(interaction)
        if resolved.status != InteractionStatus.RESPONDED:
            return types.ElicitResult(action="cancel")
        if resolved.outcome == InteractionOutcome.ACCEPT:
            if mode == "url":
                return types.ElicitResult(action="accept")
            content = tool_interactions.load_response_content(resolved)
            if content is None:
                # Fail closed: an accepted form without readable content must
                # not become an empty acceptance.
                return types.ElicitResult(action="decline")
            return types.ElicitResult(action="accept", content=content)
        if resolved.outcome == InteractionOutcome.DECLINE:
            return types.ElicitResult(action="decline")
        return types.ElicitResult(action="cancel")


# ---------------------------------------------------------------------------
# Public builders / lifetimes
# ---------------------------------------------------------------------------


def build_mcp_callbacks(
    tool: Tool,
    context: ToolCallContext,
    execution_id: UUID | None = None,
    *,
    call_timeout_seconds: float | None = None,
) -> McpCallbacks:
    """Build callback handlers for one tool call.

    The execution id falls back to :func:`current_execution_id`, which trusted
    runtimes set around the invocation boundary. ``call_timeout_seconds`` is
    the same budget passed to ``execute_mcp_tool``; the approval window is
    derived from it by subtracting :data:`MCP_CALL_RESERVE_SECONDS`. Prefer
    :func:`run_with_mcp_callbacks`, which also owns session cleanup.
    """
    resolved_execution_id = (
        execution_id if execution_id is not None else current_execution_id()
    )
    policy = _callback_policy(tool, call_timeout_seconds)
    bridge = _McpInteractionBridge(
        tool=tool,
        context=context,
        execution_id=resolved_execution_id,
        session=None,
        policy=policy,
    )
    enabled_sampling = _bool_flag(_mapping(tool.mcp_config), "enable_sampling")
    enabled_elicitation = _bool_flag(_mapping(tool.mcp_config), "enable_elicitation")
    sampling: SamplingHandler | None = bridge.sampling if enabled_sampling else None
    elicitation: ElicitationHandler | None = (
        bridge.elicitation if enabled_elicitation else None
    )
    return McpCallbacks(
        sampling=sampling,
        elicitation=elicitation,
        roots=None,
        notification=None,
        policy=policy,
    )


def _owned_callbacks(
    tool: Tool,
    context: ToolCallContext,
    execution_id: UUID | None,
    session: ManagedMcpSession,
    call_timeout_seconds: float | None = None,
) -> McpCallbacks:
    policy = _callback_policy(tool, call_timeout_seconds)
    bridge = _McpInteractionBridge(
        tool=tool,
        context=context,
        execution_id=execution_id,
        session=session,
        policy=policy,
    )
    config = _mapping(tool.mcp_config)
    return McpCallbacks(
        sampling=bridge.sampling if _bool_flag(config, "enable_sampling") else None,
        elicitation=(
            bridge.elicitation if _bool_flag(config, "enable_elicitation") else None
        ),
        roots=None,
        notification=None,
        policy=policy,
    )


async def _open(
    tool: Tool,
    context: ToolCallContext,
    execution_id: UUID | None,
    call_timeout_seconds: float | None = None,
) -> tuple[McpCallbacks, ManagedMcpSession]:
    resolved_execution_id = (
        execution_id if execution_id is not None else current_execution_id()
    )
    owner = (
        f"execution:{resolved_execution_id}"
        if resolved_execution_id is not None
        else f"tool:{tool.id}"
    )
    session = await mcp_session_runtime.acquire_session(
        owner=owner,
        execution_id=resolved_execution_id,
        max_lifetime_seconds=float(settings.MCP_INTERACTION_TTL_SECONDS),
    )
    return (
        _owned_callbacks(
            tool, context, resolved_execution_id, session, call_timeout_seconds
        ),
        session,
    )


@asynccontextmanager
async def open_mcp_callbacks(
    tool: Tool,
    context: ToolCallContext,
    execution_id: UUID | None = None,
    *,
    call_timeout_seconds: float | None = None,
) -> AsyncIterator[McpCallbacks]:
    """Yield callbacks backed by one explicitly owned, auto-closed session."""
    callbacks, session = await _open(tool, context, execution_id, call_timeout_seconds)
    try:
        yield callbacks
    except BaseException:
        await mcp_session_runtime.release_session(
            session, McpSessionTerminalReason.CONNECTION_LOST
        )
        raise
    else:
        await mcp_session_runtime.release_session(
            session, McpSessionTerminalReason.SESSION_CLOSED
        )


async def run_with_mcp_callbacks(
    tool: Tool,
    context: ToolCallContext,
    invoke: Callable[[McpCallbacks], Awaitable[Any]],
    *,
    execution_id: UUID | None = None,
    call_timeout_seconds: float | None = None,
) -> Any:
    """Run one MCP operation with owned callbacks and guaranteed cleanup.

    ``invoke`` receives the callbacks and must pass them to the MCP adapter.
    ``call_timeout_seconds`` must match the adapter's overall timeout; the
    callback budget is that value minus :data:`MCP_CALL_RESERVE_SECONDS`
    (55s for the adapter's default 60s). On any exit the session handle is
    released; pending interactions that could no longer be answered become
    ``connection_lost`` and the operation is never replayed.
    """
    async with open_mcp_callbacks(
        tool,
        context,
        execution_id,
        call_timeout_seconds=call_timeout_seconds,
    ) as callbacks:
        return await invoke(callbacks)


async def close_execution_interactions(
    execution_id: UUID,
    *,
    status: InteractionStatus = InteractionStatus.CANCELLED,
) -> int:
    """Terminally close pending interactions when a run stops (no replay)."""
    return await tool_interactions.close_pending_for_execution(
        execution_id, status=status
    )


__all__ = [
    "build_mcp_callbacks",
    "close_execution_interactions",
    "mcp_call_timeout_seconds",
    "open_mcp_callbacks",
    "run_with_mcp_callbacks",
]
