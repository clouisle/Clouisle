import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getAgentDetail = mock(() => Promise.resolve({
  agent: { agent_id: 'agent-1', agent_name: 'Agent One', request_count: 12, error_count: 1, timeout_count: 1, success_rate: 91, timeout_rate: 6, ttft_p95_ms: 3200, p50_ms: 100, p90_ms: 200, p95_ms: 300, p99_ms: 400, total_tokens: 1200, avg_tokens: 100 },
  trend: [{ bucket: '2026-01-01T00:00:00Z', request_count: 12, p95_ms: 300 }],
}))
const getWorkflowDetail = mock(() => Promise.resolve({
  workflow: { workflow_id: 'workflow-1', workflow_name: 'Workflow One', run_count: 8, error_count: 0, timeout_count: 1, success_rate: 98, timeout_rate: 2, failed_nodes: 1, p50_ms: 100, p90_ms: 200, p95_ms: 300, p99_ms: null, total_tokens: 900, avg_nodes: null },
  trend: [],
  nodes: [{ node_type: 'llm', execution_count: 8, failed_count: 1, avg_duration_ms: 1250 }],
}))
const translate = (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key
const component = (tag: string) => {
  function MockComponent({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
  return MockComponent
}
const icon = () => null

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => translate }))
mock.module('lucide-react', () => ({ AlertTriangle: icon, ChevronRight: icon, Cpu: icon, Database: icon, HardDrive: icon, Info: icon, Server: icon, Workflow: icon }))
mock.module('recharts', () => ({
  Area: component('area'), AreaChart: component('area-chart'), Bar: component('bar'), BarChart: component('bar-chart'),
  CartesianGrid: component('grid'), Legend: component('legend'), Line: component('line'), LineChart: component('line-chart'),
  ResponsiveContainer: component('responsive-container'), Tooltip: component('tooltip'), XAxis: component('x-axis'), YAxis: component('y-axis'),
}))
mock.module('@/components/ui/alert', () => ({ Alert: component('div'), AlertDescription: component('div'), AlertTitle: component('div') }))
mock.module('@/components/ui/badge', () => ({ Badge: component('span') }))
mock.module('@/components/ui/button', () => ({ Button: component('button') }))
mock.module('@/components/ui/card', () => ({ Card: component('section'), CardContent: component('div'), CardDescription: component('div'), CardHeader: component('header'), CardTitle: component('h2') }))
mock.module('@/components/ui/sheet', () => ({ Sheet: component('sheet'), SheetContent: component('div'), SheetDescription: component('div'), SheetHeader: component('header'), SheetTitle: component('h2') }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: component('span') }))
mock.module('@/components/ui/table', () => ({ Table: component('table'), TableBody: component('tbody'), TableCell: component('td'), TableHead: component('th'), TableHeader: component('thead'), TableRow: component('tr') }))
mock.module('@/lib/api/admin/observability', () => ({ observabilityApi: { getAgentDetail, getWorkflowDetail } }))

const panels = await import('./observability-panels')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function render(element: React.ReactElement) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(element) })
  return renderer!
}

function text(renderer: ReactTestRenderer) {
  return renderer.root.findAll(() => true).flatMap((node) => node.children.filter((child): child is string => typeof child === 'string')).join('|')
}

function emptyCount(renderer: ReactTestRenderer) {
  return renderer.root.findAll((node) => node.type === 'div' && node.children.length === 1 && node.children[0] === 'states.emptyTitle').length
}

function unmount(renderer: ReactTestRenderer) {
  act(() => renderer.unmount())
}

afterEach(() => mock.clearAllMocks())

test('renders table and chart loading skeleton layouts', () => {
  const table = render(<panels.ObservabilitySkeleton tab="agents" />)
  const chart = render(<panels.ObservabilitySkeleton tab="overview" />)
  expect(table.root.findAllByType('span')).toHaveLength(5)
  expect(chart.root.findAllByType('span')).toHaveLength(6)
  unmount(table)
  unmount(chart)
})

test('exposes the error retry boundary', () => {
  const retry = mock(() => {})
  const renderer = render(<panels.ErrorState onRetry={retry} />)
  expect(text(renderer)).toContain('states.errorDescription')
  act(() => renderer.root.findByType('button').props.onClick())
  expect(retry).toHaveBeenCalledTimes(1)
  unmount(renderer)
})

test('uses the shared empty state when panel data is absent', () => {
  const renderers = [
    render(<panels.OverviewPanel overview={null} throughput={null} />),
    render(<panels.HealthPanel health={null} trend={null} slowQueries={null} workers={null} />),
    render(<panels.TimeoutsPanel data={null} />),
    render(<panels.ThroughputPanel throughput={null} />),
    render(<panels.TokensPanel tokens={null} />),
    render(<panels.WorkersPanel workers={null} />),
  ]
  expect(renderers.every((renderer) => text(renderer).includes('states.emptyTitle'))).toBe(true)
  renderers.forEach(unmount)
})

test('renders overview data and empty or populated request trends at risk boundaries', () => {
  const overview = {
    cache_ttl_seconds: 60,
    rates: { timeout_rate: 5, overall_success_rate: 94 },
    latency: { p50_ms: 100, p90_ms: 500, p95_ms: 10000, p99_ms: 31000 },
    ttft: { p95_ms: 3000 },
    totals: { total_requests: 15, agent_requests: 10, workflow_runs: 5, total_tokens: 1500 },
    throughput: { current_qps: 2, peak_hourly_requests: 20 },
  }
  const empty = render(<panels.OverviewPanel overview={overview} throughput={{ buckets: [] }} />)
  expect(text(empty)).toContain('risk.critical')
  expect(text(empty)).toContain('1.5K')
  expect(emptyCount(empty)).toBeGreaterThan(0)

  const healthy = { ...overview, rates: { timeout_rate: 0, overall_success_rate: 100 }, latency: { ...overview.latency, p95_ms: 100 }, ttft: null }
  const populated = render(<panels.OverviewPanel overview={healthy} throughput={{ buckets: [{ bucket: 'bad-date', agent_requests: 1, workflow_runs: 2 }] }} />)
  expect(text(populated)).toContain('risk.healthy')
  expect(populated.root.findAllByType('area-chart')).toHaveLength(1)
  unmount(empty)
  unmount(populated)
})

test('renders health dependency boundaries, worker failure, and slow-query rows', () => {
  const health = {
    cpu: { status: 'healthy', usage_percent: 12 }, memory: { status: 'warning', usage_percent: '75' },
    disk: { status: 'danger', usage_percent: 91 }, database: { status: 'healthy', active_connections: 4 },
    redis: { status: 'unknown', ops_per_sec: 0 },
    workers: { status: 'unhealthy', worker_count: 0, active_tasks: 0, reserved_tasks: 0, scheduled_tasks: 0, queues: [], tasks: [], error: 'offline' },
  }
  const slowQueries = { available: true, reason: null, total: 1, page: 1, page_size: 10, items: [{ statement: 'select 1', calls: '2', mean_time: 1200, total_time: 2400 }] }
  const renderer = render(<panels.HealthPanel health={health} trend={{ items: [] }} workers={null} slowQueries={slowQueries} />)
  expect(text(renderer)).toContain('offline')
  expect(text(renderer)).toContain('select 1')
  expect(text(renderer)).toContain('1.2s')
  expect(emptyCount(renderer)).toBeGreaterThan(0)
  unmount(renderer)
})

test('renders agent rows and opens detail at keyboard boundaries', async () => {
  const row = { agent_id: 'agent-1', agent_name: '', team_name: null, request_count: 12, error_count: 1, timeout_count: 1, success_rate: 91, timeout_rate: 6, ttft_p95_ms: 3200, p50_ms: 100, p90_ms: 200, p95_ms: 300, p99_ms: null, total_tokens: 1200 }
  const renderer = render(<panels.AgentsPanel rows={[row]} timeRange="30d" />)
  const tableRow = renderer.root.findAllByType('tr').find((node) => node.props.role === 'button')!
  const preventDefault = mock(() => {})
  act(() => tableRow.props.onKeyDown({ key: 'Escape', preventDefault }))
  expect(getAgentDetail).not.toHaveBeenCalled()
  await act(async () => tableRow.props.onKeyDown({ key: 'Enter', preventDefault }))
  expect(preventDefault).toHaveBeenCalled()
  expect(getAgentDetail).toHaveBeenCalledWith('agent-1', '30d')
  expect(text(renderer)).toContain('Agent One')
  unmount(renderer)
})

test('renders workflow details from a row click, including nodes and empty trend', async () => {
  const row = { workflow_id: 'workflow-1', workflow_name: '', team_name: null, run_count: 8, error_count: 0, timeout_count: 1, success_rate: 98, timeout_rate: 2, failed_nodes: 1, p50_ms: 100, p90_ms: 200, p95_ms: 300, p99_ms: null, total_tokens: 900 }
  const renderer = render(<panels.WorkflowsPanel rows={[row]} timeRange="7d" />)
  const tableRow = renderer.root.findAllByType('tr').find((node) => node.props.role === 'button')!
  await act(async () => tableRow.props.onClick())
  expect(getWorkflowDetail).toHaveBeenCalledWith('workflow-1', '7d')
  expect(text(renderer)).toContain('Workflow One')
  expect(text(renderer)).toContain('llm')
  expect(text(renderer)).toContain('1.3s')
  expect(emptyCount(renderer)).toBeGreaterThan(0)
  unmount(renderer)
})

test('shows empty entity tables without opening details', () => {
  const agents = render(<panels.AgentsPanel rows={[]} timeRange="30d" />)
  const workflows = render(<panels.WorkflowsPanel rows={[]} timeRange="30d" />)
  expect(emptyCount(agents)).toBeGreaterThan(0)
  expect(emptyCount(workflows)).toBeGreaterThan(0)
  unmount(agents)
  unmount(workflows)
})

test('renders timeout availability, distribution, event, and empty boundaries', () => {
  const renderer = render(<panels.TimeoutsPanel data={{
    total: 2, page: 1, page_size: 10, agent_timeout_type_available: false, note: 'limited', distribution: { workflow: 2, custom: 1 },
    items: [{ source: 'workflow', entity_id: null, entity_name: 'Flow', model: null, timeout_type: 'global', created_at: null, duration_ms: null, status: 'timeout' }],
  }} />)
  expect(text(renderer)).toContain('limited')
  expect(text(renderer)).toContain('Flow')
  expect(text(renderer)).toContain('timeoutTypes.global')
  expect(text(renderer)).toContain('status.timeout')
  unmount(renderer)

  const empty = render(<panels.TimeoutsPanel data={{ total: 0, page: 1, page_size: 10, agent_timeout_type_available: true, note: '', distribution: {}, items: [] }} />)
  expect(emptyCount(empty)).toBeGreaterThan(0)
  expect(text(empty)).toContain('status.success')
  unmount(empty)
})

test('renders throughput chart data and its empty chart boundary', () => {
  const populated = render(<panels.ThroughputPanel throughput={{ current: { qps: 3, tps: 4, running_workflows: 1 }, buckets: [{ bucket: '2026-01-01', agent_requests: 2, workflow_runs: 1, total_requests: 3 }] }} />)
  expect(text(populated)).toContain('3')
  expect(populated.root.findAllByType('bar-chart')).toHaveLength(1)
  const empty = render(<panels.ThroughputPanel throughput={{ current: { qps: 0, tps: 0, running_workflows: 0 }, buckets: [] }} />)
  expect(emptyCount(empty)).toBeGreaterThan(0)
  unmount(populated)
  unmount(empty)
})

test('renders token source/model data and both empty-list boundaries', () => {
  const populated = render(<panels.TokensPanel tokens={{ total_tokens: 3000, by_source: [{ source: 'workflow', tokens: 1500 }, { source: 'agent', tokens: 1000 }, { source: 'other', tokens: 500 }], by_model: [{ model: 'model-a', tokens: 3000 }] }} />)
  expect(text(populated)).toContain('model-a')
  expect(text(populated)).toContain('sources.other')
  expect(text(populated)).toContain('3K')
  const empty = render(<panels.TokensPanel tokens={{ total_tokens: 0, by_source: [], by_model: [] }} />)
  expect(emptyCount(empty)).toBe(2)
  expect(text(empty)).toContain('throughput.noTokenData')
  unmount(populated)
  unmount(empty)
})

test('renders task backlog with resume workflow and handles duplicate task names gracefully', () => {
  const renderer = render(<panels.WorkersPanel workers={{ status: 'error', worker_count: 2, active_tasks: 1, reserved_tasks: 2, scheduled_tasks: 3, queues: [{ queue: 'default', pending: 2 }, { queue: 'knowledge', pending: 4 }, { queue: 'workflow', pending: 0 }, { queue: 'sandbox', pending: 0 }], tasks: [{ task: 'app.tasks.knowledge_base.embed_document_chunks_task', queue: 'knowledge', pending: 4 }, { task: 'send_notification_email', queue: 'default', pending: 2 }, { task: 'app.tasks.workflow.run_workflow_task', queue: 'workflow', pending: 1 }, { task: 'app.tasks.workflow.resume_workflow_task', queue: 'workflow', pending: 2 }, { task: 'app.tasks.agent.run_agent_task', queue: 'default', pending: 3 }, { task: 'run_agent_task', queue: 'default', pending: 1 }], error: 'broker down' }} />)
  expect(text(renderer)).toContain('broker down')
  expect(text(renderer)).toContain('workers.tasks.embedDocumentChunks')
  expect(text(renderer)).toContain('workers.tasks.sendEmailNotification')
  expect(text(renderer)).toContain('workers.tasks.runWorkflow')
  expect(text(renderer)).toContain('workers.tasks.resumeWorkflow')
  expect(text(renderer)).toContain('workers.tasks.runAgentTask')
  expect(text(renderer)).toContain('status.error')
  unmount(renderer)
})

test('renders slow-query missing, unavailable, empty, and populated states', () => {
  const missing = render(<panels.SlowQueriesPanel slowQueries={null} />)
  expect(emptyCount(missing)).toBe(1)
  const unavailable = render(<panels.SlowQueriesPanel slowQueries={{ available: false, reason: 'extension missing', total: 0, page: 1, page_size: 10, items: [] }} />)
  expect(text(unavailable)).toContain('extension missing')
  const empty = render(<panels.SlowQueriesPanel slowQueries={{ available: true, reason: null, total: 0, page: 1, page_size: 10, items: [] }} />)
  expect(text(empty)).toContain('health.noSlowQueries')
  const populated = render(<panels.SlowQueriesPanel slowQueries={{ available: true, reason: null, total: 1, page: 1, page_size: 10, items: [{ query: 'select now()', calls: 3, avg_ms: 2, total_ms: 6 }] }} />)
  expect(text(populated)).toContain('select now()')
  ;[missing, unavailable, empty, populated].forEach(unmount)
})
