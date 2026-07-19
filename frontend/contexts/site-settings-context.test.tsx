import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import { siteSettingsApi, type PublicSiteSettings } from '@/lib/api'
import { SiteSettingsProvider, useSiteSettings } from './site-settings-context'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const settings = (site_name: string, site_icon = '') => ({
  site_name,
  site_icon,
  theme_mode: 'system',
} as PublicSiteSettings)

const captured = { current: undefined as ReturnType<typeof useSiteSettings> | undefined }
function Consumer() {
  const value = useSiteSettings()
  React.useEffect(() => {
    captured.current = value
  }, [value])
  return null
}

const latest = () => captured.current!

function Harness({ children, ...props }: React.PropsWithChildren<React.ComponentProps<typeof SiteSettingsProvider>>) {
  return (
    <NextIntlClientProvider locale="en" timeZone="UTC" messages={{ platform: { admin: 'Admin' } }}>
      <SiteSettingsProvider {...props}>{children}</SiteSettingsProvider>
    </NextIntlClientProvider>
  )
}

const fakeDocument = () => {
  const icon = { href: '' }
  return {
    title: '',
    documentElement: { style: { setProperty() {}, removeProperty() {} } },
    querySelector: () => icon,
    createElement: () => ({ rel: '', href: '' }),
    head: { appendChild() {} },
    icon,
  }
}

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
  })
}

afterEach(() => {
  mock.restore()
  delete (globalThis as { document?: Document }).document
})

describe('SiteSettingsProvider', () => {
  test('exposes loading, then applies successful settings and document metadata', async () => {
    const document = fakeDocument()
    globalThis.document = document as unknown as Document
    const request = Promise.withResolvers<PublicSiteSettings>()
    spyOn(siteSettingsApi, 'getPublic').mockReturnValue(request.promise)

    let renderer: ReactTestRenderer
    await act(() => {
      renderer = create(<Harness><Consumer /></Harness>)
    })
    expect(latest().loading).toBe(true)
    expect(latest().settings.site_name).toBe('Clouisle')

    request.resolve(settings('Acme', '/acme.svg'))
    await flush()
    expect(latest().loading).toBe(false)
    expect(latest().settings.site_name).toBe('Acme')
    expect(document.title).toBe('Acme - Admin')
    expect(document.icon.href).toBe('/acme.svg')
    act(() => renderer!.unmount())
  })

  test('keeps defaults and finishes loading on error', async () => {
    globalThis.document = fakeDocument() as unknown as Document
    const error = new Error('offline')
    spyOn(siteSettingsApi, 'getPublic').mockRejectedValue(error)
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(<Harness><Consumer /></Harness>)
    })

    expect(latest().loading).toBe(false)
    expect(latest().settings.site_name).toBe('Clouisle')
    expect(consoleError).toHaveBeenCalledWith('Failed to load site settings:', error)
    act(() => renderer!.unmount())
  })

  test('refreshes settings while respecting metadata boundaries', async () => {
    const document = fakeDocument()
    document.title = 'Unchanged'
    document.icon.href = '/unchanged.svg'
    globalThis.document = document as unknown as Document
    const getPublic = spyOn(siteSettingsApi, 'getPublic')
      .mockResolvedValueOnce(settings('First'))
      .mockResolvedValueOnce(settings('Second', '/second.svg'))

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(<Harness skipTitleUpdate skipFaviconUpdate><Consumer /></Harness>)
    })
    await act(() => latest().refresh())

    expect(latest().settings.site_name).toBe('Second')
    expect(latest().loading).toBe(false)
    expect(document.title).toBe('Unchanged')
    expect(document.icon.href).toBe('/unchanged.svg')
    expect(getPublic).toHaveBeenCalledTimes(2)
    act(() => renderer!.unmount())
  })
})
