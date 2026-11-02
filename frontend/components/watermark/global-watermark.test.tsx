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

const renderers: ReactTestRenderer[] = []

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<GlobalWatermark />)
  })
  renderers.push(renderer!)
  return renderer!
}

const setToken = (token: string | null) => {
  const storage = new Map<string, string>()
  if (token) storage.set('access_token', token)
  globalThis.localStorage = {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  } as unknown as Storage
}

const overlayText = (renderer: ReactTestRenderer) => {
  const overlays = renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })
  if (overlays.length === 0) return null
  return overlays[0].findAllByType('text')[0].children.join('')
}

beforeEach(() => {
  siteSettingsState = { settings: { ...WATERMARK_SETTINGS }, loading: false }
  getCurrentUser.mockClear()
  setToken('token')
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
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

  test('falls back to the site name when the user lookup fails', async () => {
    siteSettingsState = {
      settings: { ...WATERMARK_SETTINGS, watermark_content: '{username}' },
      loading: false,
    }
    getCurrentUser.mockImplementationOnce(() => Promise.reject(new Error('offline')))
    const renderer = await render()
    expect(overlayText(renderer)).toBe('Acme')
  })
})
