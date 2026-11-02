import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

let siteSettingsState: {
  settings: Record<string, unknown>
  loading: boolean
} = { settings: {}, loading: false }

const getCurrentUser = mock(() =>
  Promise.resolve({ username: 'alice', email: 'alice@example.com' })
)

mock.module('@/contexts/site-settings-context', () => ({
  useSiteSettings: () => siteSettingsState,
}))
mock.module('@/lib/api', () => ({ authApi: { getCurrentUser } }))

const { GlobalWatermark } = await import('./global-watermark') // dynamic: mock.module() must register before the module evaluates

const WATERMARK_SETTINGS = {
  site_name: 'Acme',
  watermark_enabled: true,
  watermark_content: '{username} {date} {time}',
  watermark_opacity: 10,
  watermark_font_size: 16,
  watermark_rotation: -30,
  watermark_gap: 180,
  watermark_color: '',
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const tokenStore = new Map<string, string>()
const storageListeners = new Set<(event: { key: string | null }) => void>()

const installGlobals = () => {
  globalThis.localStorage = {
    getItem: (key: string) => tokenStore.get(key) ?? null,
    setItem: (key: string, value: string) => tokenStore.set(key, value),
  } as unknown as Storage
  globalThis.window = {
    innerWidth: 1280,
    addEventListener: (type: string, handler: (event: { key: string | null }) => void) => {
      if (type === 'storage') storageListeners.add(handler)
    },
    removeEventListener: (type: string, handler: (event: { key: string | null }) => void) => {
      if (type === 'storage') storageListeners.delete(handler)
    },
  } as unknown as Window & typeof globalThis
}

const setToken = (token: string | null, notify = false) => {
  if (token === null) tokenStore.delete('access_token')
  else tokenStore.set('access_token', token)
  if (notify) {
    for (const listener of storageListeners) listener({ key: 'access_token' })
  }
}

const renderers: ReactTestRenderer[] = []

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
  })
}

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<GlobalWatermark />)
  })
  renderers.push(renderer!)
  return renderer!
}

const overlayText = (renderer: ReactTestRenderer) => {
  const overlays = renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })
  if (overlays.length === 0) return null
  return overlays[0].findAllByType('text')[0].children.join('')
}

beforeEach(() => {
  siteSettingsState = { settings: { ...WATERMARK_SETTINGS }, loading: false }
  getCurrentUser.mockClear()
  getCurrentUser.mockImplementation(() =>
    Promise.resolve({ username: 'alice', email: 'alice@example.com' })
  )
  tokenStore.clear()
  storageListeners.clear()
  installGlobals()
  setToken('token')
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  storageListeners.clear()
})

describe('GlobalWatermark', () => {
  test('renders the resolved user identity when enabled with a session', async () => {
    const renderer = await render()
    const text = overlayText(renderer)
    expect(text).toContain('alice')
    expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true, silent: true })
  })

  test('renders nothing while site settings are loading', async () => {
    siteSettingsState = { settings: { ...WATERMARK_SETTINGS }, loading: true }
    const renderer = await render()
    expect(renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })).toHaveLength(0)
  })

  test('renders nothing when the watermark is disabled', async () => {
    siteSettingsState = {
      settings: { ...WATERMARK_SETTINGS, watermark_enabled: false },
      loading: false,
    }
    const renderer = await render()
    expect(renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })).toHaveLength(0)
    expect(getCurrentUser).not.toHaveBeenCalled()
  })

  test('renders nothing without an access token', async () => {
    setToken(null)
    const renderer = await render()
    expect(renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })).toHaveLength(0)
    expect(getCurrentUser).not.toHaveBeenCalled()
  })

  test('renders nothing when the identity cannot be resolved', async () => {
    getCurrentUser.mockImplementationOnce(() => Promise.reject(new Error('offline')))
    const renderer = await render()
    expect(renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })).toHaveLength(0)
  })

  test('re-resolves the identity when another tab replaces the access token', async () => {
    const renderer = await render()
    expect(overlayText(renderer)).toContain('alice')

    getCurrentUser.mockImplementationOnce(() =>
      Promise.resolve({ username: 'bob', email: 'bob@example.com' })
    )
    act(() => setToken('token-2', true))
    await flush()

    expect(getCurrentUser).toHaveBeenCalledTimes(2)
    expect(overlayText(renderer)).toContain('bob')
    expect(overlayText(renderer)).not.toContain('alice')
  })

  test('hides the overlay when the token is cleared in another tab', async () => {
    const renderer = await render()
    expect(overlayText(renderer)).toContain('alice')

    act(() => setToken(null, true))
    await flush()

    expect(renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })).toHaveLength(0)
  })
})
