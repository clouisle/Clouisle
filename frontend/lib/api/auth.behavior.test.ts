import { beforeEach, describe, expect, mock, test } from 'bun:test'

const postForm = mock(() => Promise.resolve({}))

mock.module('./client', () => ({
  api: { postForm },
}))

const { authApi } = await import('./auth')

beforeEach(() => {
  postForm.mockClear()
})

describe('authApi form authentication', () => {
  test('submits login credentials and optional captcha as an auth-redirect-safe form', async () => {
    await authApi.login({
      username: 'ada',
      password: 'secret',
      captcha_id: 'captcha-1',
      captcha_token: 'proof-1',
    })

    const [url, formData, options] = postForm.mock.calls[0] as [string, FormData, unknown]
    expect(url).toBe('/login/access-token')
    expect(Object.fromEntries(formData.entries())).toEqual({
      username: 'ada',
      password: 'secret',
      captcha_id: 'captcha-1',
      captcha_token: 'proof-1',
    })
    expect(options).toEqual({ skipAuthRedirect: true })
  })

  test('omits absent captcha values from login submissions', async () => {
    await authApi.login({ username: 'ada', password: 'secret' })

    const [, formData] = postForm.mock.calls[0] as [string, FormData]
    expect(Object.fromEntries(formData.entries())).toEqual({ username: 'ada', password: 'secret' })
  })

  test('submits backup-code state with the temporary TOTP token', async () => {
    await authApi.verifyTOTP('temporary-token', '123456', true)

    const [url, formData, options] = postForm.mock.calls[0] as [string, FormData, unknown]
    expect(url).toBe('/login/verify-totp')
    expect(Object.fromEntries(formData.entries())).toEqual({
      temp_token: 'temporary-token',
      code: '123456',
      is_backup_code: 'true',
    })
    expect(options).toEqual({ skipAuthRedirect: true })
  })
})
