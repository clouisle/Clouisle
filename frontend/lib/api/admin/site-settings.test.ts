import { describe, expect, it, spyOn } from 'bun:test'

import { api } from '../client'
import { siteSettingsApi } from './site-settings'

const response = (settings: Record<string, unknown>) => ({ settings })

describe('siteSettingsApi requests', () => {
  it('builds optional category queries and unwraps settings', async () => {
    const get = spyOn(api, 'get')
      .mockResolvedValueOnce(response({ one: 1 }))
      .mockResolvedValueOnce(response({ two: 2 }))
      .mockResolvedValueOnce({ key: 'site_name', value: 'Clouisle' })

    try {
      expect(await siteSettingsApi.getAll()).toEqual({ one: 1 })
      expect(await siteSettingsApi.getAll('security')).toEqual({ two: 2 })
      expect(await siteSettingsApi.get('site_name')).toEqual({ key: 'site_name', value: 'Clouisle' })
      expect(get).toHaveBeenNthCalledWith(1, '/admin/site-settings')
      expect(get).toHaveBeenNthCalledWith(2, '/admin/site-settings?category=security')
      expect(get).toHaveBeenNthCalledWith(3, '/admin/site-settings/site_name')
    } finally {
      get.mockRestore()
    }
  })

  it('sends exact update and reset payloads and returns unwrapped values', async () => {
    const put = spyOn(api, 'put')
      .mockResolvedValueOnce({ key: 'site_name', value: 'New name' })
      .mockResolvedValueOnce(response({ site_name: 'New name' }))
      .mockResolvedValueOnce(response({ allow_registration: false }))
    const post = spyOn(api, 'post')
      .mockResolvedValueOnce(response({ all: 'reset' }))
      .mockResolvedValueOnce(response({ email: 'reset' }))

    try {
      expect(await siteSettingsApi.update('site_name', 'New name')).toEqual({ key: 'site_name', value: 'New name' })
      expect(await siteSettingsApi.bulkUpdate({ site_name: 'New name' })).toEqual({ site_name: 'New name' })
      expect(await siteSettingsApi.updateSecurity({ allow_registration: false })).toEqual({ allow_registration: false })
      expect(await siteSettingsApi.reset()).toEqual({ all: 'reset' })
      expect(await siteSettingsApi.reset('email')).toEqual({ email: 'reset' })

      expect(put).toHaveBeenNthCalledWith(1, '/admin/site-settings/site_name', { value: 'New name' })
      expect(put).toHaveBeenNthCalledWith(2, '/admin/site-settings', { settings: { site_name: 'New name' } })
      expect(put).toHaveBeenNthCalledWith(3, '/admin/site-settings', { settings: { allow_registration: false } })
      expect(post).toHaveBeenNthCalledWith(1, '/admin/site-settings/reset', null)
      expect(post).toHaveBeenNthCalledWith(2, '/admin/site-settings/reset?category=email', null)
    } finally {
      put.mockRestore()
      post.mockRestore()
    }
  })

  it('normalizes general settings defaults and accepted optional values', async () => {
    const get = spyOn(api, 'get')
      .mockResolvedValueOnce(response({}))
      .mockResolvedValueOnce(response({
        site_name: '',
        auth_page_layout: 'split',
        theme_mode: 'dark',
        theme_branding_display: 'icon_only',
        theme_primary_color: '  #AbC  ',
        theme_background_color: 'not-a-color',
        terms_enabled: true,
      }))

    try {
      const defaults = await siteSettingsApi.getGeneral()
      expect(defaults.site_name).toBe('Clouisle')
      expect(defaults.auth_page_layout).toBe('centered')
      expect(defaults.theme_mode).toBe('system')
      expect(defaults.theme_branding_display).toBe('full')
      expect(defaults.theme_primary_color).toBe('')
      expect(defaults.terms_enabled).toBe(false)

      const configured = await siteSettingsApi.getGeneral()
      expect(configured.site_name).toBe('')
      expect(configured.auth_page_layout).toBe('split')
      expect(configured.theme_mode).toBe('dark')
      expect(configured.theme_branding_display).toBe('icon_only')
      expect(configured.theme_primary_color).toBe('#AbC')
      expect(configured.theme_background_color).toBe('')
      expect(configured.terms_enabled).toBe(true)
      expect(get).toHaveBeenNthCalledWith(1, '/admin/site-settings?category=general')
      expect(get).toHaveBeenNthCalledWith(2, '/admin/site-settings?category=general')
    } finally {
      get.mockRestore()
    }
  })

  it('loads security branches and category defaults from exact routes', async () => {
    const get = spyOn(api, 'get').mockResolvedValue(response({
      model_endpoint_allowlist: [],
    }))

    try {
      const security = await siteSettingsApi.getSecurity()
      expect(security).toMatchObject({
        allow_registration: true,
        require_approval: false,
        min_password_length: 8,
        sso_enabled: false,
        sso_allow_password_login: true,
        password_expiration_days: 90,
        require_totp: false,
      })
      expect(await siteSettingsApi.getEmail()).toMatchObject({ smtp_enabled: false, smtp_port: 587, smtp_encryption: 'tls' })
      expect(await siteSettingsApi.getDingTalk()).toMatchObject({ dingtalk_enabled: false, dingtalk_notification_type: 'webhook' })
      expect(await siteSettingsApi.getWeChat()).toMatchObject({ wechat_enabled: false, wechat_notification_type: 'webhook' })
      expect(await siteSettingsApi.getFeishu()).toMatchObject({ feishu_enabled: false, feishu_notification_type: 'webhook' })
      expect(await siteSettingsApi.getWebhook()).toMatchObject({ webhook_enabled: false, webhook_method: 'POST', webhook_headers: {} })
      expect(await siteSettingsApi.getSlack()).toEqual({ slack_enabled: false, slack_webhook_url: '' })

      expect(get.mock.calls.map(([route]) => route)).toEqual([
        '/admin/site-settings?category=security',
        '/admin/site-settings?category=sso',
        '/admin/site-settings?category=email',
        '/admin/site-settings?category=dingtalk',
        '/admin/site-settings?category=wechat',
        '/admin/site-settings?category=feishu',
        '/admin/site-settings?category=webhook',
        '/admin/site-settings?category=slack',
      ])
    } finally {
      get.mockRestore()
    }
  })

  it('rejects missing or malformed model endpoint allowlists', async () => {
    for (const value of [undefined, 'invalid', ['https://api.example.com', 42]]) {
      const securitySettings = value === undefined
        ? {}
        : { model_endpoint_allowlist: value }
      const get = spyOn(api, 'get')
        .mockResolvedValueOnce(response(securitySettings))
        .mockResolvedValueOnce(response({}))

      try {
        await expect(siteSettingsApi.getSecurity()).rejects.toThrow(
          'Invalid model endpoint allowlist response'
        )
      } finally {
        get.mockRestore()
      }
    }
  })

  it('uses exact action, archive, and auto-notification requests', async () => {
    const post = spyOn(api, 'post')
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({ task_id: 'task-1', status: 'queued' })
    const get = spyOn(api, 'get')
      .mockResolvedValueOnce({ task_id: 'task-1', status: 'done' })
      .mockResolvedValueOnce({ enabled: true, events: [] })
    const put = spyOn(api, 'put').mockResolvedValue({ enabled: false, events: [] })

    try {
      expect(await siteSettingsApi.sendTestEmail('admin@example.com')).toBeUndefined()
      await siteSettingsApi.sendTestDingTalk()
      await siteSettingsApi.sendTestWeChat()
      await siteSettingsApi.sendTestFeishu()
      await siteSettingsApi.sendTestWebhook()
      await siteSettingsApi.sendTestSlack()
      expect(await siteSettingsApi.archiveAuditLogs()).toEqual({ task_id: 'task-1', status: 'queued' })
      expect(await siteSettingsApi.getArchiveTaskStatus('task-1')).toEqual({ task_id: 'task-1', status: 'done' })
      expect(await siteSettingsApi.getAutoNotifications()).toEqual({ enabled: true, events: [] })
      expect(await siteSettingsApi.updateAutoNotifications({ enabled: false, events: [] })).toEqual({ enabled: false, events: [] })

      expect(post.mock.calls).toEqual([
        ['/admin/site-settings/test-email', { email: 'admin@example.com' }],
        ['/admin/site-settings/test-dingtalk', null],
        ['/admin/site-settings/test-wechat', null],
        ['/admin/site-settings/test-feishu', null],
        ['/admin/site-settings/test-webhook', null],
        ['/admin/site-settings/test-slack', null],
        ['/admin/site-settings/archive-audit-logs', null],
      ])
      expect(get).toHaveBeenNthCalledWith(1, '/admin/site-settings/archive-audit-logs/task-1')
      expect(get).toHaveBeenNthCalledWith(2, '/admin/site-settings/auto-notifications')
      expect(put).toHaveBeenCalledWith('/admin/site-settings/auto-notifications', { enabled: false, events: [] })
    } finally {
      post.mockRestore()
      get.mockRestore()
      put.mockRestore()
    }
  })

  it('delegates category updates through the bulk update payload', async () => {
    const put = spyOn(api, 'put').mockResolvedValue(response({ saved: true }))
    const updates = [
      () => siteSettingsApi.updateGeneral({ site_name: 'New' }),
      () => siteSettingsApi.updateEmail({ smtp_enabled: true }),
      () => siteSettingsApi.updateDingTalk({ dingtalk_enabled: true }),
      () => siteSettingsApi.updateWeChat({ wechat_enabled: true }),
      () => siteSettingsApi.updateFeishu({ feishu_enabled: true }),
      () => siteSettingsApi.updateWebhook({ webhook_enabled: true }),
      () => siteSettingsApi.updateSlack({ slack_enabled: true }),
    ]

    try {
      for (const update of updates) expect(await update()).toEqual({ saved: true })
      expect(put.mock.calls).toEqual([
        ['/admin/site-settings', { settings: { site_name: 'New' } }],
        ['/admin/site-settings', { settings: { smtp_enabled: true } }],
        ['/admin/site-settings', { settings: { dingtalk_enabled: true } }],
        ['/admin/site-settings', { settings: { wechat_enabled: true } }],
        ['/admin/site-settings', { settings: { feishu_enabled: true } }],
        ['/admin/site-settings', { settings: { webhook_enabled: true } }],
        ['/admin/site-settings', { settings: { slack_enabled: true } }],
      ])
    } finally {
      put.mockRestore()
    }
  })

  it('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    const get = spyOn(api, 'get').mockRejectedValue(error)

    try {
      await expect(siteSettingsApi.getAll()).rejects.toBe(error)
    } finally {
      get.mockRestore()
    }
  })
})
