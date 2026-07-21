import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { AppRouterContext } from 'next/dist/shared/lib/app-router-context.shared-runtime'
import { SearchParamsContext } from 'next/dist/shared/lib/hooks-client-context.shared-runtime'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from 'react-test-renderer'
import { toast } from 'sonner'

import authMessages from '@/i18n/en/auth.json'
import { ApiError, authApi, siteSettingsApi, ssoApi } from '@/lib/api'
import { LoginForm } from './login-form'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const originalDocument = globalThis.document
const documentStub = {
  addEventListener() {}, removeEventListener() {}, querySelectorAll: () => [], getElementById: () => null,
  createElement: () => ({ setAttribute() {}, remove() {}, sheet: null }), head: { appendChild() {} },
} as unknown as Document
const messages = authMessages.auth
const router = {
  back: mock(() => {}), forward: mock(() => {}), refresh: mock(() => {}), push: mock(() => {}),
  replace: mock(() => {}), prefetch: mock(() => Promise.resolve()),
}

function render(search = '') {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(
      <AppRouterContext.Provider value={router}>
        <SearchParamsContext.Provider value={new URLSearchParams(search)}>
          <NextIntlClientProvider locale="en" timeZone="UTC" messages={authMessages}>
            <LoginForm />
          </NextIntlClientProvider>
        </SearchParamsContext.Provider>
      </AppRouterContext.Provider>,
    )
  })
  return renderer!
}
const input = (root: ReactTestInstance, id: string) => root.findByProps({ id })
const change = (node: ReactTestInstance, value: string) => act(() => node.props.onChange({ target: { value } }))
const submit = async (root: ReactTestInstance) => act(async () => root.findByType('form').props.onSubmit({ preventDefault() {} }))
const button = (root: ReactTestInstance, label: string) => root.findAllByType('button').find(node => node.children.includes(label))!
const click = async (root: ReactTestInstance, label: string) => act(async () => button(root, label).props.onClick({ preventDefault() {} }))
const otp = (root: ReactTestInstance) => root.find(node => node.props.maxLength === 6 && node.props.onChange)
const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())
const settings = (overrides = {}) => spyOn(siteSettingsApi, 'getPublic').mockResolvedValue({
  enable_captcha: false, sso_enabled: false, sso_allow_password_login: true, ...overrides,
} as Awaited<ReturnType<typeof siteSettingsApi.getPublic>>)
const credentials = (renderer: ReactTestRenderer) => {
  change(input(renderer.root, 'username'), 'alice')
  change(input(renderer.root, 'password'), 'secret-password')
}

beforeEach(() => {
  globalThis.document = documentStub
  Object.values(router).forEach(fn => fn.mockClear())
  const storage = new Map<string, string>()
  globalThis.localStorage = {
    getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value),
    removeItem: key => storage.delete(key), clear: () => storage.clear(), key: () => null, get length() { return storage.size },
  } as Storage
  spyOn(toast, 'success').mockImplementation(() => '')
  spyOn(toast, 'info').mockImplementation(() => '')
})

afterEach(() => {
  mock.restore()
  delete (globalThis as { localStorage?: Storage }).localStorage
  if (originalDocument) globalThis.document = originalDocument
  else delete (globalThis as { document?: Document }).document
})

describe('LoginForm', () => {
  test('logs in without exposing credentials and honors a safe redirect', async () => {
    settings()
    const login = spyOn(authApi, 'login').mockResolvedValue({ access_token: 'access-token' } as Awaited<ReturnType<typeof authApi.login>>)
    spyOn(authApi, 'getCurrentUser').mockRejectedValue(new Error('profile unavailable'))
    const renderer = render('redirect=/app/kb')
    await act(async () => Promise.resolve())
    credentials(renderer)
    await submit(renderer.root)

    expect(login).toHaveBeenCalledWith(expect.objectContaining({ username: 'alice', password: 'secret-password' }))
    expect(localStorage.getItem('access_token')).toBe('access-token')
    expect(router.push).toHaveBeenCalledWith('/app/kb')
    act(() => renderer.unmount())
  })

  test('renders only field-safe API validation and recovers after edits', async () => {
    settings()
    spyOn(authApi, 'login')
      .mockRejectedValueOnce(new ApiError(1001, 'raw server secret', { errors: { username: ['Unknown account'], password: ['Invalid password'] } }))
      .mockResolvedValueOnce({ access_token: 'recovered' } as Awaited<ReturnType<typeof authApi.login>>)
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({ locale: 'en' } as Awaited<ReturnType<typeof authApi.getCurrentUser>>)
    const renderer = render()
    await act(async () => Promise.resolve())
    credentials(renderer)
    await submit(renderer.root)

    expect(text(renderer)).toContain('Unknown account')
    expect(text(renderer)).toContain('Invalid password')
    expect(text(renderer)).not.toContain('raw server secret')
    expect(input(renderer.root, 'username').props['aria-invalid']).toBe(true)
    change(input(renderer.root, 'username'), 'bob')
    change(input(renderer.root, 'password'), 'new-password')
    expect(input(renderer.root, 'username').props['aria-invalid']).toBe(false)
    expect(input(renderer.root, 'password').props['aria-invalid']).toBe(false)
    await submit(renderer.root)
    expect(localStorage.getItem('access_token')).toBe('recovered')
    act(() => renderer.unmount())
  })

  test('requires a valid CAPTCHA proof and remains retryable after failure', async () => {
    settings({ enable_captcha: true })
    const challenge = JSON.stringify({ type: 'click-choice', options: ['cat'], created_at: 1 })
    const getCaptcha = spyOn(authApi, 'getCaptcha')
      .mockResolvedValueOnce({ captcha_id: 'captcha-1', challenge, prompt: 'Click', expires_in: 60 })
      .mockResolvedValueOnce({ captcha_id: 'captcha-2', challenge, prompt: 'Retry', expires_in: 60 })
    const complete = spyOn(authApi, 'completeCaptchaClick')
      .mockRejectedValueOnce(new Error('proof rejected'))
      .mockResolvedValueOnce({ captcha_id: 'captcha-2', captcha_token: 'proof' })
    const login = spyOn(authApi, 'login').mockResolvedValue({ access_token: 'token' })
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({ locale: 'en' } as Awaited<ReturnType<typeof authApi.getCurrentUser>>)
    const renderer = render()
    await act(async () => Promise.resolve())
    credentials(renderer)
    await act(async () => Promise.resolve())

    await submit(renderer.root)
    expect(login).not.toHaveBeenCalled()
    expect(text(renderer)).toContain(messages.captchaRequired)
    await click(renderer.root, messages.captchaClickPrompt)
    expect(getCaptcha).toHaveBeenCalledTimes(2)
    expect(button(renderer.root, messages.captchaClickPrompt).props.disabled).toBe(false)
    await click(renderer.root, messages.captchaClickPrompt)
    await submit(renderer.root)
    expect(complete).toHaveBeenLastCalledWith(expect.objectContaining({ captcha_id: 'captcha-2', clicked_option: 'cat' }))
    expect(login).toHaveBeenCalledWith(expect.objectContaining({ captcha_id: 'captcha-2', captcha_token: 'proof' }))
    act(() => renderer.unmount())
  })

  test('enforces SSO-only mode and forwards the requested redirect', async () => {
    settings({ sso_enabled: true, sso_allow_password_login: false })
    spyOn(ssoApi, 'getPublicProviders').mockResolvedValue([{
      id: 'sso-1', name: 'oidc', display_name: 'Company SSO', button_text: 'Use Company SSO', icon_url: null,
    }] as Awaited<ReturnType<typeof ssoApi.getPublicProviders>>)
    const initiateLogin = spyOn(ssoApi, 'initiateLogin').mockImplementation(() => {})
    const renderer = render('redirect=/app/admin')
    await act(async () => Promise.resolve())

    expect(renderer.root.findAllByType('form')).toHaveLength(0)
    await click(renderer.root, 'Use Company SSO')
    expect(initiateLogin).toHaveBeenCalledWith('oidc', '/app/admin')
    act(() => renderer.unmount())
  })

  test('requires complete MFA codes, handles rate limits, and accepts a backup code', async () => {
    settings()
    spyOn(authApi, 'login').mockResolvedValue({ requires_totp: true, temp_token: 'temporary', access_token: '' })
    const verifyTOTP = spyOn(authApi, 'verifyTOTP')
      .mockRejectedValueOnce(new ApiError(5312, 'limited', { seconds: 30 }))
      .mockResolvedValueOnce({ access_token: 'verified' })
    spyOn(authApi, 'getCurrentUser').mockResolvedValue({ locale: 'en' } as Awaited<ReturnType<typeof authApi.getCurrentUser>>)
    const renderer = render()
    await act(async () => Promise.resolve())
    credentials(renderer)
    await submit(renderer.root)

    act(() => otp(renderer.root).props.onChange('12345'))
    expect(button(renderer.root, messages.verifyCode).props.disabled).toBe(true)
    act(() => otp(renderer.root).props.onChange('123456'))
    await click(renderer.root, messages.verifyCode)
    expect(text(renderer)).toContain('30')
    expect(otp(renderer.root).props.value).toBe('')

    await click(renderer.root, messages.useBackupCode)
    const backup = renderer.root.find(node => node.props.maxLength === 9)
    change(backup, 'ABCD-1234')
    await click(renderer.root, messages.verifyCode)
    expect(verifyTOTP).toHaveBeenLastCalledWith('temporary', 'ABCD1234', true)
    expect(localStorage.getItem('access_token')).toBe('verified')
    act(() => renderer.unmount())
  })

  test('routes TOTP setup and forced password changes without bypassing either control', async () => {
    settings()
    const login = spyOn(authApi, 'login')
      .mockResolvedValueOnce({ requires_totp_setup: true, temp_token: 'setup-token', access_token: '' })
      .mockResolvedValueOnce({ access_token: 'limited-token', force_password_change: true, reason: 'expired' })
    let renderer = render()
    await act(async () => Promise.resolve())
    credentials(renderer)
    await submit(renderer.root)
    expect(localStorage.getItem('temp_token')).toBe('setup-token')
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(router.push).toHaveBeenLastCalledWith('/totp-setup')
    act(() => renderer.unmount())

    renderer = render()
    await act(async () => Promise.resolve())
    credentials(renderer)
    await submit(renderer.root)
    expect(login).toHaveBeenCalledTimes(2)
    expect(localStorage.getItem('access_token')).toBe('limited-token')
    expect(router.push).toHaveBeenLastCalledWith('/change-password?reason=expired')
    act(() => renderer.unmount())
  })

  test('enters email recovery on an unverified account and validates the manual code', async () => {
    settings()
    spyOn(authApi, 'login').mockRejectedValue(new ApiError(5004, 'unverified', { email: 'alice@example.com' }))
    const send = spyOn(authApi, 'sendVerification').mockRejectedValueOnce(new Error('mail unavailable')).mockResolvedValueOnce(undefined)
    const verify = spyOn(authApi, 'verifyEmail')
      .mockRejectedValueOnce(new ApiError(5005, 'raw invalid response'))
      .mockResolvedValueOnce(undefined)
    const renderer = render()
    await act(async () => Promise.resolve())
    credentials(renderer)
    await submit(renderer.root)

    expect(text(renderer)).toContain('alice@example.com')
    expect(text(renderer)).not.toContain('raw invalid response')
    await click(renderer.root, messages.orEnterCodeManually)
    act(() => otp(renderer.root).props.onChange('12345'))
    expect(button(renderer.root, messages.verifyEmail).props.disabled).toBe(true)
    act(() => otp(renderer.root).props.onChange('123456'))
    await click(renderer.root, messages.verifyEmail)
    expect(verify).toHaveBeenCalledWith('alice@example.com', '123456', 'register')
    expect(text(renderer)).toContain(messages.verificationCodeInvalid)
    act(() => otp(renderer.root).props.onChange('654321'))
    expect(text(renderer)).not.toContain(messages.verificationCodeInvalid)
    await click(renderer.root, messages.verifyEmail)
    expect(text(renderer)).toContain(messages.login)
    expect(send).toHaveBeenCalledWith('alice@example.com', 'register')
    act(() => renderer.unmount())
  })
})
