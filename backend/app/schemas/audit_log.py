from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field


class AuditLogBase(BaseModel):
    """审计日志基础模型"""

    user_id: Optional[UUID] = None
    username: Optional[str] = None
    team_id: Optional[UUID] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[UUID] = None
    resource_name: Optional[str] = None
    operation: str
    status: str
    error_message: Optional[str] = None
    changes: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None
    auth_method: Optional[str] = None
    api_key_id: Optional[UUID] = None


class AuditLogCreate(AuditLogBase):
    """创建审计日志"""

    pass


class AuditLog(AuditLogBase):
    """审计日志响应模型"""

    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListParams(BaseModel):
    """审计日志查询参数"""

    user_id: Optional[UUID] = None
    team_id: Optional[UUID] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[UUID] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search: Optional[str] = None  # 搜索资源名称、IP地址
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AuditLogActionOption(BaseModel):
    """审计日志 action 筛选选项"""

    value: str
    translation_key: str
    fallback_label: str


class AuditLogStats(BaseModel):
    """审计日志统计"""

    total_logs: int
    today_logs: int
    failed_logs: int
    active_users: int
    top_actions: list[dict[str, Any]]
    top_users: list[dict[str, Any]]


class AuditLogRetentionStats(BaseModel):
    """日志保留统计"""

    total_logs: int
    logs_to_archive: int
    oldest_log_date: Optional[str] = None
    retention_days: int
    cutoff_date: str
    next_archive_date: str


class AlertType(str, Enum):
    """告警类型"""

    SUSPICIOUS_LOGIN = "suspicious_login"  # 可疑登录（多次失败）
    BULK_DELETION = "bulk_deletion"  # 批量删除
    PERMISSION_ESCALATION = "permission_escalation"  # 权限提升
    SENSITIVE_CONFIG_CHANGE = "sensitive_config_change"  # 敏感配置修改
    API_KEY_CREATED = "api_key_created"  # API密钥创建
    MASS_EMAIL_SENT = "mass_email_sent"  # 批量邮件发送


class AlertSeverity(str, Enum):
    """告警严重程度"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
