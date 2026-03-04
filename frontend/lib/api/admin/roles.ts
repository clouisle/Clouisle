import { api } from '../client'
import type {
  Role,
  Permission,
  RoleCreateInput,
  RoleUpdateInput,
  RolePermissionsUpdateInput,
  PermissionCreateInput,
  PermissionUpdateInput,
} from '../roles'
import type { PageData } from '../users'

export type {
  Role,
  Permission,
  RoleCreateInput,
  RoleUpdateInput,
  RolePermissionsUpdateInput,
  PermissionCreateInput,
  PermissionUpdateInput,
}

export const rolesApi = {
  getRoles: async (page = 1, pageSize = 50): Promise<PageData<Role>> =>
    api.get<PageData<Role>>(`/admin/roles?page=${page}&page_size=${pageSize}`),

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
  getPermissions: async (page = 1, pageSize = 100, scope?: string): Promise<PageData<Permission>> => {
    let url = `/admin/permissions?page=${page}&page_size=${pageSize}`
    if (scope) url += `&scope=${scope}`
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
