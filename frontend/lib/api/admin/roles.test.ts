import { afterEach, beforeEach, describe, expect, it, spyOn } from 'bun:test'

import { api } from '../client'
import { permissionsApi, rolesApi } from './roles'

let getSpy: ReturnType<typeof spyOn>
let postSpy: ReturnType<typeof spyOn>
let putSpy: ReturnType<typeof spyOn>
let deleteSpy: ReturnType<typeof spyOn>

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

describe('rolesApi', () => {
  it('requests role list defaults and encoded search parameters', async () => {
    getSpy.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 })

    await rolesApi.getRoles()
    await rolesApi.getRoles(3, 25, 'team admin/管理')

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/roles?page=1&page_size=50')
    expect(getSpy).toHaveBeenNthCalledWith(
      2,
      '/admin/roles?page=3&page_size=25&search=team%20admin%2F%E7%AE%A1%E7%90%86'
    )
  })

  it('requests every role detail and mutation route with its payload', async () => {
    const create = { name: 'auditor', description: 'Read only', permissions: ['audit.read'] }
    const update = { name: 'senior-auditor', description: 'Reports' }
    const permissions = ['audit.read', 'audit.export']
    getSpy.mockResolvedValue({})
    postSpy.mockResolvedValue({})
    putSpy.mockResolvedValue({})
    deleteSpy.mockResolvedValue({})

    await rolesApi.getRole('role-1')
    await rolesApi.createRole(create)
    await rolesApi.updateRole('role-1', update)
    await rolesApi.updateRolePermissions('role-1', permissions)
    await rolesApi.deleteRole('role-1')

    expect(getSpy).toHaveBeenCalledWith('/admin/roles/role-1')
    expect(postSpy).toHaveBeenCalledWith('/admin/roles', create)
    expect(putSpy).toHaveBeenNthCalledWith(1, '/admin/roles/role-1', update)
    expect(putSpy).toHaveBeenNthCalledWith(2, '/admin/roles/role-1/permissions', { permissions })
    expect(deleteSpy).toHaveBeenCalledWith('/admin/roles/role-1')
  })
})

describe('permissionsApi', () => {
  it('requests permission list defaults and repeated scope/query parameters', async () => {
    getSpy.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 100 })

    await permissionsApi.getPermissions()
    await permissionsApi.getPermissions(2, 20, ['users', 'audit'], 'read only')

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/permissions?page=1&page_size=100')
    expect(getSpy).toHaveBeenNthCalledWith(
      2,
      '/admin/permissions?page=2&page_size=20&scope=users&scope=audit&search=read+only'
    )
  })

  it('requests every permission detail and mutation route with its payload', async () => {
    const create = { scope: 'audit', code: 'read', description: 'Read audit logs' }
    const update = { scope: 'audit', code: 'export', description: 'Export audit logs' }
    getSpy.mockResolvedValue({})
    postSpy.mockResolvedValue({})
    putSpy.mockResolvedValue({})
    deleteSpy.mockResolvedValue({})

    await permissionsApi.getPermissionScopes()
    await permissionsApi.getPermission('permission-1')
    await permissionsApi.createPermission(create)
    await permissionsApi.updatePermission('permission-1', update)
    await permissionsApi.deletePermission('permission-1')

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/permissions/scopes')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/admin/permissions/permission-1')
    expect(postSpy).toHaveBeenCalledWith('/admin/permissions', create)
    expect(putSpy).toHaveBeenCalledWith('/admin/permissions/permission-1', update)
    expect(deleteSpy).toHaveBeenCalledWith('/admin/permissions/permission-1')
  })

  it('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    getSpy.mockRejectedValue(error)

    await expect(permissionsApi.getPermission('permission-1')).rejects.toBe(error)
  })
})
