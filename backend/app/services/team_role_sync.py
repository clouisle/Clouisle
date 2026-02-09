import logging

from app.models.site_setting import SiteSetting
from app.models.user import Role, TeamMember, User

logger = logging.getLogger(__name__)

# Team role to global role mapping
# owner/admin -> Admin, member -> Member, viewer -> no extra role
TEAM_ROLE_TO_GLOBAL = {
    "owner": "Admin",
    "admin": "Admin",
    "member": "Member",
}


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
