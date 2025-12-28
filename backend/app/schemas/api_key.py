from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class APIKeyUserInfo(BaseModel):
    """API Key 关联的用户简要信息"""
    id: UUID
    username: str
    nickname: Optional[str] = None

    class Config:
        from_attributes = True


class APIKeyBase(BaseModel):
    """API Key 基础字段"""
    name: str = Field(..., min_length=1, max_length=100, description="API Key name")
    scopes: List[str] = Field(default=[], description="Permission scopes")
    rate_limit: int = Field(default=0, ge=0, description="Rate limit per minute, 0 means unlimited")
    expires_at: Optional[datetime] = Field(None, description="Expiration time")


class APIKeyCreate(APIKeyBase):
    """创建 API Key 请求"""
    pass


class APIKeyUpdate(BaseModel):
    """更新 API Key 请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    scopes: Optional[List[str]] = None
    rate_limit: Optional[int] = Field(None, ge=0)
    expires_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class APIKeyResponse(BaseModel):
    """API Key 响应"""
    id: UUID
    name: str
    key_prefix: str = Field(..., description="Key prefix for identification")
    user_id: UUID = Field(..., description="Owner user ID")
    user: Optional[APIKeyUserInfo] = Field(None, description="Owner user info")
    scopes: List[str]
    rate_limit: int
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreateResponse(APIKeyResponse):
    """创建 API Key 响应（包含完整密钥，仅在创建时返回一次）"""
    key: str = Field(..., description="Full API key, only shown once")


class APIKeyStats(BaseModel):
    """API Key 统计"""
    total: int
    active: int
    inactive: int
    expired: int
