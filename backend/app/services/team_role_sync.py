import logging

from app.models.user import Role, TeamMember, User

logger = logging.getLogger(__name__)

# Team role to global role mapping
# owner/admin -> Admin, member -> Member, viewer -> no extra role
TEAM_ROLE_TO_GLOBAL = {
    "owner": "Admin",
    "admin": "Admin",
    "member": "Member",
}


async def sync_user_role_from_teams(user: User) -> None:
    """
    Sync global roles based on the user's highest team role across all teams.

    - Any team with owner/admin -> ensure user has Admin + Member global roles
    - Highest team role is member -> remove Admin, ensure Member
    - Highest is viewer or no teams -> remove Admin and Member (keep others like Viewer)
    """
    memberships = await TeamMember.filter(user=user).all()

    has_admin = False
    has_member = False

    for m in memberships:
        if m.role in ("owner", "admin"):
            has_admin = True
            has_member = True
        elif m.role == "member":
            has_member = True

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
