"""Shared workflow access helpers."""

from typing import TYPE_CHECKING
from uuid import UUID

from tortoise.expressions import Q

from app.api.team_access import check_team_access
from app.models.user import TeamMember, User
from app.models.workflow import Workflow, WorkflowVisibility
from app.schemas.response import BusinessError, ResponseCode

if TYPE_CHECKING:
    from app.schemas.workflow_access import WorkflowOperation


async def workflow_read_visibility_filter(user: User) -> Q | None:
    """Build the queryset filter matching ``check_workflow_access`` read rules.

    Returns ``None`` for superusers, who bypass every visibility check. The Q
    mirrors the per-workflow guard exactly so list/stats endpoints cannot leak
    workflows a direct ``GET /workflows/{id}`` would reject:

    - team/public workflows owned by a team the user belongs to,
    - private workflows the user created (ownership survives team removal),
    - creator-less legacy private workflows inside the user's teams.
    """
    if user.is_superuser:
        return None

    membership_ids = await TeamMember.filter(user=user).values_list(
        "team_id", flat=True
    )
    return (
        Q(
            team_id__in=membership_ids,
            visibility__in=[WorkflowVisibility.TEAM, WorkflowVisibility.PUBLIC],
        )
        | Q(created_by_id=user.id, visibility=WorkflowVisibility.PRIVATE)
        | Q(
            team_id__in=membership_ids,
            created_by_id__isnull=True,
            visibility=WorkflowVisibility.PRIVATE,
        )
    )


async def check_workflow_access(
    workflow_id: UUID,
    user: User,
    require_write: bool = False,
    *,
    operation: "WorkflowOperation | None" = None,
    enforce_policy: bool = True,
) -> Workflow:
    """Check whether a user can access a workflow.

    ``operation`` additionally applies the workflow's own access policy. The
    policy only narrows what the legacy rules below already allow, so callers
    that omit it keep the previous behaviour exactly. When omitted the
    operation is derived from ``require_write`` (write -> ``edit``, read ->
    ``view``); ``run``, ``publish`` and ``delete`` pass it explicitly.
    """
    workflow = await _legacy_workflow_access(workflow_id, user, require_write)
    if not enforce_policy:
        return workflow
    # Nothing to enforce for the common case: skip the extra role lookup so a
    # workflow without a policy costs exactly what it did before.
    if not getattr(workflow, "access_policy", None):
        return workflow
    from app.schemas.workflow_access import WorkflowOperation
    from app.services.workflow_access import (
        AccessPrincipal,
        assert_workflow_access,
    )

    effective = operation or (
        WorkflowOperation.EDIT if require_write else WorkflowOperation.VIEW
    )
    role = await workflow_team_role(workflow, user)
    assert_workflow_access(
        workflow,
        WorkflowOperation(effective),
        AccessPrincipal.from_parts(user, team_role=role),
        hidden=WorkflowOperation(effective)
        in {WorkflowOperation.VIEW, WorkflowOperation.RUN},
    )
    return workflow


async def workflow_team_role(workflow: Workflow, user: User) -> str | None:
    """The caller's role in the workflow's team (``None`` for a non-member)."""
    if not workflow.team_id:
        return None
    member = await TeamMember.filter(team_id=workflow.team_id, user_id=user.id).first()
    return str(member.role) if member is not None else None


async def _legacy_workflow_access(
    workflow_id: UUID, user: User, require_write: bool
) -> Workflow:
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
        # PRIVATE means "only the creator can access", so a non-owner is
        # rejected for writes too. A team admin is not a creator: allowing the
        # write here would let an admin modify a workflow that the list and
        # stats scope (workflow_read_visibility_filter) deliberately hides from
        # them, i.e. an IDOR reachable only by guessing the id. This mirrors
        # check_agent_access, which refuses a non-owner's write outright.
        if not workflow.created_by:
            # Creator-less legacy row: no owner exists to protect, so fall back
            # to team scope and require admin for writes.
            await check_team_access(workflow.team.id, user, require_admin=require_write)
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
