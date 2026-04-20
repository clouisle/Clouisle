import { api } from '../client'
import type {
  NotificationItem,
  NotificationAdminListParams,
  NotificationAdminCreateInput,
  PaginatedResponse,
} from '../notifications'

export type { NotificationItem, NotificationAdminListParams, NotificationAdminCreateInput, PaginatedResponse }

export const notificationsApi = {
  adminList: async (params: NotificationAdminListParams): Promise<PaginatedResponse<NotificationItem>> => {
    const queryParams = new URLSearchParams()
    params.scope?.forEach((value) => queryParams.append('scope', value))
    if (params.team_id) queryParams.append('team_id', params.team_id)
    if (params.user_id) queryParams.append('user_id', params.user_id)
    if (params.type) queryParams.append('type', params.type)
    params.level?.forEach((value) => queryParams.append('level', value))
    if (params.search) queryParams.append('search', params.search)
    if (params.include_expired !== undefined) queryParams.append('include_expired', String(params.include_expired))
    if (params.page !== undefined) queryParams.append('page', String(params.page))
    if (params.page_size !== undefined) queryParams.append('page_size', String(params.page_size))
    return api.get(`/admin/notifications?${queryParams.toString()}`)
  },

  adminCreate: async (payload: NotificationAdminCreateInput, options?: { silent?: boolean }): Promise<NotificationItem> =>
    api.post('/admin/notifications', payload, { silent: options?.silent }),

  adminDelete: async (id: string): Promise<{ id: string }> =>
    api.delete(`/admin/notifications/${id}`),
}
