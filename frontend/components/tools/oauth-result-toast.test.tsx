import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { GlobalRegistrator } from '@happy-dom/global-registrator'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const success = mock(() => {})
const error = mock(() => {})
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => `connections.${key}` }))
mock.module('next/navigation', () => ({
  usePathname: () => '/app/capabilities',
  useRouter: () => ({ replace: () => {}, push: () => {} }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

// Dynamic import applies the module mocks before the hook loads.
const { OAuthResultToast } = await import('./oauth-result-toast')

let renderer: ReactTestRenderer | undefined

beforeEach(() => {
  success.mockClear()
  error.mockClear()
  window.history.replaceState(null, '', '/app/capabilities?tab=tools')
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
})

async function render() {
  await act(async () => {
    renderer = create(<OAuthResultToast />)
  })
  await act(async () => {})
}

describe('OAuthResultToast', () => {
  test('shows success and strips only oauth metadata from the URL', async () => {
    window.history.replaceState(null, '', '/app/capabilities?tab=tools&oauth=success&connection_id=c1&code=secret')
    await render()
    expect(success).toHaveBeenCalledWith('connections.oauthSuccess')
    expect(window.location.pathname).toBe('/app/capabilities')
    expect(window.location.search).toContain('tab=tools')
    expect(window.location.search).toContain('code=secret')
    expect(window.location.search).not.toContain('oauth=')
    expect(window.location.search).not.toContain('connection_id=')
  })

  test('maps known errors and falls back for unknown slugs', async () => {
    window.history.replaceState(null, '', '/app/capabilities?oauth=error&error=oauth_expired&connection_id=c1')
    await render()
    expect(error).toHaveBeenCalledWith('connections.oauthErrors.oauth_expired')

    error.mockClear()
    window.history.replaceState(null, '', '/app/capabilities?oauth=error&error=unknown_slug')
    if (renderer) act(() => renderer.unmount())
    renderer = undefined
    await render()
    expect(error).toHaveBeenCalledWith('connections.oauthErrors.oauth_callback_failed')
  })
})
