import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from tortoise.expressions import Q

from app.api import deps
from app.core.timezone import now_utc
from app.models.notification import (
    Notification,
    NotificationRead,
    NotificationAuditAction,
    NotificationScope,
    NotificationDelivery,
    NotificationChannel,
    NotificationDeliveryStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.notification import (
    NotificationOut,
    NotificationAdminCreate,
    NotificationReadRequest,
    NotificationUnreadCount,
    NotificationDeliveryOut,
)
from app.schemas.response import Response, BusinessError, ResponseCode, success
from app.schemas.team import TeamMemberRole
from app.services.notification import create_notification_audit, create_notification

logger = logging.getLogger(__name__)
router = APIRouter()
admin_router = APIRouter()  # kept for backward compatibility; mounted via admin router


async def check_team_admin_permission(team_id: UUID, user: User) -> Team:
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


async def build_visible_query(user: User, include_expired: bool = False):
    team_ids = await TeamMember.filter(user=user).values_list("team_id", flat=True)
    base_query = Q(scope=NotificationScope.GLOBAL) | Q(
        scope=NotificationScope.USER, user_id=user.id
    )
    if team_ids:
        base_query = base_query | Q(scope=NotificationScope.TEAM, team_id__in=team_ids)
    query = Notification.filter(base_query)

    if not include_expired:
        now = now_utc()
        query = query.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    return query


@router.get("", response_model=Response[dict])
async def list_notifications(
    scope: NotificationScope | None = Query(None),
    type: str | None = Query(None),
    level: str | None = Query(None),
    search: str | None = Query(None),
    unread_only: bool = Query(False),
    created_from: str | None = Query(None),
    created_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    query = await build_visible_query(current_user)

    if scope:
        query = query.filter(scope=scope)
    if type:
        query = query.filter(type=type)
    if level:
        query = query.filter(level=level)
    if search:
        query = query.filter(
            Q(title__icontains=search)
            | Q(content__icontains=search)
            | Q(type__icontains=search)
        )
    if created_from:
        query = query.filter(created_at__gte=created_from)
    if created_to:
        query = query.filter(created_at__lte=created_to)

    if unread_only:
        read_ids = await NotificationRead.filter(user_id=current_user.id).values_list(
            "notification_id", flat=True
        )
        if read_ids:
            query = query.exclude(id__in=read_ids)

    total = await query.count()
    offset = (page - 1) * page_size
    notifications = await query.order_by("-created_at").offset(offset).limit(page_size)

    notification_ids = [n.id for n in notifications]
    read_map: dict[UUID, Any] = {}
    if notification_ids:
        reads = await NotificationRead.filter(
            user_id=current_user.id, notification_id__in=notification_ids
        )
        read_map = {r.notification_id: r.read_at for r in reads}

    items = []
    for n in notifications:
        read_at = read_map.get(n.id)
        items.append(
            NotificationOut(
                id=n.id,
                scope=n.scope,
                team_id=n.team_id,
                user_id=n.user_id,
                type=n.type,
                source=n.source,
                title=n.title,
                content=n.content,
                level=n.level,
                data=n.data,
                link_url=n.link_url,
                status=n.status,
                expires_at=n.expires_at,
                created_at=n.created_at,
                updated_at=n.updated_at,
                is_read=read_at is not None,
                read_at=read_at,
            )
        )

    return success(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/unread-count", response_model=Response[NotificationUnreadCount])
async def get_unread_count(
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    query = await build_visible_query(current_user)
    read_ids = await NotificationRead.filter(user_id=current_user.id).values_list(
        "notification_id", flat=True
    )
    if read_ids:
        query = query.exclude(id__in=read_ids)
    total = await query.count()
    return success(data=NotificationUnreadCount(total=total))


@router.post("/read", response_model=Response[dict])
async def mark_read(
    payload: NotificationReadRequest,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    if not payload.mark_all and not payload.notification_ids:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="validation_error",
            status_code=400,
        )

    query = await build_visible_query(current_user, include_expired=True)

    if payload.notification_ids:
        query = query.filter(id__in=payload.notification_ids)

    if payload.mark_all:
        read_ids = await NotificationRead.filter(user_id=current_user.id).values_list(
            "notification_id", flat=True
        )
        if read_ids:
            query = query.exclude(id__in=read_ids)

    notification_ids = await query.values_list("id", flat=True)
    if not notification_ids:
        return success(data={"updated": 0}, msg_key="notification_read_updated")

    existing_ids = await NotificationRead.filter(
        user_id=current_user.id, notification_id__in=notification_ids
    ).values_list("notification_id", flat=True)

    existing_set = set(existing_ids)
    new_ids = [nid for nid in notification_ids if nid not in existing_set]

    if not new_ids:
        return success(data={"updated": 0}, msg_key="notification_read_updated")

    now = now_utc()
    read_rows = [
        NotificationRead(
            notification_id=nid,
            user_id=current_user.id,
            read_at=now,
        )
        for nid in new_ids
    ]
    await NotificationRead.bulk_create(read_rows)

    # Use raw bulk create to avoid extra queries
    from app.models.notification import NotificationAudit

    audit_rows = [
        NotificationAudit(
            notification_id=nid,
            user_id=current_user.id,
            action=NotificationAuditAction.READ,
            meta={"source": "in_app"},
            created_at=now,
        )
        for nid in new_ids
    ]
    await NotificationAudit.bulk_create(audit_rows)

    return success(data={"updated": len(new_ids)}, msg_key="notification_read_updated")


@admin_router.get("", response_model=Response[dict])
async def admin_list_notifications(
    scope: list[NotificationScope] | None = Query(None),
    team_id: UUID | None = Query(None),
    user_id: UUID | None = Query(None),
    type: str | None = Query(None),
    level: list[str] | None = Query(None),
    search: str | None = Query(None),
    include_expired: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    if not current_user.is_superuser:
        if scope and NotificationScope.GLOBAL in scope:
            raise BusinessError(
                code=ResponseCode.INSUFFICIENT_PRIVILEGES,
                msg_key="insufficient_privileges",
                status_code=403,
            )
        if not team_id:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="notification_scope_requires_team",
                status_code=400,
            )
        await check_team_admin_permission(team_id, current_user)

    query = Notification.all()

    if scope:
        query = query.filter(scope__in=scope)
    if team_id:
        query = query.filter(team_id=team_id)
    if user_id:
        query = query.filter(user_id=user_id)
    if type:
        query = query.filter(type=type)
    if level:
        query = query.filter(level__in=level)
    if search:
        query = query.filter(
            Q(title__icontains=search)
            | Q(content__icontains=search)
            | Q(type__icontains=search)
        )

    if not include_expired:
        now = now_utc()
        query = query.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    total = await query.count()
    offset = (page - 1) * page_size
    notifications = await query.order_by("-created_at").offset(offset).limit(page_size)

    # 获取所有通知的发送状态
    notification_ids = [n.id for n in notifications]
    deliveries_map: dict[UUID, list] = {nid: [] for nid in notification_ids}
    if notification_ids:
        deliveries = await NotificationDelivery.filter(
            notification_id__in=notification_ids
        )
        for d in deliveries:
            deliveries_map[d.notification_id].append(
                NotificationDeliveryOut(
                    channel=d.channel,
                    status=d.status,
                    error_message=d.error_message,
                    retry_count=d.retry_count,
                    sent_at=d.sent_at,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
            )

    items = [
        NotificationOut(
            id=n.id,
            scope=n.scope,
            team_id=n.team_id,
            user_id=n.user_id,
            type=n.type,
            source=n.source,
            title=n.title,
            content=n.content,
            level=n.level,
            data=n.data,
            link_url=n.link_url,
            status=n.status,
            expires_at=n.expires_at,
            created_at=n.created_at,
            updated_at=n.updated_at,
            is_read=False,
            read_at=None,
            deliveries=deliveries_map.get(n.id, []),
        )
        for n in notifications
    ]

    return success(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@admin_router.post("", response_model=Response[NotificationOut])
async def admin_create_notification(
    payload: NotificationAdminCreate,
    current_user: User = Depends(deps.PermissionChecker("admin:notification:create")),
) -> Any:
    # 验证 scope 和权限
    if payload.scope == NotificationScope.GLOBAL:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.INSUFFICIENT_PRIVILEGES,
                msg_key="insufficient_privileges",
                status_code=403,
            )
    elif payload.scope == NotificationScope.TEAM:
        if not payload.team_id:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="notification_scope_requires_team",
                status_code=400,
            )
        await check_team_admin_permission(payload.team_id, current_user)
    elif payload.scope == NotificationScope.USER:
        # 批量发送用户通知
        if payload.user_ids:
            if not current_user.is_superuser:
                # 非 superuser 需要有 admin:notification:create 权限（已在依赖中检查）
                pass

            # 验证所有用户是否存在
            users = await User.filter(id__in=payload.user_ids).all()
            if len(users) != len(payload.user_ids):
                raise BusinessError(
                    code=ResponseCode.USER_NOT_FOUND,
                    msg_key="some_users_not_found",
                    status_code=404,
                )

            # 批量创建通知
            notifications = []
            for user_id in payload.user_ids:
                notification = await Notification.create(
                    scope=payload.scope,
                    team_id=None,
                    user_id=user_id,
                    type=payload.type,
                    source=payload.source,
                    title=payload.title,
                    content=payload.content,
                    level=payload.level,
                    data=payload.data,
                    link_url=payload.link_url,
                    expires_at=payload.expires_at,
                )
                await create_notification(
                    notification, actor=current_user, meta={"source": "admin"}
                )
                notifications.append(notification)

            # 返回第一个通知作为示例
            first_notification = notifications[0] if notifications else None
            if not first_notification:
                raise BusinessError(
                    code=ResponseCode.INTERNAL_ERROR,
                    msg_key="notification_creation_failed",
                )

            return success(
                data=NotificationOut(
                    id=first_notification.id,
                    scope=first_notification.scope,
                    team_id=first_notification.team_id,
                    user_id=first_notification.user_id,
                    type=first_notification.type,
                    source=first_notification.source,
                    title=first_notification.title,
                    content=first_notification.content,
                    level=first_notification.level,
                    data=first_notification.data,
                    link_url=first_notification.link_url,
                    status=first_notification.status,
                    expires_at=first_notification.expires_at,
                    created_at=first_notification.created_at,
                    updated_at=first_notification.updated_at,
                    is_read=False,
                    read_at=None,
                    deliveries=[],
                ),
                msg_key="notifications_created",
            )

        # 单个用户通知
        if not payload.user_id:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="notification_scope_requires_user",
                status_code=400,
            )
        if not current_user.is_superuser:
            # 非 superuser 需要有 admin:notification:create 权限（已在依赖中检查）
            pass
        user = await User.filter(id=payload.user_id).first()
        if not user:
            raise BusinessError(
                code=ResponseCode.USER_NOT_FOUND,
                msg_key="user_not_found",
                status_code=404,
            )
    else:
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST,
            msg_key="invalid_notification_scope",
            status_code=400,
        )

    # 校验外部通知渠道配置
    if payload.notify_channels:
        # 校验邮件渠道
        if NotificationChannel.EMAIL in payload.notify_channels:
            from app.core.email import get_smtp_config

            smtp_config = await get_smtp_config()

            if not smtp_config["enabled"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="smtp_not_enabled",
                    status_code=400,
                )

            if not smtp_config["host"] or not smtp_config["from_address"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="smtp_not_configured",
                    status_code=400,
                )

        # 校验钉钉渠道
        if NotificationChannel.DINGTALK in payload.notify_channels:
            from app.core.dingtalk import get_dingtalk_config

            dingtalk_config = await get_dingtalk_config()

            if not dingtalk_config["enabled"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="dingtalk_not_enabled",
                    status_code=400,
                )

            # Webhook 方式需要配置 webhook_url
            if dingtalk_config["notification_type"] == "webhook":
                if not dingtalk_config["webhook_url"]:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="dingtalk_not_configured",
                        status_code=400,
                    )
            # 企业应用方式需要配置 app_key, app_secret, agent_id
            elif dingtalk_config["notification_type"] == "app":
                if (
                    not dingtalk_config["app_key"]
                    or not dingtalk_config["app_secret"]
                    or not dingtalk_config["agent_id"]
                ):
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="dingtalk_not_configured",
                        status_code=400,
                    )

        # 校验企业微信渠道
        if NotificationChannel.WECHAT in payload.notify_channels:
            from app.core.wechat import get_wechat_config

            wechat_config = await get_wechat_config()

            if not wechat_config["enabled"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="wechat_not_enabled",
                    status_code=400,
                )

            if wechat_config["notification_type"] == "webhook":
                if not wechat_config["webhook_url"]:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="wechat_not_configured",
                        status_code=400,
                    )
            elif wechat_config["notification_type"] == "app":
                if (
                    not wechat_config["corp_id"]
                    or not wechat_config["secret"]
                    or not wechat_config["agent_id"]
                ):
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="wechat_not_configured",
                        status_code=400,
                    )

        # 校验飞书渠道
        if NotificationChannel.FEISHU in payload.notify_channels:
            from app.core.feishu import get_feishu_config

            feishu_config = await get_feishu_config()

            if not feishu_config["enabled"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="feishu_not_enabled",
                    status_code=400,
                )

            if feishu_config["notification_type"] == "webhook":
                if not feishu_config["webhook_url"]:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="feishu_not_configured",
                        status_code=400,
                    )
            elif feishu_config["notification_type"] == "app":
                if not feishu_config["app_id"] or not feishu_config["app_secret"]:
                    raise BusinessError(
                        code=ResponseCode.BAD_REQUEST,
                        msg_key="feishu_not_configured",
                        status_code=400,
                    )

        # 校验通用 Webhook 渠道
        if NotificationChannel.WEBHOOK in payload.notify_channels:
            from app.core.webhook import get_webhook_config

            webhook_config = await get_webhook_config()

            if not webhook_config["enabled"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="webhook_not_enabled",
                    status_code=400,
                )

            if not webhook_config["url"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="webhook_not_configured",
                    status_code=400,
                )

        # 校验 Slack 渠道
        if NotificationChannel.SLACK in payload.notify_channels:
            from app.core.slack import get_slack_config

            slack_config = await get_slack_config()

            if not slack_config["enabled"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="slack_not_enabled",
                    status_code=400,
                )

            if not slack_config["webhook_url"]:
                raise BusinessError(
                    code=ResponseCode.BAD_REQUEST,
                    msg_key="slack_not_configured",
                    status_code=400,
                )

    notification = await Notification.create(
        scope=payload.scope,
        team_id=payload.team_id,
        user_id=payload.user_id,
        type=payload.type,
        source=payload.source,
        title=payload.title,
        content=payload.content,
        level=payload.level,
        data=payload.data,
        link_url=payload.link_url,
        expires_at=payload.expires_at,
    )

    await create_notification(
        notification, actor=current_user, meta={"source": "admin"}
    )

    # 根据选择的渠道发送外部通知
    deliveries = []
    if payload.notify_channels:
        logger.info(f"Sending notifications to channels: {payload.notify_channels}")

        if NotificationChannel.EMAIL in payload.notify_channels:
            from app.tasks.notification import send_notification_email_task

            # 创建发送记录
            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=NotificationChannel.EMAIL,
                status=NotificationDeliveryStatus.PENDING,
            )
            logger.info(f"Triggering email notification task for {notification.id}")
            task_result = send_notification_email_task.delay(str(notification.id))
            delivery.task_id = task_result.id
            await delivery.save()
            deliveries.append(delivery)

        if NotificationChannel.DINGTALK in payload.notify_channels:
            from app.tasks.notification import send_notification_dingtalk_task

            # 创建发送记录
            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=NotificationChannel.DINGTALK,
                status=NotificationDeliveryStatus.PENDING,
            )
            logger.info(f"Triggering dingtalk notification task for {notification.id}")
            task_result = send_notification_dingtalk_task.delay(str(notification.id))
            delivery.task_id = task_result.id
            await delivery.save()
            logger.info(
                f"DingTalk task submitted: {task_result.id}, state: {task_result.state}"
            )
            deliveries.append(delivery)

        if NotificationChannel.WECHAT in payload.notify_channels:
            from app.tasks.notification import send_notification_wechat_task

            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=NotificationChannel.WECHAT,
                status=NotificationDeliveryStatus.PENDING,
            )
            logger.info(f"Triggering wechat notification task for {notification.id}")
            task_result = send_notification_wechat_task.delay(str(notification.id))
            delivery.task_id = task_result.id
            await delivery.save()
            deliveries.append(delivery)

        if NotificationChannel.FEISHU in payload.notify_channels:
            from app.tasks.notification import send_notification_feishu_task

            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=NotificationChannel.FEISHU,
                status=NotificationDeliveryStatus.PENDING,
            )
            logger.info(f"Triggering feishu notification task for {notification.id}")
            task_result = send_notification_feishu_task.delay(str(notification.id))
            delivery.task_id = task_result.id
            await delivery.save()
            deliveries.append(delivery)

        if NotificationChannel.WEBHOOK in payload.notify_channels:
            from app.tasks.notification import send_notification_webhook_task

            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=NotificationChannel.WEBHOOK,
                status=NotificationDeliveryStatus.PENDING,
            )
            logger.info(f"Triggering webhook notification task for {notification.id}")
            task_result = send_notification_webhook_task.delay(str(notification.id))
            delivery.task_id = task_result.id
            await delivery.save()
            deliveries.append(delivery)

        if NotificationChannel.SLACK in payload.notify_channels:
            from app.tasks.notification import send_notification_slack_task

            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=NotificationChannel.SLACK,
                status=NotificationDeliveryStatus.PENDING,
            )
            logger.info(f"Triggering slack notification task for {notification.id}")
            task_result = send_notification_slack_task.delay(str(notification.id))
            delivery.task_id = task_result.id
            await delivery.save()
            deliveries.append(delivery)

    return success(
        data=NotificationOut(
            id=notification.id,
            scope=notification.scope,
            team_id=notification.team_id,
            user_id=notification.user_id,
            type=notification.type,
            source=notification.source,
            title=notification.title,
            content=notification.content,
            level=notification.level,
            data=notification.data,
            link_url=notification.link_url,
            status=notification.status,
            expires_at=notification.expires_at,
            created_at=notification.created_at,
            updated_at=notification.updated_at,
            is_read=False,
            read_at=None,
            deliveries=[
                NotificationDeliveryOut(
                    channel=d.channel,
                    status=d.status,
                    error_message=d.error_message,
                    retry_count=d.retry_count,
                    sent_at=d.sent_at,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
                for d in deliveries
            ],
        ),
        msg_key="notification_created",
    )


@admin_router.delete("/{notification_id}", response_model=Response[dict])
async def admin_delete_notification(
    notification_id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="notification_not_found",
            status_code=404,
        )

    if notification.scope == NotificationScope.GLOBAL:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.INSUFFICIENT_PRIVILEGES,
                msg_key="insufficient_privileges",
                status_code=403,
            )
    elif notification.scope == NotificationScope.TEAM:
        if not notification.team_id:
            raise BusinessError(
                code=ResponseCode.BAD_REQUEST,
                msg_key="notification_scope_requires_team",
                status_code=400,
            )
        await check_team_admin_permission(notification.team_id, current_user)
    else:
        if not current_user.is_superuser:
            raise BusinessError(
                code=ResponseCode.INSUFFICIENT_PRIVILEGES,
                msg_key="insufficient_privileges",
                status_code=403,
            )

    await create_notification_audit(
        notification_id=notification.id,
        action=NotificationAuditAction.DELETE,
        user=current_user,
        meta={"source": "admin"},
    )

    await Notification.filter(id=notification_id).delete()

    return success(data={"id": str(notification_id)}, msg_key="notification_deleted")
