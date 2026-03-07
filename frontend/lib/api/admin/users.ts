import { api } from '../client'
import type { User } from '../auth'
import type { PageData, UserStats, UserCreateData, UserUpdateData, UserQueryParams } from '../users'

export type { User, PageData, UserStats, UserCreateData, UserUpdateData, UserQueryParams }

export interface PasswordExpirationStats {
  total_users: number
  expired_count: number
  expiring_soon_count: number
  force_change_count: number
  exempt_count: number
}

export interface ExpiringPasswordUser {
  id: string
  username: string
  email: string
  password_changed_at: string | null
  password_expires_at: string | null
  days_until_expiration: number | null
  force_password_change: boolean
  password_expiration_exempt: boolean
  last_login: string | null
}

export const usersApi = {
  getUsers: async (params: UserQueryParams = {}): Promise<PageData<User>> => {
    const { page = 1, pageSize = 20, status, search } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (status) queryParams.append('status', status)
    if (search) queryParams.append('search', search)
    return api.get<PageData<User>>(`/admin/users?${queryParams.toString()}`)
  },

  getStats: async (): Promise<UserStats> =>
    api.get<UserStats>('/admin/users/stats'),

  getUser: async (userId: string): Promise<User> =>
    api.get<User>(`/admin/users/${userId}`),

  createUser: async (data: UserCreateData): Promise<User> =>
    api.post<User>('/admin/users', data),

  updateUser: async (userId: string, data: UserUpdateData): Promise<User> =>
    api.put<User>(`/admin/users/${userId}`, data),

  deleteUser: async (userId: string): Promise<User> =>
    api.delete<User>(`/admin/users/${userId}`),

  activateUser: async (userId: string): Promise<User> =>
    api.post<User>(`/admin/users/${userId}/activate`),

  deactivateUser: async (userId: string): Promise<User> =>
    api.post<User>(`/admin/users/${userId}/deactivate`),

  sendEmail: async (
    userIds: string[],
    subject: string,
    content: string
  ): Promise<{ sent_count: number; skipped_count: number; total: number }> =>
    api.post('/admin/users/send-email', { user_ids: userIds, subject, content }),

  // Password expiration management
  forcePasswordChange: async (userId: string): Promise<void> =>
    api.post(`/admin/users/${userId}/force-password-change`),

  resetPasswordExpiration: async (userId: string): Promise<void> =>
    api.post(`/admin/users/${userId}/reset-password-expiration`),

  exemptPasswordExpiration: async (userId: string, exempt: boolean): Promise<void> =>
    api.post(`/admin/users/${userId}/exempt-password-expiration`, { exempt }),

  bulkForcePasswordChange: async (userIds: string[]): Promise<{ count: number }> =>
    api.post('/admin/users/bulk-force-password-change', { user_ids: userIds }),

  getPasswordExpirationStats: async (): Promise<PasswordExpirationStats> =>
    api.get<PasswordExpirationStats>('/admin/users/password-expiration-stats'),

  getExpiringPasswords: async (
    page: number = 1,
    pageSize: number = 20,
    filter: 'all' | 'expired' | 'expiring' | 'force_change' = 'all'
  ): Promise<PageData<ExpiringPasswordUser>> => {
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    queryParams.append('filter', filter)
    return api.get<PageData<ExpiringPasswordUser>>(`/admin/users/expiring-passwords?${queryParams.toString()}`)
  },
}
