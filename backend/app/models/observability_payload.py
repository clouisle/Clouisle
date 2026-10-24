"""Durable model-facing tool payloads for observability drill-down.

Kept out of ``messages`` and ``observability_runs`` so ordinary conversation
reads and telemetry list queries never load large payloads. Rows are written
once per executed tool call and read only by the on-demand trace-detail API.
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
