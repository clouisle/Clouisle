"""Persistent retrieval evaluation datasets and runs."""

from enum import Enum
from typing import Any
from uuid import UUID

from tortoise import fields, models


class EvaluationRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class EvaluationDataset(models.Model):
    id = fields.UUIDField(pk=True)
    knowledge_base: fields.ForeignKeyRelation[Any] = fields.ForeignKeyField(
        "models.KnowledgeBase",
        related_name="evaluation_datasets",
        on_delete=fields.CASCADE,
    )
    knowledge_base_id: UUID
    name = fields.CharField(max_length=100)
    description = fields.CharField(max_length=500, null=True)
    created_by: fields.ForeignKeyRelation[Any] | None = fields.ForeignKeyField(
        "models.User",
        related_name="evaluation_datasets",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_by_id: UUID | None
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    cases: fields.ReverseRelation["EvaluationCase"]
    runs: fields.ReverseRelation["EvaluationRun"]

    class Meta:
        table = "evaluation_datasets"
        unique_together = (("knowledge_base", "name"),)
        ordering = ["-created_at"]


class EvaluationCase(models.Model):
    id = fields.UUIDField(pk=True)
    dataset: fields.ForeignKeyRelation[EvaluationDataset] = fields.ForeignKeyField(
        "models.EvaluationDataset", related_name="cases", on_delete=fields.CASCADE
    )
    dataset_id: UUID
    query = fields.TextField()
    chunk_relevance: dict[str, int] = fields.JSONField(default=dict)
    document_relevance: dict[str, int] = fields.JSONField(default=dict)
    expected_empty = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "evaluation_cases"
        ordering = ["created_at", "id"]


class EvaluationRun(models.Model):
    id = fields.UUIDField(pk=True)
    dataset: fields.ForeignKeyRelation[EvaluationDataset] = fields.ForeignKeyField(
        "models.EvaluationDataset", related_name="runs", on_delete=fields.CASCADE
    )
    dataset_id: UUID
    created_by: fields.ForeignKeyRelation[Any] | None = fields.ForeignKeyField(
        "models.User",
        related_name="evaluation_runs",
        null=True,
        on_delete=fields.SET_NULL,
    )
    created_by_id: UUID | None
    status = fields.CharField(max_length=20, default=EvaluationRunStatus.PENDING.value)
    config_snapshot: dict[str, Any] = fields.JSONField()
    version_snapshot: dict[str, Any] = fields.JSONField(default=dict)
    summary_metrics: dict[str, Any] | None = fields.JSONField(null=True)
    case_results: fields.ReverseRelation["EvaluationCaseResult"]
    task_id = fields.CharField(max_length=100, null=True)
    error_message = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)

    class Meta:
        table = "evaluation_runs"
        ordering = ["-created_at"]


class EvaluationCaseResult(models.Model):
    id = fields.UUIDField(pk=True)
    run: fields.ForeignKeyRelation[EvaluationRun] = fields.ForeignKeyField(
        "models.EvaluationRun", related_name="case_results", on_delete=fields.CASCADE
    )
    run_id: UUID
    case: fields.ForeignKeyRelation[EvaluationCase] | None = fields.ForeignKeyField(
        "models.EvaluationCase",
        related_name="results",
        null=True,
        on_delete=fields.SET_NULL,
    )
    case_id: UUID | None
    case_snapshot: dict[str, Any] = fields.JSONField(default=dict)
    candidates: list[dict[str, Any]] = fields.JSONField(default=list)
    metrics: dict[str, Any] = fields.JSONField(default=dict)
    latency_ms = fields.FloatField(default=0)
    error_message = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "evaluation_case_results"
        unique_together = (("run", "case"),)
        ordering = ["created_at", "id"]
