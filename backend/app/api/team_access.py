"""Shared team access helpers."""

from uuid import UUID

from app.api.deps import user_has_global_permission
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode


TEAM_ADMIN_ROLES = frozenset({"owner", "admin"})

# Permissions allowed for read-only team members (viewer role)
VIEWER_ALLOWED_PERMISSIONS = frozenset(
    {
        "team:read",
        "agent:read",
        "agent:chat",
        "workflow:read",
        "workflow:run",
        "workflow:execute",
        "kb:read",
        "kb:test",
        "tool:read",
        "tool:execute",
        "skill:read",
        "skill:execute",
        "conversation:read",
    }
)

# Actions requiring team admin or owner role inside a team
TEAM_MANAGEMENT_PERMISSIONS = frozenset(
    {
        "team:update",
        "team:manage",
        "team:delete",
        "tool:delete",
    }
)


async def check_team_permission(
    team_id: UUID,
    user: User,
    required_permission: str,
    *,
    require_team_admin: bool = False,
) -> Team:
    """Require valid team membership and permission within target team scope."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if user.is_superuser:
        return team

    membership = await TeamMember.filter(team=team, user=user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.NOT_TEAM_MEMBER,
            msg_key="not_team_member",
            status_code=403,
        )

    # Enforce team admin boundary
    needs_team_admin = require_team_admin or (
        required_permission in TEAM_MANAGEMENT_PERMISSIONS
    )
    if needs_team_admin and membership.role not in TEAM_ADMIN_ROLES:
        raise BusinessError(
            code=ResponseCode.TEAM_ADMIN_REQUIRED,
            msg_key="team_admin_required",
            status_code=403,
        )

    # Viewers in this team cannot perform write operations (create/update/delete)
    if (
        membership.role == "viewer"
        and required_permission not in VIEWER_ALLOWED_PERMISSIONS
    ):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="operation_not_permitted",
            status_code=403,
            permission=required_permission,
        )

    # Check user global permission grant
    if not user_has_global_permission(user, required_permission):
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="operation_not_permitted",
            status_code=403,
            permission=required_permission,
        )

    return team


async def check_team_access(
    team_id: UUID, user: User, require_admin: bool = False
) -> Team:
    """Check membership and explicit team-read permission."""
    return await check_team_permission(
        team_id,
        user,
        "team:read",
        require_team_admin=require_admin,
    )
