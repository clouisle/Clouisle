import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { API_BASE_URL } from '@/lib/constants'
import { api } from './client'
import { ssoApi } from './sso'

let get: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>
let spies: Array<ReturnType<typeof spyOn>>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
  spies = [get, remove]
})

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
})

describe('ssoApi', () => {
  test('constructs provider and connection requests', async () => {
    await ssoApi.getPublicProviders()
    await ssoApi.disconnectConnection('connection-1')

    expect(get).toHaveBeenCalledWith('/sso/providers')
    expect(remove).toHaveBeenCalledWith('/sso/connections/connection-1')
  })

  test('initiates login with optional encoded redirect', () => {
    const originalWindow = globalThis.window
    const location = { href: '' }
    Object.assign(globalThis, { window: { location } })

    try {
      ssoApi.initiateLogin('oidc')
      expect(location.href).toBe(`${API_BASE_URL}/sso/login/oidc`)

      ssoApi.initiateLogin('saml', '/settings/sso?tab=connections&from=login')
      expect(location.href).toBe(
        `${API_BASE_URL}/sso/login/saml?redirect=%2Fsettings%2Fsso%3Ftab%3Dconnections%26from%3Dlogin`
      )
    } finally {
      Object.assign(globalThis, { window: originalWindow })
    }
  })

  test('propagates request errors', async () => {
    const providerError = new Error('provider request failed')
    const disconnectError = new Error('disconnect request failed')
    get.mockRejectedValueOnce(providerError)
    remove.mockRejectedValueOnce(disconnectError)

    await expect(ssoApi.getPublicProviders()).rejects.toBe(providerError)
    await expect(ssoApi.disconnectConnection('connection-1')).rejects.toBe(disconnectError)
  })
})
