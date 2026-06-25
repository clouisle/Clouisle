import { api } from './client'

export type AuthPageLayout = 'centered' | 'split'
export type ThemeMode = 'system' | 'light' | 'dark'
export type ThemeBrandingDisplay = 'full' | 'name_only' | 'icon_only' | 'hidden'

export interface SiteSetting {
  key: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  value: any
  value_type: string
  category: string
  description?: string
  is_public: boolean
}

export interface SiteSettings {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  settings: Record<string, any>
}

export interface PublicSiteSettings {
  site_name: string
  site_description: string
  site_url: string
  site_icon: string
  auth_page_layout: AuthPageLayout
  theme_mode: ThemeMode
  theme_primary_color: string
  theme_primary_foreground_color: string
  theme_branding_display: ThemeBrandingDisplay
  icp_record_number: string
  icp_record_url: string
  terms_enabled: boolean
  terms_url: string
  terms_text: string
  privacy_enabled: boolean
  privacy_url: string
  privacy_text: string
  require_terms_acceptance_on_register: boolean
  allow_registration: boolean
  require_approval: boolean
  email_verification: boolean
  enable_captcha: boolean
  allow_account_deletion: boolean
  sso_enabled: boolean
  sso_allow_password_login: boolean
  kb_document_max_upload_size_mb: number
}

export interface GeneralSettings {
  site_name: string
  site_description: string
  site_url: string
  site_icon: string
  default_language: string
  auth_page_layout: AuthPageLayout
  theme_mode: ThemeMode
  theme_primary_color: string
  theme_primary_foreground_color: string
  theme_branding_display: ThemeBrandingDisplay
  icp_record_number: string
  icp_record_url: string
  terms_enabled: boolean
  terms_url: string
  terms_text: string
  privacy_enabled: boolean
  privacy_url: string
  privacy_text: string
  require_terms_acceptance_on_register: boolean
}

export interface SecuritySettings {
  allow_registration: boolean
  require_approval: boolean
  email_verification: boolean
  allow_account_deletion: boolean
  default_role_id: string
  default_team_id: string
  default_team_role: 'viewer' | 'member' | 'admin'
  min_password_length: number
  require_uppercase: boolean
  require_number: boolean
  require_special_char: boolean
  session_timeout_days: number
  single_session: boolean
  max_login_attempts: number
  lockout_duration_minutes: number
  enable_captcha: boolean
  sso_enabled: boolean
  sso_allow_password_login: boolean
  sso_auto_create_users: boolean
  sso_require_approval: boolean
  sso_match_by_email: boolean
  // Password expiration
  password_expiration_enabled: boolean
  password_expiration_days: number
  password_expiration_warning_days: number
  password_history_count: number
  password_min_age_days: number
  force_password_change_first_login: boolean
  // TOTP
  require_totp: boolean
}

export interface EmailSettings {
  smtp_enabled: boolean
  smtp_host: string
  smtp_port: number
  smtp_encryption: 'none' | 'ssl' | 'tls'
  smtp_username: string
  smtp_password: string
  email_from_name: string
  email_from_address: string
}

export interface DingTalkSettings {
  dingtalk_enabled: boolean
  dingtalk_notification_type: 'webhook' | 'app'
  dingtalk_webhook_url: string
  dingtalk_secret: string
  dingtalk_app_key: string
  dingtalk_app_secret: string
  dingtalk_agent_id: string
}

export interface WeChatSettings {
  wechat_enabled: boolean
  wechat_notification_type: 'webhook' | 'app'
  wechat_webhook_url: string
  wechat_corp_id: string
  wechat_agent_id: string
  wechat_secret: string
}

export interface FeishuSettings {
  feishu_enabled: boolean
  feishu_notification_type: 'webhook' | 'app'
  feishu_webhook_url: string
  feishu_secret: string
  feishu_app_id: string
  feishu_app_secret: string
}

export interface WebhookSettings {
  webhook_enabled: boolean
  webhook_url: string
  webhook_method: 'POST' | 'GET'
  webhook_headers: Record<string, string>
  webhook_body_template: string
  webhook_secret: string
}

export interface SlackSettings {
  slack_enabled: boolean
  slack_webhook_url: string
}

export interface AutoNotificationConfig {
  channels: string[]  // Global channels for all enabled notifications
  enabled_types: string[]  // Enabled notification types
}

export const siteSettingsApi = {
  /**
   * Get public site settings (no auth required)
   */
  async getPublic(): Promise<PublicSiteSettings> {
    return api.get<PublicSiteSettings>('/site-settings/public')
  },
}
