from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.schemas.sso import UserSSOConnectionSchema


# Permission Schemas
class PermissionBase(BaseModel):
    scope: str
    code: str
    description: Optional[str] = None


class PermissionCreate(PermissionBase):
    pass


class Permission(PermissionBase):
    id: UUID
    is_system: bool = True

    class Config:
        from_attributes = True


class PermissionScopeOption(BaseModel):
    value: str
    label: str


# Role Schemas
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(RoleBase):
    permissions: List[str] = []  # List of permission codes


class Role(RoleBase):
    id: UUID
    is_system_role: bool
    permissions: List[Permission] = []

    class Config:
        from_attributes = True


# User Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    is_active: Optional[bool] = True
    approval_status: Optional[str] = "approved"
    is_superuser: Optional[bool] = False
    avatar_url: Optional[str] = None
    locale: Optional[str] = "en"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    avatar_url: Optional[str] = None
    locale: Optional[str] = None
    roles: Optional[List[str]] = None  # List of role names


class UserInDBBase(UserBase):
    id: UUID
    created_at: datetime
    last_login: Optional[datetime] = None
    auth_source: str
    external_id: Optional[str] = None
    email_verified: bool = False
    locale: str = "en"
    force_password_change: bool = False
    password_expiration_exempt: bool = False

    class Config:
        from_attributes = True


class User(UserInDBBase):
    status: str = "active"
    roles: List[Role] = []
    sso_connections: List[UserSSOConnectionSchema] = []

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Custom validation to handle sso_connections ReverseRelation"""
        if hasattr(obj, "__dict__"):
            # It's an ORM object, convert to dict first
            data = {
                "id": obj.id,
                "username": obj.username,
                "email": obj.email,
                "is_active": obj.is_active,
                "approval_status": getattr(obj, "approval_status", "approved"),
                "is_superuser": obj.is_superuser,
                "email_verified": obj.email_verified,
                "avatar_url": obj.avatar_url,
                "locale": getattr(obj, "locale", "en"),
                "created_at": obj.created_at,
                "last_login": obj.last_login,
                "auth_source": obj.auth_source,
                "external_id": obj.external_id,
                "force_password_change": getattr(obj, "force_password_change", False),
                "password_expiration_exempt": getattr(
                    obj, "password_expiration_exempt", False
                ),
                "roles": obj.roles if hasattr(obj, "roles") else [],
                "sso_connections": [],  # Always empty, will be populated separately
            }
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class UserInDB(UserInDBBase):
    hashed_password: str


User.model_rebuild()
