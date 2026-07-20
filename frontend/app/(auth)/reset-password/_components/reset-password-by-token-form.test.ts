import { describe, expect, mock, test } from 'bun:test'
import { ApiError } from '@/lib/api'
import {
  getResetPasswordByTokenLoginRedirect,
  submitResetPasswordByToken,
} from './reset-password-by-token-form'

const t = (key: string) => key

describe('reset password by token helpers', () => {
  test('submits token reset and redirects to login after success', async () => {
    const resetPasswordByToken = mock(async () => {})

    const result = await submitResetPasswordByToken(
      { token: 'token-123', newPassword: 'new-pass', confirmPassword: 'new-pass' },
      t,
      resetPasswordByToken
    )

    expect(result).toEqual({ ok: true })
    expect(resetPasswordByToken).toHaveBeenCalledWith('token-123', 'new-pass')
    expect(getResetPasswordByTokenLoginRedirect()).toBe('/login')
  })

  test('validates password before calling the API', async () => {
    const resetPasswordByToken = mock(async () => {})

    expect(await submitResetPasswordByToken({ token: 'token-123', newPassword: 'short', confirmPassword: 'short' }, t, resetPasswordByToken)).toEqual({
      ok: false,
      fieldErrors: { newPassword: 'passwordTooShort' },
    })
    expect(await submitResetPasswordByToken({ token: 'token-123', newPassword: 'new-pass', confirmPassword: 'other' }, t, resetPasswordByToken)).toEqual({
      ok: false,
      fieldErrors: { confirmPassword: 'passwordMismatch' },
    })
    expect(resetPasswordByToken).not.toHaveBeenCalled()
  })

  test('maps backend password and token errors', async () => {
    const resetPasswordByToken = mock(async () => {
      throw new ApiError(1001, 'validation.failed', {
        errors: { password: ['Too weak'] },
      })
    })

    expect(await submitResetPasswordByToken({ token: 'token-123', newPassword: 'weak-pass', confirmPassword: 'weak-pass' }, t, resetPasswordByToken)).toEqual({
      ok: false,
      fieldErrors: { newPassword: 'Too weak' },
    })

    resetPasswordByToken.mockImplementationOnce(async () => {
      throw new ApiError(5005, 'invalid token')
    })
    expect(await submitResetPasswordByToken({ token: 'bad-token', newPassword: 'new-pass', confirmPassword: 'new-pass' }, t, resetPasswordByToken)).toEqual({
      ok: false,
      fieldErrors: { token: 'verificationTokenInvalid' },
    })
  })
})
