import { afterEach, beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  localStorage: window.localStorage,
  sessionStorage: window.sessionStorage,
  IS_REACT_ACT_ENVIRONMENT: true,
})

const push = mock(() => {})
const success = mock(() => {})
const error = mock(() => {})
const completeLink = mock(async () => {})
const toastError = mock(() => {})
let searchParams = new URLSearchParams()

mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => searchParams,
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success, error: toastError } }))
mock.module('@/lib/api/sso', () => ({
  ssoApi: { completeLink },
  ssoLinkState: {
    read: () => sessionStorage.getItem('sso_link_pending_session'),
    clear: () => sessionStorage.removeItem('sso_link_pending_session'),
  },
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardDescription: ({ children, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => <p {...props}>{children}</p>,
  CardHeader: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h2 {...props}>{children}</h2>,
}))

let SSOLinkCallbackPage: typeof import('./page').default
let root: Root | undefined

beforeAll(async () => {
  ({ default: SSOLinkCallbackPage } = await import('./page'))
})

beforeEach(() => {
  searchParams = new URLSearchParams()
  sessionStorage.clear()
  for (const fn of [push, success, error, completeLink, toastError]) fn.mockClear()
  completeLink.mockImplementation(async () => {})
})

afterEach(async () => {
  if (root) await act(async () => root?.unmount())
  root = undefined
  document.body.innerHTML = ''
})

async function render(params: string, pending: string | null = 'link-state') {
  searchParams = new URLSearchParams(params)
  if (pending) sessionStorage.setItem('sso_link_pending_session', pending)
  const container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  await act(async () => {
    root?.render(<SSOLinkCallbackPage />)
  })
  return container
}

async function clickText(container: HTMLElement, text: string) {
  const button = [...container.querySelectorAll('button')].find((node) => node.textContent?.includes(text))
  expect(button).toBeTruthy()
  await act(async () => button!.dispatchEvent(new window.MouseEvent('click', { bubbles: true })))
}

describe('SSO link callback', () => {
  it('completes the binding on explicit confirmation without touching the login token', async () => {
    localStorage.setItem('access_token', 'session-token')
    const container = await render('session_id=link-state')

    expect(container.textContent).toContain('ssoLinkCallbackConfirm')
    expect(completeLink).not.toHaveBeenCalled()

    await clickText(container, 'ssoLinkCallbackConfirm')

    expect(completeLink).toHaveBeenCalledWith('link-state')
    expect(sessionStorage.getItem('sso_link_pending_session')).toBeNull()
    expect(localStorage.getItem('access_token')).toBe('session-token')
    expect(container.textContent).toContain('ssoLinkCallbackSuccessTitle')

    await clickText(container, 'ssoLinkCallbackReturnToApp')
    expect(push).toHaveBeenCalledWith('/app')
  })

  it('blocks completion when the URL state does not match the stored pending state', async () => {
    const container = await render('session_id=attacker-state', 'link-state')

    expect(completeLink).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('sso_link_pending_session')).toBeNull()
    expect(container.textContent).toContain('ssoLinkCallbackInvalidTitle')
    expect(container.textContent).not.toContain('ssoLinkCallbackConfirm')
  })

  it('blocks completion when the pending state is missing entirely', async () => {
    const container = await render('session_id=link-state', null)

    expect(completeLink).not.toHaveBeenCalled()
    expect(container.textContent).toContain('ssoLinkCallbackInvalidTitle')
  })

  it('reports a backend rejection without completing', async () => {
    const container = await render('error=sso_session_expired')

    expect(completeLink).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('sso_link_pending_session')).toBeNull()
    expect(container.textContent).toContain('ssoLinkCallbackFailedTitle')
    expect(container.textContent).not.toContain('ssoLinkCallbackConfirm')
  })

  it('reports a failed completion and keeps the login token', async () => {
    localStorage.setItem('access_token', 'session-token')
    completeLink.mockRejectedValueOnce(new Error('already linked'))
    const container = await render('session_id=link-state')

    await clickText(container, 'ssoLinkCallbackConfirm')

    expect(toastError).toHaveBeenCalled()
    expect(container.textContent).toContain('ssoLinkCallbackFailedTitle')
    expect(localStorage.getItem('access_token')).toBe('session-token')
  })
})
