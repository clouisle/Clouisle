import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'https://example.test/totp-setup' })
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.localStorage = window.localStorage
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock<(path: string) => void>()
const getCurrentUser = mock<() => Promise<unknown>>()
const toastSuccess = mock<(message: string) => void>()
const toastError = mock<(message: string) => void>()

mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api', () => ({ authApi: { getCurrentUser } }))
mock.module('@/components/totp-setup-wizard-forced', () => ({
  TOTPSetupWizardForced: ({ tempToken, onComplete, onCancel }: {
    tempToken: string
    onComplete: () => void
    onCancel: () => void
  }) => (
    <div>
      <output aria-label="temporary token">{tempToken}</output>
      <button type="button" onClick={onComplete}>complete</button>
      <button type="button" onClick={onCancel}>cancel</button>
    </div>
  ),
}))

let container: HTMLDivElement
let root: Root

async function renderPage() {
  const { default: TOTPSetupPage } = await import('./page')
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(<TOTPSetupPage />))
}

async function click(text: string) {
  const button = [...container.querySelectorAll('button')].find((node) => node.textContent === text)
  expect(button).toBeTruthy()
  await act(async () => button!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

beforeEach(() => {
  localStorage.clear()
  push.mockReset()
  getCurrentUser.mockReset()
  toastSuccess.mockReset()
  toastError.mockReset()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('TOTPSetupPage issue #255 coverage', () => {
  test('rejects an expired setup session', async () => {
    await renderPage()

    expect(container.textContent).toBe('')
    expect(toastError).toHaveBeenCalledWith('sessionExpired')
    expect(push).toHaveBeenCalledWith('/login')
  })

  test('completes setup using only mocked APIs and redirects home', async () => {
    localStorage.setItem('temp_token', 'fake-temporary-token')
    getCurrentUser.mockResolvedValue({ id: 'fake-user' })
    await renderPage()

    expect(container.querySelector('[aria-label="temporary token"]')?.textContent).toBe('fake-temporary-token')
    await click('complete')

    expect(localStorage.getItem('temp_token')).toBeNull()
    expect(localStorage.getItem('access_token')).toBe('fake-temporary-token')
    expect(getCurrentUser).toHaveBeenCalledTimes(1)
    expect(toastSuccess).toHaveBeenCalledWith('setupStep5Description')
    expect(push).toHaveBeenCalledWith('/')
  })

  test('returns to login on cancellation or completion failure', async () => {
    localStorage.setItem('temp_token', 'fake-failing-token')
    getCurrentUser.mockRejectedValue(new Error('mocked failure'))
    await renderPage()

    await click('cancel')
    expect(push).toHaveBeenCalledWith('/login')

    push.mockClear()
    await click('complete')
    expect(toastError).toHaveBeenCalledWith('setupFailed')
    expect(push).toHaveBeenCalledWith('/login')
  })
})
