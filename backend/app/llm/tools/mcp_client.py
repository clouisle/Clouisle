"""MCP (Model Context Protocol) client adapter.

Supports the three transports the platform configures: ``stdio``, ``sse`` and
``http`` (Streamable HTTP). On top of the transport this module implements the
client-side MCP surface the product needs: tools, resources, resource
templates, prompts, completion, bounded pagination, capability negotiation and
in-process sampling / elicitation / roots hooks.

SDK support matrix
------------------
The installed SDK is probed at import time; nothing here pins a protocol
version:

* ``mcp>=2`` — ``server/discover`` auto-negotiation is used first, falling back
  to the legacy ``initialize`` handshake exactly like the SDK's own ``Client``.
* ``mcp>=1.27,<2`` — only the legacy ``initialize`` handshake exists and is
  used directly.

Request shapes that changed between SDK majors (``params=`` pagination,
``allow_input_required``) are detected with :func:`inspect.signature` so the
adapter keeps working against either major. Capabilities are always read from
the negotiated session: an operation the server did not advertise fails closed
with :class:`McpCapabilityUnavailable` instead of pretending to succeed.

Durability boundary
-------------------
MCP JSON-RPC requests and stdio subprocesses are **not** durable. Every
convenience operation opens one session, negotiates, performs the request and
closes it. ``McpCallbacks`` handlers are in-process hooks evaluated only while
the owning operation is alive; they are never persisted, never replayed after a
process restart and never resurrected after a connection loss. Callers that
need a long-lived session (for example resource subscriptions) can use
:meth:`McpClient.connect` and the returned ``ClientSession`` directly.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any, Generic, Literal, Protocol, TypeVar
from urllib.parse import urlsplit

import mcp.types as types
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client as streamablehttp_client
from mcp.shared._httpx_utils import create_mcp_http_client

try:  # mcp >= 1.x: JSON-RPC errors reported by the server.
    from mcp.shared.exceptions import MCPError as _SdkMcpError
except ImportError:  # pragma: no cover - the SDK always ships this module
    _SdkMcpError = None

from app.services.error_messages import (
    exception_to_user_message,
    resolve_user_visible_error,
)

try:  # mcp >= 2: modern-version (2026-07-28) negotiation with handshake fallback.
    from mcp.client._probe import negotiate_auto as _negotiate_auto
except ImportError:  # pragma: no cover - exercised only on mcp 1.x
    _negotiate_auto = None

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_CONTENT_LIMITS",
    "DEFAULT_ENUMERATION_LIMITS",
    "DEFAULT_TIMEOUTS",
    "ElicitationHandler",
    "McpCallbacks",
    "McpCallbackPolicy",
    "McpCapabilityUnavailable",
    "McpClient",
    "McpCompletion",
    "McpCompletionReference",
    "McpContentBlock",
    "McpContentLimits",
    "McpContentTooLarge",
    "McpEnumeration",
    "McpEnumerationLimits",
    "McpError",
    "McpInputRequired",
    "McpInputRequiredInfo",
    "McpInvalidRequest",
    "McpPromptArgument",
    "McpPromptInfo",
    "McpPromptMessage",
    "McpPromptResult",
    "McpResourceContents",
    "McpResourceInfo",
    "McpResourceTemplateInfo",
    "McpRoot",
    "McpServerCapabilities",
    "McpServerError",
    "McpTimeout",
    "McpToolInfo",
    "McpToolResult",
    "McpTimeouts",
    "NotificationHandler",
    "RootsHandler",
    "SamplingHandler",
    "complete_mcp_argument",
    "enumerate_mcp_prompts",
    "enumerate_mcp_resource_templates",
    "enumerate_mcp_resources",
    "enumerate_mcp_tools",
    "execute_mcp_tool",
    "get_mcp_prompt",
    "list_mcp_tools",
    "probe_mcp_capabilities",
    "read_mcp_resource",
    "translate_mcp_error",
]

MCP_CLIENT_NAME = "clouisle"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_ENUMERATION_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_PAGES = 20
DEFAULT_MAX_ITEMS = 500
DEFAULT_MAX_CONTENT_BLOCK_BYTES = 1_000_000
DEFAULT_MAX_CONTENT_TOTAL_BYTES = 4_000_000

_CALL = "tools/call"
_READ_RESOURCE = "resources/read"
_GET_PROMPT = "prompts/get"
_LIST_TOOLS = "tools/list"
_LIST_RESOURCES = "resources/list"
_LIST_RESOURCE_TEMPLATES = "resources/templates/list"
_LIST_PROMPTS = "prompts/list"
_COMPLETE = "completion/complete"

_SENSITIVE_ELICITATION_FIELD = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|"
    r"authorization|bearer)",
    re.IGNORECASE,
)
_TEXTUAL_CONTENT_TYPES = frozenset({"text"})
_BINARY_CONTENT_TYPES = frozenset({"image", "audio"})
# Raw braces are not valid URI characters; a URI that still contains them is
# an unexpanded RFC 6570 template and must not be sent to the server.
_URI_TEMPLATE_MARKER = re.compile(r"[{}]")

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class McpError(Exception):
    """Base class for adapter failures that callers may map to API errors.

    ``code`` is a stable machine-readable discriminator. ``details`` never
    contains credentials; it is safe to log and, where noted on the subclass,
    may be surfaced to a trusted caller.
    """

    code: str = "mcp_error"

    def __init__(
        self,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.details: dict[str, Any] = dict(details or {})


class McpCapabilityUnavailable(McpError):
    """Raised when the server did not advertise a capability we need."""

    code = "capability_unavailable"

    def __init__(self, capability: str) -> None:
        super().__init__(
            f"MCP server did not advertise the {capability!r} capability",
            details={"capability": capability},
        )
        self.capability = capability


class McpTimeout(McpError):
    """Raised when an explicit connect/request/enumeration deadline expires."""

    code = "timeout"

    def __init__(self, message: str, *, timeout_seconds: float | None = None) -> None:
        super().__init__(
            message,
            details={"timeout_seconds": timeout_seconds},
        )


class McpContentTooLarge(McpError):
    """Raised when resource/prompt content exceeds the configured budget."""

    code = "content_too_large"

    def __init__(
        self,
        message: str,
        *,
        bytes_received: int,
        byte_limit: int,
        source: str,
    ) -> None:
        super().__init__(
            message,
            details={
                "bytes_received": bytes_received,
                "byte_limit": byte_limit,
                "source": source,
            },
        )


class McpInputRequired(McpError):
    """Raised when a modern server needs client input before completing a call.

    The embedded ``InputRequiredResult`` is preserved in :attr:`info`. This
    adapter does not auto-answer those requests and does not retry the original
    operation: replaying an outer request after a process loss could duplicate
    side effects.
    """

    code = "input_required"

    def __init__(self, info: McpInputRequiredInfo) -> None:
        super().__init__(
            f"MCP server requested additional input for {info.method}",
            details=info.to_dict(),
        )
        self.info = info


class McpInvalidRequest(McpError, ValueError):
    """The caller supplied a request this adapter cannot send.

    This is a local validation failure (missing configuration, blank URI, an
    unexpanded URI template), not a transport failure. It subclasses
    ``ValueError`` so historical callers keep their exception contract while
    the API can answer with a 400 instead of a misleading 502.
    """

    code = "invalid_request"

    def __init__(self, message: str, *, reason: str = "request") -> None:
        super().__init__(message, details={"reason": reason})
        self.reason = reason


class McpServerError(McpError):
    """The server answered with a JSON-RPC error instead of a result.

    The server was reachable and rejected the request, so this must never be
    reported as a connection failure. Only the numeric code is retained in
    ``details``: server-provided text may contain secrets and is never
    surfaced to API callers.
    """

    code = "server_error"

    #: JSON-RPC codes that mean the request itself was unacceptable.
    INVALID_REQUEST_CODES = frozenset({-32700, -32600, -32602, -32002})

    def __init__(self, rpc_code: int, message: str) -> None:
        super().__init__(message, details={"rpc_code": rpc_code})
        self.rpc_code = rpc_code

    @property
    def invalid_request(self) -> bool:
        return self.rpc_code in self.INVALID_REQUEST_CODES


def translate_mcp_error(exc: BaseException) -> McpError | None:
    """Return the adapter error hidden inside task-group wrappers.

    Transports and the MCP SDK group background failures with anyio/asyncio
    task groups. A typed failure raised while a session is open (a capability
    check, a deadline, or a server rejection) can therefore surface as
    ``ExceptionGroup`` -> ``ExceptionGroup`` -> ``McpError``. Callers mapping
    protocol failures must inspect the leaves; an outer group is not a
    connection failure.
    """
    if isinstance(exc, McpError):
        return exc
    if isinstance(exc, BaseExceptionGroup):
        for nested in exc.exceptions:
            found = translate_mcp_error(nested)
            if found is not None:
                return found
        return None
    if _SdkMcpError is not None and isinstance(exc, _SdkMcpError):
        return McpServerError(exc.code, exc.message)
    return None


# ---------------------------------------------------------------------------
# Limits / timeouts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class McpTimeouts:
    """Explicit budgets for each stage of an operation (seconds)."""

    connect: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    request: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    enumeration: float = DEFAULT_ENUMERATION_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class McpEnumerationLimits:
    """Hard bounds for paginated listings.

    ``max_pages`` and ``max_items`` bound a malicious or broken server;
    repeated cursors are detected separately. Hitting any bound returns an
    :class:`McpEnumeration` with ``truncated=True`` and a
    ``truncation_reason`` rather than silently returning a partial list.
    """

    max_pages: int = DEFAULT_MAX_PAGES
    max_items: int = DEFAULT_MAX_ITEMS


@dataclass(frozen=True, slots=True)
class McpContentLimits:
    """Byte budgets for content that becomes model/user context."""

    max_block_bytes: int = DEFAULT_MAX_CONTENT_BLOCK_BYTES
    max_total_bytes: int = DEFAULT_MAX_CONTENT_TOTAL_BYTES


DEFAULT_TIMEOUTS = McpTimeouts()
DEFAULT_ENUMERATION_LIMITS = McpEnumerationLimits()
DEFAULT_CONTENT_LIMITS = McpContentLimits()


# ---------------------------------------------------------------------------
# Callbacks (in-process only)
# ---------------------------------------------------------------------------


class SamplingHandler(Protocol):
    """Answers ``sampling/createMessage`` for a live connection."""

    def __call__(
        self,
        context: Any,
        params: types.CreateMessageRequestParams,
    ) -> Awaitable[
        types.CreateMessageResult | types.CreateMessageResultWithTools | types.ErrorData
    ]: ...


class ElicitationHandler(Protocol):
    """Answers ``elicitation/create`` for a live connection."""

    def __call__(
        self,
        context: Any,
        params: types.ElicitRequestParams,
    ) -> Awaitable[types.ElicitResult | types.ErrorData]: ...


class RootsHandler(Protocol):
    """Answers ``roots/list`` for a live connection."""

    def __call__(
        self,
        context: Any,
    ) -> Awaitable[types.ListRootsResult | types.ErrorData]: ...


class NotificationHandler(Protocol):
    """Observes server notifications delivered on a live connection.

    Notifications are session-scoped; a list-changed event observed here must
    not be treated as durable state.
    """

    def __call__(self, message: Any) -> Awaitable[None]: ...


@dataclass(frozen=True, slots=True)
class McpRoot:
    """A roots declaration returned to an MCP server.

    Roots are a collaboration-scope hint, **not** a sandbox boundary. Only
    file URIs listed here (or returned by an explicitly registered roots
    handler) are ever sent; host paths are never derived automatically.
    """

    uri: str
    name: str | None = None

    def to_sdk(self) -> types.Root:
        return types.Root(uri=self.uri, name=self.name)


@dataclass(frozen=True, slots=True)
class McpCallbackPolicy:
    """Safety bounds applied to server-initiated requests.

    Client capabilities are only advertised when a matching handler is
    supplied (or roots are configured), so a server never sees a capability
    this adapter cannot answer.

    Counters are per connection. Cross-session recursion (for example a
    sampling handler that starts another MCP run) must be bounded by the
    caller's execution context; this adapter does not carry that state.
    """

    max_sampling_requests: int = 4
    sampling_max_tokens: int = 1024
    sampling_tools: bool = False
    max_elicitation_requests: int = 4
    elicitation_modes: frozenset[str] = frozenset({"form"})
    elicitation_url_hosts: frozenset[str] = frozenset()
    max_callback_seconds: float = 120.0
    roots: tuple[McpRoot, ...] = ()
    roots_allowlist: tuple[str, ...] = ()


@dataclass
class McpCallbacks:
    """Optional in-process hooks for server-initiated requests.

    These handlers live only as long as the operation that opened the MCP
    session. They are not durable across process death or connection loss, and
    this adapter never retries a server-initiated request afterwards.
    """

    sampling: SamplingHandler | None = None
    elicitation: ElicitationHandler | None = None
    roots: RootsHandler | None = None
    notification: NotificationHandler | None = None
    policy: McpCallbackPolicy = field(default_factory=McpCallbackPolicy)


# ---------------------------------------------------------------------------
# Protocol value objects
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class McpInputRequiredInfo:
    """JSON-safe snapshot of a modern ``InputRequiredResult``."""

    method: str
    requests: dict[str, Any] = field(default_factory=dict)
    request_state: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "requests": self.requests,
            "request_state": self.request_state,
        }


@dataclass(slots=True)
class McpContentBlock:
    """A preserved MCP content block (text, media, resource link, resource)."""

    type: str
    text: str | None = None
    data: str | None = None
    mime_type: str | None = None
    uri: str | None = None
    name: str | None = None
    title: str | None = None
    description: str | None = None
    size: int | None = None
    resource: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None

    def byte_size(self) -> int:
        """Approximate decoded payload size in bytes."""
        if self.text is not None:
            return len(self.text.encode("utf-8"))
        if self.data is not None:
            return len(self.data) * 3 // 4
        resource = self.resource or {}
        text = resource.get("text")
        if isinstance(text, str):
            return len(text.encode("utf-8"))
        blob = resource.get("blob")
        if isinstance(blob, str):
            return len(blob) * 3 // 4
        return 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe, wire-shaped representation (camelCase keys)."""
        if self.type in _TEXTUAL_CONTENT_TYPES:
            payload: dict[str, Any] = {"type": self.type, "text": self.text}
        elif self.type in _BINARY_CONTENT_TYPES:
            payload = {
                "type": self.type,
                "data": self.data,
                "mimeType": self.mime_type,
            }
        elif self.type == "resource":
            payload = {"type": self.type, "resource": self.resource or {}}
        elif self.type == "resource_link":
            payload = {"type": self.type}
            for key, value in (
                ("uri", self.uri),
                ("name", self.name),
                ("title", self.title),
                ("description", self.description),
                ("mimeType", self.mime_type),
                ("size", self.size),
            ):
                if value is not None:
                    payload[key] = value
        else:
            payload = {"type": self.type, **(self.raw or {})}
        if self.annotations:
            payload["annotations"] = self.annotations
        if self.meta:
            payload["_meta"] = self.meta
        return payload


@dataclass
class McpToolInfo:
    """Information about an MCP tool.

    ``annotations`` are server-provided hints for display/policy configuration
    only; they are never used to auto-approve execution.
    """

    name: str
    description: str | None
    parameters: dict[str, Any]
    title: str | None = None
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
        if self.title is not None:
            payload["title"] = self.title
        if self.output_schema is not None:
            payload["outputSchema"] = self.output_schema
        if self.annotations is not None:
            payload["annotations"] = self.annotations
        if self.meta is not None:
            payload["_meta"] = self.meta
        return payload


@dataclass
class McpToolResult:
    """Result of MCP tool execution.

    ``result`` keeps the historical text/data payload shape so existing
    callers continue to work. ``content`` and ``structured_content`` preserve
    everything the server returned, including media and resource blocks, so
    callers can render or budget them explicitly instead of losing data.
    """

    success: bool
    result: Any | None = None
    error: str | None = None
    is_error: bool = False
    content: list[McpContentBlock] = field(default_factory=list, compare=False)
    structured_content: Any | None = None
    input_required: McpInputRequiredInfo | None = None

    @property
    def has_structured_content(self) -> bool:
        return self.structured_content is not None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe full result for callers that opt into the richer payload."""
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "is_error": self.is_error,
            "content": [block.to_dict() for block in self.content],
            "structured_content": self.structured_content,
            "input_required": (
                self.input_required.to_dict() if self.input_required else None
            ),
        }


@dataclass(slots=True)
class McpResourceInfo:
    """A concrete resource advertised by ``resources/list``."""

    uri: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    size: int | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"uri": self.uri}
        for key, value in (
            ("name", self.name),
            ("title", self.title),
            ("description", self.description),
            ("mimeType", self.mime_type),
            ("size", self.size),
        ):
            if value is not None:
                payload[key] = value
        if self.annotations is not None:
            payload["annotations"] = self.annotations
        if self.meta is not None:
            payload["_meta"] = self.meta
        return payload


@dataclass(slots=True)
class McpResourceTemplateInfo:
    """A URI template advertised by ``resources/templates/list``."""

    uri_template: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"uriTemplate": self.uri_template}
        for key, value in (
            ("name", self.name),
            ("title", self.title),
            ("description", self.description),
            ("mimeType", self.mime_type),
        ):
            if value is not None:
                payload[key] = value
        if self.annotations is not None:
            payload["annotations"] = self.annotations
        if self.meta is not None:
            payload["_meta"] = self.meta
        return payload


@dataclass(slots=True)
class McpResourceContents:
    """One entry of ``resources/read`` output.

    The URI is passed through verbatim; this adapter never downloads resource
    links or dereferences non-MCP URIs on its own.
    """

    uri: str
    text: str | None = None
    blob: str | None = None
    mime_type: str | None = None
    meta: dict[str, Any] | None = None

    @property
    def is_binary(self) -> bool:
        return self.blob is not None

    def byte_size(self) -> int:
        if self.text is not None:
            return len(self.text.encode("utf-8"))
        if self.blob is not None:
            return len(self.blob) * 3 // 4
        return 0

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"uri": self.uri}
        if self.mime_type is not None:
            payload["mimeType"] = self.mime_type
        if self.text is not None:
            payload["text"] = self.text
        if self.blob is not None:
            payload["blob"] = self.blob
        if self.meta is not None:
            payload["_meta"] = self.meta
        return payload


@dataclass(slots=True)
class McpPromptArgument:
    name: str
    description: str | None = None
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name}
        if self.description is not None:
            payload["description"] = self.description
        if self.required:
            payload["required"] = True
        return payload


@dataclass(slots=True)
class McpPromptInfo:
    name: str
    title: str | None = None
    description: str | None = None
    arguments: list[McpPromptArgument] = field(default_factory=list)
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name}
        if self.title is not None:
            payload["title"] = self.title
        if self.description is not None:
            payload["description"] = self.description
        if self.arguments:
            payload["arguments"] = [argument.to_dict() for argument in self.arguments]
        if self.meta is not None:
            payload["_meta"] = self.meta
        return payload


@dataclass(slots=True)
class McpPromptMessage:
    role: str
    content: McpContentBlock

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content.to_dict()}


@dataclass(slots=True)
class McpPromptResult:
    """``prompts/get`` output.

    Prompt messages are untrusted server content: callers must preview them
    and must not treat them as system instructions automatically.
    """

    messages: list[McpPromptMessage] = field(default_factory=list)
    description: str | None = None
    meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [message.to_dict() for message in self.messages]
        }
        if self.description is not None:
            payload["description"] = self.description
        if self.meta is not None:
            payload["_meta"] = self.meta
        return payload


@dataclass(frozen=True, slots=True)
class McpCompletionReference:
    """A prompt or resource-template reference for ``completion/complete``."""

    kind: Literal["prompt", "resource_template"]
    name: str | None = None
    uri: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "prompt" and not self.name:
            raise ValueError("A prompt completion reference requires 'name'")
        if self.kind == "resource_template" and not self.uri:
            raise ValueError("A resource template completion reference requires 'uri'")

    def to_sdk(self) -> types.PromptReference | types.ResourceTemplateReference:
        if self.kind == "prompt":
            assert self.name is not None
            return types.PromptReference(name=self.name)
        assert self.uri is not None
        return types.ResourceTemplateReference(uri=self.uri)


@dataclass(slots=True)
class McpCompletion:
    values: list[str] = field(default_factory=list)
    total: int | None = None
    has_more: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"values": self.values}
        if self.total is not None:
            payload["total"] = self.total
        if self.has_more:
            payload["hasMore"] = True
        return payload


TruncationReason = Literal["max_items", "max_pages", "cursor_loop", "deadline"]


@dataclass(slots=True)
class McpEnumeration(Generic[T]):
    """Bounded listing result with explicit truncation information."""

    items: list[T] = field(default_factory=list)
    pages_fetched: int = 0
    truncated: bool = False
    truncation_reason: TruncationReason | None = None
    next_cursor: str | None = None

    @property
    def total_items(self) -> int:
        return len(self.items)

    def to_dict(
        self, *, serializer: Callable[[T], Any] | None = None
    ) -> dict[str, Any]:
        items: list[Any] = []
        for item in self.items:
            if serializer is not None:
                items.append(serializer(item))
            elif hasattr(item, "to_dict"):
                items.append(item.to_dict())
            else:
                items.append(item)
        return {
            "items": items,
            "pages_fetched": self.pages_fetched,
            "truncated": self.truncated,
            "truncation_reason": self.truncation_reason,
            "next_cursor": self.next_cursor,
            "total_items": len(items),
        }


@dataclass(frozen=True, slots=True)
class McpServerCapabilities:
    """Capabilities negotiated from ``initialize`` / ``server/discover``."""

    protocol_version: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    instructions: str | None = None
    tools: bool = False
    tools_list_changed: bool = False
    resources: bool = False
    resources_subscribe: bool = False
    resources_list_changed: bool = False
    prompts: bool = False
    prompts_list_changed: bool = False
    completions: bool = False
    logging: bool = False
    experimental: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def resource_templates(self) -> bool:
        """Resource templates are part of the ``resources`` capability."""
        return self.resources

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "server_name": self.server_name,
            "server_version": self.server_version,
            "instructions": self.instructions,
            "tools": self.tools,
            "tools_list_changed": self.tools_list_changed,
            "resources": self.resources,
            "resources_subscribe": self.resources_subscribe,
            "resources_list_changed": self.resources_list_changed,
            "resource_templates": self.resource_templates,
            "prompts": self.prompts,
            "prompts_list_changed": self.prompts_list_changed,
            "completions": self.completions,
            "logging": self.logging,
            "experimental": self.experimental,
            "raw_capabilities": self.raw,
        }


# ---------------------------------------------------------------------------
# SDK serialization helpers
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Convert an SDK value to plain JSON data, preserving wire aliases."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(by_alias=True, mode="json", exclude_none=True)
        except TypeError:  # pragma: no cover - very old pydantic
            return dump()
    return value


def _payload_bytes(value: Any) -> int:
    """UTF-8 size of a plain value for content-budget accounting."""
    plain = _jsonable(value)
    try:
        return len(json.dumps(plain, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return len(str(plain).encode("utf-8"))


def _first_attr(source: Any, *names: str) -> Any:
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


def _accepts_keyword(func: Any, keyword: str) -> bool:
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return False
    return keyword in parameters


# Detected once at import: these differ between the SDK's 1.x and 2.x APIs.
_LIST_TOOLS_USES_PARAMS = _accepts_keyword(ClientSession.list_tools, "params")
_LIST_RESOURCES_USES_PARAMS = _accepts_keyword(ClientSession.list_resources, "params")
_LIST_TEMPLATES_USES_PARAMS = _accepts_keyword(
    ClientSession.list_resource_templates, "params"
)
_LIST_PROMPTS_USES_PARAMS = _accepts_keyword(ClientSession.list_prompts, "params")
_CALL_TOOL_ALLOWS_INPUT_REQUIRED = _accepts_keyword(
    ClientSession.call_tool, "allow_input_required"
)
_READ_RESOURCE_ALLOWS_INPUT_REQUIRED = _accepts_keyword(
    ClientSession.read_resource, "allow_input_required"
)
_GET_PROMPT_ALLOWS_INPUT_REQUIRED = _accepts_keyword(
    ClientSession.get_prompt, "allow_input_required"
)
_SSE_ACCEPTS_AUTH = _accepts_keyword(sse_client, "auth")
_SSE_ACCEPTS_SESSION_OBSERVER = _accepts_keyword(sse_client, "on_session_created")


def _build_client_info() -> types.Implementation:
    try:
        version = package_version("clouisle-backend")
    except PackageNotFoundError:  # pragma: no cover - source checkout edge case
        version = "0.1.0"
    return types.Implementation(name=MCP_CLIENT_NAME, version=version)


_CLIENT_INFO = _build_client_info()


# ---------------------------------------------------------------------------
# Deadline
# ---------------------------------------------------------------------------


class _Deadline:
    """Monotonic budget shared by connect + requests in one operation."""

    __slots__ = ("label", "total", "_expires")

    def __init__(self, seconds: float, label: str) -> None:
        loop = asyncio.get_running_loop()
        self.total = max(float(seconds), 0.001)
        self._expires = loop.time() + self.total
        self.label = label

    def remaining(self) -> float:
        return self._expires - asyncio.get_running_loop().time()


# ---------------------------------------------------------------------------
# Callback guard
# ---------------------------------------------------------------------------


def _error_data(code: int, message: str) -> types.ErrorData:
    return types.ErrorData(code=code, message=message)


def _schema_requests_secrets(schema: Any) -> bool:
    if not isinstance(schema, Mapping):
        return False
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return False
    for field_name, definition in properties.items():
        haystack = [str(field_name)]
        if isinstance(definition, Mapping):
            for key in ("title", "description"):
                value = definition.get(key)
                if isinstance(value, str):
                    haystack.append(value)
        if any(_SENSITIVE_ELICITATION_FIELD.search(value) for value in haystack):
            return True
    return False


def _url_host_allowed(url: Any, allowed_hosts: frozenset[str]) -> bool:
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
    return parsed.hostname.lower() in allowed_hosts


def _root_allowed(uri: Any, allowlist: tuple[str, ...]) -> bool:
    if uri is None:
        return False
    value = uri if isinstance(uri, str) else str(uri)
    if not value.startswith("file://"):
        return False
    return not allowlist or value in allowlist


class _CallbackGuard:
    """Wraps user-supplied callbacks with deadlines, counters and filtering.

    Every path returns an SDK ``ErrorData`` / explicit decline instead of
    raising, because an exception inside a server-initiated request callback
    would tear down the whole session.
    """

    def __init__(self, callbacks: McpCallbacks) -> None:
        self._callbacks = callbacks
        self._policy = callbacks.policy
        self._sampling_calls = 0
        self._elicitation_calls = 0

    @property
    def roots_enabled(self) -> bool:
        return self._callbacks.roots is not None or bool(self._policy.roots)

    async def sampling(self, context: Any, params: Any) -> Any:
        policy = self._policy
        handler = self._callbacks.sampling
        if handler is None:
            return _error_data(types.INVALID_REQUEST, "Sampling is not supported")
        if self._sampling_calls >= policy.max_sampling_requests:
            logger.warning("MCP sampling request limit reached; refusing request")
            return _error_data(types.INVALID_REQUEST, "Sampling request limit exceeded")
        self._sampling_calls += 1

        if getattr(params, "tools", None) and not policy.sampling_tools:
            logger.warning("MCP sampling requested tool use; refusing request")
            return _error_data(
                types.INVALID_REQUEST, "Sampling tool use is not supported"
            )

        token_field = next(
            (
                name
                for name in ("max_tokens", "maxTokens")
                if getattr(params, name, None) is not None
            ),
            None,
        )
        max_tokens = getattr(params, token_field, None) if token_field else None
        if (
            token_field is not None
            and isinstance(max_tokens, int)
            and max_tokens > policy.sampling_max_tokens
        ):
            try:
                params = params.model_copy(
                    update={token_field: policy.sampling_max_tokens}
                )
            except AttributeError:  # pragma: no cover - defensive
                pass

        try:
            async with asyncio.timeout(policy.max_callback_seconds):
                result = handler(context, params)
                if inspect.isawaitable(result):
                    result = await result
        except TimeoutError:
            logger.warning("MCP sampling handler timed out")
            return _error_data(types.INTERNAL_ERROR, "Sampling request timed out")
        except Exception:
            logger.exception("MCP sampling handler failed")
            return _error_data(types.INTERNAL_ERROR, "Sampling request failed")

        if isinstance(result, types.ErrorData):
            return result
        if isinstance(
            result,
            (types.CreateMessageResult, types.CreateMessageResultWithTools),
        ):
            return result
        logger.error("MCP sampling handler returned an unexpected value")
        return _error_data(types.INTERNAL_ERROR, "Invalid sampling response")

    async def elicitation(self, context: Any, params: Any) -> Any:
        policy = self._policy
        handler = self._callbacks.elicitation
        if handler is None:
            return _error_data(types.INVALID_REQUEST, "Elicitation is not supported")

        mode = getattr(params, "mode", None) or "form"
        if mode not in policy.elicitation_modes:
            logger.warning("Refusing MCP elicitation mode %r", mode)
            return _error_data(
                types.INVALID_REQUEST,
                f"Elicitation mode {mode!r} is not supported",
            )

        if mode == "form" and _schema_requests_secrets(
            _first_attr(params, "requested_schema", "requestedSchema")
        ):
            logger.warning("Declining MCP elicitation that requests sensitive fields")
            return types.ElicitResult(action="decline")

        if mode == "url" and not _url_host_allowed(
            getattr(params, "url", None), policy.elicitation_url_hosts
        ):
            logger.warning("Declining MCP URL elicitation for a non-authorized host")
            return types.ElicitResult(action="decline")

        if self._elicitation_calls >= policy.max_elicitation_requests:
            logger.warning("MCP elicitation limit reached; cancelling request")
            return types.ElicitResult(action="cancel")
        self._elicitation_calls += 1

        try:
            async with asyncio.timeout(policy.max_callback_seconds):
                result = handler(context, params)
                if inspect.isawaitable(result):
                    result = await result
        except TimeoutError:
            logger.warning("MCP elicitation handler timed out")
            return types.ElicitResult(action="cancel")
        except Exception:
            logger.exception("MCP elicitation handler failed")
            return types.ElicitResult(action="cancel")

        if isinstance(result, types.ErrorData):
            return result
        if isinstance(result, types.ElicitResult):
            return result
        logger.error("MCP elicitation handler returned an unexpected value")
        return _error_data(types.INTERNAL_ERROR, "Invalid elicitation response")

    async def list_roots(self, context: Any) -> Any:
        policy = self._policy
        handler = self._callbacks.roots
        if handler is None:
            roots: list[types.Root] = []
            for root in policy.roots:
                if not _root_allowed(root.uri, policy.roots_allowlist):
                    logger.warning(
                        "Dropping configured MCP root outside the allowed scope"
                    )
                    continue
                try:
                    roots.append(root.to_sdk())
                except Exception:
                    logger.warning("Dropping invalid configured MCP root %r", root.uri)
            return types.ListRootsResult(roots=roots)

        try:
            async with asyncio.timeout(policy.max_callback_seconds):
                result = handler(context)
                if inspect.isawaitable(result):
                    result = await result
        except TimeoutError:
            logger.warning("MCP roots handler timed out")
            return _error_data(types.INTERNAL_ERROR, "Roots request timed out")
        except Exception:
            logger.exception("MCP roots handler failed")
            return _error_data(types.INTERNAL_ERROR, "Roots request failed")

        if isinstance(result, types.ErrorData):
            return result
        roots = getattr(result, "roots", None)
        if not isinstance(roots, list):
            logger.error("MCP roots handler returned an unexpected value")
            return _error_data(types.INTERNAL_ERROR, "Invalid roots response")

        filtered: list[types.Root] = []
        for root in roots:
            uri = getattr(root, "uri", None)
            if not _root_allowed(uri, policy.roots_allowlist):
                logger.warning("Dropping MCP root outside the allowed scope")
                continue
            filtered.append(root)
        return types.ListRootsResult(roots=filtered)

    async def notification(self, message: Any) -> None:
        handler = self._callbacks.notification
        if handler is None:
            return
        try:
            async with asyncio.timeout(
                max(min(5.0, self._policy.max_callback_seconds), 0.001)
            ):
                result = handler(message)
                if inspect.isawaitable(result):
                    await result
        except TimeoutError:
            logger.warning("MCP notification handler timed out")
        except Exception:
            logger.exception("MCP notification handler failed")


# ---------------------------------------------------------------------------
# Negotiation
# ---------------------------------------------------------------------------


async def _negotiate(session: ClientSession) -> Any | None:
    """Negotiate the protocol version, returning the handshake result if any."""
    if _negotiate_auto is not None and hasattr(session, "send_discover"):
        await _negotiate_auto(session)
        return getattr(session, "initialize_result", None) or getattr(
            session, "discover_result", None
        )
    # mcp 1.x has no server/discover probe; lightweight/fake sessions that
    # only expose `initialize` take the same path.
    return await session.initialize()


def _read_negotiated(
    session: ClientSession, handshake: Any | None
) -> McpServerCapabilities:
    protocol_version = _first_attr(session, "protocol_version", "protocolVersion")
    if protocol_version is None and handshake is not None:
        protocol_version = _first_attr(handshake, "protocol_version", "protocolVersion")

    server_info = _first_attr(session, "server_info", "serverInfo")
    if server_info is None and handshake is not None:
        server_info = _first_attr(handshake, "server_info", "serverInfo")
    info = _jsonable(server_info) if server_info is not None else None
    if not isinstance(info, Mapping):
        info = {}

    capabilities = _first_attr(session, "server_capabilities")
    if capabilities is None and handshake is not None:
        capabilities = _first_attr(handshake, "capabilities")
    raw = _jsonable(capabilities) if capabilities is not None else None
    if not isinstance(raw, dict):
        raw = {}

    instructions = _first_attr(session, "instructions")
    if instructions is None and handshake is not None:
        instructions = _first_attr(handshake, "instructions")

    def capability(name: str) -> Mapping[str, Any] | None:
        value = raw.get(name)
        return value if isinstance(value, Mapping) else None

    tools = capability("tools")
    resources = capability("resources")
    prompts = capability("prompts")

    return McpServerCapabilities(
        protocol_version=protocol_version
        if isinstance(protocol_version, str)
        else None,
        server_name=info.get("name") if isinstance(info.get("name"), str) else None,
        server_version=info.get("version")
        if isinstance(info.get("version"), str)
        else None,
        instructions=instructions if isinstance(instructions, str) else None,
        tools=tools is not None,
        tools_list_changed=bool(tools.get("listChanged")) if tools else False,
        resources=resources is not None,
        resources_subscribe=bool(resources.get("subscribe")) if resources else False,
        resources_list_changed=bool(resources.get("listChanged"))
        if resources
        else False,
        prompts=prompts is not None,
        prompts_list_changed=bool(prompts.get("listChanged")) if prompts else False,
        completions=capability("completions") is not None,
        logging=capability("logging") is not None,
        experimental=bool(raw.get("experimental")),
        raw=raw,
    )


def _require_capability(capabilities: McpServerCapabilities, capability: str) -> None:
    if not getattr(capabilities, capability):
        raise McpCapabilityUnavailable(capability)


# ---------------------------------------------------------------------------
# Result conversion
# ---------------------------------------------------------------------------


def _content_block(block: Any) -> McpContentBlock:
    block_type = getattr(block, "type", None) or type(block).__name__
    annotations = _jsonable(getattr(block, "annotations", None))
    meta = _jsonable(_first_attr(block, "meta", "_meta"))

    if block_type in _TEXTUAL_CONTENT_TYPES:
        text = getattr(block, "text", None)
        return McpContentBlock(
            type="text",
            text=text if isinstance(text, str) else None,
            annotations=annotations if isinstance(annotations, dict) else None,
            meta=meta if isinstance(meta, dict) else None,
        )

    if block_type in _BINARY_CONTENT_TYPES:
        data = getattr(block, "data", None)
        return McpContentBlock(
            type=block_type,
            data=data if isinstance(data, str) else None,
            mime_type=_first_attr(block, "mime_type", "mimeType"),
            annotations=annotations if isinstance(annotations, dict) else None,
            meta=meta if isinstance(meta, dict) else None,
        )

    if block_type == "resource_link":
        size = getattr(block, "size", None)
        return McpContentBlock(
            type="resource_link",
            uri=_first_attr(block, "uri"),
            name=_first_attr(block, "name"),
            title=_first_attr(block, "title"),
            description=_first_attr(block, "description"),
            mime_type=_first_attr(block, "mime_type", "mimeType"),
            size=size if isinstance(size, int) else None,
            annotations=annotations if isinstance(annotations, dict) else None,
            meta=meta if isinstance(meta, dict) else None,
        )

    if block_type == "resource":
        resource = _jsonable(getattr(block, "resource", None))
        if not isinstance(resource, dict):
            resource = {}
        return McpContentBlock(
            type="resource",
            uri=resource.get("uri"),
            mime_type=resource.get("mimeType") or resource.get("mime_type"),
            resource=resource,
            annotations=annotations if isinstance(annotations, dict) else None,
            meta=meta if isinstance(meta, dict) else None,
        )

    raw = _jsonable(block)
    return McpContentBlock(
        type=str(block_type),
        raw=raw if isinstance(raw, dict) else {"value": raw},
        annotations=annotations if isinstance(annotations, dict) else None,
        meta=meta if isinstance(meta, dict) else None,
    )


def _legacy_result(blocks: Sequence[McpContentBlock]) -> Any:
    """Rebuild the historical ``result`` payload without dropping blocks."""
    values: list[Any] = []
    for block in blocks:
        if block.type in _TEXTUAL_CONTENT_TYPES and block.text is not None:
            values.append(block.text)
        elif block.type in _BINARY_CONTENT_TYPES and block.data is not None:
            values.append(block.data)
        else:
            # Resource links / embedded resources were previously dropped
            # silently; emit an explicit descriptor instead.
            values.append(block.to_dict())
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def _tool_info(tool: Any) -> McpToolInfo:
    input_schema = _first_attr(tool, "input_schema", "inputSchema")
    output_schema = _first_attr(tool, "output_schema", "outputSchema")
    annotations = _jsonable(getattr(tool, "annotations", None))
    meta = _jsonable(_first_attr(tool, "meta", "_meta"))
    title = getattr(tool, "title", None)
    return McpToolInfo(
        name=str(getattr(tool, "name", "")),
        description=getattr(tool, "description", None),
        parameters=input_schema if isinstance(input_schema, dict) else {},
        title=title if isinstance(title, str) else None,
        output_schema=output_schema if isinstance(output_schema, dict) else None,
        annotations=annotations if isinstance(annotations, dict) else None,
        meta=meta if isinstance(meta, dict) else None,
    )


def _resource_info(resource: Any) -> McpResourceInfo:
    annotations = _jsonable(getattr(resource, "annotations", None))
    meta = _jsonable(_first_attr(resource, "meta", "_meta"))
    size = getattr(resource, "size", None)
    return McpResourceInfo(
        uri=str(getattr(resource, "uri", "")),
        name=getattr(resource, "name", None),
        title=getattr(resource, "title", None),
        description=getattr(resource, "description", None),
        mime_type=_first_attr(resource, "mime_type", "mimeType"),
        size=size if isinstance(size, int) else None,
        annotations=annotations if isinstance(annotations, dict) else None,
        meta=meta if isinstance(meta, dict) else None,
    )


def _resource_template_info(template: Any) -> McpResourceTemplateInfo:
    annotations = _jsonable(getattr(template, "annotations", None))
    meta = _jsonable(_first_attr(template, "meta", "_meta"))
    return McpResourceTemplateInfo(
        uri_template=str(_first_attr(template, "uri_template", "uriTemplate") or ""),
        name=getattr(template, "name", None),
        title=getattr(template, "title", None),
        description=getattr(template, "description", None),
        mime_type=_first_attr(template, "mime_type", "mimeType"),
        annotations=annotations if isinstance(annotations, dict) else None,
        meta=meta if isinstance(meta, dict) else None,
    )


def _prompt_info(prompt: Any) -> McpPromptInfo:
    arguments: list[McpPromptArgument] = []
    for argument in getattr(prompt, "arguments", None) or []:
        arguments.append(
            McpPromptArgument(
                name=str(getattr(argument, "name", "")),
                description=getattr(argument, "description", None),
                required=bool(getattr(argument, "required", False)),
            )
        )
    meta = _jsonable(_first_attr(prompt, "meta", "_meta"))
    return McpPromptInfo(
        name=str(getattr(prompt, "name", "")),
        title=getattr(prompt, "title", None),
        description=getattr(prompt, "description", None),
        arguments=arguments,
        meta=meta if isinstance(meta, dict) else None,
    )


def _resource_contents(contents: Any) -> McpResourceContents:
    meta = _jsonable(_first_attr(contents, "meta", "_meta"))
    blob = getattr(contents, "blob", None)
    text = getattr(contents, "text", None)
    return McpResourceContents(
        uri=str(getattr(contents, "uri", "")),
        text=text if isinstance(text, str) else None,
        blob=blob if isinstance(blob, str) else None,
        mime_type=_first_attr(contents, "mime_type", "mimeType"),
        meta=meta if isinstance(meta, dict) else None,
    )


def _next_cursor(result: Any) -> str | None:
    cursor = _first_attr(result, "next_cursor", "nextCursor")
    return cursor if isinstance(cursor, str) and cursor else None


def _input_required_info(method: str, result: Any) -> McpInputRequiredInfo | None:
    if getattr(result, "result_type", None) != "input_required" and (
        type(result).__name__ != "InputRequiredResult"
    ):
        return None
    raw_requests = getattr(result, "input_requests", None)
    requests: dict[str, Any] = {}
    if isinstance(raw_requests, Mapping):
        requests = {str(key): _jsonable(value) for key, value in raw_requests.items()}
    request_state = getattr(result, "request_state", None)
    return McpInputRequiredInfo(
        method=method,
        requests=requests,
        request_state=request_state if isinstance(request_state, str) else None,
    )


def _enforce_content_limits(
    sizes: Sequence[tuple[str, int]],
    limits: McpContentLimits,
    *,
    source: str,
) -> None:
    total = 0
    for item_source, size in sizes:
        if size > limits.max_block_bytes:
            raise McpContentTooLarge(
                f"MCP content block exceeds the per-block byte limit for {source}",
                bytes_received=size,
                byte_limit=limits.max_block_bytes,
                source=item_source,
            )
        total += size
    if total > limits.max_total_bytes:
        raise McpContentTooLarge(
            f"MCP content exceeds the total byte limit for {source}",
            bytes_received=total,
            byte_limit=limits.max_total_bytes,
            source=source,
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class McpClient:
    """MCP client for a single server configuration.

    One instance is cheap: every operation opens its own negotiated session, so
    instances hold no live connection and no per-identity state.
    """

    def __init__(
        self,
        config: dict[str, Any],
        *,
        timeouts: McpTimeouts | None = None,
        enumeration_limits: McpEnumerationLimits | None = None,
        content_limits: McpContentLimits | None = None,
        callbacks: McpCallbacks | None = None,
        headers: Mapping[str, str] | None = None,
        auth: Any | None = None,
        on_session_created: Callable[[str], None] | None = None,
    ) -> None:
        """
        Args:
            config: MCP configuration dict with:
                - transport: "stdio" | "sse" | "http"
                - command: Command to run (for stdio)
                - args: Command arguments (for stdio)
                - env: Environment variables (for stdio)
                - url: Server URL (for sse/http)
                - headers: HTTP headers (for sse/http)
            timeouts: Explicit connect/request/enumeration budgets.
            enumeration_limits: Page/item bounds for paginated listings.
            content_limits: Byte budgets for resource and prompt content.
            callbacks: In-process sampling/elicitation/roots/notification hooks.
            headers: Connection headers supplied at runtime (for example an
                OAuth bearer token resolved for the current identity). These
                override equally named ``config['headers']`` entries and are
                never persisted or logged by this module.
            auth: Optional transport auth object. For HTTP transports it is
                forwarded to the SDK's HTTP client / SSE transport; for stdio
                it is ignored because the subprocess owns its own credentials.
            on_session_created: Optional SSE session-id observer. The session
                runtime may use it to bind a connection; it is not durable.
        """
        self.config = config
        self.transport = config.get("transport", "stdio")
        self.timeouts = timeouts or DEFAULT_TIMEOUTS
        self.enumeration_limits = enumeration_limits or DEFAULT_ENUMERATION_LIMITS
        self.content_limits = content_limits or DEFAULT_CONTENT_LIMITS
        self.callbacks = callbacks or McpCallbacks()
        self.headers: dict[str, str] = dict(headers or {})
        self.auth = auth
        self.on_session_created = on_session_created
        self.last_session_id: str | None = None

    def _http_headers(self) -> dict[str, str] | None:
        """Merge configured headers with runtime-injected headers."""
        configured = self.config.get("headers") or {}
        merged = {str(key): str(value) for key, value in configured.items()}
        merged.update(self.headers)
        return merged or None

    # -- transports ---------------------------------------------------------

    @asynccontextmanager
    async def connect(
        self, *, timeout: float | None = None
    ) -> AsyncIterator[ClientSession]:
        """Yield a live, negotiated ``ClientSession``.

        The session is scoped to this context manager; server-initiated
        callbacks registered via :class:`McpCallbacks` are only answerable
        while it is open. JSON-RPC sessions are not durable across process
        death.
        """
        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.request,
            "connect",
        )
        async with self._open(deadline) as (session, _capabilities):
            yield session

    @asynccontextmanager
    async def _open(
        self, deadline: _Deadline
    ) -> AsyncIterator[tuple[ClientSession, McpServerCapabilities]]:
        guard = _CallbackGuard(self.callbacks)
        async with AsyncExitStack() as stack:
            connect_budget = min(
                self.timeouts.connect, max(deadline.remaining(), 0.001)
            )
            try:
                async with asyncio.timeout(connect_budget):
                    read_stream, write_stream = await stack.enter_async_context(
                        self._transport()
                    )
            except TimeoutError as exc:
                raise McpTimeout(
                    "Timed out connecting to the MCP server",
                    timeout_seconds=connect_budget,
                ) from exc

            session = ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=max(
                    min(
                        max(self.timeouts.request, deadline.total),
                        deadline.remaining(),
                    ),
                    0.001,
                ),
                sampling_callback=guard.sampling
                if self.callbacks.sampling is not None
                else None,
                elicitation_callback=guard.elicitation
                if self.callbacks.elicitation is not None
                else None,
                list_roots_callback=guard.list_roots if guard.roots_enabled else None,
                message_handler=guard.notification
                if self.callbacks.notification is not None
                else None,
                client_info=_CLIENT_INFO,
            )

            init_budget = max(min(self.timeouts.connect, deadline.remaining()), 0.001)
            try:
                async with asyncio.timeout(init_budget):
                    await stack.enter_async_context(session)
                    handshake = await _negotiate(session)
            except TimeoutError as exc:
                raise McpTimeout(
                    "Timed out during MCP initialization",
                    timeout_seconds=init_budget,
                ) from exc

            capabilities = _read_negotiated(session, handshake)
            logger.debug(
                "MCP session negotiated transport=%s protocol=%s tools=%s "
                "resources=%s prompts=%s completions=%s",
                self.transport,
                capabilities.protocol_version,
                capabilities.tools,
                capabilities.resources,
                capabilities.prompts,
                capabilities.completions,
            )
            yield session, capabilities

    @asynccontextmanager
    async def _transport(self) -> AsyncIterator[tuple[Any, Any]]:
        if self.transport == "stdio":
            async with self._connect_stdio() as streams:
                yield streams
        elif self.transport == "sse":
            async with self._connect_sse() as streams:
                yield streams
        elif self.transport == "http":
            async with self._connect_http() as streams:
                yield streams
        else:
            raise McpInvalidRequest(
                f"Unsupported transport: {self.transport}",
                reason="configuration",
            )

    @asynccontextmanager
    async def _connect_stdio(self) -> AsyncIterator[tuple[Any, Any]]:
        command = self.config.get("command")
        args = self.config.get("args", [])
        env = self.config.get("env", {})

        if not command:
            raise McpInvalidRequest(
                "Command is required for stdio transport",
                reason="configuration",
            )

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env if env else None,
        )

        # stdio executes a server-side program. Command/args/env must come from
        # an administrator-reviewed server definition; this adapter adds no
        # command expansion of its own. The SDK still merges its documented
        # default environment, so deployment must keep that default minimal.
        async with stdio_client(server_params, errlog=sys.__stderr__) as (
            read_stream,
            write_stream,
        ):
            yield read_stream, write_stream

    @asynccontextmanager
    async def _connect_sse(self) -> AsyncIterator[tuple[Any, Any]]:
        url = self.config.get("url")
        headers = self._http_headers()

        if not url:
            raise McpInvalidRequest(
                "URL is required for SSE transport",
                reason="configuration",
            )

        kwargs: dict[str, Any] = {}
        if headers:
            kwargs["headers"] = headers
        if self.auth is not None:
            if _SSE_ACCEPTS_AUTH:
                kwargs["auth"] = self.auth
            else:  # pragma: no cover - mcp 1.x
                logger.warning(
                    "Installed MCP SDK cannot attach auth to SSE; pass it via headers"
                )
        if self.on_session_created is not None and _SSE_ACCEPTS_SESSION_OBSERVER:
            kwargs["on_session_created"] = self._remember_session_id

        async with sse_client(url, **kwargs) as (
            read_stream,
            write_stream,
        ):
            yield read_stream, write_stream

    def _remember_session_id(self, session_id: str) -> None:
        self.last_session_id = session_id
        observer = self.on_session_created
        if observer is not None:
            try:
                observer(session_id)
            except Exception:
                logger.exception("MCP session observer failed")

    @asynccontextmanager
    async def _connect_http(self) -> AsyncIterator[tuple[Any, Any]]:
        url = self.config.get("url")
        headers = self._http_headers()

        if not url:
            raise McpInvalidRequest(
                "URL is required for HTTP transport",
                reason="configuration",
            )

        async with AsyncExitStack() as stack:
            http_client = None
            if headers or self.auth is not None:
                client_kwargs: dict[str, Any] = {"headers": headers}
                if self.auth is not None:
                    client_kwargs["auth"] = self.auth
                http_client = create_mcp_http_client(**client_kwargs)
                await stack.enter_async_context(http_client)

            streams = await stack.enter_async_context(
                streamablehttp_client(url, http_client=http_client)
            )
            # mcp 2.x yields (read, write); 1.x also yields a session-id getter.
            read_stream, write_stream = streams[0], streams[1]
            if len(streams) > 2 and callable(streams[2]):
                try:
                    self.last_session_id = streams[2]()
                except Exception:  # pragma: no cover - transport detail
                    logger.debug("Unable to read MCP HTTP session id")
            yield read_stream, write_stream

    # -- capabilities -------------------------------------------------------

    def _request_budget(self, deadline: _Deadline) -> float:
        """Remaining request time, capped by the operation's own budget.

        A caller-supplied ``timeout`` (for example the approval window of an
        MCP tool call) must not be cut short by the default per-phase request
        timeout; the narrower of the two would make human approval impossible.
        """
        cap = max(self.timeouts.request, deadline.total)
        return max(min(cap, deadline.remaining()), 0.001)

    async def get_capabilities(
        self, *, timeout: float | None = None
    ) -> McpServerCapabilities:
        """Connect, negotiate, and return the server's advertised capabilities."""
        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.request,
            "capabilities",
        )
        async with self._open(deadline) as (_session, capabilities):
            return capabilities

    # -- enumeration --------------------------------------------------------

    async def _enumerate(
        self,
        fetch_page: Callable[[str | None], Awaitable[tuple[list[T], str | None]]],
        *,
        limits: McpEnumerationLimits,
        deadline: _Deadline,
        start_cursor: str | None = None,
    ) -> McpEnumeration[T]:
        items: list[T] = []
        cursor = start_cursor or None
        # Seeding the start cursor makes a server that loops back to it fail
        # closed instead of re-fetching the first page forever.
        seen_cursors: set[str] = {cursor} if cursor else set()
        pages = 0
        truncated = False
        reason: TruncationReason | None = None
        resume_cursor: str | None = None

        while True:
            if len(items) >= limits.max_items:
                truncated, reason, resume_cursor = True, "max_items", cursor
                break
            if pages >= limits.max_pages:
                truncated, reason, resume_cursor = True, "max_pages", cursor
                break
            if deadline.remaining() <= 0:
                truncated, reason, resume_cursor = True, "deadline", cursor
                break
            try:
                page_items, page_next = await fetch_page(cursor)
            except (TimeoutError, McpTimeout):
                if not items:
                    raise McpTimeout(
                        f"MCP {deadline.label} deadline expired",
                        timeout_seconds=deadline.total,
                    ) from None
                # The in-flight page was cancelled; resume from it, not past it.
                truncated, reason, resume_cursor = True, "deadline", cursor
                break

            pages += 1
            for item in page_items:
                if len(items) >= limits.max_items:
                    truncated, reason = True, "max_items"
                    # The current page was only partly consumed and MCP has no
                    # offset, so no cursor can resume exactly here.
                    resume_cursor = None
                    break
                items.append(item)
            if truncated:
                break

            if not page_next:
                resume_cursor = None
                break
            if page_next in seen_cursors:
                truncated, reason, resume_cursor = True, "cursor_loop", None
                break
            seen_cursors.add(page_next)
            cursor = page_next

        if truncated:
            logger.warning(
                "MCP %s listing truncated after %s page(s), %s item(s): %s",
                deadline.label,
                pages,
                len(items),
                reason,
            )

        return McpEnumeration(
            items=items,
            pages_fetched=pages,
            truncated=truncated,
            truncation_reason=reason,
            next_cursor=resume_cursor if truncated else None,
        )

    async def _fetch_page(
        self,
        method: Callable[..., Awaitable[Any]],
        cursor: str | None,
        *,
        uses_params: bool,
        deadline: _Deadline,
    ) -> Any:
        budget = self._request_budget(deadline)
        async with asyncio.timeout(budget):
            if uses_params:
                params = (
                    types.PaginatedRequestParams(cursor=cursor)
                    if cursor is not None
                    else None
                )
                return await method(params=params)
            return await method(cursor=cursor)

    async def enumerate_tools(
        self,
        *,
        timeout: float | None = None,
        limits: McpEnumerationLimits | None = None,
        start_cursor: str | None = None,
    ) -> McpEnumeration[McpToolInfo]:
        """List tools across all pages, bounded by ``limits``."""
        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.enumeration,
            _LIST_TOOLS,
        )
        effective_limits = limits or self.enumeration_limits
        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "tools")

            async def fetch(cursor: str | None) -> tuple[list[McpToolInfo], str | None]:
                result = await self._fetch_page(
                    session.list_tools,
                    cursor,
                    uses_params=_LIST_TOOLS_USES_PARAMS,
                    deadline=deadline,
                )
                tools = [
                    _tool_info(tool) for tool in getattr(result, "tools", None) or []
                ]
                return tools, _next_cursor(result)

            return await self._enumerate(
                fetch,
                limits=effective_limits,
                deadline=deadline,
                start_cursor=start_cursor,
            )

    async def list_tools(self) -> list[McpToolInfo]:
        """List tools, preserving the historical ``list[McpToolInfo]`` shape.

        Truncation is logged explicitly; call :meth:`enumerate_tools` when the
        caller needs the truncation metadata.
        """
        enumerated = await self.enumerate_tools()
        return enumerated.items

    async def enumerate_resources(
        self,
        *,
        timeout: float | None = None,
        limits: McpEnumerationLimits | None = None,
        start_cursor: str | None = None,
    ) -> McpEnumeration[McpResourceInfo]:
        """List concrete resources (``resources/list``)."""
        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.enumeration,
            _LIST_RESOURCES,
        )
        effective_limits = limits or self.enumeration_limits
        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "resources")

            async def fetch(
                cursor: str | None,
            ) -> tuple[list[McpResourceInfo], str | None]:
                result = await self._fetch_page(
                    session.list_resources,
                    cursor,
                    uses_params=_LIST_RESOURCES_USES_PARAMS,
                    deadline=deadline,
                )
                resources = [
                    _resource_info(resource)
                    for resource in getattr(result, "resources", None) or []
                ]
                return resources, _next_cursor(result)

            return await self._enumerate(
                fetch,
                limits=effective_limits,
                deadline=deadline,
                start_cursor=start_cursor,
            )

    async def enumerate_resource_templates(
        self,
        *,
        timeout: float | None = None,
        limits: McpEnumerationLimits | None = None,
        start_cursor: str | None = None,
    ) -> McpEnumeration[McpResourceTemplateInfo]:
        """List resource templates (``resources/templates/list``).

        Templates are a separate listing: never assume ``resources/list``
        enumerates everything a template can address.
        """
        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.enumeration,
            _LIST_RESOURCE_TEMPLATES,
        )
        effective_limits = limits or self.enumeration_limits
        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "resources")

            async def fetch(
                cursor: str | None,
            ) -> tuple[list[McpResourceTemplateInfo], str | None]:
                result = await self._fetch_page(
                    session.list_resource_templates,
                    cursor,
                    uses_params=_LIST_TEMPLATES_USES_PARAMS,
                    deadline=deadline,
                )
                templates = [
                    _resource_template_info(template)
                    for template in _first_attr(
                        result, "resource_templates", "resourceTemplates"
                    )
                    or []
                ]
                return templates, _next_cursor(result)

            return await self._enumerate(
                fetch,
                limits=effective_limits,
                deadline=deadline,
                start_cursor=start_cursor,
            )

    async def enumerate_prompts(
        self,
        *,
        timeout: float | None = None,
        limits: McpEnumerationLimits | None = None,
        start_cursor: str | None = None,
    ) -> McpEnumeration[McpPromptInfo]:
        """List prompts (``prompts/list``)."""
        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.enumeration,
            _LIST_PROMPTS,
        )
        effective_limits = limits or self.enumeration_limits
        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "prompts")

            async def fetch(
                cursor: str | None,
            ) -> tuple[list[McpPromptInfo], str | None]:
                result = await self._fetch_page(
                    session.list_prompts,
                    cursor,
                    uses_params=_LIST_PROMPTS_USES_PARAMS,
                    deadline=deadline,
                )
                prompts = [
                    _prompt_info(prompt)
                    for prompt in getattr(result, "prompts", None) or []
                ]
                return prompts, _next_cursor(result)

            return await self._enumerate(
                fetch,
                limits=effective_limits,
                deadline=deadline,
                start_cursor=start_cursor,
            )

    # -- resources & prompts ------------------------------------------------

    async def read_resource(
        self,
        uri: str,
        *,
        timeout: float | None = None,
        limits: McpContentLimits | None = None,
    ) -> list[McpResourceContents]:
        """Read a resource URI.

        The URI is forwarded verbatim to the MCP server; this adapter performs
        no local downloads or URI rewriting.
        """
        if not isinstance(uri, str) or not uri.strip():
            raise McpInvalidRequest(
                "Resource URI is required",
                reason="resource_uri",
            )
        if _URI_TEMPLATE_MARKER.search(uri):
            raise McpInvalidRequest(
                "Resource URI still contains an unexpanded template variable",
                reason="resource_uri",
            )

        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.request,
            _READ_RESOURCE,
        )
        kwargs: dict[str, Any] = {}
        if _READ_RESOURCE_ALLOWS_INPUT_REQUIRED:
            kwargs["allow_input_required"] = True

        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "resources")
            budget = self._request_budget(deadline)
            try:
                async with asyncio.timeout(budget):
                    result = await session.read_resource(uri, **kwargs)
            except TimeoutError as exc:
                raise McpTimeout(
                    "Timed out reading MCP resource",
                    timeout_seconds=budget,
                ) from exc

        info = _input_required_info(_READ_RESOURCE, result)
        if info is not None:
            raise McpInputRequired(info)

        contents = [
            _resource_contents(entry)
            for entry in getattr(result, "contents", None) or []
        ]
        _enforce_content_limits(
            [(entry.uri or uri, entry.byte_size()) for entry in contents],
            limits or self.content_limits,
            source=uri,
        )
        return contents

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
        limits: McpContentLimits | None = None,
    ) -> McpPromptResult:
        """Fetch and render a prompt template.

        Returned messages are untrusted server content and must be previewed
        before being applied to a conversation.
        """
        if not isinstance(name, str) or not name.strip():
            raise McpInvalidRequest("Prompt name is required")

        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.request,
            _GET_PROMPT,
        )
        kwargs: dict[str, Any] = {}
        if _GET_PROMPT_ALLOWS_INPUT_REQUIRED:
            kwargs["allow_input_required"] = True

        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "prompts")
            budget = self._request_budget(deadline)
            try:
                async with asyncio.timeout(budget):
                    result = await session.get_prompt(name, arguments, **kwargs)
            except TimeoutError as exc:
                raise McpTimeout(
                    "Timed out fetching MCP prompt",
                    timeout_seconds=budget,
                ) from exc

        info = _input_required_info(_GET_PROMPT, result)
        if info is not None:
            raise McpInputRequired(info)

        messages = [
            McpPromptMessage(
                role=str(getattr(message, "role", "")),
                content=_content_block(getattr(message, "content", None)),
            )
            for message in getattr(result, "messages", None) or []
        ]
        _enforce_content_limits(
            [
                (f"prompt:{name}:{index}", message.content.byte_size())
                for index, message in enumerate(messages)
            ],
            limits or self.content_limits,
            source=f"prompt:{name}",
        )
        meta = _jsonable(_first_attr(result, "meta", "_meta"))
        description = getattr(result, "description", None)
        return McpPromptResult(
            messages=messages,
            description=description if isinstance(description, str) else None,
            meta=meta if isinstance(meta, dict) else None,
        )

    async def complete(
        self,
        reference: McpCompletionReference,
        argument_name: str,
        argument_value: str,
        *,
        context_arguments: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> McpCompletion:
        """Request argument completion for a prompt or resource template."""
        if not isinstance(argument_name, str) or not argument_name:
            raise McpInvalidRequest("Completion argument name is required")

        deadline = _Deadline(
            timeout if timeout is not None else self.timeouts.request,
            _COMPLETE,
        )

        async with self._open(deadline) as (session, capabilities):
            _require_capability(capabilities, "completions")
            budget = self._request_budget(deadline)
            try:
                async with asyncio.timeout(budget):
                    result = await session.complete(
                        ref=reference.to_sdk(),
                        argument={
                            "name": argument_name,
                            "value": argument_value,
                        },
                        context_arguments=context_arguments,
                    )
            except TimeoutError as exc:
                raise McpTimeout(
                    "Timed out completing MCP argument",
                    timeout_seconds=budget,
                ) from exc

        completion = getattr(result, "completion", None)
        values = getattr(completion, "values", None) or []
        total = getattr(completion, "total", None)
        has_more = getattr(completion, "has_more", None)
        if has_more is None:
            has_more = getattr(completion, "hasMore", False)
        return McpCompletion(
            values=[str(value) for value in values],
            total=total if isinstance(total, int) else None,
            has_more=bool(has_more),
        )

    # -- tools --------------------------------------------------------------

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout: float = 60.0,
    ) -> McpToolResult:
        """Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            timeout: Overall connect + call budget in seconds

        Returns:
            McpToolResult with success status and result/error
        """
        deadline = _Deadline(timeout, f"{_CALL} {tool_name}")
        kwargs: dict[str, Any] = {}
        if _CALL_TOOL_ALLOWS_INPUT_REQUIRED:
            kwargs["allow_input_required"] = True

        try:
            async with self._open(deadline) as (session, capabilities):
                _require_capability(capabilities, "tools")
                budget = self._request_budget(deadline)
                try:
                    async with asyncio.timeout(budget):
                        result = await session.call_tool(tool_name, arguments, **kwargs)
                except TimeoutError as exc:
                    raise McpTimeout(
                        f"Tool execution timed out after {timeout} seconds",
                        timeout_seconds=timeout,
                    ) from exc

            info = _input_required_info(_CALL, result)
            if info is not None:
                logger.warning(
                    "MCP tool %s requires client input before completing", tool_name
                )
                raise McpInputRequired(info)

            return self._tool_result_from_sdk(result, limits=self.content_limits)

        except McpInputRequired as exc:
            logger.warning("MCP tool %s requires input: %s", tool_name, exc)
            return McpToolResult(
                success=False,
                error=resolve_user_visible_error(
                    None, fallback_key="mcp_tool_execution_failed"
                ),
                input_required=exc.info,
            )
        except McpContentTooLarge as exc:
            logger.warning(
                "MCP tool %s result exceeded byte budgets: %s", tool_name, exc
            )
            return McpToolResult(
                success=False,
                error=resolve_user_visible_error(
                    None, fallback_key="mcp_content_too_large"
                ),
            )
        except McpCapabilityUnavailable as exc:
            logger.warning("MCP tool %s unavailable: %s", tool_name, exc)
            return McpToolResult(
                success=False,
                error=resolve_user_visible_error(
                    None, fallback_key="mcp_tool_execution_failed"
                ),
            )
        except McpTimeout as exc:
            logger.warning("MCP tool %s timed out: %s", tool_name, exc)
            return McpToolResult(
                success=False,
                error=resolve_user_visible_error(
                    f"Tool execution timed out after {timeout} seconds",
                    fallback_key="request_timeout",
                ),
            )
        except TimeoutError:
            return McpToolResult(
                success=False,
                error=resolve_user_visible_error(
                    f"Tool execution timed out after {timeout} seconds",
                    fallback_key="request_timeout",
                ),
            )
        except Exception as e:
            logger.exception("MCP tool execution error")
            return McpToolResult(
                success=False,
                error=exception_to_user_message(
                    e,
                    fallback_key="mcp_tool_execution_failed",
                ),
            )

    @staticmethod
    def _tool_result_from_sdk(
        result: Any, *, limits: McpContentLimits | None = None
    ) -> McpToolResult:
        is_error = _first_attr(result, "is_error", "isError")
        blocks = [
            _content_block(block) for block in getattr(result, "content", None) or []
        ]
        structured = _first_attr(result, "structured_content", "structuredContent")
        sizes = [
            (f"tool-result:{index}", block.byte_size())
            for index, block in enumerate(blocks)
        ]
        if structured is not None:
            sizes.append(("tool-result:structured", _payload_bytes(structured)))
        _enforce_content_limits(
            sizes, limits or DEFAULT_CONTENT_LIMITS, source="tool-result"
        )

        if is_error:
            error_text = "".join(
                block.text
                for block in blocks
                if block.type in _TEXTUAL_CONTENT_TYPES and block.text
            )
            return McpToolResult(
                success=False,
                error=resolve_user_visible_error(error_text),
                is_error=True,
                content=blocks,
                structured_content=structured,
            )

        legacy_result = _legacy_result(blocks)
        if legacy_result is None and structured is not None:
            # A structured-only result must not become ``None`` for callers
            # that only read ``result``.
            legacy_result = structured
        return McpToolResult(
            success=True,
            result=legacy_result,
            content=blocks,
            structured_content=structured,
        )


# ---------------------------------------------------------------------------
# Compatible module-level helpers
# ---------------------------------------------------------------------------


def _client(
    mcp_config: dict[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
    enumeration_limits: McpEnumerationLimits | None = None,
    content_limits: McpContentLimits | None = None,
) -> McpClient:
    """Build a client with runtime-supplied credentials and hooks.

    ``headers``/``auth`` let the connection resolver inject per-identity
    secrets without mutating the persisted tool configuration; ``callbacks``
    registers the protocol hooks for server-initiated requests.
    """
    if (
        headers is None
        and auth is None
        and callbacks is None
        and timeouts is None
        and enumeration_limits is None
        and content_limits is None
    ):
        return McpClient(mcp_config)
    return McpClient(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
        enumeration_limits=enumeration_limits,
        content_limits=content_limits,
    )


async def execute_mcp_tool(
    mcp_config: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 60.0,
    *,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpToolResult:
    """
    Execute an MCP tool.

    This is a convenience function that creates a client and executes a tool.

    Args:
        mcp_config: MCP server configuration
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        timeout: Execution timeout in seconds
        headers: Runtime-injected connection headers (for example a bearer
            token resolved for the current identity).
        auth: Optional transport auth object forwarded to HTTP transports.
        callbacks: In-process sampling/elicitation/roots hooks.
        timeouts: Optional connect/request budgets.

    Returns:
        McpToolResult with success status and result/error
    """
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.execute_tool(tool_name, arguments, timeout)


async def list_mcp_tools(
    mcp_config: dict[str, Any],
    *,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
    timeout: float | None = None,
    limits: McpEnumerationLimits | None = None,
) -> list[McpToolInfo]:
    """
    List tools available from an MCP server.

    Args:
        mcp_config: MCP server configuration
        headers: Runtime-injected connection headers.
        auth: Optional transport auth object for HTTP transports.
        callbacks: In-process protocol hooks.
        timeouts: Optional connect/request budgets.
        timeout: Optional end-to-end enumeration budget.
        limits: Optional page/item bounds.

    Returns:
        List of tool information
    """
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    if timeout is None and limits is None:
        return await client.list_tools()
    enumerated = await client.enumerate_tools(timeout=timeout, limits=limits)
    return enumerated.items


# ---------------------------------------------------------------------------
# Extended module-level helpers
# ---------------------------------------------------------------------------


async def probe_mcp_capabilities(
    mcp_config: dict[str, Any],
    *,
    timeout: float | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpServerCapabilities:
    """Negotiate a session and return the server's advertised capabilities."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.get_capabilities(timeout=timeout)


async def enumerate_mcp_tools(
    mcp_config: dict[str, Any],
    *,
    timeout: float | None = None,
    limits: McpEnumerationLimits | None = None,
    start_cursor: str | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpEnumeration[McpToolInfo]:
    """List MCP tools with explicit pagination/truncation metadata."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.enumerate_tools(
        timeout=timeout, limits=limits, start_cursor=start_cursor
    )


async def enumerate_mcp_resources(
    mcp_config: dict[str, Any],
    *,
    timeout: float | None = None,
    limits: McpEnumerationLimits | None = None,
    start_cursor: str | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpEnumeration[McpResourceInfo]:
    """List MCP resources with explicit pagination/truncation metadata."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.enumerate_resources(
        timeout=timeout, limits=limits, start_cursor=start_cursor
    )


async def enumerate_mcp_resource_templates(
    mcp_config: dict[str, Any],
    *,
    timeout: float | None = None,
    limits: McpEnumerationLimits | None = None,
    start_cursor: str | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpEnumeration[McpResourceTemplateInfo]:
    """List MCP resource templates with explicit pagination metadata."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.enumerate_resource_templates(
        timeout=timeout, limits=limits, start_cursor=start_cursor
    )


async def enumerate_mcp_prompts(
    mcp_config: dict[str, Any],
    *,
    timeout: float | None = None,
    limits: McpEnumerationLimits | None = None,
    start_cursor: str | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpEnumeration[McpPromptInfo]:
    """List MCP prompts with explicit pagination/truncation metadata."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.enumerate_prompts(
        timeout=timeout, limits=limits, start_cursor=start_cursor
    )


async def read_mcp_resource(
    mcp_config: dict[str, Any],
    uri: str,
    *,
    timeout: float | None = None,
    limits: McpContentLimits | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> list[McpResourceContents]:
    """Read an MCP resource by URI, enforcing content byte budgets."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.read_resource(uri, timeout=timeout, limits=limits)


async def get_mcp_prompt(
    mcp_config: dict[str, Any],
    name: str,
    arguments: dict[str, str] | None = None,
    *,
    timeout: float | None = None,
    limits: McpContentLimits | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpPromptResult:
    """Fetch and render an MCP prompt, enforcing content byte budgets."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.get_prompt(name, arguments, timeout=timeout, limits=limits)


async def complete_mcp_argument(
    mcp_config: dict[str, Any],
    reference: McpCompletionReference,
    argument_name: str,
    argument_value: str,
    *,
    context_arguments: dict[str, str] | None = None,
    timeout: float | None = None,
    headers: Mapping[str, str] | None = None,
    auth: Any | None = None,
    callbacks: McpCallbacks | None = None,
    timeouts: McpTimeouts | None = None,
) -> McpCompletion:
    """Request MCP argument completion for a prompt or resource template."""
    client = _client(
        mcp_config,
        headers=headers,
        auth=auth,
        callbacks=callbacks,
        timeouts=timeouts,
    )
    return await client.complete(
        reference,
        argument_name,
        argument_value,
        context_arguments=context_arguments,
        timeout=timeout,
    )
