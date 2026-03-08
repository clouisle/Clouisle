from typing import Optional

from pydantic import BaseModel


class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    force_password_change: Optional[bool] = None
    reason: Optional[str] = None
    requires_totp: Optional[bool] = None
    requires_totp_setup: Optional[bool] = None
    temp_token: Optional[str] = None


class TokenPayload(BaseModel):
    sub: Optional[str] = None
