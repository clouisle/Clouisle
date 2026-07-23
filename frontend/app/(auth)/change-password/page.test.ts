import { describe, expect, mock, test } from 'bun:test'
import { ApiError } from '@/lib/api'
import { getChangePasswordRedirect, submitChangePassword } from './page'

const t = (key: string) => key

describe('change password helpers', () => {
  test('submits valid passwords and uses redirect fallback', async () => {
    const changePassword = mock(async () => {})

    const result = await submitChangePassword(
      { currentPassword: 'old-pass', newPassword: 'new-pass', confirmPassword: 'new-pass' },
      t,
      changePassword
    )

    expect(result).toEqual({ ok: true })
    expect(changePassword).toHaveBeenCalledWith({
      current_password: 'old-pass',
      new_password: 'new-pass',
    })
    expect(getChangePasswordRedirect(new URLSearchParams())).toBe('/app')
  })

  test('blocks mismatched confirmation before the API call', async () => {
    const changePassword = mock(async () => {})

    const result = await submitChangePassword(
      { currentPassword: 'old-pass', newPassword: 'new-pass', confirmPassword: 'other-pass' },
      t,
      changePassword
    )

    expect(result).toEqual({ ok: false, fieldErrors: { confirmPassword: 'passwordMismatch' } })
    expect(changePassword).not.toHaveBeenCalled()
  })

  test('returns backend validation errors and preserves explicit redirect', async () => {
    const changePassword = mock(async () => {
      throw new ApiError(1001, 'validation.failed', {
        errors: { current_password: ['Wrong password'] },
      })
    })

    const result = await submitChangePassword(
      { currentPassword: 'bad-pass', newPassword: 'new-pass', confirmPassword: 'new-pass' },
      t,
      changePassword
    )

    expect(result).toEqual({ ok: false, fieldErrors: { current_password: 'Wrong password' } })
    expect(getChangePasswordRedirect(new URLSearchParams('redirect=/app/settings'))).toBe('/app/settings')
  })
})
