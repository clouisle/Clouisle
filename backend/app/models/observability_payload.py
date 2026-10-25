"""Durable model-facing payloads for observability drill-down.

Kept out of ``messages`` and ``observability_runs`` so ordinary conversation
reads and telemetry list queries never load large payloads. Rows are written
once per executed tool call or model invocation and read only by the
on-demand trace-detail API.
"""

from __future__ import annotations

from tortoise import fields, models


class ObservabilityToolPayload(models.Model):
    """Exact display/model text pair recorded for one tool call."""

    id = fields.UUIDField(primary_key=True)
    run_id = fields.UUIDField()
    conversation_id = fields.UUIDField(null=True)
    tool_call_id = fields.CharField(max_length=100)
    tool_name = fields.CharField(max_length=100)
    display_text = fields.TextField(null=True)
    model_text = fields.TextField(null=True)
    display_bytes = fields.IntField(default=0)
    model_bytes = fields.IntField(default=0)
    model_sha256 = fields.CharField(max_length=64, null=True)
    renderer = fields.CharField(max_length=64, null=True)
    eof = fields.BooleanField(null=True)
    has_cursor = fields.BooleanField(default=False)
    partial = fields.BooleanField(default=False)
    error = fields.CharField(max_length=200, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "observability_tool_payloads"
        unique_together = (("run_id", "tool_call_id"),)
        indexes = (
            ("run_id", "created_at"),
            # Detail lookup is by run + tool_call_id; retention deletes by run_id.
            ("tool_call_id",),
        )


class ObservabilityTrajectoryEntry(models.Model):
    """Ordered, correlated execution step with bounded request/response text.

    One row is written at each model boundary (and once per tool call) so the
    run inspector can follow the actual application-level context instead of
    reconstructing it from the current agent configuration. ``input_text`` and
    ``output_text`` hold JSON snapshots capped at the same size as tool
    payloads; ``partial`` marks bounded/dropped content and ``payload_state``
    distinguishes recorded, partially recorded and unavailable history.
    """

    id = fields.UUIDField(primary_key=True)
    run_id = fields.UUIDField()
    conversation_id = fields.UUIDField(null=True)
    # Correlation only: the model entry that requested a tool call. No FK so
    # rows can be written and retained independently of execution order.
    parent_id = fields.UUIDField(null=True)
    # Microsecond wall clock at write time; keeps ordering stable across
    # resumed durable runs without a per-run counter.
    sequence = fields.BigIntField()
    kind = fields.CharField(max_length=32)
    name = fields.CharField(max_length=200)
    status = fields.CharField(max_length=32)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    duration_ms = fields.IntField(null=True)
    model = fields.CharField(max_length=200, null=True)
    token_usage = fields.JSONField(null=True)  # type: ignore[assignment]
    tool_call_ids: list[str] = fields.JSONField(default=list)  # type: ignore[assignment]
    payload_state = fields.CharField(max_length=16, default="unrecorded")
    preview = fields.CharField(max_length=300, null=True)
    input_text = fields.TextField(null=True)
    output_text = fields.TextField(null=True)
    input_bytes = fields.IntField(default=0)
    output_bytes = fields.IntField(default=0)
    partial = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "observability_trajectory_entries"
        indexes = (
            ("run_id", "sequence"),
            # Bounded orphan cleanup after run summaries expire.
            ("created_at",),
        )
