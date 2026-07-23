import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'
import { authApi } from './auth'
import { api } from './client'

afterEach(() => {
  mock.restore()
})

describe('authApi', () => {
  it('submits login credentials and provided captcha fields as form data', async () => {
    const token = { access_token: 'token', token_type: 'bearer' }
    const postForm = spyOn(api, 'postForm').mockResolvedValue(token)

    await expect(authApi.login({
      username: 'alice',
      password: 'secret',
      captcha_id: 'captcha-id',
      captcha_token: 'captcha-token',
    })).resolves.toBe(token)

    const [url, formData, config] = postForm.mock.calls[0]
    expect(url).toBe('/login/access-token')
    expect(Object.fromEntries((formData as FormData).entries())).toEqual({
      username: 'alice',
      password: 'secret',
      captcha_id: 'captcha-id',
      captcha_token: 'captcha-token',
    })
    expect(config).toEqual({ skipAuthRedirect: true })
  })

  it('omits optional captcha fields when logging in without a captcha', async () => {
    const postForm = spyOn(api, 'postForm').mockResolvedValue({ access_token: 'token', token_type: 'bearer' })

    await authApi.login({ username: 'alice', password: 'secret' })

    const [, formData] = postForm.mock.calls[0]
    expect(Object.fromEntries((formData as FormData).entries())).toEqual({
      username: 'alice',
      password: 'secret',
    })
  })

  it('posts to the logout endpoint', async () => {
    const post = spyOn(api, 'post').mockResolvedValue(null)

    await expect(authApi.logout()).resolves.toBeUndefined()

    expect(post).toHaveBeenCalledWith('/logout')
  })

  it('propagates API errors', async () => {
    const error = new Error('request failed')
    spyOn(api, 'postForm').mockRejectedValue(error)

    await expect(authApi.login({ username: 'alice', password: 'secret' })).rejects.toBe(error)
  })

  it('gets and completes a click captcha', async () => {
    const captcha = { captcha_id: 'captcha-id', challenge: 'challenge', prompt: 'Pick one', expires_in: 60 }
    const proof = { captcha_id: 'captcha-id', captcha_token: 'captcha-token' }
    const get = spyOn(api, 'get').mockResolvedValue(captcha)
    const post = spyOn(api, 'post').mockResolvedValue(proof)
    const data = {
      captcha_id: 'captcha-id',
      challenge: 'challenge',
      clicked_option: 'cat',
      elapsed_ms: 750,
      pointer: [{ x: 12, y: 34, t: 500, event: 'click' as const }],
    }

    await expect(authApi.getCaptcha()).resolves.toBe(captcha)
    await expect(authApi.completeCaptchaClick(data)).resolves.toBe(proof)

    expect(get).toHaveBeenCalledWith('/captcha')
    expect(post).toHaveBeenCalledWith('/captcha/click', data)
  })

  it('registers with the exact supplied payload', async () => {
    const user = { id: 'user-id' }
    const post = spyOn(api, 'post').mockResolvedValue(user)
    const data = {
      username: 'alice',
      email: 'alice@example.com',
      password: 'secret',
      terms_accepted: true,
      captcha_id: 'captcha-id',
      captcha_token: 'captcha-token',
      locale: 'en',
    }

    await expect(authApi.register(data)).resolves.toBe(user as never)

    expect(post).toHaveBeenCalledWith('/register', data)
  })

  it('gets the current user with explicit and omitted request options', async () => {
    const user = { id: 'user-id' }
    const get = spyOn(api, 'get').mockResolvedValue(user)

    await expect(authApi.getCurrentUser({ skipAuthRedirect: true, silent: true })).resolves.toBe(user as never)
    await authApi.getCurrentUser()

    expect(get).toHaveBeenNthCalledWith(1, '/users/me', { skipAuthRedirect: true, silent: true })
    expect(get).toHaveBeenNthCalledWith(2, '/users/me', { skipAuthRedirect: undefined, silent: undefined })
  })

  it('sends and resends email verification with default and custom purposes', async () => {
    const post = spyOn(api, 'post').mockResolvedValue(null)

    await authApi.sendVerification('alice@example.com')
    await authApi.sendVerification('alice@example.com', 'change-email')
    await authApi.resendVerification('alice@example.com')

    expect(post).toHaveBeenNthCalledWith(1, '/send-verification', {
      email: 'alice@example.com',
      purpose: 'register',
    })
    expect(post).toHaveBeenNthCalledWith(2, '/send-verification', {
      email: 'alice@example.com',
      purpose: 'change-email',
    })
    expect(post).toHaveBeenNthCalledWith(3, '/resend-verification', { email: 'alice@example.com' })
  })

  it('verifies email by code with default and custom purposes and by token', async () => {
    const verification = { verified: true, email: 'alice@example.com' }
    const post = spyOn(api, 'post').mockResolvedValue(verification)
    const get = spyOn(api, 'get').mockResolvedValue(verification)

    await expect(authApi.verifyEmail('alice@example.com', '123456')).resolves.toBe(verification)
    await authApi.verifyEmail('alice@example.com', '654321', 'change-email')
    await expect(authApi.verifyEmailByToken('verification-token')).resolves.toBe(verification)

    expect(post).toHaveBeenNthCalledWith(1, '/verify-email', {
      email: 'alice@example.com',
      code: '123456',
      purpose: 'register',
    })
    expect(post).toHaveBeenNthCalledWith(2, '/verify-email', {
      email: 'alice@example.com',
      code: '654321',
      purpose: 'change-email',
    })
    expect(get).toHaveBeenCalledWith('/verify?token=verification-token')
  })

  it('requests and completes both password reset flows', async () => {
    const post = spyOn(api, 'post').mockResolvedValue(null)

    await authApi.forgotPassword('alice@example.com')
    await authApi.resetPassword('alice@example.com', '123456', 'new-secret')
    await authApi.resetPasswordByToken('reset-token', 'new-secret')

    expect(post).toHaveBeenNthCalledWith(1, '/forgot-password', { email: 'alice@example.com' })
    expect(post).toHaveBeenNthCalledWith(2, '/reset-password', {
      email: 'alice@example.com',
      code: '123456',
      new_password: 'new-secret',
    })
    expect(post).toHaveBeenNthCalledWith(3, '/reset-password', {
      token: 'reset-token',
      new_password: 'new-secret',
    })
  })

  it('verifies TOTP and backup codes as form data', async () => {
    const token = { access_token: 'token', token_type: 'bearer' }
    const postForm = spyOn(api, 'postForm').mockResolvedValue(token)

    await expect(authApi.verifyTOTP('temp-token', '123456')).resolves.toBe(token)
    await authApi.verifyTOTP('temp-token', 'backup-code', true)

    const [firstUrl, firstFormData, firstConfig] = postForm.mock.calls[0]
    expect(firstUrl).toBe('/login/verify-totp')
    expect(Object.fromEntries((firstFormData as FormData).entries())).toEqual({
      temp_token: 'temp-token',
      code: '123456',
      is_backup_code: 'false',
    })
    expect(firstConfig).toEqual({ skipAuthRedirect: true })

    const [secondUrl, secondFormData, secondConfig] = postForm.mock.calls[1]
    expect(secondUrl).toBe('/login/verify-totp')
    expect(Object.fromEntries((secondFormData as FormData).entries())).toEqual({
      temp_token: 'temp-token',
      code: 'backup-code',
      is_backup_code: 'true',
    })
    expect(secondConfig).toEqual({ skipAuthRedirect: true })
  })

  it('preserves a meaningful error from a current-user request', async () => {
    const error = new Error('session expired')
    spyOn(api, 'get').mockRejectedValue(error)

    await expect(authApi.getCurrentUser()).rejects.toBe(error)
  })
})
