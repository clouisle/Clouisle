"""
Platform-side team endpoints.
Admin endpoints (full list, create, delete) are in app/api/v1/admin/endpoints/teams.py
"""

from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api import deps
from app.core.i18n import t, get_default_language
from app.models.user import Team, TeamMember, User
from app.models.notification import AutoNotificationType
from app.schemas.team import (
    Team as TeamSchema,
    TeamUpdate,
    TeamWithMembers,
    TeamMemberAdd,
    TeamMemberUpdate,
    TeamMemberInfo,
    TeamMemberRole,
    UserTeamInfo,
)
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService
from app.services.team_role_sync import sync_user_role_from_teams

router = APIRouter()


@router.get("/my", response_model=Response[List[UserTeamInfo]])
async def get_my_teams(
    current_user: User = Depends(deps.PermissionChecker("team:read")),
) -> Any:
    """Get all teams the current user belongs to with their role."""
    memberships = await TeamMember.filter(user=current_user).prefetch_related("team")

    result = []
    for membership in memberships:
        result.append(
            {
                "id": membership.team.id,
                "name": membership.team.name,
                "description": membership.team.description,
                "avatar_url": membership.team.avatar_url,
                "role": membership.role,
                "joined_at": membership.joined_at,
            }
        )

    return success(data=result)


@router.get("/{team_id}", response_model=Response[TeamWithMembers])
async def get_team(
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:read")),
) -> Any:
    """Get team by ID with members list."""
    team = await Team.filter(id=team_id).prefetch_related("owner").first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if not current_user.is_superuser:
        membership = await TeamMember.filter(team=team, user=current_user).first()
        if not membership:
            raise BusinessError(
                code=ResponseCode.NOT_TEAM_MEMBER,
                msg_key="not_team_member",
                status_code=403,
            )

    memberships = await TeamMember.filter(team=team).prefetch_related("user")
    members = []
    for m in memberships:
        members.append(
            {
                "id": m.id,
                "user_id": m.user.id,
                "username": m.user.username,
                "email": m.user.email,
                "avatar_url": m.user.avatar_url,
                "role": m.role,
                "joined_at": m.joined_at,
            }
        )

    return success(
        data={
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "avatar_url": team.avatar_url,
            "is_default": team.is_default,
            "owner": team.owner,
            "created_at": team.created_at,
            "updated_at": team.updated_at,
            "members": members,
        }
    )


@router.put("/{team_id}", response_model=Response[TeamSchema])
async def update_team(
    *,
    request: Request,
    team_id: UUID,
    team_in: TeamUpdate,
    current_user: User = Depends(deps.PermissionChecker("team:update")),
) -> Any:
    """Update team info. Only owner or admin can update."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if not current_user.is_superuser:
        membership = await TeamMember.filter(team=team, user=current_user).first()
        if not membership or membership.role not in [
            TeamMemberRole.OWNER,
            TeamMemberRole.ADMIN,
        ]:
            raise BusinessError(
                code=ResponseCode.TEAM_ADMIN_REQUIRED,
                msg_key="team_admin_required",
                status_code=403,
            )

    updated_fields = []
    if team_in.name is not None:
        existing = await Team.filter(name=team_in.name).exclude(id=team_id).first()
        if existing:
            raise BusinessError(
                code=ResponseCode.TEAM_NAME_EXISTS,
                msg_key="team_name_exists",
            )
        team.name = team_in.name
        updated_fields.append("name")

    if team_in.description is not None:
        team.description = team_in.description
        updated_fields.append("description")

    if team_in.avatar_url is not None:
        team.avatar_url = team_in.avatar_url
        updated_fields.append("avatar_url")

    await team.save()
    team = await Team.get(id=team_id).prefetch_related("owner")

    await AuditLogService.log(
        user=current_user,
        action="update_team",
        resource_type="team",
        resource_id=team.id,
        resource_name=team.name,
        operation="update",
        status="success",
        request=request,
        metadata={"fields_updated": updated_fields},
    )

    return success(data=team, msg_key="team_updated")


@router.post("/{team_id}/members", response_model=Response[TeamMemberInfo])
async def add_team_member(
    *,
    request: Request,
    team_id: UUID,
    member_in: TeamMemberAdd,
    current_user: User = Depends(deps.PermissionChecker("team:manage")),
) -> Any:
    """Add a member to the team. Only owner or admin can add members."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if not current_user.is_superuser:
        membership = await TeamMember.filter(team=team, user=current_user).first()
        if not membership or membership.role not in [
            TeamMemberRole.OWNER,
            TeamMemberRole.ADMIN,
        ]:
            raise BusinessError(
                code=ResponseCode.TEAM_ADMIN_REQUIRED,
                msg_key="team_admin_required",
                status_code=403,
            )

    user_to_add = await User.filter(id=member_in.user_id).first()
    if not user_to_add:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
            status_code=404,
        )

    existing = await TeamMember.filter(team=team, user=user_to_add).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ALREADY_TEAM_MEMBER,
            msg_key="already_team_member",
        )

    if member_in.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_ADD_AS_OWNER,
            msg_key="cannot_add_as_owner",
        )

    new_member = await TeamMember.create(
        team=team,
        user=user_to_add,
        role=member_in.role,
    )

    await AuditLogService.log(
        user=current_user,
        action="add_team_member",
        resource_type="team",
        resource_id=team.id,
        resource_name=team.name,
        operation="update",
        status="success",
        request=request,
        metadata={
            "added_user_id": str(user_to_add.id),
            "added_username": user_to_add.username,
            "role": member_in.role,
        },
    )

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_MEMBER_ADDED,
        user_id=user_to_add.id,
        title=t("notify_team_member_added_title", lang=user_to_add.locale),
        content=t(
            "notify_team_member_added_content",
            lang=user_to_add.locale,
            team_name=team.name,
            operator=current_user.username,
            role=member_in.role,
        ),
    )

    default_lang = await get_default_language()
    await AutoNotificationService.send_to_team(
        notification_type=AutoNotificationType.TEAM_MEMBER_ADDED,
        team_id=team.id,
        title=t("notify_team_member_added_team_title", lang=default_lang),
        content=t(
            "notify_team_member_added_team_content",
            lang=default_lang,
            username=user_to_add.username,
            role=member_in.role,
        ),
    )

    await sync_user_role_from_teams(user_to_add)

    return success(
        data={
            "id": new_member.id,
            "user_id": user_to_add.id,
            "username": user_to_add.username,
            "email": user_to_add.email,
            "avatar_url": user_to_add.avatar_url,
            "role": new_member.role,
            "joined_at": new_member.joined_at,
        },
        msg_key="team_member_added",
    )


@router.put("/{team_id}/members/{user_id}", response_model=Response[TeamMemberInfo])
async def update_team_member(
    *,
    team_id: UUID,
    user_id: UUID,
    member_in: TeamMemberUpdate,
    current_user: User = Depends(deps.PermissionChecker("team:manage")),
) -> Any:
    """Update member role. Only owner can change roles."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if not current_user.is_superuser:
        current_membership = await TeamMember.filter(
            team=team, user=current_user
        ).first()
        if not current_membership or current_membership.role != TeamMemberRole.OWNER:
            raise BusinessError(
                code=ResponseCode.TEAM_OWNER_REQUIRED,
                msg_key="team_owner_required",
                status_code=403,
            )

    target_user = await User.filter(id=user_id).first()
    if not target_user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
            status_code=404,
        )

    membership = await TeamMember.filter(team=team, user=target_user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.TEAM_MEMBER_NOT_FOUND,
            msg_key="team_member_not_found",
            status_code=404,
        )

    if membership.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_CHANGE_OWNER_ROLE,
            msg_key="cannot_change_owner_role",
        )

    if member_in.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_PROMOTE_TO_OWNER,
            msg_key="cannot_promote_to_owner",
        )

    old_role = membership.role
    membership.role = member_in.role
    await membership.save()

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_ROLE_CHANGED,
        user_id=target_user.id,
        title=t("notify_team_role_changed_title", lang=target_user.locale),
        content=t(
            "notify_team_role_changed_content",
            lang=target_user.locale,
            team_name=team.name,
            old_role=old_role,
            new_role=member_in.role,
        ),
    )

    await sync_user_role_from_teams(target_user)

    return success(
        data={
            "id": membership.id,
            "user_id": target_user.id,
            "username": target_user.username,
            "email": target_user.email,
            "avatar_url": target_user.avatar_url,
            "role": membership.role,
            "joined_at": membership.joined_at,
        },
        msg_key="team_member_updated",
    )


@router.delete("/{team_id}/members/{user_id}", response_model=Response[dict])
async def remove_team_member(
    request: Request,
    team_id: UUID,
    user_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:manage")),
) -> Any:
    """Remove a member from the team."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    target_user = await User.filter(id=user_id).first()
    if not target_user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
            status_code=404,
        )

    membership = await TeamMember.filter(team=team, user=target_user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.TEAM_MEMBER_NOT_FOUND,
            msg_key="team_member_not_found",
            status_code=404,
        )

    if membership.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_REMOVE_OWNER,
            msg_key="cannot_remove_owner",
        )

    is_self = str(target_user.id) == str(current_user.id)
    if not is_self and not current_user.is_superuser:
        current_membership = await TeamMember.filter(
            team=team, user=current_user
        ).first()
        if not current_membership or current_membership.role not in [
            TeamMemberRole.OWNER,
            TeamMemberRole.ADMIN,
        ]:
            raise BusinessError(
                code=ResponseCode.TEAM_ADMIN_REQUIRED,
                msg_key="team_admin_required",
                status_code=403,
            )

    await AuditLogService.log(
        user=current_user,
        action="remove_team_member",
        resource_type="team",
        resource_id=team.id,
        resource_name=team.name,
        operation="update",
        status="success",
        request=request,
        metadata={
            "removed_user_id": str(target_user.id),
            "removed_username": target_user.username,
            "is_self_removal": is_self,
        },
    )

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_MEMBER_REMOVED,
        user_id=target_user.id,
        title=t("notify_team_member_removed_title", lang=target_user.locale),
        content=t(
            "notify_team_member_removed_content",
            lang=target_user.locale,
            team_name=team.name,
        ),
    )

    default_lang = await get_default_language()
    await AutoNotificationService.send_to_team(
        notification_type=AutoNotificationType.TEAM_MEMBER_REMOVED,
        team_id=team.id,
        title=t("notify_team_member_removed_team_title", lang=default_lang),
        content=t(
            "notify_team_member_removed_team_content",
            lang=default_lang,
            username=target_user.username,
        ),
    )

    await membership.delete()
    await sync_user_role_from_teams(target_user)

    return success(data={"user_id": str(user_id)}, msg_key="team_member_removed")


@router.post("/{team_id}/leave", response_model=Response[dict])
async def leave_team(
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:read")),
) -> Any:
    """Leave a team. Owner cannot leave without transferring ownership first."""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    membership = await TeamMember.filter(team=team, user=current_user).first()
    if not membership:
        raise BusinessError(
            code=ResponseCode.NOT_TEAM_MEMBER,
            msg_key="not_team_member",
            status_code=404,
        )

    if membership.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.OWNER_CANNOT_LEAVE,
            msg_key="owner_cannot_leave",
        )

    await membership.delete()
    await sync_user_role_from_teams(current_user)

    return success(data={"team_id": str(team_id)}, msg_key="team_left")


@router.post("/{team_id}/transfer-ownership", response_model=Response[TeamSchema])
async def transfer_ownership(
    *,
    team_id: UUID,
    new_owner_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:manage")),
) -> Any:
    """
    Transfer team ownership to another member.

    Only current owner or superuser can do this.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    current_membership = await TeamMember.filter(team=team, user=current_user).first()
    if not current_user.is_superuser and (
        not current_membership or current_membership.role != TeamMemberRole.OWNER
    ):
        raise BusinessError(
            code=ResponseCode.TEAM_OWNER_REQUIRED,
            msg_key="team_owner_required",
            status_code=403,
        )

    previous_owner_membership = (
        await TeamMember.filter(team=team, role=TeamMemberRole.OWNER)
        .prefetch_related("user")
        .first()
    )

    new_owner = await User.filter(id=new_owner_id).first()
    new_owner_membership = (
        await TeamMember.filter(team=team, user=new_owner).first()
        if new_owner
        else None
    )
    if not new_owner_membership or not new_owner:
        raise BusinessError(
            code=ResponseCode.TEAM_MEMBER_NOT_FOUND,
            msg_key="team_member_not_found",
            status_code=404,
        )

    old_owner = (
        previous_owner_membership.user if previous_owner_membership else current_user
    )
    if previous_owner_membership:
        previous_owner_membership.role = TeamMemberRole.ADMIN
        await previous_owner_membership.save()

    new_owner_membership.role = TeamMemberRole.OWNER
    await new_owner_membership.save()

    team.owner = new_owner
    await team.save()

    team = await Team.get(id=team_id).prefetch_related("owner")

    assert new_owner is not None
    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_OWNERSHIP_TRANSFERRED,
        user_id=new_owner.id,
        title=t("notify_team_ownership_received_title", lang=new_owner.locale),
        content=t(
            "notify_team_ownership_received_content",
            lang=new_owner.locale,
            team_name=team.name,
            old_owner=old_owner.username,
        ),
    )

    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_OWNERSHIP_TRANSFERRED,
        user_id=old_owner.id,
        title=t("notify_team_ownership_transferred_title", lang=old_owner.locale),
        content=t(
            "notify_team_ownership_transferred_content",
            lang=old_owner.locale,
            team_name=team.name,
            new_owner=new_owner.username,
        ),
    )

    await sync_user_role_from_teams(old_owner)
    await sync_user_role_from_teams(new_owner)

    return success(data=team, msg_key="ownership_transferred")
