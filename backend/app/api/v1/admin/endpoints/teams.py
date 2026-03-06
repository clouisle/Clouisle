"""
Admin-only team endpoints: full list (all teams), create team, delete team.
Platform-side endpoints (my teams, get team, update, members, leave, transfer) remain in endpoints/teams.py
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query
from tortoise.expressions import Q

from app.api import deps
from app.models.user import Team, TeamMember, User
from app.schemas.team import (
    Team as TeamSchema,
    TeamCreate,
    TeamMemberRole,
)
from app.schemas.response import (
    Response,
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService

router = APIRouter()


@router.get("", response_model=Response[PageData[TeamSchema]])
async def list_all_teams(
    page: int = 1,
    page_size: int = 50,
    search: str | None = Query(None, description="Search by team name or description"),
    current_user: User = Depends(deps.PermissionChecker("admin:team:read")),
) -> Any:
    """List all teams (admin: sees all teams regardless of membership)."""
    query = Team.all()

    if search:
        query = query.filter(Q(name__icontains=search) | Q(description__icontains=search))

    total = await query.count()
    skip = (page - 1) * page_size
    teams = await query.offset(skip).limit(page_size).prefetch_related("owner")

    return success(
        data={
            "items": teams,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("", response_model=Response[TeamSchema])
async def create_team(
    *,
    request: Request,
    team_in: TeamCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:team:create")),
) -> Any:
    """Create a new team (admin)."""
    existing = await Team.filter(name=team_in.name).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.TEAM_NAME_EXISTS,
            msg_key="team_name_exists",
        )

    team = await Team.create(
        name=team_in.name,
        description=team_in.description,
        avatar_url=team_in.avatar_url,
        owner=current_user,
    )

    await TeamMember.create(
        team=team,
        user=current_user,
        role=TeamMemberRole.OWNER,
    )

    team = await Team.get(id=team.id).prefetch_related("owner")

    await AuditLogService.log(
        user=current_user,
        action="create_team",
        resource_type="team",
        resource_id=team.id,
        resource_name=team.name,
        operation="create",
        status="success",
        request=request,
    )

    return success(data=team, msg_key="team_created")


@router.delete("/{team_id}", response_model=Response[TeamSchema])
async def delete_team(
    request: Request,
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("admin:team:delete")),
) -> Any:
    """Delete a team (admin: superuser can delete any non-default team)."""
    team = await Team.filter(id=team_id).prefetch_related("owner").first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if team.is_default:
        raise BusinessError(
            code=ResponseCode.CANNOT_DELETE_DEFAULT_TEAM,
            msg_key="cannot_delete_default_team",
        )

    await AuditLogService.log(
        user=current_user,
        action="delete_team",
        resource_type="team",
        resource_id=team.id,
        resource_name=team.name,
        operation="delete",
        status="success",
        request=request,
    )

    await team.delete()
    return success(data=team, msg_key="team_deleted")
