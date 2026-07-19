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
})
