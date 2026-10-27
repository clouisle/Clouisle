"""Schemas for the authenticated MCP operations API.

The request models intentionally accept **no** server configuration: transport,
command, URL, headers and environment variables always come from the stored
:class:`~app.models.tool.Tool` row. A client may only select an identity
(``connection_mode`` / ``connection_id``); credentials are resolved by the
backend connection service and never travel in either direction.

Responses are secret-safe projections: MCP protocol payloads (schemas,
annotations, content blocks) are passed through as untrusted data, while no
connection secret, decrypted credential or server configuration is exposed.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")

McpConnectionMode = Literal["personal", "team"]
McpCompletionKind = Literal["prompt", "resource_template"]
McpOperationStatus = Literal["completed", "pending_approval"]

# Approval operation keys are namespaced (``tool:<name>`` / ``prompt:<name>``)
# and the approval service rejects keys longer than 200 characters, so leaf
# names are capped below that budget instead of being silently truncated.
MAX_MCP_TOOL_NAME_LENGTH = 190
MAX_MCP_PROMPT_NAME_LENGTH = 190
MAX_MCP_RESOURCE_URI_LENGTH = 8192


# ============ Requests ============


class McpIdentityIn(BaseModel):
    """Identity selection for one MCP request.

    ``connection_mode`` selects the scope of the stored connection. Omitting it
    on a ``personal_only`` or ``selectable`` tool means ``personal``: the
    invoking user's account, never the author's. ``connection_id`` pins an
    explicit connection the caller can already use; it is validated against the
    team and the tool on every request. When no id is given, an interactive
    request selects that user's explicit default, otherwise their sole
    non-revoked personal connection; multiple connections without a default
    fail closed with a "set a default" error.
    """

    model_config = ConfigDict(extra="forbid")

    connection_mode: McpConnectionMode | None = Field(
        default=None,
        description="Connection scope: personal or team",
    )
    connection_id: UUID | None = Field(
        default=None,
        description="Explicit stored connection; never a credential payload",
    )


class McpOperationIn(McpIdentityIn):
    """Common identity plus an optional approved-execution continuation.

    Sending ``execution_id`` resumes exactly one previously returned pending
    execution. The execution boundary verifies actor, team, tool, operation,
    parameters digest and entrypoint; a completed execution is rejected (409)
    instead of being invoked again, because MCP results are not persisted yet.
    """

    execution_id: UUID | None = Field(
        default=None,
        description="Pending execution to resume after approval",
    )


class McpToolCallIn(McpOperationIn):
    """Call one tool advertised by the saved MCP server."""

    name: str = Field(
        min_length=1,
        max_length=MAX_MCP_TOOL_NAME_LENGTH,
        description="MCP tool name as advertised by the server",
    )
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpResourceReadIn(McpOperationIn):
    """Read one resource by URI; the URI is forwarded verbatim to the server."""

    uri: str = Field(
        min_length=1,
        max_length=MAX_MCP_RESOURCE_URI_LENGTH,
        description="Resource URI (or template-expanded URI)",
    )


class McpPromptGetIn(McpOperationIn):
    """Render one prompt advertised by the server."""

    name: str = Field(min_length=1, max_length=MAX_MCP_PROMPT_NAME_LENGTH)
    arguments: dict[str, str] | None = Field(default=None)


class McpCompletionReferenceIn(BaseModel):
    """Prompt or resource-template reference for ``completion/complete``."""

    model_config = ConfigDict(extra="forbid")

    kind: McpCompletionKind
    name: str | None = Field(default=None, max_length=MAX_MCP_PROMPT_NAME_LENGTH)
    uri: str | None = Field(default=None, max_length=MAX_MCP_RESOURCE_URI_LENGTH)

    @model_validator(mode="after")
    def _validate_target(self) -> "McpCompletionReferenceIn":
        if self.kind == "prompt":
            if not self.name:
                raise ValueError("prompt_completion_requires_name")
            if self.uri is not None:
                raise ValueError("prompt_completion_does_not_accept_uri")
        else:
            if not self.uri:
                raise ValueError("template_completion_requires_uri")
            if self.name is not None:
                raise ValueError("template_completion_does_not_accept_name")
        return self


class McpCompletionIn(McpOperationIn):
    """Request argument completion for a prompt or resource template."""

    reference: McpCompletionReferenceIn
    argument_name: str = Field(min_length=1, max_length=MAX_MCP_PROMPT_NAME_LENGTH)
    argument_value: str = Field(default="")
    context_arguments: dict[str, str] | None = Field(default=None)


# ============ Responses: operation envelopes ============


class McpPendingApprovalOut(BaseModel):
    """Durable reference to an execution waiting for approval.

    The HTTP response never fakes an MCP result; the caller must resolve the
    execution through the tool-approval APIs.
    """

    execution_id: UUID
    tool_name: str
    status: Literal["awaiting_approval"] = "awaiting_approval"


class McpOperationOut(BaseModel, Generic[T]):
    """Outcome of one approval-bound MCP operation.

    ``status`` describes this HTTP request, not the external result:
    ``completed`` carries the MCP payload in ``result`` (whose own ``success``
    / ``is_error`` fields describe the external outcome), while
    ``pending_approval`` carries a durable execution reference. Retry the same
    operation with that ID in request ``execution_id`` after approval; an
    already-completed execution is rejected instead of executed twice.
    """

    status: McpOperationStatus
    operation: str
    execution_id: UUID | None = None
    result: T | None = None
    pending_approval: McpPendingApprovalOut | None = None


# ============ Responses: metadata ============


class McpCapabilitiesOut(BaseModel):
    protocol_version: str | None = None
    server_name: str | None = None
    server_version: str | None = None
    instructions: str | None = None
    tools: bool = False
    tools_list_changed: bool = False
    resources: bool = False
    resources_subscribe: bool = False
    resources_list_changed: bool = False
    resource_templates: bool = False
    prompts: bool = False
    prompts_list_changed: bool = False
    completions: bool = False
    logging: bool = False
    experimental: bool = False


class McpToolOut(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class McpResourceOut(BaseModel):
    uri: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    size: int | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class McpResourceTemplateOut(BaseModel):
    uri_template: str
    name: str | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class McpPromptArgumentOut(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class McpPromptOut(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    arguments: list[McpPromptArgumentOut] = Field(default_factory=list)
    meta: dict[str, Any] | None = None


class McpEnumerationOut(BaseModel, Generic[T]):
    """Bounded listing plus explicit truncation metadata.

    ``next_cursor`` can be sent back as the ``cursor`` query parameter to
    continue exactly where this listing stopped. A page cut mid-page reports
    ``next_cursor=None`` because MCP has no offset to resume from.
    """

    items: list[T] = Field(default_factory=list)
    pages_fetched: int = 0
    truncated: bool = False
    truncation_reason: str | None = None
    next_cursor: str | None = None
    total_items: int = 0


# ============ Responses: operation payloads ============


class McpResourceContentsOut(BaseModel):
    uri: str
    mime_type: str | None = None
    text: str | None = None
    blob: str | None = None
    meta: dict[str, Any] | None = None


class McpPromptMessageOut(BaseModel):
    role: str
    content: dict[str, Any] = Field(default_factory=dict)


class McpPromptResultOut(BaseModel):
    messages: list[McpPromptMessageOut] = Field(default_factory=list)
    description: str | None = None
    meta: dict[str, Any] | None = None


class McpCompletionOut(BaseModel):
    values: list[str] = Field(default_factory=list)
    total: int | None = None
    has_more: bool = False


class McpToolResultOut(BaseModel):
    """Full ``tools/call`` result, including media and structured content."""

    success: bool
    result: Any | None = None
    error: str | None = None
    is_error: bool = False
    content: list[dict[str, Any]] = Field(default_factory=list)
    structured_content: Any | None = None
    input_required: dict[str, Any] | None = None


__all__ = [
    "McpCapabilitiesOut",
    "McpCompletionIn",
    "McpCompletionOut",
    "McpCompletionReferenceIn",
    "McpEnumerationOut",
    "McpIdentityIn",
    "McpOperationIn",
    "McpOperationOut",
    "McpPendingApprovalOut",
    "McpPromptArgumentOut",
    "McpPromptGetIn",
    "McpPromptMessageOut",
    "McpPromptOut",
    "McpPromptResultOut",
    "McpResourceContentsOut",
    "McpResourceOut",
    "McpResourceReadIn",
    "McpResourceTemplateOut",
    "McpToolCallIn",
    "McpToolOut",
    "McpToolResultOut",
]
