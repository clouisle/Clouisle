import { api } from './client'
import type { User } from './auth'

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserStats {
  total: number
  active: number
  inactive: number
  pending: number
}

export interface UserCreateData {
  username: string
  email: string
  password: string
  is_active?: boolean
  is_superuser?: boolean
  avatar_url?: string | null
}

export interface UserUpdateData {
  email?: string
  password?: string
  is_active?: boolean
  avatar_url?: string | null
  roles?: string[]  // 角色名称列表
}

export interface UpdateProfileData {
  username?: string
  email?: string
  avatar_url?: string | null
  password?: string
  locale?: string
}

export interface ChangePasswordData {
  current_password: string
  new_password: string
}

export interface PasswordStatus {
  is_exempt: boolean
  password_changed_at: string | null
  password_expires_at: string | null
  is_expired: boolean
  days_until_expiration: number | null
  force_change_required: boolean
}

export interface UserQueryParams {
  page?: number
  pageSize?: number
  status?: 'active' | 'inactive' | 'pending'
  search?: string
}

export const usersApi = {
  /**
   * 获取当前用户信息
   */
  getCurrentUser: async (): Promise<User> => {
    return api.get<User>('/users/me')
  },

  /**
   * 更新当前用户资料
   */
  updateProfile: async (data: UpdateProfileData, options?: { skipAuthRedirect?: boolean }): Promise<User> => {
    return api.put<User>('/users/me', data, { skipAuthRedirect: options?.skipAuthRedirect })
  },

  /**
   * 修改当前用户密码
   */
  changePassword: async (data: ChangePasswordData): Promise<void> => {
    await api.post<null>('/users/me/change-password', data)
  },

  /**
   * 获取密码过期状态
   */
  getPasswordStatus: async (): Promise<PasswordStatus> => {
    return api.get<PasswordStatus>('/users/me/password-status')
  },

  /**
   * 删除当前用户账号
   */
  deleteAccount: async (password: string): Promise<void> => {
    await api.delete<null>('/users/me', { password })
  },
}
