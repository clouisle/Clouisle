from typing import Any, Optional, TypedDict

from tortoise import fields, models


class SiteSetting(models.Model):
    """站点设置模型 - 键值对存储"""

    id = fields.UUIDField(pk=True)
    key = fields.CharField(max_length=100, unique=True, description="Setting key")
    value = fields.TextField(
        null=True, description="Setting value (JSON string for complex types)"
    )
    value_type = fields.CharField(
        max_length=20, default="string", description="string, int, bool, json"
    )
    category = fields.CharField(
        max_length=50, default="general", description="Setting category"
    )
    description = fields.CharField(max_length=255, null=True)
    is_public = fields.BooleanField(
        default=False, description="If True, visible to unauthenticated users"
    )
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "site_settings"

    def __str__(self):
        return f"{self.key}={self.value}"

    @classmethod
    async def get_value(cls, key: str, default=None):
        """Get setting value with type conversion"""
        setting = await cls.filter(key=key).first()
        if not setting:
            return default
        return cls._convert_value(setting.value, setting.value_type)

    @classmethod
    async def set_value(
        cls,
        key: str,
        value: Any,
        value_type: str = "string",
        category: Optional[str] = "general",
        description: Optional[str] = None,
        is_public: bool = False,
    ):
        """Set setting value"""
        import json

        # Convert value to string for storage
        str_value: Optional[str]
        if value_type == "bool":
            str_value = "true" if value else "false"
        elif value_type == "json":
            str_value = json.dumps(value) if value is not None else None
        else:
            str_value = str(value) if value is not None else None

        setting, created = await cls.get_or_create(
            key=key,
            defaults={
                "value": str_value,
                "value_type": value_type,
                "category": category,
                "description": description,
                "is_public": is_public,
            },
        )
        if not created:
            setting.value = str_value  # type: ignore[assignment]
            setting.value_type = str(value_type)
            if category is not None:
                setting.category = category  # type: ignore[assignment]
            if description is not None:
                setting.description = description
            setting.is_public = is_public
            await setting.save()
        return setting

    @classmethod
    async def get_all_by_category(
        cls, category: Optional[str] = None, public_only: bool = False
    ) -> dict[str, Any]:
        """Get all settings, optionally filtered by category"""
        query = cls.all()
        if category:
            query = query.filter(category=category)
        if public_only:
            query = query.filter(is_public=True)

        settings = await query
        return {s.key: cls._convert_value(s.value, s.value_type) for s in settings}

    @staticmethod
    def _convert_value(value: Optional[str], value_type: str) -> Any:
        """Convert string value to appropriate type"""
        import json

        if value is None:
            return None

        if value_type == "int":
            return int(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        elif value_type == "json":
            return json.loads(value)
        else:
            return value


class SettingConfig(TypedDict):
    value: Any
    type: str
    category: str
    public: bool
    desc: str


KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB = 50
KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB = 1
KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB = 1024


# Default settings definitions
DEFAULT_SETTINGS: dict[str, SettingConfig] = {
    # General
    "site_name": {
        "value": "Clouisle",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Site name",
    },
    "site_description": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Site description",
    },
    "site_url": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Site URL",
    },
    "site_icon": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Site icon URL",
    },
    "default_language": {
        "value": "en",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Default language for system messages (en, zh)",
    },
    "auth_page_layout": {
        "value": "centered",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Authentication page layout (centered, split)",
    },
    "theme_mode": {
        "value": "system",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_mode.description",
    },
    "theme_primary_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_primary_color.description",
    },
    "theme_primary_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_primary_foreground_color.description",
    },
    "theme_background_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_background_color.description",
    },
    "theme_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_foreground_color.description",
    },
    "theme_card_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_card_color.description",
    },
    "theme_card_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_card_foreground_color.description",
    },
    "theme_border_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_border_color.description",
    },
    "theme_ring_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_ring_color.description",
    },
    "theme_sidebar_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_color.description",
    },
    "theme_sidebar_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_foreground_color.description",
    },
    "theme_sidebar_primary_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_primary_color.description",
    },
    "theme_sidebar_primary_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_primary_foreground_color.description",
    },
    "theme_sidebar_accent_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_accent_color.description",
    },
    "theme_sidebar_accent_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_accent_foreground_color.description",
    },
    "theme_sidebar_border_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_sidebar_border_color.description",
    },
    "theme_navbar_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_navbar_color.description",
    },
    "theme_navbar_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_navbar_foreground_color.description",
    },
    "theme_navbar_hover_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_navbar_hover_color.description",
    },
    "theme_navbar_hover_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_navbar_hover_foreground_color.description",
    },
    "theme_accent_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_accent_color.description",
    },
    "theme_accent_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_accent_foreground_color.description",
    },
    "theme_muted_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_muted_color.description",
    },
    "theme_muted_foreground_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_muted_foreground_color.description",
    },
    "theme_chart_1_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_chart_1_color.description",
    },
    "theme_chart_2_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_chart_2_color.description",
    },
    "theme_chart_3_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_chart_3_color.description",
    },
    "theme_chart_4_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_chart_4_color.description",
    },
    "theme_chart_5_color": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_chart_5_color.description",
    },
    "theme_branding_display": {
        "value": "full",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "site_settings.theme_branding_display.description",
    },
    "icp_record_number": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "ICP record number",
    },
    "icp_record_url": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "ICP record URL",
    },
    "terms_enabled": {
        "value": False,
        "type": "bool",
        "category": "general",
        "public": True,
        "desc": "Show terms of service entry",
    },
    "terms_url": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Terms of service URL",
    },
    "terms_text": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Terms of service text",
    },
    "privacy_enabled": {
        "value": False,
        "type": "bool",
        "category": "general",
        "public": True,
        "desc": "Show privacy policy entry",
    },
    "privacy_url": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Privacy policy URL",
    },
    "privacy_text": {
        "value": "",
        "type": "string",
        "category": "general",
        "public": True,
        "desc": "Privacy policy text",
    },
    "require_terms_acceptance_on_register": {
        "value": False,
        "type": "bool",
        "category": "general",
        "public": True,
        "desc": "Require terms acceptance during registration",
    },
    # Registration & Security
    "allow_registration": {
        "value": True,
        "type": "bool",
        "category": "security",
        "public": True,
        "desc": "Allow user registration",
    },
    "require_approval": {
        "value": True,
        "type": "bool",
        "category": "security",
        "public": True,
        "desc": "Require admin approval for new users",
    },
    "email_verification": {
        "value": True,
        "type": "bool",
        "category": "security",
        "public": True,
        "desc": "Require email verification",
    },
    "allow_account_deletion": {
        "value": True,
        "type": "bool",
        "category": "security",
        "public": True,
        "desc": "Allow users to delete their own account",
    },
    "default_role_id": {
        "value": "",
        "type": "string",
        "category": "security",
        "public": False,
        "desc": "Default role ID for new users",
    },
    "default_team_id": {
        "value": "",
        "type": "string",
        "category": "security",
        "public": False,
        "desc": "Default team ID for new users",
    },
    "default_team_role": {
        "value": "member",
        "type": "string",
        "category": "security",
        "public": False,
        "desc": "Default team role for new users",
    },
    # Security
    "min_password_length": {
        "value": 8,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Minimum password length",
    },
    "require_uppercase": {
        "value": True,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Require uppercase in password",
    },
    "require_number": {
        "value": True,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Require number in password",
    },
    "require_special_char": {
        "value": False,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Require special character in password",
    },
    "session_timeout_days": {
        "value": 30,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Session timeout in days",
    },
    "single_session": {
        "value": False,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Allow only single session per user",
    },
    "max_login_attempts": {
        "value": 5,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Max login attempts before lockout",
    },
    "lockout_duration_minutes": {
        "value": 15,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Account lockout duration in minutes",
    },
    "enable_captcha": {
        "value": False,
        "type": "bool",
        "category": "security",
        "public": True,
        "desc": "Enable captcha on login",
    },
    # Password Expiration
    "password_expiration_enabled": {
        "value": False,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Enable password expiration policy",
    },
    "password_expiration_days": {
        "value": 90,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Password expiration period in days",
    },
    "password_expiration_warning_days": {
        "value": 7,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Warning period before expiration in days",
    },
    "password_history_count": {
        "value": 5,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Number of previous passwords to check",
    },
    "password_min_age_days": {
        "value": 0,
        "type": "int",
        "category": "security",
        "public": False,
        "desc": "Minimum password age in days before change allowed",
    },
    "force_password_change_first_login": {
        "value": False,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Force password change on first login",
    },
    "require_totp": {
        "value": False,
        "type": "bool",
        "category": "security",
        "public": False,
        "desc": "Require all users to enable TOTP two-factor authentication",
    },
    # Email
    "smtp_enabled": {
        "value": False,
        "type": "bool",
        "category": "email",
        "public": False,
        "desc": "Enable SMTP",
    },
    "smtp_host": {
        "value": "",
        "type": "string",
        "category": "email",
        "public": False,
        "desc": "SMTP host",
    },
    "smtp_port": {
        "value": 587,
        "type": "int",
        "category": "email",
        "public": False,
        "desc": "SMTP port",
    },
    "smtp_encryption": {
        "value": "tls",
        "type": "string",
        "category": "email",
        "public": False,
        "desc": "SMTP encryption (none, ssl, tls)",
    },
    "smtp_username": {
        "value": "",
        "type": "string",
        "category": "email",
        "public": False,
        "desc": "SMTP username",
    },
    "smtp_password": {
        "value": "",
        "type": "string",
        "category": "email",
        "public": False,
        "desc": "SMTP password",
    },
    "email_from_name": {
        "value": "Clouisle",
        "type": "string",
        "category": "email",
        "public": False,
        "desc": "Email sender name",
    },
    "email_from_address": {
        "value": "",
        "type": "string",
        "category": "email",
        "public": False,
        "desc": "Email sender address",
    },
    # DingTalk
    "dingtalk_enabled": {
        "value": False,
        "type": "bool",
        "category": "dingtalk",
        "public": False,
        "desc": "Enable DingTalk notifications",
    },
    "dingtalk_notification_type": {
        "value": "webhook",
        "type": "string",
        "category": "dingtalk",
        "public": False,
        "desc": "DingTalk notification type (webhook or app)",
    },
    "dingtalk_webhook_url": {
        "value": "",
        "type": "string",
        "category": "dingtalk",
        "public": False,
        "desc": "DingTalk webhook URL",
    },
    "dingtalk_secret": {
        "value": "",
        "type": "string",
        "category": "dingtalk",
        "public": False,
        "desc": "DingTalk webhook secret",
    },
    "dingtalk_app_key": {
        "value": "",
        "type": "string",
        "category": "dingtalk",
        "public": False,
        "desc": "DingTalk app key",
    },
    "dingtalk_app_secret": {
        "value": "",
        "type": "string",
        "category": "dingtalk",
        "public": False,
        "desc": "DingTalk app secret",
    },
    "dingtalk_agent_id": {
        "value": "",
        "type": "string",
        "category": "dingtalk",
        "public": False,
        "desc": "DingTalk agent ID",
    },
    # Storage
    "audit_log_retention_days": {
        "value": 365,
        "type": "int",
        "category": "storage",
        "public": False,
        "desc": "Audit log retention days (30-3650)",
    },
    "audit_log_archive_path": {
        "value": "/var/log/clouisle/audit_archives",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "Archive file storage path",
    },
    "kb_document_max_upload_size_mb": {
        "value": KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
        "type": "int",
        "category": "storage",
        "public": True,
        "desc": "Knowledge base document max upload size in MB (1-1024)",
    },
    "upload_storage_backend": {
        "value": "local",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "Upload storage backend (local or object)",
    },
    "object_storage_endpoint": {
        "value": "",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "S3-compatible object storage endpoint",
    },
    "object_storage_bucket": {
        "value": "",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "Object storage bucket for uploaded files",
    },
    "object_storage_region": {
        "value": "",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "Object storage region",
    },
    "object_storage_access_key": {
        "value": "",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "Object storage access key",
    },
    "object_storage_secret_key": {
        "value": "",
        "type": "string",
        "category": "storage",
        "public": False,
        "desc": "Object storage secret key",
    },
    "object_storage_force_path_style": {
        "value": True,
        "type": "bool",
        "category": "storage",
        "public": False,
        "desc": "Use path-style S3 object storage URLs",
    },
    "object_storage_secure": {
        "value": True,
        "type": "bool",
        "category": "storage",
        "public": False,
        "desc": "Use HTTPS for object storage endpoint when no scheme is provided",
    },
    # Audit Alert
    "audit_alert_enabled": {
        "value": True,
        "type": "bool",
        "category": "audit",
        "public": False,
        "desc": "Enable audit log alerts",
    },
    "audit_alert_webhook": {
        "value": "",
        "type": "string",
        "category": "audit",
        "public": False,
        "desc": "Webhook URL for audit alerts",
    },
    "audit_alert_failed_login_threshold": {
        "value": 5,
        "type": "int",
        "category": "audit",
        "public": False,
        "desc": "Failed login attempts threshold for alert",
    },
    "audit_alert_failed_login_window": {
        "value": 5,
        "type": "int",
        "category": "audit",
        "public": False,
        "desc": "Time window in minutes for failed login detection",
    },
    "audit_alert_bulk_deletion_threshold": {
        "value": 10,
        "type": "int",
        "category": "audit",
        "public": False,
        "desc": "Bulk deletion threshold for alert",
    },
    # WeChat Work (企业微信)
    "wechat_enabled": {
        "value": False,
        "type": "bool",
        "category": "wechat",
        "public": False,
        "desc": "Enable WeChat Work notifications",
    },
    "wechat_notification_type": {
        "value": "webhook",
        "type": "string",
        "category": "wechat",
        "public": False,
        "desc": "WeChat Work notification type (webhook or app)",
    },
    "wechat_webhook_url": {
        "value": "",
        "type": "string",
        "category": "wechat",
        "public": False,
        "desc": "WeChat Work webhook URL",
    },
    "wechat_corp_id": {
        "value": "",
        "type": "string",
        "category": "wechat",
        "public": False,
        "desc": "WeChat Work corp ID",
    },
    "wechat_agent_id": {
        "value": "",
        "type": "string",
        "category": "wechat",
        "public": False,
        "desc": "WeChat Work agent ID",
    },
    "wechat_secret": {
        "value": "",
        "type": "string",
        "category": "wechat",
        "public": False,
        "desc": "WeChat Work app secret",
    },
    # Feishu (飞书)
    "feishu_enabled": {
        "value": False,
        "type": "bool",
        "category": "feishu",
        "public": False,
        "desc": "Enable Feishu notifications",
    },
    "feishu_notification_type": {
        "value": "webhook",
        "type": "string",
        "category": "feishu",
        "public": False,
        "desc": "Feishu notification type (webhook or app)",
    },
    "feishu_webhook_url": {
        "value": "",
        "type": "string",
        "category": "feishu",
        "public": False,
        "desc": "Feishu webhook URL",
    },
    "feishu_secret": {
        "value": "",
        "type": "string",
        "category": "feishu",
        "public": False,
        "desc": "Feishu webhook secret for signature",
    },
    "feishu_app_id": {
        "value": "",
        "type": "string",
        "category": "feishu",
        "public": False,
        "desc": "Feishu app ID",
    },
    "feishu_app_secret": {
        "value": "",
        "type": "string",
        "category": "feishu",
        "public": False,
        "desc": "Feishu app secret",
    },
    # Generic Webhook
    "webhook_enabled": {
        "value": False,
        "type": "bool",
        "category": "webhook",
        "public": False,
        "desc": "Enable generic webhook notifications",
    },
    "webhook_url": {
        "value": "",
        "type": "string",
        "category": "webhook",
        "public": False,
        "desc": "Webhook URL",
    },
    "webhook_method": {
        "value": "POST",
        "type": "string",
        "category": "webhook",
        "public": False,
        "desc": "HTTP method (POST or GET)",
    },
    "webhook_headers": {
        "value": {},
        "type": "json",
        "category": "webhook",
        "public": False,
        "desc": "Custom HTTP headers as JSON",
    },
    "webhook_body_template": {
        "value": '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
        "type": "string",
        "category": "webhook",
        "public": False,
        "desc": "Request body template with {{title}}, {{content}}, {{link_url}} placeholders",
    },
    "webhook_secret": {
        "value": "",
        "type": "string",
        "category": "webhook",
        "public": False,
        "desc": "Secret for HMAC signature",
    },
    # Slack
    "slack_enabled": {
        "value": False,
        "type": "bool",
        "category": "slack",
        "public": False,
        "desc": "Enable Slack notifications",
    },
    "slack_webhook_url": {
        "value": "",
        "type": "string",
        "category": "slack",
        "public": False,
        "desc": "Slack incoming webhook URL",
    },
    # SSO Settings
    "sso_enabled": {
        "value": False,
        "type": "bool",
        "category": "sso",
        "public": True,
        "desc": "Enable SSO authentication",
    },
    "sso_allow_password_login": {
        "value": True,
        "type": "bool",
        "category": "sso",
        "public": True,
        "desc": "Allow password-based login when SSO is enabled",
    },
    "sso_auto_create_users": {
        "value": True,
        "type": "bool",
        "category": "sso",
        "public": False,
        "desc": "Automatically create users from SSO providers",
    },
    "sso_require_approval": {
        "value": False,
        "type": "bool",
        "category": "sso",
        "public": False,
        "desc": "Require admin approval for SSO-created users",
    },
    "sso_match_by_email": {
        "value": True,
        "type": "bool",
        "category": "sso",
        "public": False,
        "desc": "Match existing users by email address",
    },
    # Auto Notification Settings
    "auto_notification_config": {
        "value": {
            "channels": [],  # Global channels for all enabled notifications
            "enabled_types": [
                "team.member_added",
                "team.member_removed",
                "team.role_changed",
                "team.ownership_transferred",
                "team.model_granted",
                "team.model_revoked",
                "user.activated",
                "user.deactivated",
                "user.password_reset",
                "user.pending_approval",
                "kb.doc_indexed",
                "kb.doc_failed",
                "workflow.run_failed",
                "apikey.expiring",
                "apikey.expired",
                "security.login_anomaly",
                "security.account_locked",
                "security.password_changed",
            ],
        },
        "type": "json",
        "category": "notification",
        "public": False,
        "desc": "Auto notification configuration",
    },
}


async def init_default_settings():
    """Initialize default settings if not exist"""
    for key, config in DEFAULT_SETTINGS.items():
        existing = await SiteSetting.filter(key=key).first()
        if not existing:
            await SiteSetting.set_value(
                key=key,
                value=config["value"],
                value_type=config["type"],
                category=config["category"],
                description=config["desc"],
                is_public=config["public"],
            )
