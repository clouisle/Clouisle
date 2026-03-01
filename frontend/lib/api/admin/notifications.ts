import { api } from '../client'
import type {
  NotificationItem,
  NotificationAdminListParams,
  NotificationAdminCreateInput,
  PaginatedResponse,
} from '../notifications'

export type { NotificationItem, NotificationAdminListParams, NotificationAdminCreateInput, PaginatedResponse }

export const notificationsApi = {
  adminList: async (params: NotificationAdminListParams): Promise<PaginatedResponse<NotificationItem>> =>
    api.get('/admin/notifications', { params }),

  adminCreate: async (payload: NotificationAdminCreateInput): Promise<NotificationItem> =>
    api.post('/admin/notifications', payload),

  adminDelete: async (id: string): Promise<{ id: string }> =>
    api.delete(`/admin/notifications/${id}`),
}
