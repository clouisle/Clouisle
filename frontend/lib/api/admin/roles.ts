import { api } from '../client'
import type { PageData } from '../users'

export interface Permission {
  id: string
  scope: string
  code: string
  description: string | null
}

export interface Role {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
  permissions: Permission[]
}

export interface RoleCreateInput {
  name: string
  description?: string
  permissions?: string[]
}

export interface RoleUpdateInput {
  name?: string
  description?: string
}

export interface RolePermissionsUpdateInput {
  permissions: string[]
}

export interface PermissionCreateInput {
  scope: string
  code: string
  description?: string
}

export interface PermissionUpdateInput {
  scope: string
  code: string
  description?: string
}

export const rolesApi = {
  getRoles: async (page = 1, pageSize = 50, search?: string): Promise<PageData<Role>> => {
    let url = `/admin/roles?page=${page}&page_size=${pageSize}`
    if (search) url += `&search=${encodeURIComponent(search)}`
    return api.get<PageData<Role>>(url)
  },

  getRole: async (id: string): Promise<Role> =>
    api.get<Role>(`/admin/roles/${id}`),

  createRole: async (data: RoleCreateInput): Promise<Role> =>
    api.post<Role>('/admin/roles', data),

  updateRole: async (id: string, data: RoleUpdateInput): Promise<Role> =>
    api.put<Role>(`/admin/roles/${id}`, data),

  updateRolePermissions: async (id: string, permissions: string[]): Promise<Role> =>
    api.put<Role>(`/admin/roles/${id}/permissions`, { permissions }),

  deleteRole: async (id: string): Promise<Role> =>
    api.delete<Role>(`/admin/roles/${id}`),
}

export const permissionsApi = {
  getPermissions: async (page = 1, pageSize = 100, scope?: string, search?: string): Promise<PageData<Permission>> => {
    let url = `/admin/permissions?page=${page}&page_size=${pageSize}`
    if (scope) url += `&scope=${encodeURIComponent(scope)}`
    if (search) url += `&search=${encodeURIComponent(search)}`
    return api.get<PageData<Permission>>(url)
  },

  getPermission: async (id: string): Promise<Permission> =>
    api.get<Permission>(`/admin/permissions/${id}`),

  createPermission: async (data: PermissionCreateInput): Promise<Permission> =>
    api.post<Permission>('/admin/permissions', data),

  updatePermission: async (id: string, data: PermissionUpdateInput): Promise<Permission> =>
    api.put<Permission>(`/admin/permissions/${id}`, data),

  deletePermission: async (id: string): Promise<Permission> =>
    api.delete<Permission>(`/admin/permissions/${id}`),
}
