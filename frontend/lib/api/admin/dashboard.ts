import { api } from '../client'
import type {
  DashboardStats,
  DashboardTrends,
  TopAgent,
  TeamTokenUsage,
  WorkflowSummary,
  ModelDistribution,
} from '../dashboard'

export type {
  DashboardStats,
  DashboardTrends,
  TopAgent,
  TeamTokenUsage,
  WorkflowSummary,
  ModelDistribution,
}

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> =>
    api.get<DashboardStats>('/admin/dashboard/stats'),

  getTrends: async (period: '7d' | '30d' | '90d' | 'all' = '30d'): Promise<DashboardTrends> =>
    api.get<DashboardTrends>(`/admin/dashboard/stats/trends?period=${period}`),

  getTopAgents: async (params: {
    limit?: number
    metric?: 'conversation_count' | 'message_count' | 'total_tokens'
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<TopAgent[]> => {
    const queryParams = new URLSearchParams({
      limit: String(params.limit || 10),
      metric: params.metric || 'conversation_count',
      time_range: params.time_range || '30d',
    })
    return api.get<TopAgent[]>(`/admin/dashboard/stats/agents/top?${queryParams}`)
  },

  getTeamTokenUsage: async (params: {
    limit?: number
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<TeamTokenUsage[]> => {
    const queryParams = new URLSearchParams({
      limit: String(params.limit || 10),
      time_range: params.time_range || '30d',
    })
    return api.get<TeamTokenUsage[]>(`/admin/dashboard/stats/teams/token-usage?${queryParams}`)
  },

  getWorkflowSummary: async (params: {
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<WorkflowSummary> => {
    const queryParams = new URLSearchParams({
      time_range: params.time_range || '30d',
    })
    return api.get<WorkflowSummary>(`/admin/dashboard/stats/workflows/summary?${queryParams}`)
  },

  getModelDistribution: async (params: {
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<ModelDistribution[]> => {
    const queryParams = new URLSearchParams({
      time_range: params.time_range || '30d',
    })
    return api.get<ModelDistribution[]>(`/admin/dashboard/stats/models/distribution?${queryParams}`)
  },
}
