from datetime import timedelta
from typing import Any
from uuid import UUID
import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from tortoise.expressions import Q

from app.api import deps
from app.core.timezone import now_utc
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.site_setting import SiteSetting
from app.schemas.audit_log import (
    AuditLog as AuditLogSchema,
    AuditLogStats,
    AuditLogRetentionStats,
)
from app.schemas.response import Response, success, ResponseCode, BusinessError

router = APIRouter()


@router.get("", response_model=Response[dict])
async def list_audit_logs(
    user_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: UUID | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    查询审计日志（仅超级管理员）

    支持多种过滤条件和分页
    """
    # 构建查询条件
    query = AuditLog.all()

    if user_id:
        query = query.filter(user_id=user_id)
    if team_id:
        query = query.filter(team_id=team_id)
    if action:
        query = query.filter(action=action)
    if resource_type:
        query = query.filter(resource_type=resource_type)
    if resource_id:
        query = query.filter(resource_id=resource_id)
    if status:
        query = query.filter(status=status)
    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)
    if search:
        # 搜索资源名称或IP地址
        query = query.filter(
            Q(resource_name__icontains=search) | Q(ip_address__icontains=search)
        )

    # 获取总数
    total = await query.count()

    # 分页查询
    offset = (page - 1) * page_size
    logs = await query.order_by("-created_at").offset(offset).limit(page_size)

    # 转换为schema
    logs_data = [AuditLogSchema.model_validate(log) for log in logs]

    return success(
        data={
            "items": logs_data,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }
    )


@router.get("/stats", response_model=Response[AuditLogStats])
async def get_audit_log_stats(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    获取审计日志统计信息（仅超级管理员）
    """
    # 总日志数
    total_logs = await AuditLog.all().count()

    # 今日日志数
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    today_logs = await AuditLog.filter(created_at__gte=today_start).count()

    # 失败日志数
    failed_logs = await AuditLog.filter(status="failed").count()

    # 活跃用户数（最近7天）
    seven_days_ago = now_utc() - timedelta(days=7)
    active_users = (
        await AuditLog.filter(created_at__gte=seven_days_ago)
        .distinct()
        .values_list("user_id", flat=True)
    )
    active_users_count = len([u for u in active_users if u])

    # Top 5 操作类型
    from tortoise.functions import Count

    top_actions = (
        await AuditLog.all()
        .annotate(count=Count("id"))
        .group_by("action")
        .order_by("-count")
        .limit(5)
        .values("action", "count")
    )

    # Top 5 活跃用户
    top_users = (
        await AuditLog.filter(user_id__not_isnull=True)
        .annotate(count=Count("id"))
        .group_by("user_id", "username")
        .order_by("-count")
        .limit(5)
        .values("user_id", "username", "count")
    )

    return success(
        data=AuditLogStats(
            total_logs=total_logs,
            today_logs=today_logs,
            failed_logs=failed_logs,
            active_users=active_users_count,
            top_actions=top_actions,
            top_users=top_users,
        )
    )


@router.get("/stats/retention", response_model=Response[AuditLogRetentionStats])
async def get_retention_stats(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """获取日志保留统计信息"""
    retention_days = await SiteSetting.get_value("audit_log_retention_days", 365)
    cutoff_date = now_utc() - timedelta(days=retention_days)

    total_logs = await AuditLog.all().count()
    logs_to_archive = await AuditLog.filter(created_at__lt=cutoff_date).count()
    oldest_log = await AuditLog.all().order_by("created_at").first()

    return success(
        data=AuditLogRetentionStats(
            total_logs=total_logs,
            logs_to_archive=logs_to_archive,
            oldest_log_date=oldest_log.created_at.isoformat() if oldest_log else None,
            retention_days=retention_days,
            cutoff_date=cutoff_date.isoformat(),
            next_archive_date=(now_utc() + timedelta(days=1))
            .replace(hour=3, minute=0, second=0, microsecond=0)
            .isoformat(),
        )
    )


@router.post("/archive", response_model=Response[dict])
async def trigger_manual_archive(
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """手动触发归档任务"""
    from app.tasks.audit_log import archive_old_audit_logs

    # 异步执行归档任务
    task = archive_old_audit_logs.delay()

    return success(data={"task_id": str(task.id), "message": "归档任务已启动"})


@router.get("/export", response_model=None)
async def export_audit_logs(
    format: str = Query("csv", regex="^(csv|json)$"),
    user_id: UUID | None = Query(None),
    team_id: UUID | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    search: str | None = Query(None),
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    导出审计日志（仅超级管理员）

    支持CSV和JSON格式
    """
    # 构建查询条件（与list_audit_logs相同）
    query = AuditLog.all()

    if user_id:
        query = query.filter(user_id=user_id)
    if team_id:
        query = query.filter(team_id=team_id)
    if action:
        query = query.filter(action=action)
    if resource_type:
        query = query.filter(resource_type=resource_type)
    if status:
        query = query.filter(status=status)
    if start_date:
        query = query.filter(created_at__gte=start_date)
    if end_date:
        query = query.filter(created_at__lte=end_date)
    if search:
        query = query.filter(
            Q(resource_name__icontains=search) | Q(ip_address__icontains=search)
        )

    # 获取所有日志（限制最多10000条）
    logs = await query.order_by("-created_at").limit(10000)

    if format == "csv":
        # 生成CSV
        output = StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow([
            "ID", "Time", "User", "Action", "Resource Type",
            "Resource Name", "Operation", "Status", "IP Address", "Error Message"
        ])

        # 写入数据
        for log in logs:
            writer.writerow([
                str(log.id),
                log.created_at.isoformat() if log.created_at else "",
                log.username or "",
                log.action,
                log.resource_type,
                log.resource_name or "",
                log.operation,
                log.status,
                log.ip_address or "",
                log.error_message or "",
            ])

        # 返回CSV文件
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit-logs-{now_utc().strftime('%Y%m%d-%H%M%S')}.csv"
            }
        )

    else:  # JSON
        # 生成JSON
        logs_data = [log.to_dict() for log in logs]
        json_str = json.dumps(logs_data, indent=2, ensure_ascii=False)

        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit-logs-{now_utc().strftime('%Y%m%d-%H%M%S')}.json"
            }
        )


@router.get("/{log_id}", response_model=Response[AuditLogSchema])
async def get_audit_log(
    log_id: UUID,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """获取单个审计日志详情"""
    log = await AuditLog.get_or_none(id=log_id)
    if not log:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="audit_log_not_found",
        )

    return success(data=AuditLogSchema.model_validate(log))
