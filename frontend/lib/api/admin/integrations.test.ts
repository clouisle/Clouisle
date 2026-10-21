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
