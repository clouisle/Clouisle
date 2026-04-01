import uuid
from enum import Enum
from uuid import UUID
from tortoise import fields, models


class NotificationScope(str, Enum):
    GLOBAL = "global"
    TEAM = "team"
    USER = "user"


class NotificationSource(str, Enum):
    SYSTEM = "system"
    USER = "user"
    BIZ = "biz"


class NotificationLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NotificationStatus(str, Enum):
    ACTIVE = "active"


class NotificationAuditAction(str, Enum):
    CREATE = "create"
    DELIVER = "deliver"
    READ = "read"
    DELETE = "delete"


class NotificationChannel(str, Enum):
    """通知渠道"""

    EMAIL = "email"
    DINGTALK = "dingtalk"
    WECHAT = "wechat"
    FEISHU = "feishu"
    WEBHOOK = "webhook"
    SLACK = "slack"


class AutoNotificationType(str, Enum):
    """自动通知类型"""

    # 团队相关
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_REMOVED = "team.member_removed"
    TEAM_ROLE_CHANGED = "team.role_changed"
    TEAM_OWNERSHIP_TRANSFERRED = "team.ownership_transferred"
    TEAM_MODEL_GRANTED = "team.model_granted"
    TEAM_MODEL_REVOKED = "team.model_revoked"

    # 用户相关
    USER_ACTIVATED = "user.activated"
    USER_DEACTIVATED = "user.deactivated"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_PENDING_APPROVAL = "user.pending_approval"

    # 知识库相关
    KB_DOC_INDEXED = "kb.doc_indexed"
    KB_DOC_FAILED = "kb.doc_failed"

    # 工作流相关
    WORKFLOW_RUN_SUCCESS = "workflow.run_success"
    WORKFLOW_RUN_FAILED = "workflow.run_failed"

    # Agent 相关
    AGENT_PUBLISHED = "agent.published"
    AGENT_UNPUBLISHED = "agent.unpublished"

    # API Key 相关
    APIKEY_EXPIRING = "apikey.expiring"
    APIKEY_EXPIRED = "apikey.expired"

    # 安全相关
    SECURITY_LOGIN_ANOMALY = "security.login_anomaly"
    SECURITY_ACCOUNT_LOCKED = "security.account_locked"
    SECURITY_PASSWORD_CHANGED = "security.password_changed"

    # 密码过期相关
    PASSWORD_EXPIRING = "password.expiring"
    PASSWORD_EXPIRED = "password.expired"
    PASSWORD_FORCE_CHANGE = "password.force_change"


class NotificationDeliveryStatus(str, Enum):
    """通知发送状态"""

    PENDING = "pending"  # 待发送
    SENDING = "sending"  # 发送中
    SUCCESS = "success"  # 发送成功
    FAILED = "failed"  # 发送失败


class Notification(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)

    scope = fields.CharEnumField(NotificationScope, max_length=20)
    team = fields.ForeignKeyField(
        "models.Team",
        related_name="notifications",
        null=True,
        on_delete=fields.CASCADE,
    )
    team_id: UUID | None  # type: ignore[assignment]
    user = fields.ForeignKeyField(
        "models.User",
        related_name="notifications",
        null=True,
        on_delete=fields.CASCADE,
    )
    user_id: UUID | None  # type: ignore[assignment]

    type = fields.CharField(max_length=100)
    source = fields.CharEnumField(NotificationSource, max_length=20)
    title = fields.CharField(max_length=255)
    content = fields.TextField()
    level = fields.CharEnumField(NotificationLevel, max_length=20)
    data: dict = fields.JSONField(null=True)  # type: ignore[assignment]
    link_url = fields.CharField(max_length=500, null=True)
    status = fields.CharEnumField(
        NotificationStatus, max_length=20, default=NotificationStatus.ACTIVE
    )
    expires_at = fields.DatetimeField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "notifications"
        indexes = [
            ("scope", "created_at"),
            ("team_id", "created_at"),
            ("user_id", "created_at"),
            ("type", "created_at"),
        ]


class NotificationRead(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)

    notification = fields.ForeignKeyField(
        "models.Notification",
        related_name="reads",
        on_delete=fields.CASCADE,
    )
    notification_id: UUID  # type: ignore[assignment]
    user = fields.ForeignKeyField(
        "models.User",
        related_name="notification_reads",
        on_delete=fields.CASCADE,
    )
    user_id: UUID  # type: ignore[assignment]

    read_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "notification_reads"
        unique_together = ("notification", "user")
        indexes = [
            ("user_id", "read_at"),
            ("notification_id", "user_id"),
        ]


class NotificationAudit(models.Model):
    id = fields.UUIDField(pk=True, default=uuid.uuid4)

    notification = fields.ForeignKeyField(
        "models.Notification",
        related_name="audits",
        on_delete=fields.CASCADE,
    )
    notification_id: UUID  # type: ignore[assignment]
    user = fields.ForeignKeyField(
        "models.User",
        related_name="notification_audits",
        null=True,
        on_delete=fields.SET_NULL,
    )
    user_id: UUID | None  # type: ignore[assignment]

    action = fields.CharEnumField(NotificationAuditAction, max_length=20)
    meta: dict = fields.JSONField(null=True)  # type: ignore[assignment]
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "notification_audits"
        indexes = [
            ("notification_id", "created_at"),
            ("user_id", "created_at"),
        ]


class NotificationDelivery(models.Model):
    """通知发送记录 - 跟踪每个渠道的发送状态"""

    id = fields.UUIDField(pk=True, default=uuid.uuid4)

    notification = fields.ForeignKeyField(
        "models.Notification",
        related_name="deliveries",
        on_delete=fields.CASCADE,
    )
    notification_id: UUID  # type: ignore[assignment]

    channel = fields.CharEnumField(NotificationChannel, max_length=20)
    status = fields.CharEnumField(
        NotificationDeliveryStatus,
        max_length=20,
        default=NotificationDeliveryStatus.PENDING,
    )
    task_id = fields.CharField(max_length=100, null=True)  # Celery task ID
    error_message = fields.TextField(null=True)  # 错误信息
    retry_count = fields.IntField(default=0)  # 重试次数
    sent_at = fields.DatetimeField(null=True)  # 发送成功时间

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "notification_deliveries"
        unique_together = ("notification", "channel")
        indexes = [
            ("notification_id", "channel"),
            ("status", "created_at"),
        ]
