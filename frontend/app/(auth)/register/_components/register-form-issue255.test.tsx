import { Window } from 'happy-dom'
import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window()
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.Event = window.Event as unknown as typeof Event
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock<(path: string) => void>()
const register = mock<(data: Record<string, unknown>) => Promise<Record<string, unknown>>>()
const sendVerification = mock<() => Promise<void>>()
const verifyEmail = mock<() => Promise<void>>()
const resendVerification = mock<() => Promise<void>>()
const getCaptcha = mock<() => Promise<Record<string, unknown>>>()
const completeCaptchaClick = mock<() => Promise<{ captcha_token: string }>>()
const getPublic = mock<() => Promise<Record<string, unknown>>>()
const toastSuccess = mock<(message: string) => void>()

class ApiError extends Error {
  constructor(public code: number) {
    super(String(code))
  }
}

mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values?.seconds === undefined ? key : `${key}:${values.seconds}`,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('lucide-react', () => ({ Loader2: () => null, Mail: () => null, CheckCircle2: () => null, ArrowLeft: () => null, ChevronDown: () => null }))
mock.module('@/lib/api', () => ({
  authApi: { register, sendVerification, verifyEmail, resendVerification, getCaptcha, completeCaptchaClick },
  siteSettingsApi: { getPublic },
  ApiError,
}))
mock.module('@/lib/utils', () => ({ isValidEmail: (value: string) => value.includes('@') }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrorsRaw: (error: unknown) => error instanceof ApiError ? {} : (error as { errors?: Record<string, string[]> }).errors || {},
}))
mock.module('@/components/ui/input', () => ({ Input: ({ onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} onInput={(event) => onChange?.(event as unknown as React.ChangeEvent<HTMLInputElement>)} /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ onCheckedChange, ...props }: { onCheckedChange: (checked: boolean) => void } & React.InputHTMLAttributes<HTMLInputElement>) => <input type="checkbox" {...props} onChange={(event) => onCheckedChange(event.target.checked)} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: { children?: React.ReactNode }) => children ? <p>{children}</p> : null }))
mock.module('@/components/ui/input-otp', () => ({
  InputOTP: ({ value, onChange, children }: { value: string; onChange: (value: string) => void; children: React.ReactNode }) => <div><output>{value}</output><button type="button" onClick={() => onChange('123456')}>enter-code</button>{children}</div>,
  InputOTPGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  InputOTPSlot: () => <span />,
}))
mock.module('@/components/ui/dialog', () => ({ Dialog: ({ children }: { children: React.ReactNode }) => <>{children}</>, DialogTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button> }))
mock.module('../../_components/legal-markdown', () => ({ LegalMarkdownDialogContent: () => null }))

const { RegisterForm } = await import('./register-form')
let container: HTMLDivElement
let root: Root

async function render() {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => root.render(<RegisterForm />))
}

async function click(text: string) {
  const button = [...container.querySelectorAll('button')].find((node) => node.textContent === text)
  expect(button).toBeTruthy()
  await act(async () => button!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

async function input(id: string, value: string) {
  const node = container.querySelector(`#${id}`) as HTMLInputElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(node, value)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function submit() {
  await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
}

async function fillValidForm() {
  await input('username', 'fake-user')
  await input('email', 'fake@example.test')
  await input('password', 'secret1')
  await input('confirmPassword', 'secret1')
}

beforeEach(() => {
  for (const fn of [push, register, sendVerification, verifyEmail, resendVerification, getCaptcha, completeCaptchaClick, getPublic, toastSuccess]) fn.mockReset()
  getPublic.mockResolvedValue({ enable_captcha: false, require_terms_acceptance_on_register: false })
  register.mockResolvedValue({ is_superuser: false, email_verified: true, is_active: true })
  sendVerification.mockResolvedValue(undefined)
  verifyEmail.mockResolvedValue(undefined)
  resendVerification.mockResolvedValue(undefined)
  getCaptcha.mockResolvedValue({ captcha_id: 'fake-captcha', challenge: JSON.stringify({ type: 'click-choice', options: ['fake-choice'], created_at: 1 }) })
  completeCaptchaClick.mockResolvedValue({ captcha_token: 'fake-token' })
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

test('validates fields and submits the successful registration callback', async () => {
  await render()
  await submit()
  expect(container.textContent).toContain('invalidEmail')

  await input('email', 'fake@example.test')
  await input('password', 'secret1')
  await input('confirmPassword', 'different')
  await submit()
  expect(container.textContent).toContain('passwordMismatch')

  await input('confirmPassword', 'short')
  await input('password', 'short')
  await submit()
  expect(container.textContent).toContain('passwordTooShort')

  await fillValidForm()
  await submit()
  expect(register).toHaveBeenCalledWith({ username: 'fake-user', email: 'fake@example.test', password: 'secret1', terms_accepted: undefined, captcha_id: undefined, captcha_token: undefined, locale: 'en' })
  expect(container.textContent).toContain('registrationComplete')
  await click('goToLogin')
  expect(push).toHaveBeenCalledWith('/login')
})

test('covers terms, translated API validation, and captcha callbacks', async () => {
  getPublic.mockResolvedValue({ enable_captcha: true, require_terms_acceptance_on_register: true, terms_enabled: true, terms_url: 'https://example.test/terms', terms_text: '', privacy_enabled: true, privacy_url: '', privacy_text: 'fake privacy' })
  await render()
  await fillValidForm()
  await submit()
  expect(container.textContent).toContain('termsAcceptanceRequired')

  const terms = container.querySelector('#termsAccepted') as HTMLInputElement
  await act(async () => terms.click())
  await act(async () => {})
  expect(getCaptcha).toHaveBeenCalledTimes(1)

  const captchaButton = [...container.querySelectorAll('button')].find((node) => node.textContent === 'captchaClickPrompt')!
  Object.defineProperty(captchaButton, 'getBoundingClientRect', { value: () => ({ left: 0, top: 0, width: 200, height: 80 }) })
  await act(async () => captchaButton.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
  await act(async () => captchaButton.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 50, clientY: 20 })))
  expect(completeCaptchaClick).toHaveBeenCalledWith(expect.objectContaining({ captcha_id: 'fake-captcha', clicked_option: 'fake-choice' }))

  register.mockRejectedValueOnce({ errors: { password: ['password_min_length:8'], username: ['custom:fake'] } })
  await submit()
  expect(container.textContent).toContain('password_min_length')
  expect(container.textContent).toContain('custom')
})

test('runs verification, resend, back, and failed verification callbacks', async () => {
  register.mockResolvedValue({ is_superuser: false, email_verified: false, is_active: false })
  await render()
  await fillValidForm()
  await submit()
  expect(sendVerification).toHaveBeenCalled()
  expect(container.textContent).toContain('verifyYourEmail')

  await click('orEnterCodeManually')
  await click('enter-code')
  verifyEmail.mockRejectedValueOnce(new ApiError(400))
  await click('verifyEmail')
  expect(container.textContent).toContain('verificationCodeInvalid')

  await click('verifyEmail')
  expect(container.textContent).toContain('registrationComplete')
})

test('handles failed verification email delivery and allows resend and back', async () => {
  register.mockResolvedValue({ is_superuser: false, email_verified: false, is_active: false })
  sendVerification.mockRejectedValueOnce(new Error('fake smtp failure'))
  await render()
  await fillValidForm()
  await submit()
  expect(container.textContent).toContain('resendEmail')

  await click('resendEmail')
  expect(resendVerification).toHaveBeenCalledWith('fake@example.test')
  expect(toastSuccess).toHaveBeenCalledWith('verificationEmailSent')

  await click('backToRegister')
  expect(container.querySelector('form')).toBeTruthy()
})
