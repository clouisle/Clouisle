import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import { SearchParamsContext } from 'next/dist/shared/lib/hooks-client-context.shared-runtime'
import { ThemeProvider } from 'next-themes'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

import authMessages from '@/i18n/en/auth.json'
import commonMessages from '@/i18n/en/common.json'
import { authApi } from '@/lib/api'
import { AuthLayoutShell } from './_components/auth-layout-shell'
import { LegalMarkdown } from './_components/legal-markdown'
import { LoginRedirect } from './login/_components/login-redirect'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const router = {
  back: mock(() => {}), forward: mock(() => {}), refresh: mock(() => {}),
  push: mock(() => {}), replace: mock(() => {}), prefetch: mock(() => Promise.resolve()),
}
const legalSettings = {
  icp_record_number: '', icp_record_url: '', terms_enabled: false, terms_url: '', terms_text: '',
  privacy_enabled: false, privacy_url: '', privacy_text: '',
}
const brandingSettings = {
  site_name: 'Acme', site_description: 'Knowledge for everyone', site_icon: '', theme_branding_display: 'full' as const,
}

function render(component: React.ReactNode, search = '') {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(
      <AppRouterContext.Provider value={router}>
        <SearchParamsContext.Provider value={new URLSearchParams(search)}>
          <NextIntlClientProvider locale="en" timeZone="UTC" messages={{ ...authMessages, ...commonMessages }}>
            {component}
          </NextIntlClientProvider>
        </SearchParamsContext.Provider>
      </AppRouterContext.Provider>,
    )
  })
  return renderer!
}

const json = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())

afterEach(() => {
  mock.restore()
  Object.values(router).forEach(fn => fn.mockClear())
  delete (globalThis as { localStorage?: Storage }).localStorage
  delete (globalThis as { window?: Window }).window
})

describe('auth components', () => {
  test('renders centered and split auth layouts with their distinct content', () => {
    const centered = render(
      <AuthLayoutShell layout="centered" previewImageAlt="Preview" brandingSettings={brandingSettings} legalSettings={legalSettings}>
        <span>Form</span>
      </AuthLayoutShell>,
    )
    expect(json(centered)).toContain('Acme')
    expect(json(centered)).toContain('Knowledge for everyone')
    expect(centered.root.findAllByType('aside')).toHaveLength(0)
    act(() => centered.unmount())

    const split = render(
      <AuthLayoutShell layout="split" previewImageAlt="Preview" brandingSettings={brandingSettings} legalSettings={legalSettings}>
        <span>Form</span>
      </AuthLayoutShell>,
    )
    expect(split.root.findByType('aside')).toBeDefined()
    expect(split.root.findAllByType('img').some(image => image.props.alt === 'Preview')).toBe(true)
    act(() => split.unmount())
  })

  test('renders enabled legal links and ICP text while omitting disabled entries', () => {
    const renderer = render(
      <AuthLayoutShell
        layout="centered"
        previewImageAlt="Preview"
        brandingSettings={{ ...brandingSettings, theme_branding_display: 'hidden' }}
        legalSettings={{ ...legalSettings, terms_enabled: true, terms_url: '/terms', icp_record_number: 'ICP 123' }}
      >
        <span>Form</span>
      </AuthLayoutShell>,
    )
    const links = renderer.root.findAllByType('a')
    expect(links).toHaveLength(1)
    expect(links[0].props.href).toBe('/terms')
    expect(json(renderer)).toContain('ICP 123')
    expect(json(renderer)).not.toContain('Acme')
    act(() => renderer.unmount())
  })

  test('renders markdown source in the light-mode wrapper', () => {
    ;(globalThis as { window?: Window }).window = {
      matchMedia: () => ({ matches: false, addListener() {}, removeListener() {} }),
      addEventListener() {}, removeEventListener() {},
    } as unknown as Window
    const renderer = render(<ThemeProvider><LegalMarkdown source="# Terms" /></ThemeProvider>)
    const wrapper = renderer.root.findByProps({ className: 'wmde-markdown text-sm' })
    expect(wrapper.props['data-color-mode']).toBe('light')
    expect(wrapper.findByProps({ 'aria-hidden': 'true' })).toBeDefined()
    act(() => renderer.unmount())
  })

  test('redirects an authenticated login visitor to the requested page', async () => {
    ;(globalThis as { window?: Window }).window = {} as Window
    globalThis.localStorage = {
      getItem: () => 'token', removeItem: mock(() => {}),
    } as unknown as Storage
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({} as Awaited<ReturnType<typeof authApi.getCurrentUser>>)

    const renderer = render(<LoginRedirect />, 'redirect=/app/team')
    await act(async () => Promise.resolve())

    expect(authApi.getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true, silent: true })
    expect(router.replace).toHaveBeenCalledWith('/app/team')
    act(() => renderer.unmount())
  })
})
