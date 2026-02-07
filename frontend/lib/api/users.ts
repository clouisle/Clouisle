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

export interface UserQueryParams {
  page?: number
  pageSize?: number
  status?: 'active' | 'inactive' | 'pending'
  search?: string
}

export const usersApi = {
  /**
   * 获取用户列表（分页）
   */
  getUsers: async (params: UserQueryParams = {}): Promise<PageData<User>> => {
    const { page = 1, pageSize = 20, status, search } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (status) queryParams.append('status', status)
    if (search) queryParams.append('search', search)
    return api.get<PageData<User>>(`/users?${queryParams.toString()}`)
  },

  /**
   * 获取用户统计信息
   */
  getStats: async (): Promise<UserStats> => {
    return api.get<UserStats>('/users/stats')
  },

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
   * 删除当前用户账号
   */
  deleteAccount: async (password: string): Promise<void> => {
    await api.delete<null>('/users/me', { password })
  },

  /**
   * 获取单个用户
   */
  getUser: async (userId: string): Promise<User> => {
    return api.get<User>(`/users/${userId}`)
  },

  /**
   * 创建用户
   */
  createUser: async (data: UserCreateData): Promise<User> => {
    return api.post<User>('/users', data)
  },

  /**
   * 更新用户
   */
  updateUser: async (userId: string, data: UserUpdateData): Promise<User> => {
    return api.put<User>(`/users/${userId}`, data)
  },

  /**
   * 删除用户
   */
  deleteUser: async (userId: string): Promise<User> => {
    return api.delete<User>(`/users/${userId}`)
  },

  /**
   * 激活用户
   */
  activateUser: async (userId: string): Promise<User> => {
    return api.post<User>(`/users/${userId}/activate`)
  },

  /**
   * 停用用户
   */
  deactivateUser: async (userId: string): Promise<User> => {
    return api.post<User>(`/users/${userId}/deactivate`)
  },

  /**
   * 发送邮件给用户
   */
  sendEmail: async (userIds: string[], subject: string, content: string): Promise<{ sent_count: number; skipped_count: number; total: number }> => {
    return api.post<{ sent_count: number; skipped_count: number; total: number }>('/users/send-email', {
      user_ids: userIds,
      subject,
      content,
    })
  },
}
