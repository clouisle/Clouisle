import type { TimeRange } from '@/components/dashboard/time-range-selector'
import { api } from '../client'

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
  password_expiration?: {
    expired_count: number
    expiring_soon_count: number
    force_change_count: number
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

export interface DashboardActivitySummary {
  conversations: number
  messages: number
  tokens: number
}


export interface TopAgent {
  agent_id: string
  name: string
  icon: string | null
  value: number
  team_name: string
}

export interface TeamTokenUsage {
  team_id: string
  name: string
  total_tokens: number
  conversations: number
  messages: number
}

export interface WorkflowSummary {
  total_runs: number
  success_rate: number
  avg_duration_ms: number
  trigger_type_distribution: Array<{ type: string; count: number }>
  status_distribution: Array<{ status: string; count: number }>
  top_workflows: Array<{
    workflow_id: string
    name: string
    run_count: number
    success_rate: number
  }>
}

export interface ModelDistribution {
  model: string
  count: number
  percentage: number
}

function normalizeModelDistribution(data: unknown): ModelDistribution[] {
  const payload = Array.isArray(data)
    ? data
    : data && typeof data === 'object' && 'items' in data && Array.isArray((data as { items?: unknown }).items)
      ? (data as { items: unknown[] }).items
      : []

  return payload
    .map((item) => {
      const record = item as Record<string, unknown>
      const count = Number(record.count ?? record.usage_count ?? record.token_usage ?? 0)
      const percentageValue = Number(record.percentage ?? 0)

      return {
        model: String(record.model ?? record.model_name ?? record.model_used ?? '').trim(),
        count,
        percentage: Number.isFinite(percentageValue)
          ? percentageValue > 0 && percentageValue <= 1
            ? percentageValue * 100
            : percentageValue
          : 0,
      }
    })
    .filter((item) => item.count > 0)
}

function appendTimeRange(query: URLSearchParams, key: 'period' | 'time_range', range: TimeRange) {
  query.set(key, typeof range === 'string' ? range : 'custom')
  if (typeof range === 'object') {
    query.set('start_time', range.start_time)
    query.set('end_time', range.end_time)
  }
}

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> =>
    api.get<DashboardStats>('/admin/dashboard/stats'),

  getTrends: async (period: TimeRange = '30d'): Promise<DashboardTrends> => {
    const queryParams = new URLSearchParams()
    appendTimeRange(queryParams, 'period', period)
    return api.get<DashboardTrends>(`/admin/dashboard/stats/trends?${queryParams}`)
  },

  getTopAgents: async (params: {
    limit?: number
    metric?: 'conversation_count' | 'message_count' | 'total_tokens'
    time_range?: TimeRange
  } = {}): Promise<TopAgent[]> => {
    const queryParams = new URLSearchParams({
      limit: String(params.limit || 10),
      metric: params.metric || 'conversation_count',
    })
    appendTimeRange(queryParams, 'time_range', params.time_range ?? '30d')
    return api.get<TopAgent[]>(`/admin/dashboard/stats/agents/top?${queryParams}`)
  },

  getTeamTokenUsage: async (params: {
    limit?: number
    time_range?: TimeRange
  } = {}): Promise<TeamTokenUsage[]> => {
    const queryParams = new URLSearchParams({
      limit: String(params.limit || 10),
    })
    appendTimeRange(queryParams, 'time_range', params.time_range ?? '30d')
    return api.get<TeamTokenUsage[]>(`/admin/dashboard/stats/teams/token-usage?${queryParams}`)
  },

  getWorkflowSummary: async (params: {
    time_range?: TimeRange
  } = {}): Promise<WorkflowSummary> => {
    const queryParams = new URLSearchParams()
    appendTimeRange(queryParams, 'time_range', params.time_range ?? '30d')
    return api.get<WorkflowSummary>(`/admin/dashboard/stats/workflows/summary?${queryParams}`)
  },

  getModelDistribution: async (params: {
    time_range?: TimeRange
  } = {}): Promise<ModelDistribution[]> => {
    const queryParams = new URLSearchParams()
    appendTimeRange(queryParams, 'time_range', params.time_range ?? '30d')
    const data = await api.get<unknown>(`/admin/dashboard/stats/models/distribution?${queryParams}`)
    return normalizeModelDistribution(data)
  },
}
