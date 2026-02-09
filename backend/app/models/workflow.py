"""
Workflow models for visual workflow orchestration.
Supports visual editing, execution tracking, and nested workflows.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team, User


class WorkflowVisibility(str, Enum):
    """Workflow visibility"""

    PRIVATE = "private"  # Only creator can access
    TEAM = "team"  # Team members can access
    PUBLIC = "public"  # Public access (future)


class WorkflowStatus(str, Enum):
    """Workflow status"""

    DRAFT = "draft"  # Draft, not published
    PUBLISHED = "published"  # Published and available
    ARCHIVED = "archived"  # Archived, not visible


class TriggerType(str, Enum):
    """Workflow trigger type"""

    MANUAL = "manual"  # Manual trigger
    CRON = "cron"  # Scheduled trigger
    WEBHOOK = "webhook"  # Webhook trigger


class RunStatus(str, Enum):
    """Workflow run status"""

    PENDING = "pending"  # Waiting to execute
    RUNNING = "running"  # Executing
    SUCCESS = "success"  # Completed successfully
    FAILED = "failed"  # Failed
    CANCELLED = "cancelled"  # Cancelled
    TIMEOUT = "timeout"  # Timed out


class NodeStatus(str, Enum):
    """Node execution status"""

    PENDING = "pending"  # Waiting to execute
    RUNNING = "running"  # Executing
    SUCCESS = "success"  # Completed successfully
    FAILED = "failed"  # Failed
    SKIPPED = "skipped"  # Skipped


class Workflow(models.Model):
    """
    Workflow entity.

    A workflow is a visual orchestration of nodes that can be executed
    to automate tasks, process data, or interact with AI models.
    """

    id = fields.UUIDField(pk=True)

    # Team association for data isolation
    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="workflows",
        on_delete=fields.CASCADE,
        description="Team that owns this workflow",
    )
    team_id: UUID  # type: ignore[assignment]

    # Basic info
    name = fields.CharField(max_length=100, description="Workflow name")
    description = fields.TextField(null=True, description="Workflow description")
    icon = fields.CharField(max_length=500, null=True, description="Icon emoji or URL")

    # Visibility
    visibility = fields.CharEnumField(
        WorkflowVisibility, default=WorkflowVisibility.PRIVATE, description="Visibility"
    )

    # Workflow definition (ReactFlow format)
    # {
    #   "nodes": [...],
    #   "edges": [...],
    #   "viewport": {...}
    # }
    definition: dict = fields.JSONField(
        default=dict, description="Workflow definition in ReactFlow format"
    )  # type: ignore[assignment]

    # Global variable definitions
    # [{"name": "input_text", "type": "string", "required": true, "default": ""}]
    variables: list = fields.JSONField(
        default=list, description="Input variables definition"
    )  # type: ignore[assignment]

    # Status
    status = fields.CharEnumField(
        WorkflowStatus, default=WorkflowStatus.DRAFT, description="Workflow status"
    )
    version = fields.IntField(default=1, description="Workflow version")

    # Trigger configuration
    trigger_type = fields.CharEnumField(
        TriggerType, default=TriggerType.MANUAL, description="Trigger type"
    )
    trigger_config: dict = fields.JSONField(
        default=dict,
        description="Trigger configuration (cron expression, webhook secret, etc.)",
    )  # type: ignore[assignment]
    webhook_token = fields.CharField(
        max_length=100, null=True, unique=True, description="Webhook token"
    )

    # Statistics (累计统计，不会因删除而减少)
    run_count = fields.IntField(default=0, description="Total run count")
    success_count = fields.IntField(default=0, description="Successful run count")
    fail_count = fields.IntField(default=0, description="Failed run count")
    total_tokens = fields.BigIntField(
        default=0, description="Total tokens consumed (累计)"
    )

    # Audit
    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_workflows",
        on_delete=fields.SET_NULL,
        null=True,
        description="Creator",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # Relations
    runs: fields.ReverseRelation["WorkflowRun"]

    class Meta:
        table = "workflows"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class WorkflowRun(models.Model):
    """
    Workflow execution record.

    Records a single execution of a workflow, including status,
    inputs, outputs, timing, and node-level execution details.
    """

    id = fields.UUIDField(pk=True)

    # Workflow association
    workflow: fields.ForeignKeyRelation[Workflow] | None = fields.ForeignKeyField(
        "models.Workflow",
        related_name="runs",
        on_delete=fields.SET_NULL,
        null=True,
        description="Workflow being executed (null if workflow deleted)",
    )
    workflow_id: UUID | None  # type: ignore[assignment]

    # Trigger info
    trigger_type = fields.CharEnumField(
        TriggerType, description="How this run was triggered"
    )
    triggered_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="workflow_runs",
        on_delete=fields.SET_NULL,
        null=True,
        description="User who triggered (null for webhook/cron)",
    )

    # Execution mode
    is_debug = fields.BooleanField(
        default=False, description="Whether this is a debug run"
    )

    # Status
    status = fields.CharEnumField(
        RunStatus, default=RunStatus.PENDING, description="Run status"
    )

    # Inputs and outputs
    inputs: dict = fields.JSONField(default=dict, description="Workflow inputs")  # type: ignore[assignment]
    outputs: dict | None = fields.JSONField(null=True, description="Workflow outputs")  # type: ignore[assignment]

    # Context snapshot
    context_snapshot: dict = fields.JSONField(
        default=dict, description="Execution context snapshot"
    )  # type: ignore[assignment]

    # Sub-workflow association
    parent_run_id = fields.UUIDField(
        null=True, description="Parent run ID for nested workflows"
    )
    root_run_id = fields.UUIDField(
        null=True, description="Root run ID for nested workflows"
    )
    depth = fields.IntField(default=0, description="Execution depth (0 for root)")

    # Timing
    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True, description="When execution started")
    finished_at = fields.DatetimeField(null=True, description="When execution finished")

    # Statistics summary
    total_nodes = fields.IntField(default=0, description="Total number of nodes")
    executed_nodes = fields.IntField(default=0, description="Number of executed nodes")
    failed_nodes = fields.IntField(default=0, description="Number of failed nodes")
    skipped_nodes = fields.IntField(default=0, description="Number of skipped nodes")
    total_duration_ms = fields.IntField(
        null=True, description="Total duration in milliseconds"
    )
    total_token_usage: dict = fields.JSONField(
        default=dict, description="Total token usage {'prompt': 0, 'completion': 0}"
    )  # type: ignore[assignment]

    # Error info
    error_message = fields.TextField(null=True, description="Error message if failed")
    error_node_id = fields.CharField(
        max_length=100, null=True, description="Node ID where error occurred"
    )
    error_traceback = fields.TextField(null=True, description="Error traceback")

    # Relations
    node_executions: fields.ReverseRelation["NodeExecution"]

    class Meta:
        table = "workflow_runs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id} ({self.status})"


class NodeExecution(models.Model):
    """
    Node execution record.

    Records the execution of a single node within a workflow run,
    including timing, inputs, outputs, and any errors.
    """

    id = fields.UUIDField(pk=True)

    # Run association
    run: fields.ForeignKeyRelation[WorkflowRun] = fields.ForeignKeyField(
        "models.WorkflowRun",
        related_name="node_executions",
        on_delete=fields.CASCADE,
        description="Workflow run this execution belongs to",
    )
    run_id: UUID  # type: ignore[assignment]

    # Node identification
    node_id = fields.CharField(max_length=100, description="ReactFlow node ID")
    node_type = fields.CharField(
        max_length=50, description="Node type (start/end/llm/etc.)"
    )
    node_name = fields.CharField(max_length=200, description="Node display name")

    # Execution order
    execution_order = fields.IntField(description="Order of execution")

    # Status
    status = fields.CharEnumField(
        NodeStatus, default=NodeStatus.PENDING, description="Execution status"
    )

    # Timing (millisecond precision)
    queued_at = fields.DatetimeField(null=True, description="When node was queued")
    started_at = fields.DatetimeField(null=True, description="When execution started")
    finished_at = fields.DatetimeField(null=True, description="When execution finished")

    # Duration (redundant for easy querying)
    queue_duration_ms = fields.IntField(null=True, description="Queue duration in ms")
    execution_duration_ms = fields.IntField(
        null=True, description="Execution duration in ms"
    )

    # Input data
    inputs: dict | None = fields.JSONField(null=True, description="Node inputs")  # type: ignore[assignment]
    inputs_storage_key = fields.CharField(
        max_length=200, null=True, description="External storage key for large inputs"
    )

    # Output data
    outputs: dict | None = fields.JSONField(null=True, description="Node outputs")  # type: ignore[assignment]
    outputs_storage_key = fields.CharField(
        max_length=200, null=True, description="External storage key for large outputs"
    )

    # Node config snapshot
    config_snapshot: dict | None = fields.JSONField(
        null=True, description="Node configuration at execution time"
    )  # type: ignore[assignment]

    # LLM-related (for llm/agent nodes)
    model_used = fields.CharField(max_length=100, null=True, description="Model used")
    prompt_tokens = fields.IntField(null=True, description="Prompt tokens used")
    completion_tokens = fields.IntField(null=True, description="Completion tokens used")
    total_tokens = fields.IntField(null=True, description="Total tokens used")

    # Sub-workflow (for sub_workflow nodes)
    sub_run_id = fields.UUIDField(null=True, description="Sub-workflow run ID")

    # Error info
    error_message = fields.TextField(null=True, description="Error message")
    error_type = fields.CharField(max_length=100, null=True, description="Error type")
    error_traceback = fields.TextField(null=True, description="Error traceback")

    # Retry
    retry_count = fields.IntField(default=0, description="Number of retries")

    class Meta:
        table = "workflow_node_executions"
        ordering = ["execution_order"]

    def __str__(self):
        return f"Node {self.node_id} ({self.status})"


class WorkflowVersion(models.Model):
    """
    Workflow version history.

    Stores a snapshot of the workflow definition at each version,
    allowing users to view and restore previous versions.
    """

    id = fields.UUIDField(pk=True)

    # Parent workflow
    workflow: fields.ForeignKeyRelation["Workflow"] = fields.ForeignKeyField(
        "models.Workflow",
        related_name="versions",
        on_delete=fields.CASCADE,
        description="Parent workflow",
    )
    workflow_id: UUID  # type: ignore[assignment]

    # Version number
    version = fields.IntField(description="Version number")

    # Snapshot of definition at this version
    definition: dict = fields.JSONField(
        default=dict, description="Workflow definition snapshot"
    )  # type: ignore[assignment]

    # Snapshot of variables at this version
    variables: list = fields.JSONField(default=list, description="Variables snapshot")  # type: ignore[assignment]

    # Trigger configuration snapshot
    trigger_type = fields.CharEnumField(
        TriggerType, default=TriggerType.MANUAL, description="Trigger type snapshot"
    )
    trigger_config: dict | None = fields.JSONField(
        null=True, description="Trigger config snapshot"
    )  # type: ignore[assignment]

    # Version metadata
    description = fields.TextField(null=True, description="Version description/notes")

    # Created by
    created_by: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="workflow_versions",
        on_delete=fields.SET_NULL,
        null=True,
        description="User who created this version",
    )
    created_by_id: UUID | None  # type: ignore[assignment]

    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True, description="Creation time")

    class Meta:
        table = "workflow_versions"
        ordering = ["-version"]
        unique_together = (("workflow", "version"),)

    def __str__(self):
        return f"Workflow {self.workflow_id} v{self.version}"
