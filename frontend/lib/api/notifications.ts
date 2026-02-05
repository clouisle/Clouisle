import { api } from './client'

export type NotificationScope = 'global' | 'team' | 'user'
export type NotificationSource = 'system' | 'user' | 'biz'
export type NotificationLevel = 'low' | 'medium' | 'high'
export type NotificationStatus = 'active'
export type NotificationChannel = 'email' | 'dingtalk' | 'webhook' | 'slack' | 'wechat'
export type NotificationDeliveryStatus = 'pending' | 'sending' | 'success' | 'failed'

export interface NotificationDelivery {
  channel: NotificationChannel
  status: NotificationDeliveryStatus
  error_message?: string | null
  retry_count: number
  sent_at?: string | null
  created_at: string
  updated_at: string
}

export interface NotificationItem {
  id: string
  scope: NotificationScope
  team_id?: string | null
  user_id?: string | null
  type: string
  source: NotificationSource
  title: string
  content: string
  level: NotificationLevel
  data?: Record<string, any> | null
  link_url?: string | null
  status: NotificationStatus
  expires_at?: string | null
  created_at: string
  updated_at: string
  is_read: boolean
  read_at?: string | null
  deliveries?: NotificationDelivery[]
}

export interface NotificationListParams {
  scope?: NotificationScope
  type?: string
  level?: NotificationLevel
  search?: string
  unread_only?: boolean
  created_from?: string
  created_to?: string
  page?: number
  page_size?: number
}

export interface NotificationAdminListParams {
  scope?: NotificationScope
  team_id?: string
  user_id?: string
  type?: string
  level?: NotificationLevel
  include_expired?: boolean
  page?: number
  page_size?: number
}

export interface NotificationAdminCreateInput {
  scope: NotificationScope
  team_id?: string | null
  user_id?: string | null
  type: string
  source?: NotificationSource
  title: string
  content: string
  level?: NotificationLevel
  data?: Record<string, any> | null
  link_url?: string | null
  expires_at?: string | null
  notify_channels?: NotificationChannel[]
}

export interface NotificationReadRequest {
  notification_ids?: string[]
  mark_all?: boolean
}

export interface NotificationUnreadCount {
  total: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export const notificationsApi = {
  list: async (params: NotificationListParams): Promise<PaginatedResponse<NotificationItem>> => {
    return api.get('/notifications', { params })
  },

  unreadCount: async (): Promise<NotificationUnreadCount> => {
    return api.get('/notifications/unread-count')
  },

  markRead: async (payload: NotificationReadRequest): Promise<{ updated: number }> => {
    return api.post('/notifications/read', payload)
  },

  adminList: async (params: NotificationAdminListParams): Promise<PaginatedResponse<NotificationItem>> => {
    return api.get('/admin/notifications', { params })
  },

  adminCreate: async (payload: NotificationAdminCreateInput): Promise<NotificationItem> => {
    return api.post('/admin/notifications', payload)
  },

  adminDelete: async (id: string): Promise<{ id: string }> => {
    return api.delete(`/admin/notifications/${id}`)
  },
}
