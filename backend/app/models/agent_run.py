"""
Durable AgentRun and queued run input models.

An ``AgentRun`` records one agent-loop execution independent of any browser
connection: the worker (Celery ``agent`` queue) executes the loop, SSE
endpoints subscribe to buffered/live per-run events, and the database is the
terminal source of truth. ``AgentRunInput`` durably queues steering /
follow-up / stop commands so a lost Redis wakeup never loses a message.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.agent import Agent, Conversation
    from app.models.user import User


class AgentRunStatus(str, Enum):
    """Lifecycle status of an agent run."""

    QUEUED = "queued"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class AgentRunMode(str, Enum):
    """Entry mode that created the run."""

    SEND = "send"
    EDIT = "edit"
    REGENERATE = "regenerate"
    NON_STREAM = "non_stream"


class AgentRunInputKind(str, Enum):
    """Queued control input kinds."""

    STEER = "steer"
    FOLLOW_UP = "follow_up"
    STOP = "stop"


class AgentRunInputStatus(str, Enum):
    """Consumption status of a queued input."""

    QUEUED = "queued"
    CONSUMED = "consumed"
    DROPPED = "dropped"


class AgentRun(models.Model):
    """One durable agent-loop execution."""

    id = fields.UUIDField(primary_key=True)

    agent: fields.ForeignKeyRelation["Agent"] = fields.ForeignKeyField(
        "models.Agent",
        related_name="agent_runs",
        on_delete=fields.CASCADE,
    )
    agent_id: UUID  # type: ignore[assignment]

    conversation: fields.ForeignKeyRelation["Conversation"] = fields.ForeignKeyField(
        "models.Conversation",
        related_name="agent_runs",
        on_delete=fields.CASCADE,
    )
    conversation_id: UUID  # type: ignore[assignment]

    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="agent_runs",
        on_delete=fields.CASCADE,
    )
    user_id: UUID  # type: ignore[assignment]

    # Entry mode and origin
    mode = fields.CharEnumField(AgentRunMode, description="Entry mode")
    celery_task_id = fields.CharField(
        max_length=100, null=True, description="Celery task id"
    )
    source_message_id = fields.UUIDField(
        null=True,
        description="User/assistant message that started the run (edit/regenerate)",
    )
    canonical_message_id = fields.UUIDField(
        null=True,
        description="Canonical assistant message produced by the run",
    )
    active_round_id = fields.UUIDField(
        null=True, description="Round id of the run's visible branch"
    )

    # Lifecycle
    status = fields.CharEnumField(
        AgentRunStatus, default=AgentRunStatus.QUEUED, description="Run status"
    )
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # Terminal error details
    error_code = fields.CharField(max_length=100, null=True)
    error_message = fields.TextField(null=True)

    class Meta:
        table = "agent_runs"

    def __str__(self) -> str:
        return f"AgentRun {self.id} ({self.status.value})"


class AgentRunInput(models.Model):
    """Durable queued user control input for a run.

    PostgreSQL is the authoritative queue: rows are consumed in ``sequence``
    order with row-level locking; Redis only wakes the worker.
    """

    id = fields.UUIDField(primary_key=True)
    run: fields.ForeignKeyRelation["AgentRun"] = fields.ForeignKeyField(
        "models.AgentRun",
        related_name="inputs",
        on_delete=fields.CASCADE,
    )
    run_id: UUID  # type: ignore[assignment]

    sequence = fields.IntField(description="Order within the run")
    kind = fields.CharEnumField(AgentRunInputKind, description="Input kind")
    content = fields.TextField(null=True, description="Steer/follow-up text")
    attachment_meta: dict = fields.JSONField(default=dict)  # type: ignore[assignment]
    status = fields.CharEnumField(
        AgentRunInputStatus, default=AgentRunInputStatus.QUEUED, description="Status"
    )
    request_id = fields.CharField(
        max_length=100, null=True, description="Client idempotency key"
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    consumed_at = fields.DatetimeField(null=True)

    class Meta:
        table = "agent_run_inputs"
        unique_together = [("run", "sequence")]
        ordering = ["sequence"]

    def __str__(self) -> str:
        return f"AgentRunInput {self.kind.value} #{self.sequence} ({self.status.value})"
