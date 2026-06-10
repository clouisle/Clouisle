import logging
from uuid import UUID

from app.models.site_setting import SiteSetting
from app.models.user import Role, Team, TeamMember, User

logger = logging.getLogger(__name__)

# Team role to global role mapping
# owner/admin -> Admin, member -> Member, viewer -> no extra role
TEAM_ROLE_TO_GLOBAL = {
    "owner": "Admin",
    "admin": "Admin",
    "member": "Member",
}

DEFAULT_TEAM_ROLES = {"viewer", "member", "admin"}


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

    _, created = await TeamMember.get_or_create(
        team=team,
        user=user,
        defaults={"role": default_team_role},
    )
    return created


async def sync_user_role_from_teams(user: User) -> None:
    """
    Sync global roles based on the user's highest team role across all teams.

    - Any team with owner/admin -> ensure user has Admin + Member global roles
    - Highest team role is member -> remove Admin, ensure Member
    - Highest is viewer or no teams -> remove Admin and Member (keep others like Viewer)
    """
    memberships = await TeamMember.filter(user=user).all()

    roles = {m.role for m in memberships}
    has_admin = "owner" in roles or "admin" in roles
    has_member = has_admin or "member" in roles

    admin_role = await Role.filter(name="Admin").first()
    member_role = await Role.filter(name="Member").first()

    if has_admin and admin_role:
        await user.roles.add(admin_role)
    elif admin_role:
        await user.roles.remove(admin_role)

    if has_member and member_role:
        await user.roles.add(member_role)
    elif member_role:
        await user.roles.remove(member_role)
