import { afterEach, beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  localStorage: window.localStorage,
  IS_REACT_ACT_ENVIRONMENT: true,
})

const push = mock(() => {})
const success = mock(() => {})
const error = mock(() => {})
const getCurrentUser = mock(async (): Promise<{ locale?: string }> => ({ locale: 'zh' }))
const updateProfile = mock(async () => {})
let searchParams = new URLSearchParams()

mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('@/lib/api', () => ({
  authApi: { getCurrentUser },
  usersApi: { updateProfile },
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))

let SSOCallbackPage: typeof import('./page').default
let root: Root | undefined

beforeAll(async () => {
  ({ default: SSOCallbackPage } = await import('./page'))
})

beforeEach(() => {
  searchParams = new URLSearchParams()
  localStorage.clear()
  for (const fn of [push, success, error, getCurrentUser, updateProfile]) fn.mockClear()
  getCurrentUser.mockImplementation(async () => ({ locale: 'zh' }))
  updateProfile.mockImplementation(async () => {})
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = undefined
  document.body.innerHTML = ''
})

async function render(params: string) {
  searchParams = new URLSearchParams(params)
  const container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  await act(async () => {
    root?.render(<SSOCallbackPage />)
  })
  return container
}

describe('SSO callback processing', () => {
  it('stores the fake token, syncs locale, and navigates to a safe redirect', async () => {
    const container = await render('token=fake-token&redirect=%2Fapp%2Fsettings')

    expect(container.textContent).toContain('ssoCallbackProcessing')
    expect(localStorage.getItem('access_token')).toBe('fake-token')
    expect(getCurrentUser).toHaveBeenCalledWith({ skipAuthRedirect: true })
    expect(updateProfile).toHaveBeenCalledWith(
      { locale: 'en' },
      { skipAuthRedirect: true },
    )
    expect(success).toHaveBeenCalledWith('loginSuccess')
    expect(push).toHaveBeenCalledWith('/app/settings')
    expect(error).not.toHaveBeenCalled()
  })

  it('uses the default app redirect and skips an unnecessary locale update', async () => {
    getCurrentUser.mockImplementation(async () => ({ locale: 'en' }))

    await render('token=another-fake-token')

    expect(updateProfile).not.toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/app')
  })

  it('keeps successful navigation when locale synchronization fails', async () => {
    getCurrentUser.mockImplementation(async () => {
      throw new Error('fake locale failure')
    })

    await render('token=fake-token&redirect=%2Fapp%2Fprojects')

    expect(success).toHaveBeenCalledWith('loginSuccess')
    expect(push).toHaveBeenCalledWith('/app/projects')
  })

  it('reports a missing token and returns to login without storing credentials', async () => {
    await render('redirect=%2Fapp%2Fsettings')

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(getCurrentUser).not.toHaveBeenCalled()
    expect(success).not.toHaveBeenCalled()
    expect(error).toHaveBeenCalledWith('loginFailed')
    expect(push).toHaveBeenCalledWith('/login')
  })

  it('shows a generic provider failure and navigates back without processing its token', async () => {
    const container = await render('error=provider_failure&token=ignored')

    expect(container.textContent).toContain('ssoCallbackFailedTitle')
    expect(container.textContent).toContain('ssoCallbackFailedDescription')
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(getCurrentUser).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()

    container.querySelector('button')?.click()
    expect(push).toHaveBeenCalledWith('/login')
  })
})
