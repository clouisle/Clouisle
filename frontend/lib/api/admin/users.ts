import { api } from '../client'
import type { User } from '../auth'
import type { PageData, UserStats, UserCreateData, UserUpdateData, UserQueryParams } from '../users'

export type { User, PageData, UserStats, UserCreateData, UserUpdateData, UserQueryParams }

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
}
