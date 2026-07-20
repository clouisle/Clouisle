import { afterEach, beforeAll, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLButtonElement: window.HTMLButtonElement,
  HTMLInputElement: window.HTMLInputElement,
  getComputedStyle: window.getComputedStyle,
  requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(callback, 0),
  cancelAnimationFrame: clearTimeout,
})

const dom = { window }
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const toast = { error: mock(() => {}), success: mock(() => {}) }

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h1>{children}</h1>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardContent: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}))
mock.module('@/components/ui/input-otp', () => ({
  InputOTP: ({ onChange }: { value: string, onChange: (value: string) => void }) => (
    <button onClick={() => onChange('123456')}>enter verification code</button>
  ),
  InputOTPGroup: () => null,
  InputOTPSlot: () => null,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))
mock.module('@/components/totp-qr-code', () => ({
  TOTPQRCode: ({ secret }: { secret: string }) => <div>QR: {secret}</div>,
}))
mock.module('lucide-react', () => ({
  Loader2: () => null,
  ShieldCheck: () => null,
  Download: () => null,
  Copy: () => null,
  Check: () => null,
  Info: () => null,
}))

let TOTPSetupWizardForced: typeof import('./totp-setup-wizard-forced').TOTPSetupWizardForced

beforeAll(async () => {
  ;({ TOTPSetupWizardForced } = await import('./totp-setup-wizard-forced'))
})

const roots: Root[] = []

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  toast.error.mockClear()
  toast.success.mockClear()
  mock.restore()
})

function render() {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(<TOTPSetupWizardForced tempToken="temporary-token" onComplete={() => {}} onCancel={() => {}} />))
  return container
}

async function click(button: Element) {
  await act(async () => {
    button.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

describe('TOTPSetupWizardForced', () => {
  it('starts setup and enables TOTP with the temporary token', async () => {
    const fetch = mock(async (url: string, options: RequestInit) => {
      if (url.endsWith('/setup')) {
        expect(options).toMatchObject({ method: 'POST', headers: { Authorization: 'Bearer temporary-token' } })
        return new Response(JSON.stringify({ data: { secret: 'SECRET', qr_code: 'qr', backup_codes: ['one'] } }), { status: 200 })
      }
      expect(url).toEndWith('/enable')
      expect(options).toMatchObject({ method: 'POST', body: JSON.stringify({ code: '123456' }) })
      return new Response(JSON.stringify({ data: null }), { status: 200 })
    })
    globalThis.fetch = fetch as typeof globalThis.fetch
    const container = render()

    await click(container.querySelector('button')!)
    expect(container.textContent).toContain('QR: SECRET')
    await click(container.querySelector('button')!)
    await click(Array.from(container.querySelectorAll('button')).find((button) => button.textContent === 'enter verification code')!)
    await click(Array.from(container.querySelectorAll('button')).find((button) => button.textContent === 'verifyCode')!)

    expect(fetch).toHaveBeenCalledTimes(2)
    expect(toast.success).toHaveBeenCalledWith('twoFactorEnabledSuccess')
    expect(container.textContent).toContain('setupStep4Title')
  })

  it('reports a failed setup request', async () => {
    globalThis.fetch = mock(async () => new Response(JSON.stringify({ msg: 'denied' }), { status: 403 })) as typeof globalThis.fetch
    const container = render()

    await click(container.querySelector('button')!)

    expect(toast.error).toHaveBeenCalledWith('setupFailed')
    expect(container.textContent).toContain('setupStep1Title')
  })
})
