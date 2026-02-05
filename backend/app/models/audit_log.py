import uuid
from tortoise import fields, models


class AuditLog(models.Model):
    """审计日志模型 - 记录系统中的关键操作"""

    id = fields.UUIDField(pk=True, default=uuid.uuid4)

    # 操作者信息
    user_id = fields.UUIDField(null=True)  # 可能是系统操作
    username = fields.CharField(max_length=255, null=True)
    team_id = fields.UUIDField(null=True)  # 所属团队

    # 请求信息
    ip_address = fields.CharField(max_length=45, null=True)  # IPv6支持
    user_agent = fields.TextField(null=True)

    # 操作信息
    action = fields.CharField(
        max_length=100
    )  # login_success, create_user, update_agent等
    resource_type = fields.CharField(max_length=50)  # user, agent, role, setting等
    resource_id = fields.UUIDField(null=True)  # 资源ID
    resource_name = fields.CharField(max_length=255, null=True)  # 资源名称
    operation = fields.CharField(max_length=20)  # create, read, update, delete

    # 结果信息
    status = fields.CharField(max_length=20)  # success, failed
    error_message = fields.TextField(null=True)

    # 变更详情（JSON）
    changes = fields.JSONField(null=True)  # {"before": {...}, "after": {...}}
    metadata = fields.JSONField(null=True)  # 额外信息

    # 认证方式
    auth_method = fields.CharField(max_length=20, null=True)  # jwt, api_key
    api_key_id = fields.UUIDField(null=True)  # 如果通过API密钥访问

    # 时间戳
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "audit_logs"
        indexes = [
            ("user_id", "created_at"),
            ("team_id", "created_at"),
            ("resource_type", "resource_id"),
            ("action", "created_at"),
            ("created_at",),  # 按时间查询
        ]

    def to_dict(self) -> dict:
        """转换为字典格式（用于归档）"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "username": self.username,
            "team_id": str(self.team_id) if self.team_id else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": str(self.resource_id) if self.resource_id else None,
            "resource_name": self.resource_name,
            "operation": self.operation,
            "status": self.status,
            "error_message": self.error_message,
            "changes": self.changes,
            "metadata": self.metadata,
            "auth_method": self.auth_method,
            "api_key_id": str(self.api_key_id) if self.api_key_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
