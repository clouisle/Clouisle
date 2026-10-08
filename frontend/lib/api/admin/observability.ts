import { api } from '../client'

export type ObservabilityPeriod = '15m' | '1h' | '24h' | '7d'
export type ObservabilityState = 'fresh' | 'partial' | 'stale' | 'unavailable' | 'no_data'
export type ObservabilitySource = 'agent' | 'workflow'

export interface ObservabilityMeta {
  window_start: string
  window_end: string
  sampled_at: string
  period: ObservabilityPeriod | string
  state: ObservabilityState
  sample_count: number
}

export interface TrendPoint {
  bucket: string
  submitted: number
  completed: number
  failed: number
  tokens: number
  p95_ms: number | null
  first_token_p95_ms: number | null
}

export interface ObservabilityIssue {
  kind: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  affected_count: number
  href: string
}

export interface SummaryResponse {
  meta: ObservabilityMeta
  agents: { submitted: number; completed: number; failed: number; success_rate: number | null; p50_ms: number | null; p95_ms: number | null; first_token_p95_ms: number | null; tokens: number }
  workflows: { submitted: number; completed: number; failed: number; success_rate: number | null; p50_ms: number | null; p95_ms: number | null; tokens: number }
  trend: TrendPoint[]
  issues: ObservabilityIssue[]
}

export interface RunSummary {
  run_id: string
  source: ObservabilitySource
  resource_id: string
  resource_name: string
  team_id: string | null
  team_name: string | null
  status: string
  submitted_at: string | null
  started_at: string | null
  message_started_at: string | null
  worker_bootstrap_ms: number | null
  finished_at: string | null
  queue_duration_ms: number | null
  execution_duration_ms: number | null
  total_duration_ms: number | null
  first_token_ms: number | null
  total_tokens: number | null
  error_category: string | null
  error_code: string | null
  trace_available: boolean
  trace_complete: boolean
}

export interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  kind: string
  name: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  attempt: number | null
  model: string | null
  tool: string | null
  error_category: string | null
  token_usage: Record<string, number> | null
  metadata: Record<string, unknown>
}

export interface RunDetailResponse {
  run: RunSummary
  spans: TraceSpan[]
  trace: { complete: boolean; expired: boolean; truncated: boolean; recorded_count: number }
  meta: ObservabilityMeta
}

export interface RunsResponse {
  items: RunSummary[]
  next_cursor: string | null
  meta: ObservabilityMeta
}

export interface DependencyRow {
  name: string
  requests: number
  completed: number
  failed: number
  success_rate: number | null
  p50_ms: number | null
  p95_ms: number | null
  first_token_p95_ms: number | null
  tokens: number | null
  sample_count: number
}

export interface ModelDependencyRow extends DependencyRow {
  id: string
  provider: string | null
  provider_display_name: string | null
}

export interface DependenciesResponse {
  meta: ObservabilityMeta
  models: ModelDependencyRow[]
  tools: DependencyRow[]
  retrieval: DependencyRow[]
}

export interface WorkerRow {
  worker_id: string
  status: string
  queues: string[]
  last_heartbeat: string | null
  active_tasks: number | null
  reserved_tasks: number | null
  scheduled_tasks: number | null
}

export interface QueueTrendPoint { bucket: string; pending: number | null }

export interface QueueRow {
  name: string
  consumers: number | null
  pending: number | null
  oldest_wait_ms: number | null
  observed_at: string | null
  state: 'healthy' | 'warning' | 'unavailable' | 'unknown'
  trend: QueueTrendPoint[]
}

export interface QueuesResponse { meta: ObservabilityMeta; workers: WorkerRow[]; queues: QueueRow[] }

export interface InstanceRow {
  instance_id: string
  name: string
  role: 'api'
  metric_scope: 'host'
  cpu_percent: number | null
  memory_percent: number | null
  observed_at: string | null
  state: 'healthy' | 'warning' | 'unavailable' | 'stale' | 'offline'
}

export interface InfrastructureDependency {
  name: string
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown'
  observed_at: string | null
  latency_ms: number | null
  detail: string | null
}

export interface SlowQuery {
  query_id: string
  query: string
  calls: number
  mean_ms: number
  max_ms: number
  total_ms: number
}

export interface InfrastructureResponse {
  meta: ObservabilityMeta
  instances: InstanceRow[]
  dependencies: InfrastructureDependency[]
  slow_queries: { available: boolean; reset_at: string | null; items: SlowQuery[] }
}

export interface AlertEvent {
  id: string
  rule_id: string
  kind: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  affected_count: number
  status: 'active' | 'resolved'
  opened_at: string
  resolved_at: string | null
  acknowledged_at: string | null
  silenced_until: string | null
}

export interface AlertRule {
  id: string
  name: string
  threshold: number
  enabled: boolean
  evaluation_window_seconds: number
  recovery_window_seconds: number
  updated_at: string | null
}

export interface AlertsResponse { items: AlertEvent[]; next_cursor: string | null; meta: ObservabilityMeta }

function withParams(path: string, params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') query.set(key, String(value))
  })
  const serialized = query.toString()
  return serialized ? `${path}?${serialized}` : path
}

export const observabilityApi = {
  getSummary: (params: { period?: ObservabilityPeriod; team_id?: string } = {}): Promise<SummaryResponse> =>
    api.get<SummaryResponse>(withParams('/admin/observability/summary', params)),
  getRuns: (params: { period?: ObservabilityPeriod; team_id?: string; source?: 'all' | ObservabilitySource; status?: string; error_category?: string; run_id?: string; cursor?: string; limit?: number } = {}): Promise<RunsResponse> =>
    api.get<RunsResponse>(withParams('/admin/observability/runs', params)),
  getRun: (source: ObservabilitySource, runId: string): Promise<RunDetailResponse> =>
    api.get<RunDetailResponse>(`/admin/observability/runs/${source}/${encodeURIComponent(runId)}`),
  getDependencies: (params: { period?: ObservabilityPeriod; team_id?: string } = {}): Promise<DependenciesResponse> =>
    api.get<DependenciesResponse>(withParams('/admin/observability/dependencies', params)),
  getQueues: (): Promise<QueuesResponse> => api.get<QueuesResponse>('/admin/observability/queues'),
  getInfrastructure: (): Promise<InfrastructureResponse> => api.get<InfrastructureResponse>('/admin/observability/infrastructure'),
  getAlerts: (params: { status?: 'active' | 'resolved' | 'all'; cursor?: string; limit?: number } = {}): Promise<AlertsResponse> =>
    api.get<AlertsResponse>(withParams('/admin/observability/alerts', params)),
  getAlertRules: (): Promise<AlertRule[]> => api.get<AlertRule[]>('/admin/observability/alerts/rules'),
  acknowledgeAlert: (id: string): Promise<AlertEvent> => api.post<AlertEvent>(`/admin/observability/alerts/${encodeURIComponent(id)}/acknowledge`, {}),
  silenceAlert: (id: string, duration_seconds: number): Promise<AlertEvent> =>
    api.post<AlertEvent>(withParams(`/admin/observability/alerts/${encodeURIComponent(id)}/silence`, { duration_seconds }), {}),
  updateAlertRule: (id: string, rule: Pick<AlertRule, 'threshold' | 'enabled' | 'evaluation_window_seconds' | 'recovery_window_seconds'>): Promise<AlertRule> =>
    api.put<AlertRule>(`/admin/observability/alerts/rules/${encodeURIComponent(id)}`, rule),
}
