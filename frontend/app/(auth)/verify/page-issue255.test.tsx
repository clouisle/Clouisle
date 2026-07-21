import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window()
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock<(path: string) => void>()
const verifyEmailByToken = mock<(token: string) => Promise<unknown>>()
let token: string | null = null

mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: () => token }),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/lib/api', () => ({
  authApi: { verifyEmailByToken },
  ApiError: class ApiError extends Error {},
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h1>{children}</h1>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))

let container: HTMLDivElement
let root: Root

async function renderPage() {
  const { default: VerifyPage } = await import('./page')
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(<VerifyPage />))
}

async function clickLogin() {
  const button = container.querySelector('button')
  expect(button).toBeTruthy()
  await act(async () => button!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

beforeEach(() => {
  token = null
  push.mockReset()
  verifyEmailByToken.mockReset()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('VerifyPage issue #255 coverage', () => {
  test('reports a missing token and returns to login', async () => {
    await renderPage()

    expect(container.textContent).toContain('verificationTokenMissing')
    expect(verifyEmailByToken).not.toHaveBeenCalled()
    await clickLogin()
    expect(push).toHaveBeenCalledWith('/login')
  })

  test('verifies the opaque token and shows success', async () => {
    token = 'fake-verification-token'
    verifyEmailByToken.mockResolvedValue({ verified: true })

    await renderPage()

    expect(verifyEmailByToken).toHaveBeenCalledWith('fake-verification-token')
    expect(container.textContent).toContain('emailVerifiedSuccess')
    await clickLogin()
    expect(push).toHaveBeenCalledWith('/login')
  })

  test('shows the generic message when verification fails', async () => {
    token = 'fake-expired-token'
    verifyEmailByToken.mockRejectedValue(new Error('network failure'))

    await renderPage()

    expect(container.textContent).toContain('verificationTokenInvalid')
  })
})
