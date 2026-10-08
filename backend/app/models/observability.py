"""Bounded operational telemetry and durable alert state.

Only allowlisted summaries are stored; run inputs, messages, traces, and errors
are deliberately excluded. Records are retained for a fixed window by a
bounded maintenance call.
"""

from tortoise import fields, models


class ObservabilityRun(models.Model):
    id = fields.UUIDField(primary_key=True)
    source = fields.CharField(max_length=16)
    resource_id = fields.CharField(max_length=64, null=True)
    model_name = fields.CharField(max_length=200, null=True)
    resource_name = fields.CharField(max_length=200, null=True)
    team_id = fields.CharField(max_length=64, null=True)
    team_name = fields.CharField(max_length=200, null=True)
    status = fields.CharField(max_length=24)
    submitted_at = fields.DatetimeField(null=True)
    started_at = fields.DatetimeField(null=True)
    message_started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    queue_duration_ms = fields.IntField(null=True)
    execution_duration_ms = fields.IntField(null=True)
    total_duration_ms = fields.IntField(null=True)
    first_token_ms = fields.IntField(null=True)
    total_tokens = fields.BigIntField(default=0)
    error_category = fields.CharField(max_length=32, null=True)
    error_code = fields.CharField(max_length=100, null=True)
    trace_available = fields.BooleanField(default=False)
    trace_complete = fields.BooleanField(default=False)
    dependency_metrics: list[dict] = fields.JSONField(default=list)  # type: ignore[assignment]
    dependency_metrics_truncated = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "observability_runs"
        indexes = (
            ("submitted_at", "id"),
            ("source", "submitted_at", "id"),
            ("team_id", "submitted_at", "id"),
            ("submitted_at", "model_name"),
            ("error_category", "submitted_at", "id"),
            ("status", "submitted_at", "id"),
        )


class ObservabilityAlertRule(models.Model):
    id = fields.CharField(max_length=64, primary_key=True)
    name = fields.CharField(max_length=160)
    threshold = fields.FloatField()
    enabled = fields.BooleanField(default=True)
    evaluation_window_seconds = fields.IntField(default=300)
    recovery_window_seconds = fields.IntField(default=600)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "observability_alert_rules"


class ObservabilityAlertEvent(models.Model):
    id = fields.UUIDField(primary_key=True)
    rule_id = fields.CharField(max_length=64)
    kind = fields.CharField(max_length=64)
    severity = fields.CharField(max_length=16)
    title = fields.CharField(max_length=200)
    detail = fields.CharField(max_length=500)
    affected_count = fields.IntField(default=0)
    status = fields.CharField(max_length=16, default="active")
    opened_at = fields.DatetimeField()
    resolved_at = fields.DatetimeField(null=True)
    acknowledged_at = fields.DatetimeField(null=True)
    acknowledged_by_id = fields.CharField(max_length=64, null=True)
    silenced_until = fields.DatetimeField(null=True)

    class Meta:
        table = "observability_alert_events"
        indexes = (
            ("status", "opened_at", "id"),
            ("rule_id", "status", "opened_at"),
            ("opened_at", "id"),
        )
