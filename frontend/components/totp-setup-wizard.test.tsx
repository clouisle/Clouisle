import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { act } from 'react'

const window = new Window()
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.Event = window.Event as unknown as typeof Event
globalThis.Blob = window.Blob as unknown as typeof Blob
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const setup = mock<() => Promise<unknown>>()
const enable = mock<(code: string) => Promise<void>>()
const toastSuccess = mock<(message: string) => void>()

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('sonner', () => ({
  toast: { success: toastSuccess },
}))

mock.module('@/lib/api/users', () => ({
  totpApi: { setup, enable },
}))

mock.module('./totp-qr-code', () => ({
  TOTPQRCode: ({ qrCode }: { secret: string; qrCode: string }) => <div data-testid="qr">{qrCode}</div>,
}))

mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))

mock.module('@/components/ui/input-otp', () => ({
  InputOTP: ({ value, onChange, children }: { value: string; onChange: (value: string) => void; children: React.ReactNode }) => (
    <div>
      <output aria-label="otp">{value}</output>
      <button type="button" onClick={() => onChange('12345')}>enter-short-code</button>
      <button type="button" onClick={() => onChange('123456')}>enter-code</button>
      <button type="button" onClick={() => onChange('654321')}>enter-second-code</button>
      {children}
    </div>
  ),
  InputOTPGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  InputOTPSlot: () => <span />,
}))

mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div role="alert">{children}</div>,
  AlertDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

const setupData = {
  secret: 'FAKE-TEST-SECRET',
  qr_code: 'otpauth://totp/fake-test',
  backup_codes: ['FAKE-BACKUP-1', 'FAKE-BACKUP-2'],
}

let container: HTMLDivElement
let root: Root

async function render(ui: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(ui))
}

async function click(text: string) {
  const button = [...container.querySelectorAll('button')].find((node) => node.textContent === text)
  expect(button).toBeTruthy()
  await act(async () => button!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  return button as HTMLButtonElement
}

async function typeOtp(value: string) {
  await click(value === '12345' ? 'enter-short-code' : value === '123456' ? 'enter-code' : 'enter-second-code')
}

beforeEach(() => {
  setup.mockReset()
  enable.mockReset()
  toastSuccess.mockReset()
  setup.mockResolvedValue(setupData)
  enable.mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: mock(() => Promise.resolve()) } })
  URL.createObjectURL = mock(() => 'blob:fake-codes') as typeof URL.createObjectURL
  URL.revokeObjectURL = mock(() => undefined) as typeof URL.revokeObjectURL
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('TOTPSetupWizard', () => {
  test('resets dialog state and blocks incomplete verification', async () => {
    const onOpenChange = mock<(open: boolean) => void>()
    const { TOTPSetupWizard } = await import('./totp-setup-wizard')

    await render(<TOTPSetupWizard open onOpenChange={onOpenChange} />)
    expect(container.textContent).toContain('Step 1 of 5')

    await click('setupStepNext')
    expect(setup).toHaveBeenCalledTimes(1)
    expect(container.textContent).toContain('Step 2 of 5')
    expect(container.textContent).not.toContain(setupData.secret)

    await click('setupStepNext')
    const verify = [...container.querySelectorAll('button')].find((node) => node.textContent === 'verifyCode') as HTMLButtonElement
    expect(verify.disabled).toBe(true)

    await typeOtp('12345')
    expect(verify.disabled).toBe(true)
    expect(enable).not.toHaveBeenCalled()
  })

  test('cleans verification input after API error and enables backup code actions after success', async () => {
    enable.mockRejectedValueOnce(new Error('bad code'))
    const { TOTPSetupWizard } = await import('./totp-setup-wizard')

    await render(<TOTPSetupWizard open onOpenChange={mock()} />)
    await click('setupStepNext')
    await click('setupStepNext')

    await typeOtp('123456')
    await click('verifyCode')
    expect(enable).toHaveBeenCalledWith('123456')
    expect(container.querySelector('[aria-label="otp"]')?.textContent).toBe('')

    await typeOtp('654321')
    await click('verifyCode')
    expect(container.textContent).toContain('FAKE-BACKUP-1')
    expect(container.textContent).toContain('FAKE-BACKUP-2')

    await click('setupStep4Copy')
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('FAKE-BACKUP-1\nFAKE-BACKUP-2')

    await click('setupStep4Download')
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake-codes')
  })

  test('closes and calls success only from finish step', async () => {
    const onOpenChange = mock<(open: boolean) => void>()
    const onSuccess = mock<() => void>()
    const { TOTPSetupWizard } = await import('./totp-setup-wizard')

    await render(<TOTPSetupWizard open onOpenChange={onOpenChange} onSuccess={onSuccess} />)
    await click('setupStepNext')
    await click('setupStepNext')
    await typeOtp('654321')
    await click('verifyCode')
    await click('setupStepNext')
    await click('setupStepFinish')

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })
})
