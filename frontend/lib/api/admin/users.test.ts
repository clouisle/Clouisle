import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from '../client'
import { adminTOTPApi, usersApi } from './users'

let getSpy: ReturnType<typeof spyOn> | undefined
let postSpy: ReturnType<typeof spyOn> | undefined
let putSpy: ReturnType<typeof spyOn> | undefined
let deleteSpy: ReturnType<typeof spyOn> | undefined

afterEach(() => {
  getSpy?.mockRestore()
  postSpy?.mockRestore()
  putSpy?.mockRestore()
  deleteSpy?.mockRestore()
  getSpy = postSpy = putSpy = deleteSpy = undefined
})

describe('admin users requests', () => {
  it('serializes default and repeated user query parameters', async () => {
    const response = { items: [], total: 0, page: 1, page_size: 20 }
    getSpy = spyOn(api, 'get').mockResolvedValue(response)

    expect(await usersApi.getUsers()).toBe(response)
    expect(await usersApi.getUsers({
      page: 3,
      pageSize: 50,
      status: ['active', 'pending'],
      roles: ['admin', 'editor'],
      search: 'Ada Lovelace',
      excludeUserIds: ['user/1', 'user-2'],
    })).toBe(response)
    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/users?page=1&page_size=20')
    expect(getSpy).toHaveBeenNthCalledWith(
      2,
      '/admin/users?page=3&page_size=50&status=active&status=pending&role=admin&role=editor&exclude_user_id=user%2F1&exclude_user_id=user-2&search=Ada+Lovelace'
    )
  })

  it('uses exact CRUD and activation routes and payloads', async () => {
    const response = { id: 'user-1' }
    getSpy = spyOn(api, 'get').mockResolvedValue(response)
    postSpy = spyOn(api, 'post').mockResolvedValue(response)
    putSpy = spyOn(api, 'put').mockResolvedValue(response)
    deleteSpy = spyOn(api, 'delete').mockResolvedValue(response)
    const create = { username: 'ada', email: 'ada@example.com', password: 'secret' }
    const update = { email: 'new@example.com', roles: ['admin'] }

    expect(await usersApi.getStats()).toBe(response)
    expect(await usersApi.getUser('user-1')).toBe(response)
    expect(await usersApi.createUser(create)).toBe(response)
    expect(await usersApi.updateUser('user-1', update)).toBe(response)
    expect(await usersApi.deleteUser('user-1')).toBe(response)
    expect(await usersApi.activateUser('user-1')).toBe(response)
    expect(await usersApi.deactivateUser('user-1')).toBe(response)

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/users/stats')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/admin/users/user-1')
    expect(postSpy).toHaveBeenNthCalledWith(1, '/admin/users', create)
    expect(putSpy).toHaveBeenCalledWith('/admin/users/user-1', update)
    expect(deleteSpy).toHaveBeenCalledWith('/admin/users/user-1')
    expect(postSpy).toHaveBeenNthCalledWith(2, '/admin/users/user-1/activate')
    expect(postSpy).toHaveBeenNthCalledWith(3, '/admin/users/user-1/deactivate')
  })

  it('posts email and password-management payloads and options unchanged', async () => {
    const response = { sent_count: 2, skipped_count: 0, total: 2 }
    postSpy = spyOn(api, 'post').mockResolvedValue(response)

    expect(await usersApi.sendEmail(['user-1', 'user-2'], 'Subject', 'Body', { silent: true })).toBe(response)
    await usersApi.forcePasswordChange('user-1')
    await usersApi.resetPasswordExpiration('user-1')
    await usersApi.exemptPasswordExpiration('user-1', false)
    expect(await usersApi.bulkForcePasswordChange(['user-1', 'user-2'])).toBe(response)

    expect(postSpy).toHaveBeenNthCalledWith(1, '/admin/users/send-email', {
      user_ids: ['user-1', 'user-2'], subject: 'Subject', content: 'Body',
    }, { silent: true })
    expect(postSpy).toHaveBeenNthCalledWith(2, '/admin/users/user-1/force-password-change')
    expect(postSpy).toHaveBeenNthCalledWith(3, '/admin/users/user-1/reset-password-expiration')
    expect(postSpy).toHaveBeenNthCalledWith(4, '/admin/users/user-1/exempt-password-expiration', { exempt: false })
    expect(postSpy).toHaveBeenNthCalledWith(5, '/admin/users/bulk-force-password-change', {
      user_ids: ['user-1', 'user-2'],
    })
  })

  it('uses exact password-expiration routes and query defaults', async () => {
    const response = { items: [], total: 0, page: 1, page_size: 20 }
    getSpy = spyOn(api, 'get').mockResolvedValue(response)

    expect(await usersApi.getPasswordExpirationStats()).toBe(response)
    expect(await usersApi.getExpiringPasswords()).toBe(response)
    expect(await usersApi.getExpiringPasswords(2, 10, 'expired')).toBe(response)

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/users/password-expiration-stats')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/admin/users/expiring-passwords?page=1&page_size=20&filter=all')
    expect(getSpy).toHaveBeenNthCalledWith(3, '/admin/users/expiring-passwords?page=2&page_size=10&filter=expired')
  })

  it('uses exact admin TOTP routes', async () => {
    const response = { enabled: true, enabled_at: null }
    getSpy = spyOn(api, 'get').mockResolvedValue(response)
    postSpy = spyOn(api, 'post').mockResolvedValue(null)

    expect(await adminTOTPApi.getStats()).toBe(response)
    await adminTOTPApi.disableUserTOTP('user-1')
    expect(await adminTOTPApi.getUserTOTPStatus('user-1')).toBe(response)

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/totp/stats')
    expect(postSpy).toHaveBeenCalledWith('/admin/users/user-1/totp/disable')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/admin/users/user-1/totp/status')
  })

  it('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    getSpy = spyOn(api, 'get').mockRejectedValue(error)
    postSpy = spyOn(api, 'post').mockRejectedValue(error)

    await expect(usersApi.getUsers()).rejects.toBe(error)
    await expect(usersApi.createUser({ username: 'ada', email: 'ada@example.com', password: 'secret' })).rejects.toBe(error)
    await expect(adminTOTPApi.disableUserTOTP('user-1')).rejects.toBe(error)
  })
})
