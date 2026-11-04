import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import { PathnameContext, SearchParamsContext } from 'next/dist/shared/lib/hooks-client-context.shared-runtime'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { authApi } from '@/lib/api'
import ColslandPage from './page'
import ColslandLayout, { viewport } from './layout'
import platformMessages from '@/i18n/en/platform.json'

const router = { back: mock(() => {}), forward: mock(() => {}), refresh: mock(() => {}), push: mock(() => {}), replace: mock(() => {}), prefetch: mock(() => Promise.resolve()) }
let renderer: ReactTestRenderer | undefined

globalThis.IS_REACT_ACT_ENVIRONMENT = true

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  mock.restore()
  router.replace.mockClear()
  delete (globalThis as { localStorage?: Storage }).localStorage
})

describe('standalone Colsland page', () => {
  test('redirects unauthenticated visitors without displaying the page or robot', async () => {
    globalThis.localStorage = { getItem: () => null } as Storage
    await act(async () => {
      renderer = create(<NextIntlClientProvider locale="en" messages={platformMessages}><AppRouterContext.Provider value={router}><PathnameContext.Provider value="/colsland/project"><SearchParamsContext.Provider value={new URLSearchParams()}><ColslandPage /></SearchParamsContext.Provider></PathnameContext.Provider></AppRouterContext.Provider></NextIntlClientProvider>)
    })
    expect(router.replace).toHaveBeenCalledWith('/login?redirect=%2Fcolsland%2Fproject')
    expect(document.querySelector('main')).toBeNull()
    expect(document.querySelector('[data-testid="nav-colsland"]')).toBeNull()
  })

  test('renders the editor without the landing robot after authentication', async () => {
    globalThis.localStorage = { getItem: () => 'token' } as Storage
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({} as Awaited<ReturnType<typeof authApi.getCurrentUser>>)
    await act(async () => {
      renderer = create(<NextIntlClientProvider locale="en" messages={platformMessages}><AppRouterContext.Provider value={router}><PathnameContext.Provider value="/colsland/project"><SearchParamsContext.Provider value={new URLSearchParams()}><ColslandPage /></SearchParamsContext.Provider></PathnameContext.Provider></AppRouterContext.Provider></NextIntlClientProvider>)
      await Promise.resolve()
    })
    expect(document.querySelector('input[aria-label="Document title"]')).not.toBeNull()
    expect(document.querySelector('[data-testid="platform-header-nav"]')).toBeNull()
    expect(document.querySelector('[data-testid="nav-colsland"]')).toBeNull()
  })

  test('renders the layout and exports the viewport configuration', () => {
    expect(viewport.interactiveWidget).toBe('resizes-content')
    expect(ColslandLayout({ children: 'content' })).toBe('content')
  })
})
