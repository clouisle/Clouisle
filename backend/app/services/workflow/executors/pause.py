"""
Pause node executor - pauses the workflow for external variable input.

The node creates a pending WorkflowPauseRequest and returns a waiting result,
which pauses the run (RunStatus.WAITING). When an authorized submitter passes
values through the submit API, a resume task re-runs this node: the pending
request is resolved, so the executor emits the submitted values as outputs and
the run continues.

Approval is the node's approval mode: the submitter passes a fixed
decision/comment payload; decision=rejected fails the run.
"""

from typing import TYPE_CHECKING

import logging
from tortoise.exceptions import IntegrityError

from app.models.workflow import (
    NodeExecution,
    PauseRequestStatus,
    WorkflowPauseRequest,
)
from app.services.workflow.executor import (
    ExecutionResult,
    NodeExecutor,
    NodeExecutorRegistry,
)
from app.services.workflow.pause_approvers import notify_pause_pending

if TYPE_CHECKING:
    from app.models.workflow import WorkflowRun
    from app.services.workflow.context import ExecutionContext

logger = logging.getLogger(__name__)

APPROVAL_DECISION_KEY = "decision"
APPROVAL_COMMENT_KEY = "comment"


@NodeExecutorRegistry.register("pause")
class PauseNodeExecutor(NodeExecutor):
    """
    Human-in-the-loop pause node.

    Node Config:
        {
            "mode": "variables" | "approval",
            "inputVariables": [{"name", "type", "required", "description"}],
            "title": "...",
            "description": "..."
        }

    Outputs (variables mode):
        The submitted input variables (one output per declared variable).

    Outputs (approval mode):
        decision: "approved" | "rejected"
        approved: boolean
        comment: submitter comment (or None)
        submitted_by: UUID string of the submitter (or None)
    """

    async def execute(
        self,
        node: dict,
        context: "ExecutionContext",
        run: "WorkflowRun",
    ) -> ExecutionResult:
        node_data = node.get("data", {})
        config = node_data.get("pauseConfig") or node_data.get("config") or {}
        node_id = str(node.get("id", ""))
        mode = str(config.get("mode") or "variables")
        title = str(config.get("title") or "")
        node_name = str(node_data.get("label") or title or "Pause")

        # Reuse the latest request for this run+node (resume path re-runs the
        # node after submission); create one when first paused.
        request = (
            await WorkflowPauseRequest.filter(run_id=run.id, node_id=node_id)
            .order_by("-created_at")
            .first()
        )
        if request is None:
            node_execution = (
                await NodeExecution.filter(run_id=run.id, node_id=node_id)
                .order_by("-started_at")
                .first()
            )
            raw_description = config.get("description")
            resolved_description: str | None = None
            if isinstance(raw_description, str) and raw_description.strip():
                try:
                    # Unavailable references resolve to "" (never raw {{var}}
                    # text); store exactly what resolved so the request and
                    # notification never show template placeholders.
                    resolved_description = await context.resolve_template(
                        raw_description
                    )
                except Exception:
                    # Template failures must never expose the raw {{...}} source.
                    resolved_description = ""
            try:
                pause_request = await WorkflowPauseRequest.create(
                    run_id=run.id,
                    node_execution_id=node_execution.id if node_execution else None,
                    workflow_id=run.workflow_id,
                    node_id=node_id,
                    node_name=node_name,
                    mode=mode,
                    status=PauseRequestStatus.PENDING,
                    description=resolved_description,
                )
            except IntegrityError:
                # The database uniqueness constraint elects the first delivery.
                request = await WorkflowPauseRequest.filter(
                    run_id=run.id, node_id=node_id
                ).first()
                if request is None:
                    raise
            else:
                await notify_pause_pending(
                    run,
                    config,
                    node_name,
                    pause_request_id=pause_request.id,
                    node_id=node_id,
                    description=resolved_description,
                )
            return ExecutionResult(waiting=True)

        if request.status == PauseRequestStatus.PENDING:
            # Still awaiting submission; keep the run paused.
            return ExecutionResult(waiting=True)

        if request.status != PauseRequestStatus.SUBMITTED:
            # Cancelled or unexpected state: treat as a failed pause.
            return ExecutionResult(error="workflow_execution_error")

        values = dict(request.values or {})
        outputs: dict[str, object] = dict(values)

        if mode == "approval":
            decision = values.get(APPROVAL_DECISION_KEY)
            outputs["approved"] = decision == "approved"
            outputs["comment"] = request.comment
            outputs["submitted_by"] = (
                str(request.submitted_by_id) if request.submitted_by_id else None
            )
            if decision != "approved":
                return ExecutionResult(
                    error="workflow_approval_rejected",
                    outputs=outputs,  # type: ignore[arg-type]
                )
        return ExecutionResult(outputs=outputs)  # type: ignore[arg-type]

    def get_output_variables(self, config: dict) -> list[dict]:
        mode = str(config.get("mode") or "variables")
        if mode == "approval":
            return [
                {
                    "name": APPROVAL_DECISION_KEY,
                    "type": "string",
                    "description": "Approval decision (approved/rejected)",
                },
                {
                    "name": "approved",
                    "type": "boolean",
                    "description": "Whether the approval was granted",
                },
                {
                    "name": APPROVAL_COMMENT_KEY,
                    "type": "string",
                    "description": "Submitter comment",
                },
                {
                    "name": "submitted_by",
                    "type": "string",
                    "description": "User id of the submitter",
                },
            ]
        variables = config.get("inputVariables") or []
        return [
            {
                "name": str(v.get("name")),
                "type": str(v.get("type") or "string"),
                "description": str(v.get("description") or ""),
            }
            for v in variables
            if v.get("name")
        ]
