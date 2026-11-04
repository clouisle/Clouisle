import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import { PathnameContext, SearchParamsContext } from 'next/dist/shared/lib/hooks-client-context.shared-runtime'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { authApi } from '@/lib/api'
import ColslandPage from './page'

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

describe('Colsland placeholder page', () => {
  test('keeps the route behind auth', async () => {
    globalThis.localStorage = { getItem: () => null } as Storage
    await act(async () => {
      renderer = create(
        <AppRouterContext.Provider value={router}>
          <PathnameContext.Provider value="/colsland">
            <SearchParamsContext.Provider value={new URLSearchParams()}>
              <ColslandPage />
            </SearchParamsContext.Provider>
          </PathnameContext.Provider>
        </AppRouterContext.Provider>,
      )
    })
    expect(router.replace).toHaveBeenCalledWith('/login?redirect=%2Fcolsland')
    expect(document.querySelector('main')).toBeNull()
  })

  test('renders an empty page after authentication', async () => {
    globalThis.localStorage = { getItem: () => 'token' } as Storage
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({} as Awaited<ReturnType<typeof authApi.getCurrentUser>>)
    await act(async () => {
      renderer = create(
        <AppRouterContext.Provider value={router}>
          <PathnameContext.Provider value="/colsland">
            <SearchParamsContext.Provider value={new URLSearchParams()}>
              <ColslandPage />
            </SearchParamsContext.Provider>
          </PathnameContext.Provider>
        </AppRouterContext.Provider>,
      )
      await Promise.resolve()
    })
    const main = document.querySelector('main')
    expect(main).not.toBeNull()
    expect(main?.childElementCount).toBe(0)
  })
})
