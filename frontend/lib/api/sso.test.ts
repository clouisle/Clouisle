import { afterEach, beforeEach, describe, expect, spyOn, test, type Spy } from 'bun:test'
import { Window } from 'happy-dom'

import { API_BASE_URL } from '@/lib/constants'
import { api } from './client'
import { ssoApi, ssoLinkState, SSO_LINK_PENDING_KEY, SSOLinkStateError } from './sso'

// The module resolves `sessionStorage` from the global scope at call time, so the
// test must install one before importing it.
const window = new Window()
globalThis.sessionStorage = window.sessionStorage as unknown as Storage

let get: Spy<typeof api.get>
let post: Spy<typeof api.post>
let remove: Spy<typeof api.delete>
let spies: Array<Spy<unknown>>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue({
    authorization_url: 'https://accounts.feishu.cn/authorize?state=link-state',
    session_id: 'link-state',
  })
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
  spies = [get, post, remove]
  sessionStorage.clear()
})

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
  sessionStorage.clear()
})

describe('ssoApi', () => {
  test('constructs provider and connection requests', async () => {
    await ssoApi.getPublicIntegrations()
    await ssoApi.disconnectConnection('connection-1')

    expect(get).toHaveBeenCalledWith('/sso/integrations')
    expect(remove).toHaveBeenCalledWith('/sso/connections/connection-1')
  })

  test('initiates login with optional encoded redirect', () => {
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
    const location = { href: '' }
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: { location },
    })

    try {
      ssoApi.initiateLogin('oidc')
      expect(location.href).toBe(`${API_BASE_URL}/sso/login/oidc`)

      ssoApi.initiateLogin('saml', '/settings/sso?tab=connections&from=login')
      expect(location.href).toBe(
        `${API_BASE_URL}/sso/login/saml?redirect=%2Fsettings%2Fsso%3Ftab%3Dconnections%26from%3Dlogin`
      )
    } finally {
      if (originalWindow) {
        Object.defineProperty(globalThis, 'window', originalWindow)
      } else {
        Reflect.deleteProperty(globalThis, 'window')
      }
    }
  })

  test('propagates request errors', async () => {
    const providerError = new Error('provider request failed')
    const disconnectError = new Error('disconnect request failed')
    get.mockRejectedValueOnce(providerError)
    remove.mockRejectedValueOnce(disconnectError)

    await expect(ssoApi.getPublicIntegrations()).rejects.toBe(providerError)
    await expect(ssoApi.disconnectConnection('connection-1')).rejects.toBe(disconnectError)
  })

  test('lists linkable providers for the authenticated user', async () => {
    await ssoApi.getLinkableIntegrations()
    expect(get).toHaveBeenCalledWith('/sso/links/integrations')
  })

  test('starts a link, stores the pending session, and completes it', async () => {
    const link = await ssoApi.startLink('feishu')

    expect(post).toHaveBeenCalledWith('/sso/links?provider_name=feishu')
    expect(link.session_id).toBe('link-state')
    expect(ssoLinkState.read()).toBe('link-state')
    expect(sessionStorage.getItem(SSO_LINK_PENDING_KEY)).toBe('link-state')

    await ssoApi.completeLink('link-state')
    expect(post).toHaveBeenLastCalledWith('/sso/links/complete', { session_id: 'link-state' })

    ssoLinkState.clear()
    expect(ssoLinkState.read()).toBeNull()
  })

  test('encodes the provider name into the link start query', async () => {
    await ssoApi.startLink('fei shu+1')
    expect(post).toHaveBeenCalledWith('/sso/links?provider_name=fei%20shu%2B1')
    ssoLinkState.clear()
  })

  test('rejects and keeps the pending state empty when it cannot be stored', async () => {
    const store = sessionStorage as { setItem: Storage['setItem'] }
    const originalSetItem = store.setItem
    Object.defineProperty(store, 'setItem', {
      configurable: true,
      writable: true,
      value: () => {
        throw new Error('QuotaExceededError')
      },
    })

    try {
      await expect(ssoApi.startLink('feishu')).rejects.toBeInstanceOf(SSOLinkStateError)
      expect(ssoLinkState.read()).toBeNull()
    } finally {
      Object.defineProperty(store, 'setItem', {
        configurable: true,
        writable: true,
        value: originalSetItem,
      })
    }
  })
})
