"""Shared workflow access helpers."""

from uuid import UUID

from app.api.team_access import check_team_access
from app.models.user import User
from app.models.workflow import Workflow, WorkflowVisibility
from app.schemas.response import BusinessError, ResponseCode


async def check_workflow_access(
    workflow_id: UUID, user: User, require_write: bool = False
) -> Workflow:
    """Check whether a user can access a workflow."""
    workflow = (
        await Workflow.filter(id=workflow_id)
        .prefetch_related("team", "created_by")
        .first()
    )
    if not workflow:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="workflow_not_found",
            status_code=404,
        )

    if user.is_superuser:
        return workflow

    is_owner = workflow.created_by and workflow.created_by.id == user.id
    if workflow.visibility == WorkflowVisibility.PRIVATE:
        if is_owner:
            return workflow
        if require_write:
            await check_team_access(workflow.team.id, user, require_admin=True)
            return workflow
        if not workflow.created_by:
            await check_team_access(workflow.team.id, user)
            return workflow
        raise BusinessError(
            code=ResponseCode.FORBIDDEN,
            msg_key="workflow_access_denied",
            status_code=403,
        )

    await check_team_access(workflow.team.id, user)
    if require_write and not is_owner:
        await check_team_access(workflow.team.id, user, require_admin=True)

    return workflow
