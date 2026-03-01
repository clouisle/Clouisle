import { api } from '../client'
import type {
  AdminConversationListItem,
  AdminConversationWithMessages,
  ConversationStats,
  ConversationTrends,
  AdminConversationQueryParams,
} from '../agents'

export type {
  AdminConversationListItem,
  AdminConversationWithMessages,
  ConversationStats,
  ConversationTrends,
  AdminConversationQueryParams,
}

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export const conversationsApi = {
  listAll: async (params: AdminConversationQueryParams): Promise<PageData<AdminConversationListItem>> =>
    api.get('/admin/conversations', { params }),

  getStats: async (params?: { team_id?: string }): Promise<ConversationStats> =>
    api.get('/admin/conversations/stats', { params }),

  getTrends: async (params?: { team_id?: string; period?: '7d' | '30d' }): Promise<ConversationTrends> =>
    api.get('/admin/conversations/stats/trends', { params }),

  getDetail: async (id: string): Promise<AdminConversationWithMessages> =>
    api.get(`/admin/conversations/${id}`),

  delete: async (id: string): Promise<{ id: string }> =>
    api.delete(`/admin/conversations/${id}`),

  batchDelete: async (ids: string[]): Promise<{ deleted_count: number; ids: string[] }> => {
    const params = new URLSearchParams()
    ids.forEach(id => params.append('ids', id))
    return api.delete(`/admin/conversations?${params.toString()}`)
  },
}
