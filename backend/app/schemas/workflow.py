"""
Workflow schemas for API request/response validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.workflow import (
    WorkflowStatus,
    TriggerType,
    RunStatus,
    NodeStatus,
)


# ============================================================================
# Workflow Schemas
# ============================================================================


class WorkflowCreate(BaseModel):
    """Schema for creating a workflow"""

    team_id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None


class WorkflowUpdate(BaseModel):
    """Schema for updating a workflow"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = None
    definition: dict | None = None
    variables: list[dict] | None = None
    trigger_type: TriggerType | None = None
    trigger_config: dict | None = None


class WorkflowOut(BaseModel):
    """Schema for workflow response"""

    id: UUID
    team_id: UUID
    name: str
    description: str | None
    icon: str | None
    definition: dict
    variables: list[dict]
    status: WorkflowStatus
    version: int
    trigger_type: TriggerType
    trigger_config: dict
    webhook_token: str | None
    run_count: int
    success_count: int
    fail_count: int
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowListItem(BaseModel):
    """Schema for workflow list item (simplified)"""

    id: UUID
    name: str
    description: str | None
    icon: str | None
    status: WorkflowStatus
    trigger_type: TriggerType
    run_count: int
    success_count: int
    fail_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# WorkflowRun Schemas
# ============================================================================


class WorkflowRunRequest(BaseModel):
    """Schema for running a workflow"""

    inputs: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunOut(BaseModel):
    """Schema for workflow run response"""

    id: UUID
    workflow_id: UUID
    trigger_type: TriggerType
    triggered_by_id: UUID | None
    is_debug: bool
    status: RunStatus
    inputs: dict
    outputs: dict | None
    parent_run_id: UUID | None
    root_run_id: UUID | None
    depth: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    total_nodes: int
    executed_nodes: int
    failed_nodes: int
    skipped_nodes: int
    total_duration_ms: int | None
    total_token_usage: dict
    error_message: str | None
    error_node_id: str | None

    class Config:
        from_attributes = True


class WorkflowRunListItem(BaseModel):
    """Schema for workflow run list item (simplified)"""

    id: UUID
    workflow_id: UUID
    trigger_type: TriggerType
    is_debug: bool
    status: RunStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    total_duration_ms: int | None
    executed_nodes: int
    total_nodes: int
    error_message: str | None

    class Config:
        from_attributes = True


# ============================================================================
# NodeExecution Schemas
# ============================================================================


class NodeExecutionOut(BaseModel):
    """Schema for node execution response"""

    id: UUID
    run_id: UUID
    node_id: str
    node_type: str
    node_name: str
    execution_order: int
    status: NodeStatus
    queued_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    queue_duration_ms: int | None
    execution_duration_ms: int | None
    inputs: dict | None
    outputs: dict | None
    config_snapshot: dict | None
    model_used: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    sub_run_id: UUID | None
    error_message: str | None
    error_type: str | None
    retry_count: int

    class Config:
        from_attributes = True


# ============================================================================
# Variable Definition Schema
# ============================================================================


class VariableType(str):
    """Variable types"""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class VariableDefinition(BaseModel):
    """Schema for variable definition"""

    name: str = Field(..., min_length=1, max_length=50)
    type: str = Field(default="string")
    required: bool = Field(default=False)
    default: Any | None = None
    description: str | None = None


# ============================================================================
# Node Configuration Schemas
# ============================================================================


class StartNodeConfig(BaseModel):
    """Configuration for start node"""

    pass  # Start node uses workflow-level variables


class EndNodeConfig(BaseModel):
    """Configuration for end node"""

    output_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map workflow output names to expressions",
    )


class LLMNodeConfig(BaseModel):
    """Configuration for LLM node"""

    model_id: UUID | None = None
    prompt: str = Field(..., description="Prompt template with {{variable}} placeholders")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0, le=1)


class AgentNodeConfig(BaseModel):
    """Configuration for agent node"""

    agent_id: UUID
    message: str = Field(..., description="Message template with {{variable}} placeholders")


class SubWorkflowNodeConfig(BaseModel):
    """Configuration for sub-workflow node"""

    workflow_id: UUID
    input_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map sub-workflow input names to parent expressions",
    )
    output_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map parent variable names to sub-workflow outputs",
    )
    timeout_seconds: int = Field(default=300, ge=1)
    fail_on_error: bool = Field(default=True)


class KBRetrievalNodeConfig(BaseModel):
    """Configuration for knowledge base retrieval node"""

    knowledge_base_id: UUID
    query: str = Field(..., description="Query template with {{variable}} placeholders")
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float = Field(default=0.3, ge=0, le=1)


class ConditionNodeConfig(BaseModel):
    """Configuration for condition node"""

    expression: str = Field(..., description="Boolean expression with {{variable}} placeholders")
    true_output: str = Field(default="true")
    false_output: str = Field(default="false")


class LoopNodeConfig(BaseModel):
    """Configuration for loop node"""

    array_expression: str = Field(..., description="Expression that evaluates to an array")
    item_variable: str = Field(default="item", description="Variable name for current item")
    index_variable: str = Field(default="index", description="Variable name for current index")
    max_iterations: int = Field(default=100, ge=1, le=1000)


class CodeNodeConfig(BaseModel):
    """Configuration for code node"""

    language: str = Field(default="python", pattern="^(python|javascript)$")
    code: str = Field(..., description="Code to execute")
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class HTTPNodeConfig(BaseModel):
    """Configuration for HTTP request node"""

    method: str = Field(default="GET", pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    url: str = Field(..., description="URL template with {{variable}} placeholders")
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict | str | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)


class ToolNodeConfig(BaseModel):
    """Configuration for tool node"""

    tool_id: UUID
    arguments: dict[str, str] = Field(
        default_factory=dict,
        description="Map argument names to expressions",
    )


class VariableNodeConfig(BaseModel):
    """Configuration for variable assignment node"""

    assignments: dict[str, str] = Field(
        ...,
        description="Map variable names to expressions",
    )


class DelayNodeConfig(BaseModel):
    """Configuration for delay node"""

    seconds: float = Field(..., ge=0, le=3600, description="Seconds to wait")


# ============================================================================
# Node Data Schema (for ReactFlow)
# ============================================================================


class NodeData(BaseModel):
    """Data stored in a ReactFlow node"""

    type: str = Field(..., description="Node type")
    label: str = Field(..., description="Display label")
    config: dict = Field(default_factory=dict, description="Node configuration")


class WorkflowDefinition(BaseModel):
    """Complete workflow definition (ReactFlow format)"""

    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    viewport: dict = Field(default_factory=lambda: {"x": 0, "y": 0, "zoom": 1})
