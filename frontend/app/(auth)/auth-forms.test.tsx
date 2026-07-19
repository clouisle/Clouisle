import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import { SearchParamsContext } from 'next/dist/shared/lib/hooks-client-context.shared-runtime'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from 'react-test-renderer'
import { toast } from 'sonner'

import authMessages from '@/i18n/en/auth.json'
import { ApiError, authApi, siteSettingsApi, ssoApi } from '@/lib/api'
import { ForgotPasswordForm } from './forgot-password/_components/forgot-password-form'
import { LoginForm } from './login/_components/login-form'
import { RegisterForm } from './register/_components/register-form'
import { ResetPasswordByTokenForm } from './reset-password/_components/reset-password-by-token-form'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const originalDocument = globalThis.document
const documentStub = {
  addEventListener() {},
  removeEventListener() {},
  querySelectorAll: () => [],
  getElementById: () => null,
  createElement: () => ({ setAttribute() {}, remove() {}, sheet: null }),
  head: { appendChild() {} },
} as unknown as Document

const messages = authMessages.auth
const router = {
  back: mock(() => {}),
  forward: mock(() => {}),
  refresh: mock(() => {}),
  push: mock(() => {}),
  replace: mock(() => {}),
  prefetch: mock(() => Promise.resolve()),
}

function render(component: React.ReactNode, search = '') {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(
      <AppRouterContext.Provider value={router}>
        <SearchParamsContext.Provider value={new URLSearchParams(search)}>
          <NextIntlClientProvider locale="en" timeZone="UTC" messages={authMessages}>
            {component}
          </NextIntlClientProvider>
        </SearchParamsContext.Provider>
      </AppRouterContext.Provider>,
    )
  })
  return renderer!
}

const input = (root: ReactTestInstance, id: string) => root.findByProps({ id })
const change = (node: ReactTestInstance, value: string) => act(() => node.props.onChange({ target: { value } }))
const submit = async (root: ReactTestInstance) => {
  await act(async () => root.findByType('form').props.onSubmit({ preventDefault() {} }))
}
const clickButton = async (root: ReactTestInstance, label: string) => {
  const button = root.findAllByType('button').find(node => node.children.includes(label))!
  await act(async () => button.props.onClick({ preventDefault() {} }))
}
const otp = (root: ReactTestInstance) => root.find(node => node.props.maxLength === 6 && node.props.onChange)
const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())

beforeEach(() => {
  globalThis.document = documentStub
  Object.values(router).forEach(fn => fn.mockClear())
  const storage = new Map<string, string>()
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key),
  } as Storage
  spyOn(toast, 'success').mockImplementation(() => '')
})

afterEach(() => {
  mock.restore()
  delete (globalThis as { localStorage?: Storage }).localStorage
  if (originalDocument) globalThis.document = originalDocument
  else delete (globalThis as { document?: Document }).document
})

describe('auth forms', () => {
  test('logs in, stores the token, and honors the redirect query', async () => {
    spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
      enable_captcha: false,
      sso_enabled: false,
      sso_allow_password_login: true,
    } as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
    const login = spyOn(authApi, 'login').mockResolvedValue({ access_token: 'token' } as Awaited<ReturnType<typeof authApi.login>>)
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({ locale: 'en' } as Awaited<ReturnType<typeof authApi.getCurrentUser>>)

    const renderer = render(<LoginForm />, 'redirect=/app/kb')
    await act(async () => Promise.resolve())
    change(input(renderer.root, 'username'), 'alice')
    change(input(renderer.root, 'password'), 'secret')
    await submit(renderer.root)

    expect(login).toHaveBeenCalledWith(expect.objectContaining({ username: 'alice', password: 'secret' }))
    expect(localStorage.getItem('access_token')).toBe('token')
    expect(router.push).toHaveBeenCalledWith('/app/kb')
    act(() => renderer.unmount())
  })

  test('registers a valid first user and renders the activated state', async () => {
    spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
      enable_captcha: false,
      require_terms_acceptance_on_register: false,
    } as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
    const register = spyOn(authApi, 'register').mockResolvedValue({
      is_superuser: true,
      is_active: true,
      email_verified: true,
    } as Awaited<ReturnType<typeof authApi.register>>)

    const renderer = render(<RegisterForm />)
    await act(async () => Promise.resolve())
    change(input(renderer.root, 'username'), 'alice')
    change(input(renderer.root, 'email'), 'alice@example.com')
    change(input(renderer.root, 'password'), 'secret')
    change(input(renderer.root, 'confirmPassword'), 'secret')
    await submit(renderer.root)

    expect(register).toHaveBeenCalledWith(expect.objectContaining({
      username: 'alice', email: 'alice@example.com', password: 'secret', locale: 'en',
    }))
    expect(text(renderer)).toContain(messages.registrationComplete)
    expect(text(renderer)).toContain(messages.accountActivated)
    act(() => renderer.unmount())
  })

  test('rejects an invalid reset email before sending, then advances after a valid email', async () => {
    const forgotPassword = spyOn(authApi, 'forgotPassword').mockResolvedValue(undefined)
    const renderer = render(<ForgotPasswordForm />)

    change(input(renderer.root, 'email'), 'not-an-email')
    await submit(renderer.root)
    expect(forgotPassword).not.toHaveBeenCalled()
    expect(text(renderer)).toContain(messages.invalidEmail)

    change(input(renderer.root, 'email'), 'alice@example.com')
    await submit(renderer.root)
    expect(forgotPassword).toHaveBeenCalledWith('alice@example.com')
    expect(text(renderer)).toContain(messages.checkYourEmail)
    act(() => renderer.unmount())
  })

  test('renders SSO-only providers and starts SSO with the redirect', async () => {
    spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
      enable_captcha: false,
      sso_enabled: true,
      sso_allow_password_login: false,
    } as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
    spyOn(ssoApi, 'getPublicProviders').mockResolvedValue([{
      id: 'sso-1', name: 'oidc', display_name: 'Company SSO', button_text: 'Use Company SSO', icon_url: null,
    }] as Awaited<ReturnType<typeof ssoApi.getPublicProviders>>)
    const initiateLogin = spyOn(ssoApi, 'initiateLogin').mockImplementation(() => {})

    const renderer = render(<LoginForm />, 'redirect=/app/admin')
    await act(async () => Promise.resolve())

    expect(renderer.root.findAllByType('form')).toHaveLength(0)
    await clickButton(renderer.root, 'Use Company SSO')
    expect(initiateLogin).toHaveBeenCalledWith('oidc', '/app/admin')
    act(() => renderer.unmount())
  })

  test('requires and completes captcha before login', async () => {
    spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
      enable_captcha: true,
      sso_enabled: false,
      sso_allow_password_login: true,
    } as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
    spyOn(authApi, 'getCaptcha').mockResolvedValue({
      captcha_id: 'captcha-1', challenge: JSON.stringify({ type: 'click-choice', options: ['cat'], created_at: 1 }),
      prompt: 'Click', expires_in: 60,
    })
    const complete = spyOn(authApi, 'completeCaptchaClick').mockResolvedValue({ captcha_id: 'captcha-1', captcha_token: 'proof' })
    const login = spyOn(authApi, 'login').mockResolvedValue({ access_token: 'token' })
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({ locale: 'en' } as Awaited<ReturnType<typeof authApi.getCurrentUser>>)

    const renderer = render(<LoginForm />)
    await act(async () => Promise.resolve())
    change(input(renderer.root, 'username'), 'alice')
    change(input(renderer.root, 'password'), 'secret')
    await act(async () => Promise.resolve())
    await submit(renderer.root)
    expect(login).not.toHaveBeenCalled()
    expect(text(renderer)).toContain(messages.captchaRequired)

    await clickButton(renderer.root, messages.captchaClickPrompt)
    expect(complete).toHaveBeenCalledWith(expect.objectContaining({ captcha_id: 'captcha-1', clicked_option: 'cat' }))
    await submit(renderer.root)
    expect(login).toHaveBeenCalledWith(expect.objectContaining({ captcha_id: 'captcha-1', captcha_token: 'proof' }))
    act(() => renderer.unmount())
  })

  test('handles TOTP verification errors and accepts a backup code', async () => {
    spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
      enable_captcha: false, sso_enabled: false, sso_allow_password_login: true,
    } as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
    spyOn(authApi, 'login').mockResolvedValue({ requires_totp: true, temp_token: 'temporary', access_token: '' })
    const verifyTOTP = spyOn(authApi, 'verifyTOTP')
      .mockRejectedValueOnce(new ApiError(5312, 'limited', { seconds: 30 }))
      .mockResolvedValueOnce({ access_token: 'verified' })
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({ locale: 'en' } as Awaited<ReturnType<typeof authApi.getCurrentUser>>)

    const renderer = render(<LoginForm />)
    await act(async () => Promise.resolve())
    change(input(renderer.root, 'username'), 'alice')
    change(input(renderer.root, 'password'), 'secret')
    await submit(renderer.root)

    act(() => otp(renderer.root).props.onChange('123456'))
    await clickButton(renderer.root, messages.verifyCode)
    expect(text(renderer)).toContain('30')

    await clickButton(renderer.root, messages.useBackupCode)
    const backupInput = renderer.root.find(node => node.props.maxLength === 9)
    change(backupInput, 'ABCD-1234')
    await clickButton(renderer.root, messages.verifyCode)
    expect(verifyTOTP).toHaveBeenLastCalledWith('temporary', 'ABCD1234', true)
    expect(localStorage.getItem('access_token')).toBe('verified')
    expect(router.push).toHaveBeenCalledWith('/app')
    act(() => renderer.unmount())
  })

  test('requires registration terms and reports API validation errors', async () => {
    spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
      enable_captcha: false,
      require_terms_acceptance_on_register: true,
      terms_enabled: true,
      terms_url: '/terms',
      terms_text: '',
      privacy_enabled: false,
      privacy_url: '',
      privacy_text: '',
    } as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
    const register = spyOn(authApi, 'register').mockRejectedValue(
      new ApiError(1001, 'invalid', { errors: { username: ['invalidEmail'] } }),
    )

    const renderer = render(<RegisterForm />)
    await act(async () => Promise.resolve())
    change(input(renderer.root, 'username'), 'alice')
    change(input(renderer.root, 'email'), 'alice@example.com')
    change(input(renderer.root, 'password'), 'secret')
    change(input(renderer.root, 'confirmPassword'), 'secret')
    await submit(renderer.root)
    expect(register).not.toHaveBeenCalled()
    expect(text(renderer)).toContain(messages.termsAcceptanceRequired)

    act(() => renderer.root.findByProps({ id: 'termsAccepted' }).props.onCheckedChange(true))
    await submit(renderer.root)
    expect(register).toHaveBeenCalledWith(expect.objectContaining({ terms_accepted: true }))
    expect(text(renderer)).toContain(messages.invalidEmail)
    act(() => renderer.unmount())
  })

  test('validates and completes the manual forgot-password reset', async () => {
    spyOn(authApi, 'forgotPassword').mockResolvedValue(undefined)
    const resetPassword = spyOn(authApi, 'resetPassword')
      .mockRejectedValueOnce(new ApiError(5005, 'invalid code'))
      .mockResolvedValueOnce(undefined)
    const renderer = render(<ForgotPasswordForm />)

    change(input(renderer.root, 'email'), 'alice@example.com')
    await submit(renderer.root)
    await clickButton(renderer.root, messages.orEnterCodeManually)
    change(input(renderer.root, 'newPassword'), 'secret')
    change(input(renderer.root, 'confirmPassword'), 'different')
    await submit(renderer.root)
    expect(text(renderer)).toContain(messages.passwordMismatch)

    change(input(renderer.root, 'confirmPassword'), 'secret')
    act(() => otp(renderer.root).props.onChange('123456'))
    await submit(renderer.root)
    expect(text(renderer)).toContain(messages.verificationCodeInvalid)
    await submit(renderer.root)
    expect(resetPassword).toHaveBeenLastCalledWith('alice@example.com', '123456', 'secret')
    expect(text(renderer)).toContain(messages.passwordResetComplete)
    act(() => renderer.unmount())
  })

  test('validates matching token-reset passwords and routes after success', async () => {
    const resetPassword = spyOn(authApi, 'resetPasswordByToken').mockResolvedValue(undefined)
    const renderer = render(<ResetPasswordByTokenForm token="reset-token" />)

    change(input(renderer.root, 'newPassword'), 'secret')
    change(input(renderer.root, 'confirmPassword'), 'different')
    await submit(renderer.root)
    expect(resetPassword).not.toHaveBeenCalled()
    expect(text(renderer)).toContain(messages.passwordMismatch)

    change(input(renderer.root, 'confirmPassword'), 'secret')
    await submit(renderer.root)
    expect(resetPassword).toHaveBeenCalledWith('reset-token', 'secret')
    expect(text(renderer)).toContain(messages.passwordResetComplete)

    act(() => renderer.root.findByType('button').props.onClick())
    expect(router.push).toHaveBeenCalledWith('/login')
    act(() => renderer.unmount())
  })
})
