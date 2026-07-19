import { afterEach, beforeEach, describe, expect, it, spyOn } from 'bun:test'
import { usersApi as adminUsersApi } from './admin/users'
import { api } from './client'
import { totpApi, usersApi } from './users'

let getSpy: ReturnType<typeof spyOn<typeof api, 'get'>>
let postSpy: ReturnType<typeof spyOn<typeof api, 'post'>>
let putSpy: ReturnType<typeof spyOn<typeof api, 'put'>>
let deleteSpy: ReturnType<typeof spyOn<typeof api, 'delete'>>

beforeEach(() => {
  getSpy = spyOn(api, 'get')
  postSpy = spyOn(api, 'post')
  putSpy = spyOn(api, 'put')
  deleteSpy = spyOn(api, 'delete')
})

afterEach(() => {
  getSpy.mockRestore()
  postSpy.mockRestore()
  putSpy.mockRestore()
  deleteSpy.mockRestore()
})

describe('admin users API', () => {
  it('lists users with default pagination', async () => {
    getSpy.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })

    await adminUsersApi.getUsers()

    expect(getSpy).toHaveBeenCalledWith('/admin/users?page=1&page_size=20')
  })

  it('serializes list filters', async () => {
    getSpy.mockResolvedValue({ items: [], total: 0, page: 2, page_size: 50 })

    await adminUsersApi.getUsers({
      page: 2,
      pageSize: 50,
      status: ['active', 'pending'],
      roles: ['admin', 'editor'],
      excludeUserIds: ['self', 'service'],
      search: 'Ada Lovelace',
    })

    expect(getSpy).toHaveBeenCalledWith(
      '/admin/users?page=2&page_size=50&status=active&status=pending&role=admin&role=editor&exclude_user_id=self&exclude_user_id=service&search=Ada+Lovelace'
    )
  })

  it('uses CRUD routes and preserves role updates', async () => {
    postSpy.mockResolvedValue({})
    putSpy.mockResolvedValue({})
    deleteSpy.mockResolvedValue({})

    await adminUsersApi.createUser({ username: 'ada', email: 'ada@example.com', password: 'secret' })
    await adminUsersApi.updateUser('user-1', { roles: ['admin'] })
    await adminUsersApi.deleteUser('user-1')

    expect(postSpy).toHaveBeenCalledWith('/admin/users', { username: 'ada', email: 'ada@example.com', password: 'secret' })
    expect(putSpy).toHaveBeenCalledWith('/admin/users/user-1', { roles: ['admin'] })
    expect(deleteSpy).toHaveBeenCalledWith('/admin/users/user-1')
  })
})

describe('current user API', () => {
  it('gets the current user and password status', async () => {
    getSpy.mockResolvedValue({})

    await usersApi.getCurrentUser()
    await usersApi.getPasswordStatus()

    expect(getSpy).toHaveBeenNthCalledWith(1, '/users/me')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/users/me/password-status')
  })

  it('updates the profile with and without request options', async () => {
    const data = { username: 'ada', locale: 'en' }
    putSpy.mockResolvedValue({})

    await usersApi.updateProfile(data)
    await usersApi.updateProfile(data, { skipAuthRedirect: true, silent: true })

    expect(putSpy).toHaveBeenNthCalledWith(1, '/users/me', data, {
      skipAuthRedirect: undefined,
      silent: undefined,
    })
    expect(putSpy).toHaveBeenNthCalledWith(2, '/users/me', data, {
      skipAuthRedirect: true,
      silent: true,
    })
  })

  it('posts password changes with the requested silent option', async () => {
    postSpy.mockResolvedValue(null)

    await usersApi.changePassword({ current_password: 'old', new_password: 'new' }, { silent: true })

    expect(postSpy).toHaveBeenCalledWith(
      '/users/me/change-password',
      { current_password: 'old', new_password: 'new' },
      { silent: true }
    )
  })

  it('posts password changes without request options', async () => {
    postSpy.mockResolvedValue(null)

    await usersApi.changePassword({ current_password: 'old', new_password: 'new' })

    expect(postSpy).toHaveBeenCalledWith(
      '/users/me/change-password',
      { current_password: 'old', new_password: 'new' },
      { silent: undefined }
    )
  })

  it('deletes the account with and without request options', async () => {
    deleteSpy.mockResolvedValue(null)

    await usersApi.deleteAccount('secret')
    await usersApi.deleteAccount('secret', { silent: true })

    expect(deleteSpy).toHaveBeenNthCalledWith(1, '/users/me', { password: 'secret' }, { silent: undefined })
    expect(deleteSpy).toHaveBeenNthCalledWith(2, '/users/me', { password: 'secret' }, { silent: true })
  })

  it('propagates password status errors', async () => {
    const error = new Error('unavailable')
    getSpy.mockRejectedValue(error)

    await expect(usersApi.getPasswordStatus()).rejects.toBe(error)
    expect(getSpy).toHaveBeenCalledWith('/users/me/password-status')
  })

  it('propagates mutation errors', async () => {
    const error = new Error('rejected')
    putSpy.mockRejectedValue(error)
    postSpy.mockRejectedValue(error)
    deleteSpy.mockRejectedValue(error)

    await expect(usersApi.updateProfile({ username: 'ada' })).rejects.toBe(error)
    await expect(usersApi.changePassword({ current_password: 'old', new_password: 'new' })).rejects.toBe(error)
    await expect(usersApi.deleteAccount('secret')).rejects.toBe(error)
  })
})

describe('TOTP API', () => {
  it('uses setup, enable, and status routes', async () => {
    postSpy.mockResolvedValue({})
    getSpy.mockResolvedValue({})

    await totpApi.setup()
    await totpApi.enable('123456')
    await totpApi.getStatus()

    expect(postSpy).toHaveBeenNthCalledWith(1, '/totp/setup')
    expect(postSpy).toHaveBeenNthCalledWith(2, '/totp/enable', { code: '123456' })
    expect(getSpy).toHaveBeenCalledWith('/totp/status')
  })

  it('disables TOTP with default and explicit options', async () => {
    postSpy.mockResolvedValue(null)

    await totpApi.disable('secret', '123456')
    await totpApi.disable('secret', 'backup-code', true, { silent: true })

    expect(postSpy).toHaveBeenNthCalledWith(
      1,
      '/totp/disable',
      { password: 'secret', code: '123456', is_backup_code: false },
      { silent: undefined }
    )
    expect(postSpy).toHaveBeenNthCalledWith(
      2,
      '/totp/disable',
      { password: 'secret', code: 'backup-code', is_backup_code: true },
      { silent: true }
    )
  })

  it('regenerates backup codes with and without request options', async () => {
    postSpy.mockResolvedValue({ codes: ['backup-code'] })

    await totpApi.regenerateBackupCodes('123456')
    await totpApi.regenerateBackupCodes('123456', { silent: true })

    expect(postSpy).toHaveBeenNthCalledWith(
      1,
      '/totp/regenerate-backup-codes',
      { code: '123456' },
      { silent: undefined }
    )
    expect(postSpy).toHaveBeenNthCalledWith(
      2,
      '/totp/regenerate-backup-codes',
      { code: '123456' },
      { silent: true }
    )
  })

  it('propagates TOTP request errors', async () => {
    const error = new Error('invalid code')
    postSpy.mockRejectedValue(error)

    await expect(totpApi.enable('bad-code')).rejects.toBe(error)
    expect(postSpy).toHaveBeenCalledWith('/totp/enable', { code: 'bad-code' })
  })
})
