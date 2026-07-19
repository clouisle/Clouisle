import { afterEach, beforeEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from './client'
import { usersApi as adminUsersApi } from './admin/users'
import { usersApi } from './users'

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
  it('posts password changes with the requested silent option', async () => {
    postSpy.mockResolvedValue(null)

    await usersApi.changePassword({ current_password: 'old', new_password: 'new' }, { silent: true })

    expect(postSpy).toHaveBeenCalledWith(
      '/users/me/change-password',
      { current_password: 'old', new_password: 'new' },
      { silent: true }
    )
  })

  it('propagates password status errors', async () => {
    const error = new Error('unavailable')
    getSpy.mockRejectedValue(error)

    await expect(usersApi.getPasswordStatus()).rejects.toBe(error)
    expect(getSpy).toHaveBeenCalledWith('/users/me/password-status')
  })
})
