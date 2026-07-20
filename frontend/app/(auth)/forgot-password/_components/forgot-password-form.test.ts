import { describe, expect, mock, test } from 'bun:test'
import { ApiError } from '@/lib/api'
import {
  getForgotPasswordLoginRedirect,
  submitResetEmail,
  submitResetPasswordWithCode,
} from './forgot-password-form'

const t = (key: string) => key

describe('forgot password helpers', () => {
  test('sends reset email and redirects back to login', async () => {
    const forgotPassword = mock(async () => {})

    const result = await submitResetEmail(
      { email: 'person@example.test' },
      t,
      forgotPassword
    )

    expect(result).toEqual({ ok: true })
    expect(forgotPassword).toHaveBeenCalledWith('person@example.test')
    expect(getForgotPasswordLoginRedirect()).toBe('/login')
  })

  test('validates email before sending reset email', async () => {
    const forgotPassword = mock(async () => {})

    expect(await submitResetEmail({ email: '' }, t, forgotPassword)).toEqual({
      ok: false,
      fieldErrors: { email: 'emailRequired' },
    })
    expect(await submitResetEmail({ email: 'not-email' }, t, forgotPassword)).toEqual({
      ok: false,
      fieldErrors: { email: 'invalidEmail' },
    })
    expect(forgotPassword).not.toHaveBeenCalled()
  })

  test('submits code reset and maps validation password errors', async () => {
    const resetPassword = mock(async () => {})

    const success = await submitResetPasswordWithCode(
      {
        email: 'person@example.test',
        verificationCode: '123456',
        newPassword: 'new-pass',
        confirmPassword: 'new-pass',
      },
      t,
      resetPassword
    )

    expect(success).toEqual({ ok: true })
    expect(resetPassword).toHaveBeenCalledWith('person@example.test', '123456', 'new-pass')

    resetPassword.mockImplementationOnce(async () => {
      throw new ApiError(1001, 'validation.failed', {
        errors: { password: ['Too weak'] },
      })
    })
    const apiError = await submitResetPasswordWithCode(
      {
        email: 'person@example.test',
        verificationCode: '123456',
        newPassword: 'weak-pass',
        confirmPassword: 'weak-pass',
      },
      t,
      resetPassword
    )

    expect(apiError).toEqual({ ok: false, fieldErrors: { newPassword: 'Too weak' } })
  })

  test('validates code reset locally and maps invalid code errors', async () => {
    const resetPassword = mock(async () => {})
    const base = { email: 'person@example.test', verificationCode: '123456' }

    expect(await submitResetPasswordWithCode({ ...base, newPassword: 'new-pass', confirmPassword: 'other' }, t, resetPassword)).toEqual({
      ok: false,
      fieldErrors: { confirmPassword: 'passwordMismatch' },
    })
    expect(await submitResetPasswordWithCode({ ...base, newPassword: 'short', confirmPassword: 'short' }, t, resetPassword)).toEqual({
      ok: false,
      fieldErrors: { newPassword: 'passwordTooShort' },
    })
    expect(await submitResetPasswordWithCode({ ...base, verificationCode: '123', newPassword: 'new-pass', confirmPassword: 'new-pass' }, t, resetPassword)).toEqual({
      ok: false,
      fieldErrors: { code: 'verificationCodeRequired' },
    })
    expect(resetPassword).not.toHaveBeenCalled()

    resetPassword.mockImplementationOnce(async () => {
      throw new ApiError(5005, 'invalid code')
    })
    expect(await submitResetPasswordWithCode({ ...base, newPassword: 'new-pass', confirmPassword: 'new-pass' }, t, resetPassword)).toEqual({
      ok: false,
      fieldErrors: { code: 'verificationCodeInvalid' },
    })
  })
})
