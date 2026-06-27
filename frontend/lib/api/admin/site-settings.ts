import { api } from '../client'
import type {
  SiteSetting,
  SiteSettings,
  GeneralSettings,
  SecuritySettings,
  EmailSettings,
  DingTalkSettings,
  WeChatSettings,
  FeishuSettings,
  WebhookSettings,
  SlackSettings,
  StorageSettings,
  AutoNotificationConfig,
  ThemeBrandingDisplay,
  ThemeMode,
} from '../site-settings'

export type {
  SiteSetting,
  SiteSettings,
  GeneralSettings,
  SecuritySettings,
  EmailSettings,
  DingTalkSettings,
  WeChatSettings,
  FeishuSettings,
  WebhookSettings,
  SlackSettings,
  StorageSettings,
  AutoNotificationConfig,
}

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/

function normalizeThemeMode(value: unknown): ThemeMode {
  return value === 'light' || value === 'dark' || value === 'system' ? value : 'system'
}

function normalizeBrandingDisplay(value: unknown): ThemeBrandingDisplay {
  if (value === 'name_only' || value === 'icon_only' || value === 'hidden') {
    return value
  }
  return 'full'
}

function normalizeThemeColor(value: unknown): string {
  return typeof value === 'string' && HEX_COLOR_PATTERN.test(value.trim()) ? value.trim() : ''
}

export const siteSettingsApi = {
  async getAll(category?: string): Promise<Record<string, unknown>> {
    const params = category ? `?category=${category}` : ''
    const res = await api.get<SiteSettings>(`/admin/site-settings${params}`)
    return res.settings
  },

  async get(key: string): Promise<SiteSetting> {
    return api.get<SiteSetting>(`/admin/site-settings/${key}`)
  },

  async update(key: string, value: unknown): Promise<SiteSetting> {
    return api.put<SiteSetting>(`/admin/site-settings/${key}`, { value })
  },

  async bulkUpdate(settings: Record<string, unknown>): Promise<Record<string, unknown>> {
    const res = await api.put<SiteSettings>('/admin/site-settings', { settings })
    return res.settings
  },

  async reset(category?: string): Promise<Record<string, unknown>> {
    const params = category ? `?category=${category}` : ''
    const res = await api.post<SiteSettings>(`/admin/site-settings/reset${params}`, null)
    return res.settings
  },

  async getGeneral(): Promise<GeneralSettings> {
    const settings = await this.getAll('general')
    return {
      site_name: (settings.site_name as string) ?? 'Clouisle',
      site_description: (settings.site_description as string) ?? '',
      site_url: (settings.site_url as string) ?? '',
      site_icon: (settings.site_icon as string) ?? '',
      default_language: (settings.default_language as string) ?? 'en',
      auth_page_layout: settings.auth_page_layout === 'split' ? 'split' : 'centered',
      theme_mode: normalizeThemeMode(settings.theme_mode),
      theme_primary_color: normalizeThemeColor(settings.theme_primary_color),
      theme_primary_foreground_color: normalizeThemeColor(settings.theme_primary_foreground_color),
      theme_branding_display: normalizeBrandingDisplay(settings.theme_branding_display),
      icp_record_number: (settings.icp_record_number as string) ?? '',
      icp_record_url: (settings.icp_record_url as string) ?? '',
      terms_enabled: (settings.terms_enabled as boolean) ?? false,
      terms_url: (settings.terms_url as string) ?? '',
      terms_text: (settings.terms_text as string) ?? '',
      privacy_enabled: (settings.privacy_enabled as boolean) ?? false,
      privacy_url: (settings.privacy_url as string) ?? '',
      privacy_text: (settings.privacy_text as string) ?? '',
      require_terms_acceptance_on_register: (settings.require_terms_acceptance_on_register as boolean) ?? false,
    }
  },

  async updateGeneral(data: Partial<GeneralSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async getSecurity(): Promise<SecuritySettings> {
    const settings = await this.getAll('security')
    const ssoSettings = await this.getAll('sso')
    return {
      allow_registration: (settings.allow_registration as boolean) ?? true,
      require_approval: (settings.require_approval as boolean) ?? false,
      email_verification: (settings.email_verification as boolean) ?? true,
      allow_account_deletion: (settings.allow_account_deletion as boolean) ?? true,
      default_role_id: (settings.default_role_id as string) ?? '',
      default_team_id: (settings.default_team_id as string) ?? '',
      default_team_role: (settings.default_team_role as 'viewer' | 'member' | 'admin') ?? 'member',
      min_password_length: (settings.min_password_length as number) ?? 8,
      require_uppercase: (settings.require_uppercase as boolean) ?? true,
      require_number: (settings.require_number as boolean) ?? true,
      require_special_char: (settings.require_special_char as boolean) ?? false,
      session_timeout_days: (settings.session_timeout_days as number) ?? 30,
      single_session: (settings.single_session as boolean) ?? false,
      max_login_attempts: (settings.max_login_attempts as number) ?? 5,
      lockout_duration_minutes: (settings.lockout_duration_minutes as number) ?? 15,
      enable_captcha: (settings.enable_captcha as boolean) ?? false,
      sso_enabled: (ssoSettings.sso_enabled as boolean) ?? false,
      sso_allow_password_login: (ssoSettings.sso_allow_password_login as boolean) ?? true,
      sso_auto_create_users: (ssoSettings.sso_auto_create_users as boolean) ?? true,
      sso_require_approval: (ssoSettings.sso_require_approval as boolean) ?? false,
      sso_match_by_email: (ssoSettings.sso_match_by_email as boolean) ?? true,
      // Password expiration
      password_expiration_enabled: (settings.password_expiration_enabled as boolean) ?? false,
      password_expiration_days: (settings.password_expiration_days as number) ?? 90,
      password_expiration_warning_days: (settings.password_expiration_warning_days as number) ?? 7,
      password_history_count: (settings.password_history_count as number) ?? 5,
      password_min_age_days: (settings.password_min_age_days as number) ?? 0,
      force_password_change_first_login: (settings.force_password_change_first_login as boolean) ?? false,
      // TOTP
      require_totp: (settings.require_totp as boolean) ?? false,
    }
  },

  async updateSecurity(data: Partial<SecuritySettings>): Promise<Record<string, unknown>> {
    const res = await api.put<SiteSettings>('/admin/site-settings', { settings: data })
    return res.settings
  },

  async getEmail(): Promise<EmailSettings> {
    const settings = await this.getAll('email')
    return {
      smtp_enabled: (settings.smtp_enabled as boolean) ?? false,
      smtp_host: (settings.smtp_host as string) ?? '',
      smtp_port: (settings.smtp_port as number) ?? 587,
      smtp_encryption: (settings.smtp_encryption as 'none' | 'ssl' | 'tls') ?? 'tls',
      smtp_username: (settings.smtp_username as string) ?? '',
      smtp_password: (settings.smtp_password as string) ?? '',
      email_from_name: (settings.email_from_name as string) ?? 'Clouisle',
      email_from_address: (settings.email_from_address as string) ?? '',
    }
  },

  async updateEmail(data: Partial<EmailSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async sendTestEmail(email: string): Promise<void> {
    await api.post<null>('/admin/site-settings/test-email', { email })
  },

  async getDingTalk(): Promise<DingTalkSettings> {
    const settings = await this.getAll('dingtalk')
    return {
      dingtalk_enabled: (settings.dingtalk_enabled as boolean) ?? false,
      dingtalk_notification_type: (settings.dingtalk_notification_type as 'webhook' | 'app') ?? 'webhook',
      dingtalk_webhook_url: (settings.dingtalk_webhook_url as string) ?? '',
      dingtalk_secret: (settings.dingtalk_secret as string) ?? '',
      dingtalk_app_key: (settings.dingtalk_app_key as string) ?? '',
      dingtalk_app_secret: (settings.dingtalk_app_secret as string) ?? '',
      dingtalk_agent_id: (settings.dingtalk_agent_id as string) ?? '',
    }
  },

  async updateDingTalk(data: Partial<DingTalkSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async sendTestDingTalk(): Promise<void> {
    await api.post<null>('/admin/site-settings/test-dingtalk', null)
  },

  async getWeChat(): Promise<WeChatSettings> {
    const settings = await this.getAll('wechat')
    return {
      wechat_enabled: (settings.wechat_enabled as boolean) ?? false,
      wechat_notification_type: (settings.wechat_notification_type as 'webhook' | 'app') ?? 'webhook',
      wechat_webhook_url: (settings.wechat_webhook_url as string) ?? '',
      wechat_corp_id: (settings.wechat_corp_id as string) ?? '',
      wechat_agent_id: (settings.wechat_agent_id as string) ?? '',
      wechat_secret: (settings.wechat_secret as string) ?? '',
    }
  },

  async updateWeChat(data: Partial<WeChatSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async sendTestWeChat(): Promise<void> {
    await api.post<null>('/admin/site-settings/test-wechat', null)
  },

  async getFeishu(): Promise<FeishuSettings> {
    const settings = await this.getAll('feishu')
    return {
      feishu_enabled: (settings.feishu_enabled as boolean) ?? false,
      feishu_notification_type: (settings.feishu_notification_type as 'webhook' | 'app') ?? 'webhook',
      feishu_webhook_url: (settings.feishu_webhook_url as string) ?? '',
      feishu_secret: (settings.feishu_secret as string) ?? '',
      feishu_app_id: (settings.feishu_app_id as string) ?? '',
      feishu_app_secret: (settings.feishu_app_secret as string) ?? '',
    }
  },

  async updateFeishu(data: Partial<FeishuSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async sendTestFeishu(): Promise<void> {
    await api.post<null>('/admin/site-settings/test-feishu', null)
  },

  async getWebhook(): Promise<WebhookSettings> {
    const settings = await this.getAll('webhook')
    return {
      webhook_enabled: (settings.webhook_enabled as boolean) ?? false,
      webhook_url: (settings.webhook_url as string) ?? '',
      webhook_method: (settings.webhook_method as 'POST' | 'GET') ?? 'POST',
      webhook_headers: (settings.webhook_headers as Record<string, string>) ?? {},
      webhook_body_template: (settings.webhook_body_template as string) ?? '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
      webhook_secret: (settings.webhook_secret as string) ?? '',
    }
  },

  async updateWebhook(data: Partial<WebhookSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async sendTestWebhook(): Promise<void> {
    await api.post<null>('/admin/site-settings/test-webhook', null)
  },

  async getSlack(): Promise<SlackSettings> {
    const settings = await this.getAll('slack')
    return {
      slack_enabled: (settings.slack_enabled as boolean) ?? false,
      slack_webhook_url: (settings.slack_webhook_url as string) ?? '',
    }
  },

  async updateSlack(data: Partial<SlackSettings>): Promise<Record<string, unknown>> {
    return this.bulkUpdate(data)
  },

  async sendTestSlack(): Promise<void> {
    await api.post<null>('/admin/site-settings/test-slack', null)
  },

  async archiveAuditLogs(): Promise<{ task_id: string; status: string }> {
    return api.post<{ task_id: string; status: string }>('/admin/site-settings/archive-audit-logs', null)
  },

  async getArchiveTaskStatus(taskId: string): Promise<{
    task_id: string
    status: string
    message?: string
    result?: {
   status: string
      archived_count?: number
      retention_days?: number
    cutoff_date?: string
    }
    error?: string
  }> {
    return api.get(`/admin/site-settings/archive-audit-logs/${taskId}`)
  },

  async getAutoNotifications(): Promise<AutoNotificationConfig> {
    return api.get<AutoNotificationConfig>('/admin/site-settings/auto-notifications')
  },

  async updateAutoNotifications(config: AutoNotificationConfig): Promise<AutoNotificationConfig> {
    return api.put<AutoNotificationConfig>('/admin/site-settings/auto-notifications', config)
  },
}
