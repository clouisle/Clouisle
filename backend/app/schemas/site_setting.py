from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SiteSettingResponse(BaseModel):
    key: str
    value: Any
    value_type: str
    category: str
    description: Optional[str] = None
    is_public: bool

    class Config:
        from_attributes = True


class SiteSettingUpdate(BaseModel):
    value: Any


class SiteSettingBulkUpdate(BaseModel):
    settings: Dict[str, Any]


class SiteSettingsResponse(BaseModel):
    settings: Dict[str, Any]


class PublicSiteSettingsResponse(BaseModel):
    """Public settings visible to unauthenticated users"""

    site_name: str = "Clouisle"
    site_description: str = ""
    site_url: str = ""
    site_icon: str = ""
    allow_registration: bool = True
    require_approval: bool = False
    email_verification: bool = True
    enable_captcha: bool = False
    allow_account_deletion: bool = True
    sso_enabled: bool = False
    sso_allow_password_login: bool = True


class AutoNotificationConfigResponse(BaseModel):
    """自动通知配置响应"""

    channels: List[str] = []  # Global channels
    enabled_types: List[str] = []  # Enabled notification types


class AutoNotificationConfigUpdate(BaseModel):
    """自动通知配置更新请求"""

    channels: List[str] = []
    enabled_types: List[str] = []
