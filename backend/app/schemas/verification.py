"""
邮件验证相关 Schema
"""

from typing import Optional
from pydantic import BaseModel, EmailStr, model_validator


class SendVerificationRequest(BaseModel):
    """发送验证邮件请求"""

    email: EmailStr
    purpose: str = "register"  # register, reset_password


class VerifyCodeRequest(BaseModel):
    """验证码验证请求"""

    email: EmailStr
    code: str
    purpose: str = "register"


class VerifyTokenRequest(BaseModel):
    """Token 验证请求"""

    token: str


class ResendVerificationRequest(BaseModel):
    """重新发送验证邮件请求"""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""

    email: EmailStr


class ResetPasswordConfirmRequest(BaseModel):
    """确认重置密码请求 - 支持验证码或 token 两种方式"""

    email: Optional[EmailStr] = None
    code: Optional[str] = None
    token: Optional[str] = None
    new_password: str

    @model_validator(mode="after")
    def check_auth_method(self) -> "ResetPasswordConfirmRequest":
        has_code = self.email is not None and self.code is not None
        has_token = self.token is not None
        if not has_code and not has_token:
            raise ValueError("Either (email + code) or token must be provided")
        return self


class VerificationResponse(BaseModel):
    """验证响应"""

    verified: bool
    email: Optional[str] = None
