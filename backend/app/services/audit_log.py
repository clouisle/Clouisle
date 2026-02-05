from typing import Optional
from uuid import UUID

from fastapi import Request

from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.api_key import APIKey


class AuditLogService:
    """审计日志服务"""

    # 敏感字段列表
    SENSITIVE_FIELDS = {
        "password",
        "hashed_password",
        "api_key",
        "secret_key",
        "access_token",
        "refresh_token",
        "private_key",
        "secret",
        "token",
    }

    @staticmethod
    async def log(
        user: Optional[User],
        action: str,
        resource_type: str,
        resource_id: Optional[UUID],
        resource_name: Optional[str],
        operation: str,
        status: str,
        request: Request,
        changes: Optional[dict] = None,
        metadata: Optional[dict] = None,
        error_message: Optional[str] = None,
        api_key: Optional[APIKey] = None,
    ) -> AuditLog:
        """
        记录审计日志

        Args:
            user: 操作用户
            action: 操作类型（如 login_success, create_user）
            resource_type: 资源类型（如 user, agent, role）
            resource_id: 资源ID
            resource_name: 资源名称
            operation: CRUD操作（create, read, update, delete）
            status: 状态（success, failed）
            request: FastAPI请求对象
            changes: 变更详情（before/after）
            metadata: 额外元数据
            error_message: 错误信息
            api_key: API密钥（如果通过API密钥认证）

        Returns:
            创建的审计日志对象
        """
        # 获取客户端IP
        ip_address = AuditLogService.get_client_ip(request)

        # 获取User-Agent
        user_agent = request.headers.get("user-agent")

        # 脱敏变更数据
        if changes:
            changes = AuditLogService.sanitize_changes(changes)

        # 确定认证方式
        auth_method = "api_key" if api_key else "jwt"

        # 创建审计日志
        audit_log = await AuditLog.create(
            user_id=user.id if user else None,
            username=user.username if user else None,
            team_id=getattr(user, "current_team_id", None) if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            operation=operation,
            status=status,
            error_message=error_message,
            changes=changes,
            metadata=metadata,
            auth_method=auth_method,
            api_key_id=api_key.id if api_key else None,
        )

        return audit_log

    @staticmethod
    def get_client_ip(request: Request) -> str:
        """
        获取客户端IP地址（支持代理）

        优先级：
        1. X-Forwarded-For（代理）
        2. X-Real-IP（Nginx）
        3. request.client.host（直连）
        """
        # 检查 X-Forwarded-For
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For 可能包含多个IP，取第一个
            return forwarded_for.split(",")[0].strip()

        # 检查 X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # 直连IP
        if request.client:
            return request.client.host

        return "unknown"

    @staticmethod
    def sanitize_changes(changes: dict) -> dict:
        """
        清理敏感信息

        对密码、API密钥等敏感字段进行脱敏处理
        """
        sanitized = {}

        for key, value in changes.items():
            if key in ("before", "after"):
                # 递归处理 before/after 对象
                if isinstance(value, dict):
                    sanitized[key] = AuditLogService._sanitize_dict(value)
                else:
                    sanitized[key] = value
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def _sanitize_dict(data: dict) -> dict:
        """递归脱敏字典中的敏感字段"""
        sanitized = {}

        for key, value in data.items():
            # 检查是否是敏感字段
            if any(
                sensitive in key.lower()
                for sensitive in AuditLogService.SENSITIVE_FIELDS
            ):
                # 脱敏处理
                if isinstance(value, str) and len(value) > 8:
                    # 只显示前8位
                    sanitized[key] = value[:8] + "***"
                else:
                    sanitized[key] = "***"
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                sanitized[key] = AuditLogService._sanitize_dict(value)
            elif key == "email" and isinstance(value, str):
                # 邮箱部分隐藏
                sanitized[key] = AuditLogService._mask_email(value)
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def _mask_email(email: str) -> str:
        """邮箱部分隐藏"""
        if "@" not in email:
            return email

        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = local[0] + "***"
        else:
            masked_local = local[0] + "***" + local[-1]

        return f"{masked_local}@{domain}"
