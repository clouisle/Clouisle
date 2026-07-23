import { describe, expect, it, mock } from 'bun:test'

mock.module('next/navigation', () => ({
  useRouter: () => ({ push: mock() }),
  useSearchParams: () => new URLSearchParams(),
}))

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => `auth.${key}`,
}))

mock.module('sonner', () => ({ toast: { error: mock(), info: mock(), success: mock() } }))
mock.module('@/components/ui/button', () => ({ Button: 'button' }))
mock.module('@/components/ui/card', () => ({ Card: 'div', CardContent: 'div', CardHeader: 'div', CardTitle: 'h2' }))
mock.module('@/components/totp-setup-wizard-forced', () => ({ TOTPSetupWizardForced: 'div' }))

const t = (key: string) => `auth.${key}`

describe('auth form helper coverage', () => {
  it('accepts only valid click captcha challenges for login and registration', async () => {
    const [{ parseClickChallenge: parseLoginClickChallenge }, { parseClickChallenge: parseRegisterClickChallenge }] = await Promise.all([
      import('./login/_components/login-form'),
      import('./register/_components/register-form'),
    ])
    const challenge = JSON.stringify({ type: 'click-choice', options: ['mock-option'], created_at: 123 })

    expect(parseLoginClickChallenge(challenge)).toEqual({ type: 'click-choice', options: ['mock-option'], created_at: 123 })
    expect(parseRegisterClickChallenge(challenge)).toEqual({ type: 'click-choice', options: ['mock-option'], created_at: 123 })
    expect(parseLoginClickChallenge('not-json')).toBeNull()
    expect(parseRegisterClickChallenge(JSON.stringify({ type: 'text', options: ['mock-option'], created_at: 123 }))).toBeNull()
  })

  it('parses register validation keys with field-specific params', async () => {
    const { parseErrorKey } = await import('./register/_components/register-form')

    expect(parseErrorKey('password_min_length:12')).toEqual({ key: 'password_min_length', params: { length: '12' } })
    expect(parseErrorKey('username_taken:demo-user')).toEqual({ key: 'username_taken', params: { value: 'demo-user' } })
    expect(parseErrorKey('email_required')).toEqual({ key: 'email_required', params: {} })
  })

  it('returns forgot-password email validation messages before API calls', async () => {
    const { getForgotPasswordEmailError } = await import('./forgot-password/_components/forgot-password-form')

    expect(getForgotPasswordEmailError('', t)).toBe('auth.emailRequired')
    expect(getForgotPasswordEmailError('invalid-email', t)).toBe('auth.invalidEmail')
    expect(getForgotPasswordEmailError('user@example.test', t)).toBeNull()
  })
})

describe('auth page decision coverage', () => {
  it('classifies inactive SSO callback errors and keeps redirect defaults predictable', async () => {
    const { getSsoCallbackRedirect, isInactiveSsoCallbackError } = await import('./sso-callback/page')

    expect(isInactiveSsoCallbackError('inactive')).toBe(true)
    expect(isInactiveSsoCallbackError('pending_approval')).toBe(true)
    expect(isInactiveSsoCallbackError('provider_failed')).toBe(false)
    expect(getSsoCallbackRedirect(null)).toBe('/app')
    expect(getSsoCallbackRedirect('/app?demo=1')).toBe('/app?demo=1')
  })

  it('routes TOTP setup outcomes without exposing temp tokens', async () => {
    const { getTotpSetupRedirect } = await import('./totp-setup/page')

    expect(getTotpSetupRedirect(false, false)).toBe('/login')
    expect(getTotpSetupRedirect(true, true)).toBe('/')
    expect(getTotpSetupRedirect(true, false)).toBe('/login')
  })

  it('uses API verification messages and falls back for unknown failures', async () => {
    const [{ ApiError }, { getVerifyEmailErrorMessage }] = await Promise.all([
      import('@/lib/api/client'),
      import('./verify/page'),
    ])

    expect(getVerifyEmailErrorMessage(new ApiError(5005, 'expired demo token'), t)).toBe('expired demo token')
    expect(getVerifyEmailErrorMessage(new ApiError(5005, ''), t)).toBe('auth.verificationTokenInvalid')
    expect(getVerifyEmailErrorMessage(new Error('network'), t)).toBe('auth.verificationTokenInvalid')
  })
})
