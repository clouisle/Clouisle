from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api import deps
from app.core.i18n import t
from app.models.user import Team, TeamMember, User
from app.models.notification import AutoNotificationType
from app.schemas.team import (
    Team as TeamSchema,
    TeamCreate,
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
    PageData,
    ResponseCode,
    BusinessError,
    success,
)
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService

router = APIRouter()


# ============ Team CRUD ============


@router.get("/", response_model=Response[PageData[TeamSchema]])
async def list_teams(
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(deps.PermissionChecker("team:read")),
) -> Any:
    """
    List all teams the current user belongs to.
    Superuser can see all teams.
    """
    if current_user.is_superuser:
        total = await Team.all().count()
        skip = (page - 1) * page_size
        teams = await Team.all().offset(skip).limit(page_size).prefetch_related("owner")
    else:
        # Only teams where user is a member
        memberships = await TeamMember.filter(user=current_user).prefetch_related(
            "team", "team__owner"
        )
        total = len(memberships)
        skip = (page - 1) * page_size
        teams = [m.team for m in memberships[skip : skip + page_size]]

    return success(
        data={
            "items": teams,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/", response_model=Response[TeamSchema])
async def create_team(
    *,
    request: Request,
    team_in: TeamCreate,
    current_user: User = Depends(deps.PermissionChecker("team:create")),
) -> Any:
    """
    Create a new team. The creator becomes the owner.
    """
    # Check if team name already exists
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

    # Add creator as owner member
    await TeamMember.create(
        team=team,
        user=current_user,
        role=TeamMemberRole.OWNER,
    )

    # Reload with owner
    team = await Team.get(id=team.id).prefetch_related("owner")

    # 记录审计日志
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


@router.get("/my", response_model=Response[List[UserTeamInfo]])
async def get_my_teams(
    current_user: User = Depends(deps.PermissionChecker("team:read")),
) -> Any:
    """
    Get all teams the current user belongs to with their role.
    """
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
    """
    Get team by ID with members list.
    """
    team = await Team.filter(id=team_id).prefetch_related("owner").first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # Check access permission
    if not current_user.is_superuser:
        membership = await TeamMember.filter(team=team, user=current_user).first()
        if not membership:
            raise BusinessError(
                code=ResponseCode.NOT_TEAM_MEMBER,
                msg_key="not_team_member",
                status_code=403,
            )

    # Get members
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
    """
    Update team info. Only owner or admin can update.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # Check permission
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

    # Update fields
    updated_fields = []
    if team_in.name is not None:
        # Check name uniqueness
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

    # 记录审计日志
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


@router.delete("/{team_id}", response_model=Response[TeamSchema])
async def delete_team(
    request: Request,
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:delete")),
) -> Any:
    """
    Delete a team. Only owner or superuser can delete.
    """
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

    # Check permission
    if not current_user.is_superuser:
        membership = await TeamMember.filter(team=team, user=current_user).first()
        if not membership or membership.role != TeamMemberRole.OWNER:
            raise BusinessError(
                code=ResponseCode.TEAM_OWNER_REQUIRED,
                msg_key="team_owner_required",
                status_code=403,
            )

    # 记录审计日志（在删除前）
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


# ============ Team Members ============


@router.post("/{team_id}/members", response_model=Response[TeamMemberInfo])
async def add_team_member(
    *,
    request: Request,
    team_id: UUID,
    member_in: TeamMemberAdd,
    current_user: User = Depends(deps.PermissionChecker("team:manage")),
) -> Any:
    """
    Add a member to the team. Only owner or admin can add members.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # Check permission
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

    # Get user to add
    user_to_add = await User.filter(id=member_in.user_id).first()
    if not user_to_add:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
            status_code=404,
        )

    # Check if already member
    existing = await TeamMember.filter(team=team, user=user_to_add).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.ALREADY_TEAM_MEMBER,
            msg_key="already_team_member",
        )

    # Cannot add as owner
    if member_in.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_ADD_AS_OWNER,
            msg_key="cannot_add_as_owner",
        )

    # Create membership
    new_member = await TeamMember.create(
        team=team,
        user=user_to_add,
        role=member_in.role,
    )

    # 记录审计日志
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

    # 发送自动通知给被添加的用户
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

    # 发送团队通知
    await AutoNotificationService.send_to_team(
        notification_type=AutoNotificationType.TEAM_MEMBER_ADDED,
        team_id=team.id,
        title=t("notify_team_member_added_team_title", lang="en"),
        content=t(
            "notify_team_member_added_team_content",
            lang="en",
            username=user_to_add.username,
            role=member_in.role,
        ),
    )

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
    """
    Update member role. Only owner can change roles.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # Check permission - only owner can change roles
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

    # Get target membership
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

    # Cannot change owner role
    if membership.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_CHANGE_OWNER_ROLE,
            msg_key="cannot_change_owner_role",
        )

    # Cannot promote to owner
    if member_in.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_PROMOTE_TO_OWNER,
            msg_key="cannot_promote_to_owner",
        )

    old_role = membership.role
    membership.role = member_in.role
    await membership.save()

    # 发送自动通知给角色变更的用户
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
    """
    Remove a member from the team.
    Owner/admin can remove others. Members can remove themselves.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # Get target user
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

    # Owner cannot be removed
    if membership.role == TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.CANNOT_REMOVE_OWNER,
            msg_key="cannot_remove_owner",
        )

    # Check permission
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

    # 记录审计日志（在删除前）
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

    # 发送自动通知给被移除的用户
    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_MEMBER_REMOVED,
        user_id=target_user.id,
        title=t("notify_team_member_removed_title", lang=target_user.locale),
        content=t("notify_team_member_removed_content", lang=target_user.locale, team_name=team.name),
    )

    # 发送团队通知
    await AutoNotificationService.send_to_team(
        notification_type=AutoNotificationType.TEAM_MEMBER_REMOVED,
        team_id=team.id,
        title=t("notify_team_member_removed_team_title", lang="en"),
        content=t(
            "notify_team_member_removed_team_content", lang="en", username=target_user.username
        ),
    )

    await membership.delete()
    return success(data={"user_id": str(user_id)}, msg_key="team_member_removed")


@router.post("/{team_id}/leave", response_model=Response[dict])
async def leave_team(
    team_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:read")),
) -> Any:
    """
    Leave a team. Owner cannot leave (must transfer ownership first or delete team).
    """
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
    return success(data={"team_id": str(team_id)}, msg_key="team_left")


@router.post("/{team_id}/transfer-ownership", response_model=Response[TeamSchema])
async def transfer_ownership(
    *,
    team_id: UUID,
    new_owner_id: UUID,
    current_user: User = Depends(deps.PermissionChecker("team:manage")),
) -> Any:
    """
    Transfer team ownership to another member. Only current owner can do this.
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # Check current user is owner
    current_membership = await TeamMember.filter(team=team, user=current_user).first()
    if not current_membership or current_membership.role != TeamMemberRole.OWNER:
        raise BusinessError(
            code=ResponseCode.TEAM_OWNER_REQUIRED,
            msg_key="team_owner_required",
            status_code=403,
        )

    # Get new owner (must be a member)
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

    # Transfer ownership
    current_membership.role = TeamMemberRole.ADMIN
    await current_membership.save()

    new_owner_membership.role = TeamMemberRole.OWNER
    await new_owner_membership.save()

    team.owner = new_owner
    await team.save()

    team = await Team.get(id=team_id).prefetch_related("owner")

    # 发送自动通知给新所有者 (new_owner 已在上面验证不为 None)
    assert new_owner is not None  # for type checker
    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_OWNERSHIP_TRANSFERRED,
        user_id=new_owner.id,
        title=t("notify_team_ownership_received_title", lang=new_owner.locale),
        content=t(
            "notify_team_ownership_received_content",
            lang=new_owner.locale,
            team_name=team.name,
            old_owner=current_user.username,
        ),
    )

    # 发送自动通知给原所有者
    await AutoNotificationService.send_to_user(
        notification_type=AutoNotificationType.TEAM_OWNERSHIP_TRANSFERRED,
        user_id=current_user.id,
        title=t("notify_team_ownership_transferred_title", lang=current_user.locale),
        content=t(
            "notify_team_ownership_transferred_content",
            lang=current_user.locale,
            team_name=team.name,
            new_owner=new_owner.username,
        ),
    )

    return success(data=team, msg_key="ownership_transferred")
