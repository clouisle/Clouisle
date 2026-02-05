import secrets
from typing import TYPE_CHECKING
from tortoise import fields, models

if TYPE_CHECKING:
    from .user import User
    from .agent import Agent
    from .workflow import Workflow


class APIKey(models.Model):
    """API 密钥模型 - 用于 API 访问认证"""

    id = fields.UUIDField(pk=True)
    name = fields.CharField(max_length=100, description="API Key name")
    key_prefix = fields.CharField(
        max_length=16, description="First 12 characters of the key for identification"
    )
    key_hash = fields.CharField(
        max_length=255, description="Hashed API key for secure storage"
    )
    
    # 关联用户
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(  # type: ignore
        "models.User", related_name="api_keys", on_delete=fields.CASCADE
    )

    # 关联可访问的 Agent（多对多）
    agents: fields.ManyToManyRelation["Agent"] = fields.ManyToManyField(  # type: ignore
        "models.Agent",
        related_name="api_keys",
        through="api_key_agents",
        description="Agents this API key can access"
    )

    # 关联可访问的 Workflow（多对多）
    workflows: fields.ManyToManyRelation["Workflow"] = fields.ManyToManyField(  # type: ignore
        "models.Workflow",
        related_name="api_keys",
        through="api_key_workflows",
        description="Workflows this API key can access"
    )
    
    # 权限和限制
    scopes = fields.JSONField(
        default=list,
        description="List of permission scopes, empty means full access"
    )
    rate_limit = fields.IntField(
        default=1000, description="Rate limit per minute, 0 means unlimited"
    )
    
    # 状态
    is_active = fields.BooleanField(default=True)
    expires_at = fields.DatetimeField(null=True, description="Expiration time")
    last_used_at = fields.DatetimeField(null=True)
    
    # 时间戳
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "api_keys"

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"

    @classmethod
    def generate_key(cls) -> tuple[str, str, str]:
        """
        生成 API Key
        返回: (完整密钥, 密钥前缀, 密钥哈希)
        """
        from app.core.security import get_password_hash
        
        # 生成 32 字节的随机密钥（64 个十六进制字符）
        raw_key = secrets.token_hex(32)
        full_key = f"clou_{raw_key}"  # 添加前缀标识
        key_prefix = full_key[:12]  # 保存前 12 个字符用于识别
        key_hash = get_password_hash(full_key)
        
        return full_key, key_prefix, key_hash

    @classmethod
    def verify_key(cls, plain_key: str, hashed_key: str) -> bool:
        """验证 API Key"""
        from app.core.security import verify_password
        return verify_password(plain_key, hashed_key)
