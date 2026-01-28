import { api } from './client'

// ============ Dashboard Types ============

export interface DashboardStats {
  overview: {
    total_users: number
    total_teams: number
    total_agents: number
    total_workflows: number
    total_knowledge_bases: number
    total_conversations: number
    total_messages: number
    total_tokens: number
  }
  active_users: {
    dau: number
    wau: number
    mau: number
  }
  growth: {
    new_users_30d: number
    new_conversations_30d: number
  }
}

export interface DashboardTrends {
  period: string
  data: Array<{
    date: string
    new_users: number
    active_users: number
    new_conversations: number
    messages: number
    tokens: number
  }>
}

// ============ Dashboard API ============

export const dashboardApi = {
  /**
   * 获取全站统计数据
   */
  getStats: async (): Promise<DashboardStats> => {
    return api.get<DashboardStats>('/dashboard/stats')
  },

  /**
   * 获取全站趋势数据
   */
  getTrends: async (period: '7d' | '30d' = '30d'): Promise<DashboardTrends> => {
    return api.get<DashboardTrends>(`/dashboard/stats/trends?period=${period}`)
  },
}
