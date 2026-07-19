import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, mock, spyOn } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { cleanup, render, waitFor, within } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { ThemeProvider as NextThemesProvider } from 'next-themes'
import * as React from 'react'

import { siteSettingsApi, type PublicSiteSettings } from '@/lib/api'
import { SiteSettingsProvider } from '@/contexts/site-settings-context'
import { DefaultSiteIcon } from './default-site-icon'
import { DynamicFavicon } from './dynamic-favicon'
import { SiteBranding } from './site-branding'
import { ThemeProvider } from './providers/theme-provider'
import { ThemeToggle } from './theme-toggle'

const settings = (overrides: Partial<PublicSiteSettings> = {}) => ({
  site_name: 'Acme',
  site_description: 'Knowledge for everyone',
  site_icon: '',
  theme_mode: 'system',
  theme_branding_display: 'full',
  ...overrides,
} as PublicSiteSettings)

function SiteHarness({ children, value = settings() }: React.PropsWithChildren<{ value?: PublicSiteSettings }>) {
  spyOn(siteSettingsApi, 'getPublic').mockResolvedValue(value)
  return (
    <NextIntlClientProvider locale="en" messages={{ platform: { admin: 'Admin' } }}>
      <NextThemesProvider forcedTheme="dark">
        <SiteSettingsProvider skipTitleUpdate skipFaviconUpdate>{children}</SiteSettingsProvider>
      </NextThemesProvider>
    </NextIntlClientProvider>
  )
}

beforeAll(() => GlobalRegistrator.register({ url: 'http://localhost' }))
beforeEach(() => {
  spyOn(siteSettingsApi, 'getPublic').mockResolvedValue(settings())
})
afterEach(() => {
  cleanup()
  mock.restore()
  document.head.querySelectorAll("link[rel*='icon']").forEach(link => link.remove())
  document.documentElement.removeAttribute('class')
  localStorage.clear()
})
afterAll(() => GlobalRegistrator.unregister())

describe('branding and theme components', () => {
  it('renders the default icon with its requested dimensions after mounting', async () => {
    const light = render(
      <NextThemesProvider forcedTheme="light">
        <DefaultSiteIcon className="brand-icon" width={24} height={20} />
      </NextThemesProvider>,
    )

    await waitFor(() => expect(within(document.body).getByAltText('Site Icon').getAttribute('src')).toBe('/clouisle-light.svg'))
    const lightIcon = within(document.body).getByAltText('Site Icon')
    expect(lightIcon.getAttribute('width')).toBe('24')
    expect(lightIcon.getAttribute('height')).toBe('20')
    expect(lightIcon.className).toContain('brand-icon')

    light.unmount()
  })

  it('renders loading, full, custom-icon, and hidden branding variants', async () => {
    const pending = Promise.withResolvers<PublicSiteSettings>()
    spyOn(siteSettingsApi, 'getPublic').mockReturnValue(pending.promise)
    const loading = render(
      <NextIntlClientProvider locale="en" timeZone="UTC" messages={{ platform: { admin: 'Admin' } }}>
        <NextThemesProvider><SiteSettingsProvider><SiteBranding className="extra" /></SiteSettingsProvider></NextThemesProvider>
      </NextIntlClientProvider>,
    )
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
    pending.resolve(settings())
    await waitFor(() => expect(within(document.body).getByText('Acme')).toBeTruthy())
    loading.unmount()

    const custom = render(<SiteHarness value={settings({ site_icon: '/acme.png' })}><SiteBranding size="lg" showDescription /></SiteHarness>)
    await waitFor(() => expect(within(document.body).getByText('Knowledge for everyone')).toBeTruthy())
    expect(within(document.body).getByAltText('Acme').getAttribute('src')).toBe('/acme.png')
    custom.unmount()

    render(<SiteHarness value={settings({ theme_branding_display: 'hidden' })}><SiteBranding /></SiteHarness>)
    await waitFor(() => expect(siteSettingsApi.getPublic).toHaveBeenCalled())
    expect(within(document.body).queryByText('Acme')).toBeNull()
  })

  it('replaces favicons, uses custom icons, and restores prior links on cleanup', async () => {
    const original = document.createElement('link')
    original.rel = 'shortcut icon'
    original.href = '/original.ico'
    document.head.appendChild(original)

    const view = render(
      <NextIntlClientProvider locale="en" timeZone="UTC" messages={{ platform: { admin: 'Admin' } }}>
        <NextThemesProvider forcedTheme="dark"><SiteSettingsProvider skipTitleUpdate skipFaviconUpdate><DynamicFavicon /></SiteSettingsProvider></NextThemesProvider>
      </NextIntlClientProvider>,
    )
    await waitFor(() => expect(document.head.querySelector('link[rel="icon"]')?.getAttribute('href')).toMatch(/^\/clouisle-(light|dark)\.svg\?v=\d+$/))
    expect(document.head.contains(original)).toBe(false)
    view.unmount()
    expect(document.head.contains(original)).toBe(true)

    const custom = render(<SiteHarness value={settings({ site_icon: '/brand.ico' })}><DynamicFavicon /></SiteHarness>)
    await waitFor(() => expect(document.head.querySelector('link[rel="icon"]')?.getAttribute('href')).toMatch(/^\/brand\.ico\?v=\d+$/))
    expect(document.head.querySelector('link[rel="icon"]')?.getAttribute('type')).toBe('image/x-icon')
    custom.unmount()
  })

  it('passes provider children through and exposes theme choices', async () => {
    render(<ThemeProvider storageKey="branding-test-theme"><output>provider child</output></ThemeProvider>)
    expect(within(document.body).getByText('provider child')).toBeTruthy()

    render(
      <NextIntlClientProvider locale="en" timeZone="UTC" messages={{ settings: { theme: 'Theme', light: 'Light', dark: 'Dark', system: 'System' } }}>
        <ThemeToggle />
      </NextIntlClientProvider>,
    )
    expect(within(document.body).getByRole('button', { name: 'Theme' })).toBeTruthy()
  })
})
