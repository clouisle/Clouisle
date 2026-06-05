import { api } from '../client'

export type ObservabilityTimeRange = '7d' | '30d' | '90d' | 'all'
export type ObservabilitySortOrder = 'asc' | 'desc'

export interface ObservabilityPercentiles {
  p50_ms: number | null
  p90_ms: number | null
  p95_ms: number | null
  p99_ms?: number | null
}

export interface ObservabilityOverview {
  time_range: ObservabilityTimeRange
  generated_at: string
  cache_ttl_seconds: number
  totals: {
    agent_requests: number
    workflow_runs: number
    total_requests: number
    total_tokens: number
  }
  rates: {
    agent_success_rate: number
    workflow_success_rate: number
    overall_success_rate: number
    timeout_rate: number
  }
  latency: ObservabilityPercentiles
  ttft?: ObservabilityPercentiles
  throughput: {
    current_qps: number
    peak_hourly_requests: number
  }
}

export interface ObservabilityPage<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  time_range?: ObservabilityTimeRange
}

export interface AgentPerformanceRow extends ObservabilityPercentiles {
  agent_id: string
  agent_name: string | null
  team_name: string | null
  request_count: number
  success_count: number
  error_count: number
  timeout_count: number
  total_tokens: number
  ttft_p50_ms?: number | null
  ttft_p90_ms?: number | null
  ttft_p95_ms?: number | null
  ttft_p99_ms?: number | null
  success_rate: number
  timeout_rate: number
  avg_tokens: number
}

export interface WorkflowPerformanceRow extends ObservabilityPercentiles {
  workflow_id: string
  workflow_name: string | null
  team_name: string | null
  run_count: number
  success_count: number
  error_count: number
  timeout_count: number
  failed_nodes: number
  avg_nodes: number | null
  total_tokens: number
  success_rate: number
  timeout_rate: number
  avg_tokens: number
}

export interface ObservabilityTrendPoint {
  bucket: string
  request_count?: number
  run_count?: number
  p50_ms?: number | null
  p90_ms?: number | null
  p95_ms?: number | null
  ttft_p95_ms?: number | null
  success_rate?: number
  timeout_count?: number
  failed_nodes?: number
}

export interface AgentDetailResponse {
  time_range: ObservabilityTimeRange
  agent: AgentPerformanceRow | null
  trend: ObservabilityTrendPoint[]
}

export interface WorkflowDetailResponse {
  time_range: ObservabilityTimeRange
  workflow: WorkflowPerformanceRow | null
  trend: ObservabilityTrendPoint[]
  nodes: Array<{
    node_type: string
    execution_count: number
    failed_count: number
    avg_duration_ms: number | null
  }>
}

export interface TimeoutEvent {
  source: 'agent' | 'workflow'
  entity_id: string | null
  entity_name: string
  model: string | null
  timeout_type: string
  created_at: string | null
  duration_ms: number | null
  status: string | null
}

export interface TimeoutResponse extends ObservabilityPage<TimeoutEvent> {
  distribution: Record<string, number>
  agent_timeout_type_available: boolean
  note: string
}

export interface ThroughputResponse {
  time_range: ObservabilityTimeRange
  granularity: string
  current: {
    qps: number
    tps: number
    running_workflows: number
  }
  buckets: Array<{
    bucket: string
    agent_requests: number
    workflow_runs: number
    total_requests: number
  }>
}

export interface TokenResponse {
  time_range: ObservabilityTimeRange
  total_tokens: number
  by_source: Array<{ source: string; tokens: number }>
  by_model: Array<{ model: string; tokens: number }>
}

export interface SystemHealthResponse {
  generated_at: string
  cache_ttl_seconds: number
  cpu: Record<string, unknown>
  memory: Record<string, unknown>
  disk: Record<string, unknown>
  database: Record<string, unknown>
  redis: Record<string, unknown>
  workers: WorkerResponse
}

export interface SystemTrendResponse {
  items: Array<Record<string, unknown>>
}

export interface SlowQueriesResponse {
  available: boolean
  reason: string | null
  items: Array<Record<string, unknown>>
  total: number
  page: number
  page_size: number
}

export interface WorkerResponse {
  status: string
  worker_count: number
  active_tasks: number
  reserved_tasks: number
  scheduled_tasks: number
  queues: Array<{ queue: string; pending: number }>
  error?: string
}

function withParams(path: string, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      query.set(key, String(value))
    }
  })
  const serialized = query.toString()
  return serialized ? `${path}?${serialized}` : path
}

export const observabilityApi = {
  getOverview: (timeRange: ObservabilityTimeRange = '30d'): Promise<ObservabilityOverview> =>
    api.get<ObservabilityOverview>(withParams('/admin/observability/overview', { time_range: timeRange })),

  getAgents: (params: {
    time_range?: ObservabilityTimeRange
    page?: number
    page_size?: number
    sort_by?: string
    sort_order?: ObservabilitySortOrder
  } = {}): Promise<ObservabilityPage<AgentPerformanceRow>> =>
    api.get<ObservabilityPage<AgentPerformanceRow>>(withParams('/admin/observability/agents', params)),

  getAgentDetail: (agentId: string, timeRange: ObservabilityTimeRange = '30d'): Promise<AgentDetailResponse> =>
    api.get<AgentDetailResponse>(withParams(`/admin/observability/agent/${agentId}`, { time_range: timeRange })),

  getWorkflows: (params: {
    time_range?: ObservabilityTimeRange
    page?: number
    page_size?: number
    sort_by?: string
    sort_order?: ObservabilitySortOrder
  } = {}): Promise<ObservabilityPage<WorkflowPerformanceRow>> =>
    api.get<ObservabilityPage<WorkflowPerformanceRow>>(withParams('/admin/observability/workflows', params)),

  getWorkflowDetail: (workflowId: string, timeRange: ObservabilityTimeRange = '30d'): Promise<WorkflowDetailResponse> =>
    api.get<WorkflowDetailResponse>(withParams(`/admin/observability/workflow/${workflowId}`, { time_range: timeRange })),

  getTimeouts: (params: {
    time_range?: ObservabilityTimeRange
    source?: 'all' | 'agent' | 'workflow'
    page?: number
    page_size?: number
  } = {}): Promise<TimeoutResponse> =>
    api.get<TimeoutResponse>(withParams('/admin/observability/timeouts', params)),

  getThroughput: (params: {
    time_range?: ObservabilityTimeRange
    granularity?: 'hour' | 'day'
  } = {}): Promise<ThroughputResponse> =>
    api.get<ThroughputResponse>(withParams('/admin/observability/throughput', params)),

  getTokens: (timeRange: ObservabilityTimeRange = '30d'): Promise<TokenResponse> =>
    api.get<TokenResponse>(withParams('/admin/observability/tokens', { time_range: timeRange })),

  getSystemHealth: (): Promise<SystemHealthResponse> =>
    api.get<SystemHealthResponse>('/admin/observability/system/health'),

  getSystemTrend: (): Promise<SystemTrendResponse> =>
    api.get<SystemTrendResponse>('/admin/observability/system/trend'),

  getSlowQueries: (params: { threshold_ms?: number; page?: number; page_size?: number } = {}): Promise<SlowQueriesResponse> =>
    api.get<SlowQueriesResponse>(withParams('/admin/observability/system/slow-queries', params)),

  getWorkers: (): Promise<WorkerResponse> =>
    api.get<WorkerResponse>('/admin/observability/system/workers'),
}
