import logging
from uuid import UUID

from app.models.site_setting import SiteSetting
from app.models.user import Role, ScopedRoleAssignment, Team, TeamMember, User

logger = logging.getLogger(__name__)

# Team role to scoped role mapping. Team roles no longer grant global roles.
TEAM_ROLE_TO_GLOBAL: dict[str, tuple[str, ...]] = {}
TEAM_ROLE_TO_SCOPED_ROLE = {
    "owner": "Admin",
    "admin": "Admin",
    "member": "Member",
    "viewer": "Viewer",
}

DEFAULT_TEAM_ROLES = {"viewer", "member", "admin"}


async def sync_scoped_role_assignment(membership: TeamMember) -> None:
    """Mirror a team membership role into a team-scoped role assignment."""
    role_name = TEAM_ROLE_TO_SCOPED_ROLE.get(membership.role)
    if not role_name:
        logger.warning("Unknown team role %r for scoped sync", membership.role)
        return

    role = await Role.filter(name=role_name).first()
    if not role:
        logger.warning("Scoped sync role %s not found", role_name)
        return

    await ScopedRoleAssignment.filter(
        user=membership.user,
        scope_type="team",
        scope_id=membership.team.id,
    ).delete()
    await ScopedRoleAssignment.get_or_create(
        user=membership.user,
        role=role,
        scope_type="team",
        scope_id=membership.team.id,
        defaults={"source": "system"},
    )


async def remove_scoped_role_assignment(user: User, team_id: UUID) -> None:
    """Remove team-scoped role assignments for a user in one team."""
    await ScopedRoleAssignment.filter(
        user=user,
        scope_type="team",
        scope_id=team_id,
    ).delete()


async def assign_default_role(user: User) -> None:
    """
    Assign the global default role (from site settings) to a user.
    Used for new user registration (both regular and SSO fallback).
    """
    default_role_id = await SiteSetting.get_value("default_role_id", "")
    if default_role_id:
        role = await Role.get_or_none(id=default_role_id)
        if role:
            await user.roles.add(role)


async def assign_default_team(user: User) -> bool:
    """Assign the configured default team membership to a newly registered user."""
    default_team_id = await SiteSetting.get_value("default_team_id", "")
    if not default_team_id:
        return False

    default_team_role = await SiteSetting.get_value("default_team_role", "member")
    if default_team_role not in DEFAULT_TEAM_ROLES:
        logger.warning(
            "Invalid default_team_role %r; falling back to member",
            default_team_role,
        )
        default_team_role = "member"

    try:
        team_id = UUID(str(default_team_id))
    except ValueError:
        logger.warning(
            "Invalid default_team_id %r; skipping assignment", default_team_id
        )
        return False

    team = await Team.filter(id=team_id, is_deleted=False).first()
    if not team:
        logger.warning(
            "Default team %s not found; skipping assignment", default_team_id
        )
        return False

    membership, created = await TeamMember.get_or_create(
        team=team,
        user=user,
        defaults={"role": default_team_role},
    )
    if created:
        await sync_scoped_role_assignment(membership)
    return created


async def sync_user_role_from_teams(user: User) -> None:
    """Sync team memberships into scoped role assignments.

    Legacy behavior granted/removing global Admin/Member from team roles. Do not do
    that anymore: existing global roles may be manual, and source was not tracked.
    """
    memberships = await TeamMember.filter(user=user).prefetch_related("team", "user")
    active_team_ids = set()
    for membership in memberships:
        active_team_ids.add(membership.team.id)
        await sync_scoped_role_assignment(membership)

    await (
        ScopedRoleAssignment.filter(
            user=user,
            scope_type="team",
        )
        .exclude(scope_id__in=active_team_ids)
        .delete()
    )
