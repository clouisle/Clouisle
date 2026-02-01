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
  getTrends: async (period: '7d' | '30d' | '90d' | 'all' = '30d'): Promise<DashboardTrends> => {
    return api.get<DashboardTrends>(`/dashboard/stats/trends?period=${period}`)
  },

  /**
   * 获取 Agent 使用排行
   */
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
    return api.get<TopAgent[]>(`/dashboard/stats/agents/top?${queryParams}`)
  },

  /**
   * 获取团队 Token 消耗排行
   */
  getTeamTokenUsage: async (params: {
    limit?: number
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<TeamTokenUsage[]> => {
    const queryParams = new URLSearchParams({
      limit: String(params.limit || 10),
      time_range: params.time_range || '30d',
    })
    return api.get<TeamTokenUsage[]>(`/dashboard/stats/teams/token-usage?${queryParams}`)
  },

  /**
   * 获取工作流统计摘要
   */
  getWorkflowSummary: async (params: {
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<WorkflowSummary> => {
    const queryParams = new URLSearchParams({
      time_range: params.time_range || '30d',
    })
    return api.get<WorkflowSummary>(`/dashboard/stats/workflows/summary?${queryParams}`)
  },

  /**
   * 获取模型使用分布
   */
  getModelDistribution: async (params: {
    time_range?: '7d' | '30d' | '90d' | 'all'
  } = {}): Promise<ModelDistribution[]> => {
    const queryParams = new URLSearchParams({
      time_range: params.time_range || '30d',
    })
    return api.get<ModelDistribution[]>(`/dashboard/stats/models/distribution?${queryParams}`)
  },
}
