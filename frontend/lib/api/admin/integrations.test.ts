import { describe, expect, it, spyOn } from 'bun:test'

import { api } from '../client'
import { integrationsApi } from './integrations'
import type { Integration, IntegrationCreate, IntegrationUpdate, LoginSettings } from './integrations'
import type { EmailSettings, WebhookSettings } from '../site-settings'

const provider = { id: 'provider-1' } as Integration

describe('admin integrationsApi requests', () => {
  it('uses the provider routes and forwards payloads and return values', async () => {
    const created: IntegrationCreate = {
      name: 'work',
      provider_type: 'oidc',
      display_name: 'Work SSO',
      config: { issuer: 'https://id.example.com' },
      enabled_capabilities: ['user_login'],
    }
    const updated: IntegrationUpdate = { is_enabled: false }
    const get = spyOn(api, 'get').mockResolvedValue([provider])
    const post = spyOn(api, 'post')
      .mockResolvedValueOnce(provider)
      .mockResolvedValueOnce({ status: 'ok', message: 'connected' })
    const put = spyOn(api, 'put').mockResolvedValue(provider)
    const remove = spyOn(api, 'delete').mockResolvedValue(undefined)

    try {
      expect(await integrationsApi.list()).toEqual([provider])
      expect(await integrationsApi.create(created)).toBe(provider)
      expect(await integrationsApi.update('provider-1', updated)).toBe(provider)
      expect(await integrationsApi.delete('provider-1')).toBeUndefined()
      expect(await integrationsApi.testConnection('provider-1')).toEqual({ status: 'ok', message: 'connected' })
      expect(await integrationsApi.adminDisconnectConnection('connection-1')).toBeUndefined()

      expect(get).toHaveBeenCalledWith('/admin/integrations')
      expect(post).toHaveBeenNthCalledWith(1, '/admin/integrations', created)
      expect(put).toHaveBeenCalledWith('/admin/integrations/provider-1', updated)
      expect(remove).toHaveBeenNthCalledWith(1, '/admin/integrations/provider-1')
      expect(post).toHaveBeenNthCalledWith(2, '/admin/integrations/provider-1/test')
      expect(remove).toHaveBeenNthCalledWith(2, '/admin/integrations/connections/connection-1')
    } finally {
      get.mockRestore()
      post.mockRestore()
      put.mockRestore()
      remove.mockRestore()
    }
  })
  it('covers settings, email, webhook, and Feishu administration wrappers', async () => {
    const login = { password_login_enabled: true } as LoginSettings
    const email = { enabled: true, from_email: 'noreply@example.com' } as EmailSettings
    const webhook = { enabled: true, url: 'https://hooks.example.com' } as WebhookSettings
    const feishu = { app_id: 'app-1', app_secret_configured: true, department_ids: ['d1'], is_enabled: true }
    const agentChat = {
      connection_mode: 'long_connection', event_verification_token_configured: true,
      event_encrypt_key_configured: false, is_enabled: true, capability_enabled: true,
      receiver_status: { state: 'connected', managed: true },
    } as const
    const departments = [{ department_id: 'd1', name: 'Engineering', parent_department_id: null, children: [] }]
    const recipients = [{ id: 'u1', username: 'yun', email: 'yun@example.com' }]
    const get = spyOn(api, 'get').mockResolvedValueOnce([{ name: 'oidc' }]).mockResolvedValueOnce(login).mockResolvedValueOnce(email).mockResolvedValueOnce(webhook).mockResolvedValueOnce(feishu).mockResolvedValueOnce(agentChat).mockResolvedValueOnce(departments).mockResolvedValueOnce(recipients).mockResolvedValueOnce(recipients).mockResolvedValueOnce(recipients)
    const put = spyOn(api, 'put').mockResolvedValueOnce(login).mockResolvedValueOnce(email).mockResolvedValueOnce(webhook).mockResolvedValueOnce(feishu).mockResolvedValueOnce(agentChat).mockResolvedValueOnce({ department_ids: ['d1'] })
    const post = spyOn(api, 'post').mockResolvedValueOnce(undefined).mockResolvedValueOnce(undefined).mockResolvedValueOnce({ status: 'ok' }).mockResolvedValueOnce({ status: 'sent' }).mockResolvedValueOnce({ created: 1, updated: 2, skipped: 3, teams_created: 4 })

    try {
      expect(await integrationsApi.types()).toEqual([{ name: 'oidc' }])
      expect(await integrationsApi.getLoginSettings()).toBe(login)
      expect(await integrationsApi.updateLoginSettings({ password_login_enabled: false })).toBe(login)
      expect(await integrationsApi.getEmail()).toBe(email)
      expect(await integrationsApi.updateEmail({ enabled: false })).toBe(email)
      await integrationsApi.sendTestEmail('test@example.com')
      expect(await integrationsApi.getWebhook()).toBe(webhook)
      expect(await integrationsApi.updateWebhook({ enabled: false })).toBe(webhook)
      await integrationsApi.sendTestWebhook()
      expect(await integrationsApi.getFeishuConfig()).toBe(feishu)
      expect(await integrationsApi.updateFeishuConfig({ app_id: 'app-2', app_secret: 'secret' })).toBe(feishu)
      expect(await integrationsApi.getFeishuAgentChatConfig()).toBe(agentChat)
      expect(await integrationsApi.updateFeishuAgentChatConfig({ connection_mode: 'callback', event_verification_token: 'token' })).toBe(agentChat)
      expect(await integrationsApi.getFeishuDepartments()).toBe(departments)
      expect(await integrationsApi.updateFeishuDepartmentScope(['d1'])).toEqual({ department_ids: ['d1'] })
      expect(await integrationsApi.checkFeishuConnection()).toEqual({ status: 'ok' })
      expect(await integrationsApi.getFeishuTestRecipients()).toBe(recipients)
      expect(await integrationsApi.getFeishuTestRecipients('yun+ops@example.com &')).toBe(recipients)
      expect(await integrationsApi.sendFeishuTestMessage('u1', 'Title', 'Hello')).toEqual({ status: 'sent' })
      expect(await integrationsApi.syncFeishuContacts()).toEqual({ created: 1, updated: 2, skipped: 3, teams_created: 4 })

      expect(get).toHaveBeenNthCalledWith(1, '/admin/integrations/types')
      expect(get).toHaveBeenNthCalledWith(2, '/admin/integrations/login-settings')
      expect(put).toHaveBeenNthCalledWith(1, '/admin/integrations/login-settings', { password_login_enabled: false })
      expect(get).toHaveBeenNthCalledWith(3, '/admin/integrations/email')
      expect(put).toHaveBeenNthCalledWith(2, '/admin/integrations/email', { enabled: false })
      expect(post).toHaveBeenNthCalledWith(1, '/admin/integrations/email/test', { email: 'test@example.com' })
      expect(get).toHaveBeenNthCalledWith(4, '/admin/integrations/webhook')
      expect(put).toHaveBeenNthCalledWith(3, '/admin/integrations/webhook', { enabled: false })
      expect(post).toHaveBeenNthCalledWith(2, '/admin/integrations/webhook/test', null)
      expect(get).toHaveBeenNthCalledWith(5, '/admin/integrations/feishu/config')
      expect(put).toHaveBeenNthCalledWith(4, '/admin/integrations/feishu/config', { app_id: 'app-2', app_secret: 'secret' })
      expect(get).toHaveBeenNthCalledWith(6, '/admin/integrations/feishu/agent-chat/config')
      expect(put).toHaveBeenNthCalledWith(5, '/admin/integrations/feishu/agent-chat/config', { connection_mode: 'callback', event_verification_token: 'token' })
      expect(get).toHaveBeenNthCalledWith(7, '/admin/integrations/feishu/departments')
      expect(put).toHaveBeenNthCalledWith(6, '/admin/integrations/feishu/department-scope', { department_ids: ['d1'] })
      expect(post).toHaveBeenNthCalledWith(3, '/admin/integrations/feishu/connection-check', null)
      expect(get).toHaveBeenNthCalledWith(8, '/admin/integrations/feishu/test-recipients')
      expect(get).toHaveBeenNthCalledWith(9, '/admin/integrations/feishu/test-recipients?search=yun%2Bops%40example.com%20%26')
      expect(post).toHaveBeenNthCalledWith(4, '/admin/integrations/feishu/test-message', { user_id: 'u1', title: 'Title', content: 'Hello' })
      expect(post).toHaveBeenNthCalledWith(5, '/admin/integrations/feishu/sync', null, { timeout: 120000 })
    } finally {
      get.mockRestore()
      put.mockRestore()
      post.mockRestore()
    }
  })



  it('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    const get = spyOn(api, 'get').mockRejectedValue(error)

    try {
      await expect(integrationsApi.list()).rejects.toBe(error)
    } finally {
      get.mockRestore()
    }
  })
})
