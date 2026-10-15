import { describe, expect, it, spyOn } from 'bun:test'

import { api } from '../client'
import { integrationsApi } from './integrations'
import type { Integration, IntegrationCreate, IntegrationUpdate } from './integrations'

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

  it('uses typed builtin and global login settings endpoints', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({})
    const put = spyOn(api, 'put').mockResolvedValue({})
    const post = spyOn(api, 'post').mockResolvedValue(undefined)
    try {
      await integrationsApi.types()
      await integrationsApi.getEmail()
      await integrationsApi.getWebhook()
      await integrationsApi.getFeishuConfig()
      await integrationsApi.getFeishuDepartments()
      await integrationsApi.getFeishuTestRecipients('ada user')
      await integrationsApi.getLoginSettings()
      await integrationsApi.updateEmail({ smtp_enabled: false })
      await integrationsApi.updateWebhook({ webhook_enabled: true })
      await integrationsApi.updateFeishuConfig({ is_enabled: true })
      await integrationsApi.updateFeishuDepartmentScope(['department-1'])
      await integrationsApi.updateLoginSettings({ sso_enabled: false })
      await integrationsApi.sendTestEmail('admin@example.com')
      await integrationsApi.sendTestWebhook()
      await integrationsApi.checkFeishuConnection()
      await integrationsApi.sendFeishuTestMessage('user-1', 'Test', 'Message')
      await integrationsApi.syncFeishuContacts()
      expect(get.mock.calls.map(([url]) => url)).toEqual([
        '/admin/integrations/types', '/admin/integrations/email', '/admin/integrations/webhook',
        '/admin/integrations/feishu/config', '/admin/integrations/feishu/departments',
        '/admin/integrations/feishu/test-recipients?search=ada%20user', '/admin/integrations/login-settings',
      ])
      expect(put.mock.calls).toEqual([
        ['/admin/integrations/email', { smtp_enabled: false }],
        ['/admin/integrations/webhook', { webhook_enabled: true }],
        ['/admin/integrations/feishu/config', { is_enabled: true }],
        ['/admin/integrations/feishu/department-scope', { department_ids: ['department-1'] }],
        ['/admin/integrations/login-settings', { sso_enabled: false }],
      ])
      expect(post.mock.calls).toEqual([
        ['/admin/integrations/email/test', { email: 'admin@example.com' }],
        ['/admin/integrations/webhook/test', null],
        ['/admin/integrations/feishu/connection-check', null],
        ['/admin/integrations/feishu/test-message', { user_id: 'user-1', title: 'Test', content: 'Message' }],
        ['/admin/integrations/feishu/sync', null, { timeout: 120000 }],
      ])
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
