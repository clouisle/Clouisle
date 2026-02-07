import { api } from './client'

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
  allow_registration: boolean
  require_approval: boolean
  email_verification: boolean
  enable_captcha: boolean
  allow_account_deletion: boolean
  sso_enabled: boolean
  sso_allow_password_login: boolean
}

export interface GeneralSettings {
  site_name: string
  site_description: string
  site_url: string
  site_icon: string
  default_language: string
}

export interface SecuritySettings {
  allow_registration: boolean
  require_approval: boolean
  email_verification: boolean
  allow_account_deletion: boolean
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

  /**
   * Get all settings (admin only)
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async getAll(category?: string): Promise<Record<string, any>> {
    const params = category ? `?category=${category}` : ''
    const res = await api.get<SiteSettings>(`/site-settings${params}`)
    return res.settings
  },

  /**
   * Get a specific setting
   */
  async get(key: string): Promise<SiteSetting> {
    return api.get<SiteSetting>(`/site-settings/${key}`)
  },

  /**
   * Update a specific setting
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async update(key: string, value: any): Promise<SiteSetting> {
    return api.put<SiteSetting>(`/site-settings/${key}`, { value })
  },

  /**
   * Bulk update multiple settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async bulkUpdate(settings: Record<string, any>): Promise<Record<string, any>> {
    const res = await api.put<SiteSettings>('/site-settings', { settings })
    return res.settings
  },

  /**
   * Reset settings to default values
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async reset(category?: string): Promise<Record<string, any>> {
    const params = category ? `?category=${category}` : ''
    const res = await api.post<SiteSettings>(`/site-settings/reset${params}`, null)
    return res.settings
  },

  /**
   * Get general settings
   */
  async getGeneral(): Promise<GeneralSettings> {
    const settings = await this.getAll('general')
    return {
      site_name: settings.site_name ?? 'Clouisle',
      site_description: settings.site_description ?? '',
      site_url: settings.site_url ?? '',
      site_icon: settings.site_icon ?? '',
      default_language: settings.default_language ?? 'en',
    }
  },

  /**
   * Update general settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateGeneral(data: Partial<GeneralSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Get security settings
   */
  async getSecurity(): Promise<SecuritySettings> {
    const settings = await this.getAll('security')
    const ssoSettings = await this.getAll('sso')
    return {
      allow_registration: settings.allow_registration ?? true,
      require_approval: settings.require_approval ?? false,
      email_verification: settings.email_verification ?? true,
      allow_account_deletion: settings.allow_account_deletion ?? true,
      min_password_length: settings.min_password_length ?? 8,
      require_uppercase: settings.require_uppercase ?? true,
      require_number: settings.require_number ?? true,
      require_special_char: settings.require_special_char ?? false,
      session_timeout_days: settings.session_timeout_days ?? 30,
      single_session: settings.single_session ?? false,
      max_login_attempts: settings.max_login_attempts ?? 5,
      lockout_duration_minutes: settings.lockout_duration_minutes ?? 15,
      enable_captcha: settings.enable_captcha ?? false,
      sso_enabled: ssoSettings.sso_enabled ?? false,
      sso_allow_password_login: ssoSettings.sso_allow_password_login ?? true,
      sso_auto_create_users: ssoSettings.sso_auto_create_users ?? true,
      sso_require_approval: ssoSettings.sso_require_approval ?? false,
      sso_match_by_email: ssoSettings.sso_match_by_email ?? true,
    }
  },

  /**
   * Update security settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateSecurity(data: Partial<SecuritySettings>): Promise<Record<string, any>> {
    const res = await api.put<SiteSettings>('/site-settings', { settings: data }, { silent: true })
    return res.settings
  },

  /**
   * Get email settings
   */
  async getEmail(): Promise<EmailSettings> {
    const settings = await this.getAll('email')
    return {
      smtp_enabled: settings.smtp_enabled ?? false,
      smtp_host: settings.smtp_host ?? '',
      smtp_port: settings.smtp_port ?? 587,
      smtp_encryption: settings.smtp_encryption ?? 'tls',
      smtp_username: settings.smtp_username ?? '',
      smtp_password: settings.smtp_password ?? '',
      email_from_name: settings.email_from_name ?? 'Clouisle',
      email_from_address: settings.email_from_address ?? '',
    }
  },

  /**
   * Update email settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateEmail(data: Partial<EmailSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Send test email
   */
  async sendTestEmail(email: string): Promise<void> {
    await api.post<null>('/site-settings/test-email', { email })
  },

  /**
   * Get DingTalk settings
   */
  async getDingTalk(): Promise<DingTalkSettings> {
    const settings = await this.getAll('dingtalk')
    return {
      dingtalk_enabled: settings.dingtalk_enabled ?? false,
      dingtalk_notification_type: settings.dingtalk_notification_type ?? 'webhook',
      dingtalk_webhook_url: settings.dingtalk_webhook_url ?? '',
      dingtalk_secret: settings.dingtalk_secret ?? '',
      dingtalk_app_key: settings.dingtalk_app_key ?? '',
      dingtalk_app_secret: settings.dingtalk_app_secret ?? '',
      dingtalk_agent_id: settings.dingtalk_agent_id ?? '',
    }
  },

  /**
   * Update DingTalk settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateDingTalk(data: Partial<DingTalkSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Send test DingTalk message
   */
  async sendTestDingTalk(): Promise<void> {
    await api.post<null>('/site-settings/test-dingtalk', null)
  },

  /**
   * Get WeChat Work settings
   */
  async getWeChat(): Promise<WeChatSettings> {
    const settings = await this.getAll('wechat')
    return {
      wechat_enabled: settings.wechat_enabled ?? false,
      wechat_notification_type: settings.wechat_notification_type ?? 'webhook',
      wechat_webhook_url: settings.wechat_webhook_url ?? '',
      wechat_corp_id: settings.wechat_corp_id ?? '',
      wechat_agent_id: settings.wechat_agent_id ?? '',
      wechat_secret: settings.wechat_secret ?? '',
    }
  },

  /**
   * Update WeChat Work settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateWeChat(data: Partial<WeChatSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Send test WeChat Work message
   */
  async sendTestWeChat(): Promise<void> {
    await api.post<null>('/site-settings/test-wechat', null)
  },

  /**
   * Get Feishu settings
   */
  async getFeishu(): Promise<FeishuSettings> {
    const settings = await this.getAll('feishu')
    return {
      feishu_enabled: settings.feishu_enabled ?? false,
      feishu_notification_type: settings.feishu_notification_type ?? 'webhook',
      feishu_webhook_url: settings.feishu_webhook_url ?? '',
      feishu_secret: settings.feishu_secret ?? '',
      feishu_app_id: settings.feishu_app_id ?? '',
      feishu_app_secret: settings.feishu_app_secret ?? '',
    }
  },

  /**
   * Update Feishu settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateFeishu(data: Partial<FeishuSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Send test Feishu message
   */
  async sendTestFeishu(): Promise<void> {
    await api.post<null>('/site-settings/test-feishu', null)
  },

  /**
   * Get Webhook settings
   */
  async getWebhook(): Promise<WebhookSettings> {
    const settings = await this.getAll('webhook')
    return {
      webhook_enabled: settings.webhook_enabled ?? false,
      webhook_url: settings.webhook_url ?? '',
      webhook_method: settings.webhook_method ?? 'POST',
      webhook_headers: settings.webhook_headers ?? {},
      webhook_body_template: settings.webhook_body_template ?? '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
      webhook_secret: settings.webhook_secret ?? '',
    }
  },

  /**
   * Update Webhook settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateWebhook(data: Partial<WebhookSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Send test Webhook notification
   */
  async sendTestWebhook(): Promise<void> {
    await api.post<null>('/site-settings/test-webhook', null)
  },

  /**
   * Get Slack settings
   */
  async getSlack(): Promise<SlackSettings> {
    const settings = await this.getAll('slack')
    return {
      slack_enabled: settings.slack_enabled ?? false,
      slack_webhook_url: settings.slack_webhook_url ?? '',
    }
  },

  /**
   * Update Slack settings
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async updateSlack(data: Partial<SlackSettings>): Promise<Record<string, any>> {
    return this.bulkUpdate(data)
  },

  /**
   * Send test Slack message
   */
  async sendTestSlack(): Promise<void> {
    await api.post<null>('/site-settings/test-slack', null)
  },

  /**
   * Manually trigger audit log archiving
   */
  async archiveAuditLogs(): Promise<{ task_id: string; status: string }> {
    return api.post<{ task_id: string; status: string }>('/site-settings/archive-audit-logs', null)
  },

  /**
   * Get auto notification configuration
   */
  async getAutoNotifications(): Promise<AutoNotificationConfig> {
    return api.get<AutoNotificationConfig>('/site-settings/auto-notifications')
  },

  /**
   * Update auto notification configuration
   */
  async updateAutoNotifications(config: AutoNotificationConfig): Promise<AutoNotificationConfig> {
    return api.put<AutoNotificationConfig>('/site-settings/auto-notifications', config)
  },
}
