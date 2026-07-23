import { describe, expect, it, spyOn } from 'bun:test'

import { api } from '../client'
import { ssoApi } from './sso'
import type { SSOProviderAdmin, SSOProviderCreate, SSOProviderUpdate } from './sso'

const provider = { id: 'provider-1' } as SSOProviderAdmin

describe('admin ssoApi requests', () => {
  it('uses the provider routes and forwards payloads and return values', async () => {
    const created: SSOProviderCreate = {
      name: 'work',
      protocol: 'oidc',
      display_name: 'Work SSO',
      config: { issuer: 'https://id.example.com' },
    }
    const updated: SSOProviderUpdate = { is_enabled: false }
    const get = spyOn(api, 'get').mockResolvedValue([provider])
    const post = spyOn(api, 'post')
      .mockResolvedValueOnce(provider)
      .mockResolvedValueOnce({ status: 'ok', message: 'connected' })
    const put = spyOn(api, 'put').mockResolvedValue(provider)
    const remove = spyOn(api, 'delete').mockResolvedValue(undefined)

    try {
      expect(await ssoApi.listProviders()).toEqual([provider])
      expect(await ssoApi.createProvider(created)).toBe(provider)
      expect(await ssoApi.updateProvider('provider-1', updated)).toBe(provider)
      expect(await ssoApi.deleteProvider('provider-1')).toBeUndefined()
      expect(await ssoApi.testConnection('provider-1')).toEqual({ status: 'ok', message: 'connected' })
      expect(await ssoApi.adminDisconnectConnection('connection-1')).toBeUndefined()

      expect(get).toHaveBeenCalledWith('/admin/sso/providers')
      expect(post).toHaveBeenNthCalledWith(1, '/admin/sso/providers', created)
      expect(put).toHaveBeenCalledWith('/admin/sso/providers/provider-1', updated)
      expect(remove).toHaveBeenNthCalledWith(1, '/admin/sso/providers/provider-1')
      expect(post).toHaveBeenNthCalledWith(2, '/admin/sso/providers/provider-1/test')
      expect(remove).toHaveBeenNthCalledWith(2, '/admin/sso/connections/connection-1')
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
      await expect(ssoApi.listProviders()).rejects.toBe(error)
    } finally {
      get.mockRestore()
    }
  })
})
