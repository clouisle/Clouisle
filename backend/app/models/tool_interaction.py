"""Durable record of one server-initiated interaction.

MCP ``sampling/createMessage`` and ``elicitation/create`` are server-initiated
JSON-RPC requests that can only be answered by the live session that opened
them. This table is the durable *truth* about the human decision, never a
resumable JSON-RPC continuation: the live worker waits on the row and answers
its own in-memory request. If that worker or the MCP session dies, no process
replays the outer tool call; the row becomes ``connection_lost`` (or expires)
and the caller is told to start a new execution.

``payload`` is a secret-safe preview (bounded text, schema, URL and metadata).
Accepted form content is Fernet-encrypted in ``response_cipher`` because it is
user-entered business data; no credential is ever requested or stored.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from .tool import Tool
    from .user import User


class InteractionKind(str, Enum):
    """Which MCP server-initiated request the row represents."""

    SAMPLING = "sampling"
    ELICITATION = "elicitation"


class InteractionStatus(str, Enum):
    """Terminal-once lifecycle of one interaction row.

    ``pending -> responded`` records a human decision. ``expired``,
    ``cancelled`` and ``connection_lost`` are the three ways a pending row dies
    without a decision; none of them may ever be turned back into a response.
    """

    PENDING = "pending"
    RESPONDED = "responded"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CONNECTION_LOST = "connection_lost"


class InteractionOutcome(str, Enum):
    """The answer carried by a responded row."""

    ACCEPT = "accept"
    DECLINE = "decline"
    CANCEL = "cancel"


class InteractionRequest(models.Model):
    """One human-facing sampling approval or elicitation form/URL.

    The row is created by the worker that owns the live MCP session and is
    response-authorized by its stored ``audience`` only — broad run/tool read
    permission is deliberately not enough to answer it.
    """

    id = fields.UUIDField(primary_key=True)

    kind = fields.CharEnumField(InteractionKind, description="Interaction kind")
    status = fields.CharEnumField(InteractionStatus, default=InteractionStatus.PENDING)

    # Origin: which durable run/execution/tool call opened the MCP session.
    run_kind = fields.CharField(max_length=20, null=True)
    run_id = fields.UUIDField(null=True)
    execution_id = fields.UUIDField(null=True)
    session_key = fields.CharField(
        max_length=120,
        null=True,
        description="Process-local managed session that can answer this row",
    )
    tool_call_id = fields.CharField(max_length=200, null=True)
    tool: fields.ForeignKeyRelation["Tool"] | None = fields.ForeignKeyField(
        "models.Tool",
        related_name="interaction_requests",
        on_delete=fields.SET_NULL,
        null=True,
    )
    tool_id: UUID | None  # type: ignore[assignment]
    tool_name = fields.CharField(max_length=200, null=True)
    team_id = fields.UUIDField(null=True)

    # Requester/effective principal; never a client-supplied actor assertion.
    actor_user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="interaction_requests",
        on_delete=fields.CASCADE,
    )
    actor_user_id: UUID  # type: ignore[assignment]

    # Display-safe preview and the explicit responder audience.
    payload: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    audience: dict = fields.JSONField(default=dict)  # type: ignore[assignment]

    # Decision. Content is encrypted; previews never leave this module raw.
    outcome = fields.CharEnumField(InteractionOutcome, null=True)
    response_cipher = fields.TextField(null=True)
    responded_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="interaction_responses",
        on_delete=fields.SET_NULL,
        null=True,
    )
    responded_by_id: UUID | None  # type: ignore[assignment]
    responded_at = fields.DatetimeField(null=True)
    response_idempotency_key = fields.CharField(max_length=100, null=True)
    response_digest = fields.CharField(
        max_length=64, null=True, description="sha256 of action + canonical content"
    )

    # How the client answers. Not a promise that the RPC survives a restart.
    answered_via = fields.CharField(max_length=20, null=True)
    expires_at = fields.DatetimeField(description="Hard answer deadline")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_interaction_requests"
        ordering = ["-created_at"]
        indexes = [
            ("status", "expires_at"),
            ("run_kind", "run_id"),
            ("execution_id",),
            ("session_key",),
            ("actor_user", "status"),
        ]

    def __str__(self) -> str:
        return f"InteractionRequest {self.id} ({self.kind.value}/{self.status.value})"


__all__ = [
    "InteractionKind",
    "InteractionOutcome",
    "InteractionRequest",
    "InteractionStatus",
]
