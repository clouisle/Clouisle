import logging
from uuid import UUID

from app.models.site_setting import SiteSetting
from app.models.user import Role, Team, TeamMember, User

logger = logging.getLogger(__name__)

DEFAULT_TEAM_ROLES = {"viewer", "member", "admin"}


async def assign_default_role(user: User) -> None:
    """Assign the configured visible global role to a new user."""
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

    _membership, created = await TeamMember.get_or_create(
        team=team,
        user=user,
        defaults={"role": default_team_role},
    )
    return created
