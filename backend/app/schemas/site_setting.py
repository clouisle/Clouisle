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
    auth_page_layout: str = "centered"
    theme_mode: str = "system"
    theme_primary_color: str = ""
    theme_primary_foreground_color: str = ""
    theme_background_color: str = ""
    theme_foreground_color: str = ""
    theme_card_color: str = ""
    theme_card_foreground_color: str = ""
    theme_border_color: str = ""
    theme_ring_color: str = ""
    theme_sidebar_color: str = ""
    theme_sidebar_foreground_color: str = ""
    theme_sidebar_primary_color: str = ""
    theme_sidebar_primary_foreground_color: str = ""
    theme_sidebar_accent_color: str = ""
    theme_sidebar_accent_foreground_color: str = ""
    theme_sidebar_border_color: str = ""
    theme_navbar_color: str = ""
    theme_navbar_foreground_color: str = ""
    theme_navbar_hover_color: str = ""
    theme_navbar_hover_foreground_color: str = ""
    theme_accent_color: str = ""
    theme_accent_foreground_color: str = ""
    theme_muted_color: str = ""
    theme_muted_foreground_color: str = ""
    theme_chart_1_color: str = ""
    theme_chart_2_color: str = ""
    theme_chart_3_color: str = ""
    theme_chart_4_color: str = ""
    theme_chart_5_color: str = ""
    theme_branding_display: str = "full"
    icp_record_number: str = ""
    icp_record_url: str = ""
    terms_enabled: bool = False
    terms_url: str = ""
    terms_text: str = ""
    privacy_enabled: bool = False
    privacy_url: str = ""
    privacy_text: str = ""
    require_terms_acceptance_on_register: bool = False
    allow_registration: bool = True
    require_approval: bool = False
    email_verification: bool = True
    enable_captcha: bool = False
    allow_account_deletion: bool = True
    sso_enabled: bool = False
    sso_allow_password_login: bool = True
    kb_document_max_upload_size_mb: int = 50


class AutoNotificationConfigResponse(BaseModel):
    """自动通知配置响应"""

    channels: List[str] = []  # Global channels
    enabled_types: List[str] = []  # Enabled notification types


class AutoNotificationConfigUpdate(BaseModel):
    """自动通知配置更新请求"""

    channels: List[str] = []
    enabled_types: List[str] = []
