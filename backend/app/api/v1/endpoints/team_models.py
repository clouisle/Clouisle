"""
团队模型授权管理 API

提供团队模型授权的增删改查功能。
"""

from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api import deps
from app.core.i18n import t
from app.models import Model, Team, TeamModel
from app.models.notification import AutoNotificationType
from app.models.user import TeamMember, User
from app.schemas.model import (
    ModelBrief,
    TeamModelCreate,
    TeamModelUpdate,
    TeamModelResponse,
    TeamModelBatchCreate,
    TeamModelBatchDelete,
    TeamModelQuotaStatus,
)
from app.schemas.response import (
    Response,
    ResponseCode,
    BusinessError,
    success,
)
from app.schemas.team import TeamMemberRole
from app.services.auto_notification import AutoNotificationService
from app.services.audit_log import AuditLogService

router = APIRouter()


async def check_team_admin_permission(team_id: UUID, user: User) -> Team:
    """检查用户是否有团队管理权限（owner/admin 或超级管理员）"""
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    if not user.is_superuser:
        membership = await TeamMember.filter(team=team, user=user).first()
        if not membership or membership.role not in [
            TeamMemberRole.OWNER,
            TeamMemberRole.ADMIN,
        ]:
            raise BusinessError(
                code=ResponseCode.TEAM_ADMIN_REQUIRED,
                msg_key="team_admin_required",
                status_code=403,
            )

    return team


# ============ 团队模型授权管理 ============


@router.get("/{team_id}/models", response_model=Response[List[TeamModelResponse]])
async def list_team_models(
    team_id: UUID,
    model_type: str | None = None,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    获取团队已授权的模型列表
    """
    # 检查团队存在性和访问权限
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # 非超管需要是团队成员
    if not current_user.is_superuser:
        membership = await TeamMember.filter(team=team, user=current_user).first()
        if not membership:
            raise BusinessError(
                code=ResponseCode.NOT_TEAM_MEMBER,
                msg_key="not_team_member",
                status_code=403,
            )

    # 查询授权
    query = TeamModel.filter(team_id=team_id)
    if model_type:
        query = query.filter(model__model_type=model_type)

    authorizations = await query.prefetch_related("model").order_by(
        "-priority", "created_at"
    )

    result = [TeamModelResponse.model_validate(auth) for auth in authorizations]

    return success(data=result)


@router.post("/{team_id}/models", response_model=Response[TeamModelResponse])
async def add_team_model(
    team_id: UUID,
    request: Request,
    auth_in: TeamModelCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    为团队授权模型（仅超级管理员）
    """
    # 检查团队
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # 检查模型
    model = await Model.filter(id=auth_in.model_id).first()
    if not model:
        raise BusinessError(
            code=ResponseCode.MODEL_NOT_FOUND,
            msg_key="model_not_found",
            status_code=404,
        )

    # 检查是否已授权
    existing = await TeamModel.filter(
        team_id=team_id, model_id=auth_in.model_id
    ).first()
    if existing:
        raise BusinessError(
            code=ResponseCode.TEAM_MODEL_EXISTS,
            msg_key="team_model_already_authorized",
        )

    # 创建授权
    team_model = await TeamModel.create(
        team=team,
        model=model,
        daily_token_limit=auth_in.daily_token_limit,
        monthly_token_limit=auth_in.monthly_token_limit,
        daily_request_limit=auth_in.daily_request_limit,
        monthly_request_limit=auth_in.monthly_request_limit,
        is_enabled=auth_in.is_enabled,
        priority=auth_in.priority,
    )

    # 重新加载关联
    team_model = await TeamModel.get(id=team_model.id).prefetch_related("model")

    # 发送模型授权通知给团队
    await AutoNotificationService.send_to_team(
        notification_type=AutoNotificationType.TEAM_MODEL_GRANTED,
        team_id=team.id,
        title=t("notify_team_model_granted_title"),
        content=t(
            "notify_team_model_granted_content",
            model_name=model.name,
            team_name=team.name,
        ),
        data={
            "model_id": str(model.id),
            "model_name": model.name,
            "team_id": str(team.id),
            "team_name": team.name,
        },
    )

    await AuditLogService.log(
        user=current_user,
        action="add_team_model",
        resource_type="team_model",
        resource_id=team_model.id,
        resource_name=f"{team.name} - {model.name}",
        operation="create",
        status="success",
        request=request,
        metadata={
            "team_id": str(team_id),
            "model_id": str(auth_in.model_id),
            "model_name": model.name,
        },
    )

    return success(
        data={
            "id": team_model.id,
            "team_id": team_model.team_id,
            "model_id": team_model.model_id,
            "model": {
                "id": model.id,
                "name": model.name,
                "provider": model.provider,
                "model_id": model.model_id,
                "model_type": model.model_type,
            },
            "daily_token_limit": team_model.daily_token_limit,
            "monthly_token_limit": team_model.monthly_token_limit,
            "daily_request_limit": team_model.daily_request_limit,
            "monthly_request_limit": team_model.monthly_request_limit,
            "daily_tokens_used": team_model.daily_tokens_used,
            "monthly_tokens_used": team_model.monthly_tokens_used,
            "daily_requests_used": team_model.daily_requests_used,
            "monthly_requests_used": team_model.monthly_requests_used,
            "is_enabled": team_model.is_enabled,
            "priority": team_model.priority,
            "created_at": team_model.created_at,
            "updated_at": team_model.updated_at,
        },
        msg_key="team_model_authorized",
    )


@router.put("/{team_id}/models/{model_id}", response_model=Response[TeamModelResponse])
async def update_team_model(
    team_id: UUID,
    model_id: UUID,
    request: Request,
    auth_in: TeamModelUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    更新团队模型授权配置（仅超级管理员）
    """
    team_model = (
        await TeamModel.filter(team_id=team_id, model_id=model_id)
        .prefetch_related("model")
        .first()
    )

    if not team_model:
        raise BusinessError(
            code=ResponseCode.TEAM_MODEL_NOT_FOUND,
            msg_key="team_model_not_found",
            status_code=404,
        )

    # 更新字段
    update_data = auth_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(team_model, field, value)

    await team_model.save()

    await AuditLogService.log(
        user=current_user,
        action="update_team_model",
        resource_type="team_model",
        resource_id=team_model.id,
        resource_name=f"{team_id} - {team_model.model.name}",
        operation="update",
        status="success",
        request=request,
        metadata={
            "team_id": str(team_id),
            "model_id": str(model_id),
            "updated_fields": list(update_data.keys()),
        },
    )

    return success(
        data={
            "id": team_model.id,
            "team_id": team_model.team_id,
            "model_id": team_model.model_id,
            "model": {
                "id": team_model.model.id,
                "name": team_model.model.name,
                "provider": team_model.model.provider,
                "model_id": team_model.model.model_id,
                "model_type": team_model.model.model_type,
            },
            "daily_token_limit": team_model.daily_token_limit,
            "monthly_token_limit": team_model.monthly_token_limit,
            "daily_request_limit": team_model.daily_request_limit,
            "monthly_request_limit": team_model.monthly_request_limit,
            "daily_tokens_used": team_model.daily_tokens_used,
            "monthly_tokens_used": team_model.monthly_tokens_used,
            "daily_requests_used": team_model.daily_requests_used,
            "monthly_requests_used": team_model.monthly_requests_used,
            "is_enabled": team_model.is_enabled,
            "priority": team_model.priority,
            "created_at": team_model.created_at,
            "updated_at": team_model.updated_at,
        },
        msg_key="team_model_updated",
    )


@router.delete("/{team_id}/models/{model_id}", response_model=Response[dict])
async def remove_team_model(
    team_id: UUID,
    model_id: UUID,
    request: Request,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    撤销团队模型授权（仅超级管理员）
    """
    team_model = (
        await TeamModel.filter(team_id=team_id, model_id=model_id)
        .prefetch_related("model", "team")
        .first()
    )

    if not team_model:
        raise BusinessError(
            code=ResponseCode.TEAM_MODEL_NOT_FOUND,
            msg_key="team_model_not_found",
            status_code=404,
        )

    # 保存信息用于通知
    model_name = team_model.model.name
    team_name = team_model.team.name
    team_id_for_notify = team_model.team.id

    await team_model.delete()

    # 发送模型授权撤销通知给团队
    await AutoNotificationService.send_to_team(
        notification_type=AutoNotificationType.TEAM_MODEL_REVOKED,
        team_id=team_id_for_notify,
        title=t("notify_team_model_revoked_title"),
        content=t(
            "notify_team_model_revoked_content",
            model_name=model_name,
            team_name=team_name,
        ),
        data={
            "model_id": str(model_id),
            "model_name": model_name,
            "team_id": str(team_id),
            "team_name": team_name,
        },
    )

    await AuditLogService.log(
        user=current_user,
        action="remove_team_model",
        resource_type="team_model",
        resource_id=model_id,
        resource_name=f"{team_name} - {model_name}",
        operation="delete",
        status="success",
        request=request,
        metadata={
            "team_id": str(team_id),
            "model_id": str(model_id),
            "model_name": model_name,
        },
    )

    return success(
        data={"team_id": str(team_id), "model_id": str(model_id)},
        msg_key="team_model_revoked",
    )


# ============ 批量操作 ============


@router.post(
    "/{team_id}/models/batch", response_model=Response[List[TeamModelResponse]]
)
async def batch_add_team_models(
    team_id: UUID,
    request: Request,
    batch_in: TeamModelBatchCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    批量为团队授权模型（仅超级管理员）
    """
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # 获取所有模型
    models = await Model.filter(id__in=batch_in.model_ids)
    model_map = {m.id: m for m in models}

    # 检查已存在的授权
    existing = await TeamModel.filter(
        team_id=team_id, model_id__in=batch_in.model_ids
    ).values_list("model_id", flat=True)
    existing_set = set(existing)

    # 创建新授权
    results = []
    for model_id in batch_in.model_ids:
        if model_id in existing_set:
            continue
        if model_id not in model_map:
            continue

        model = model_map[model_id]
        team_model = await TeamModel.create(
            team=team,
            model=model,
            daily_token_limit=batch_in.daily_token_limit,
            monthly_token_limit=batch_in.monthly_token_limit,
            daily_request_limit=batch_in.daily_request_limit,
            monthly_request_limit=batch_in.monthly_request_limit,
        )

        results.append(
            {
                "id": team_model.id,
                "team_id": team_model.team_id,
                "model_id": team_model.model_id,
                "model": {
                    "id": model.id,
                    "name": model.name,
                    "provider": model.provider,
                    "model_id": model.model_id,
                    "model_type": model.model_type,
                },
                "daily_token_limit": team_model.daily_token_limit,
                "monthly_token_limit": team_model.monthly_token_limit,
                "daily_request_limit": team_model.daily_request_limit,
                "monthly_request_limit": team_model.monthly_request_limit,
                "daily_tokens_used": team_model.daily_tokens_used,
                "monthly_tokens_used": team_model.monthly_tokens_used,
                "daily_requests_used": team_model.daily_requests_used,
                "monthly_requests_used": team_model.monthly_requests_used,
                "is_enabled": team_model.is_enabled,
                "priority": team_model.priority,
                "created_at": team_model.created_at,
                "updated_at": team_model.updated_at,
            }
        )

    # 发送批量授权通知
    if results:
        model_names = [r["model"]["name"] for r in results]
        await AutoNotificationService.send_to_team(
            notification_type=AutoNotificationType.TEAM_MODEL_GRANTED,
            team_id=team.id,
            title=t("notify_team_model_granted_title"),
            content=t(
                "notify_team_model_granted_content",
                model_name=", ".join(model_names),
                team_name=team.name,
            ),
            data={
                "model_count": len(results),
                "model_names": model_names,
                "team_id": str(team.id),
                "team_name": team.name,
            },
        )

    await AuditLogService.log(
        user=current_user,
        action="batch_add_team_models",
        resource_type="team_model",
        resource_name=f"{team.name} - {len(results)} models",
        operation="create",
        status="success",
        request=request,
        metadata={
            "team_id": str(team_id),
            "team_name": team.name,
            "model_count": len(results),
            "model_ids": [str(m) for m in batch_in.model_ids],
        },
    )

    return success(data=results, msg_key="team_models_authorized")


@router.delete("/{team_id}/models/batch", response_model=Response[dict])
async def batch_remove_team_models(
    team_id: UUID,
    request: Request,
    batch_in: TeamModelBatchDelete,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    批量撤销团队模型授权（仅超级管理员）
    """
    # 获取团队信息
    team = await Team.filter(id=team_id).first()
    if not team:
        raise BusinessError(
            code=ResponseCode.TEAM_NOT_FOUND,
            msg_key="team_not_found",
            status_code=404,
        )

    # 获取要删除的模型名称（用于通知）
    team_models = await TeamModel.filter(
        team_id=team_id, model_id__in=batch_in.model_ids
    ).prefetch_related("model")
    model_names = [tm.model.name for tm in team_models]

    deleted_count = await TeamModel.filter(
        team_id=team_id, model_id__in=batch_in.model_ids
    ).delete()

    # 发送批量撤销通知
    if deleted_count > 0 and model_names:
        await AutoNotificationService.send_to_team(
            notification_type=AutoNotificationType.TEAM_MODEL_REVOKED,
            team_id=team.id,
            title=t("notify_team_model_revoked_title"),
            content=t(
                "notify_team_model_revoked_content",
                model_name=", ".join(model_names),
                team_name=team.name,
            ),
            data={
                "model_count": deleted_count,
                "model_names": model_names,
                "team_id": str(team.id),
                "team_name": team.name,
            },
        )

    await AuditLogService.log(
        user=current_user,
        action="batch_remove_team_models",
        resource_type="team_model",
        resource_name=f"{team.name} - {deleted_count} models",
        operation="delete",
        status="success",
        request=request,
        metadata={
            "team_id": str(team_id),
            "team_name": team.name,
            "deleted_count": deleted_count,
            "model_names": model_names,
        },
    )

    return success(
        data={"deleted_count": deleted_count},
        msg_key="team_models_revoked",
    )


# ============ 可用模型查询（中台使用） ============


@router.get("/{team_id}/available-models", response_model=Response[List[ModelBrief]])
async def get_team_available_models(
    team_id: UUID,
    model_type: str | None = None,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    获取团队可用的模型列表（中台使用）

    只返回已授权且启用的模型。
    """
    # 检查团队成员权限
    team = await Team.filter(id=team_id).first()
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

    # 查询已授权且启用的模型
    query = TeamModel.filter(
        team_id=team_id,
        is_enabled=True,
        model__is_enabled=True,
    )

    if model_type:
        query = query.filter(model__model_type=model_type)

    authorizations = await query.prefetch_related("model").order_by("-priority")

    models = [
        {
            "id": auth.model.id,
            "name": auth.model.name,
            "provider": auth.model.provider,
            "model_id": auth.model.model_id,
            "model_type": auth.model.model_type,
        }
        for auth in authorizations
    ]

    return success(data=models)


@router.get(
    "/{team_id}/models/quota", response_model=Response[List[TeamModelQuotaStatus]]
)
async def get_team_models_quota(
    team_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    获取团队模型配额使用状态
    """
    # 检查团队成员权限
    team = await Team.filter(id=team_id).first()
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

    authorizations = await TeamModel.filter(team_id=team_id).prefetch_related("model")

    result = []
    for auth in authorizations:
        # 计算使用百分比
        daily_percent = None
        if auth.daily_token_limit:
            daily_percent = round(
                auth.daily_tokens_used / auth.daily_token_limit * 100, 2
            )

        monthly_percent = None
        if auth.monthly_token_limit:
            monthly_percent = round(
                auth.monthly_tokens_used / auth.monthly_token_limit * 100, 2
            )

        # 检查是否超出配额
        is_exceeded = False
        if auth.daily_token_limit and auth.daily_tokens_used >= auth.daily_token_limit:
            is_exceeded = True
        if (
            auth.monthly_token_limit
            and auth.monthly_tokens_used >= auth.monthly_token_limit
        ):
            is_exceeded = True

        result.append(
            {
                "model_id": auth.model.id,
                "model_name": auth.model.name,
                "model_type": auth.model.model_type,
                "daily_token_limit": auth.daily_token_limit,
                "daily_tokens_used": auth.daily_tokens_used,
                "daily_token_percent": daily_percent,
                "monthly_token_limit": auth.monthly_token_limit,
                "monthly_tokens_used": auth.monthly_tokens_used,
                "monthly_token_percent": monthly_percent,
                "is_enabled": auth.is_enabled,
                "is_quota_exceeded": is_exceeded,
            }
        )

    return success(data=result)
