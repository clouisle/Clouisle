"""API DTOs for durable server-initiated interactions.

Only the explicit audience may list or answer a row, so responses never embed
connection secrets, MCP server configuration or raw ciphertext. ``payload`` is
the bounded preview written when the server asked; ``response`` is the
decrypted, audience-owned form answer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.tool_interaction import (
    InteractionKind,
    InteractionOutcome,
    InteractionStatus,
)

InteractionAction = Literal["accept", "decline", "cancel"]


class RunInteractionOut(BaseModel):
    """Secret-safe projection of one interaction row."""

    id: UUID
    kind: InteractionKind
    status: InteractionStatus
    outcome: InteractionOutcome | None = None
    run_kind: str | None = None
    run_id: UUID | None = None
    execution_id: UUID | None = None
    tool_id: UUID | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    team_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    audience: dict[str, list[str]] = Field(default_factory=dict)
    expires_at: datetime
    responded_at: datetime | None = None
    responded_by_id: UUID | None = None
    response: dict[str, Any] | None = None
    created_at: datetime

    @classmethod
    def from_record(
        cls, record: Any, *, response: dict[str, Any] | None = None
    ) -> "RunInteractionOut":
        return cls(
            id=record.id,
            kind=record.kind,
            status=record.status,
            outcome=record.outcome,
            run_kind=record.run_kind,
            run_id=record.run_id,
            execution_id=record.execution_id,
            tool_id=record.tool_id,
            tool_name=record.tool_name,
            tool_call_id=record.tool_call_id,
            team_id=record.team_id,
            payload=record.payload or {},
            audience=record.audience or {},
            expires_at=record.expires_at,
            responded_at=record.responded_at,
            responded_by_id=record.responded_by_id,
            response=response,
            created_at=record.created_at,
        )


class RunInteractionResponseIn(BaseModel):
    """One answer to a pending sampling or elicitation request.

    ``content`` is only allowed for ``accept`` on a form elicitation; the
    server validates it against the schema stored when the request was made.
    ``idempotency_key`` makes retries safe without allowing a second answer to
    replace the first.
    """

    model_config = ConfigDict(extra="forbid")

    action: InteractionAction
    content: dict[str, Any] | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)


__all__ = [
    "InteractionAction",
    "RunInteractionOut",
    "RunInteractionResponseIn",
]
