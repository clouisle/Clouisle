import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { format } from 'date-fns'
import { enUS, zhCN } from 'date-fns/locale'
import type { DateRange } from 'react-day-picker'
import type { DependenciesResponse, InfrastructureResponse, RunDetailResponse } from '@/lib/api/admin/observability'
import enDashboard from '@/i18n/en/dashboard.json'
import zhDashboard from '@/i18n/zh/dashboard.json'
const agentRunStatuses = ['queued', 'running', 'stopping', 'completing', 'completed', 'stopped', 'failed', 'interrupted', 'waiting'] as const
let instanceLocale: 'en' | 'zh' | null = null
let canManageObservability = true
const translate = Object.assign((key: string) => {
  if (instanceLocale && (key.startsWith('infrastructure.') || key.startsWith('periods.') || key.startsWith('customRange.') || key === 'status.stale' || key === 'status.offline' || key === 'status.healthy')) {
    const messages = instanceLocale === 'en' ? enDashboard : zhDashboard
    return key.split('.').reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], messages.dashboard.observability) as string
  }
  return key
}, { has: (key: string) => key !== 'status.future_state' })

const meta: DependenciesResponse['meta'] = { window_start: '2026-10-08T10:00:00Z', window_end: '2026-10-08T11:00:00Z', sampled_at: '2026-10-08T11:00:00Z', period: '1h', state: 'fresh', sample_count: 4 }
const run = { run_id: 'failed-run', source: 'agent', resource_id: 'agent-1', resource_name: 'Support agent', team_id: 'team-1', team_name: 'Support', status: 'failed', submitted_at: '2026-10-08T10:30:00Z', started_at: '2026-10-08T10:30:01Z', message_started_at: null, worker_bootstrap_ms: null, finished_at: '2026-10-08T10:30:03Z', queue_duration_ms: 1000, execution_duration_ms: 2000, total_duration_ms: 3000, first_token_ms: null, total_tokens: 22, error_category: 'provider', error_code: 'UPSTREAM', trace_available: true, trace_complete: true }
const alert = { id: 'alert-1', rule_id: 'rule-1', kind: 'failure_rate', severity: 'critical', title: 'Failure rate elevated', detail: 'Agent failures exceeded threshold.', affected_count: 3, status: 'active', opened_at: '2026-10-08T10:45:00Z', resolved_at: null, acknowledged_at: null, silenced_until: null }
const getSummary = mock(async () => ({ meta, agents: { submitted: 4, completed: 3, failed: 1, success_rate: 0.75, p50_ms: 900, p95_ms: 1800, first_token_p95_ms: 400, tokens: 150 }, workflows: { submitted: 0, completed: 0, failed: 0, success_rate: null, p50_ms: null, p95_ms: null, tokens: 0 }, trend: [{ bucket: '2026-10-08T10:30:00Z', submitted: 4, completed: 3, failed: 1, tokens: 150, p95_ms: 1800, first_token_p95_ms: 400 }], issues: [] }))
const getRuns = mock(async () => ({ items: [run], next_cursor: 'opaque-cursor', meta }))
const getRun = mock(async () => ({
  run,
  spans: [
    { span_id: 'root', parent_span_id: null, kind: 'run', name: 'Agent execution', status: 'failed', started_at: run.started_at, finished_at: run.finished_at, duration_ms: 2000, attempt: null, model: null, tool: null, error_category: 'provider', token_usage: { total: 22 }, metadata: {} },
    { span_id: 'child', parent_span_id: 'root', kind: 'tool', name: 'HTTP request', status: 'completed', started_at: '2026-10-08T10:30:01.250Z', finished_at: '2026-10-08T10:30:01.550Z', duration_ms: 300, attempt: null, model: null, tool: 'http', error_category: null, token_usage: { total: 5 }, metadata: {} },
  ],
  trace: { complete: false, expired: false, truncated: true, recorded_count: 2 },
  meta,
}))
const getDependencies = mock(async (): Promise<DependenciesResponse> => ({ meta, models: [{ id: 'model-1', name: 'gpt-test', provider: 'custom', provider_display_name: 'Test gateway', requests: 4, completed: 3, failed: 1, success_rate: 0.75, p50_ms: 500, p95_ms: 900, first_token_p95_ms: 250, tokens: 80, sample_count: 4 }], tools: [], retrieval: [] }))
const getQueues = mock(async () => ({ meta, workers: [{ worker_id: 'agent-worker-1', status: 'healthy', queues: ['agent', 'sandbox-1'], last_heartbeat: '2026-10-08T10:59:00Z', active_tasks: 1, reserved_tasks: null, scheduled_tasks: 0 }], queues: [{ name: 'agent', consumers: 1, pending: 2, oldest_wait_ms: 400, observed_at: '2026-10-08T11:00:00Z', state: 'healthy', trend: [{ bucket: '2026-10-08T10:59:00Z', pending: 1 }, { bucket: '2026-10-08T11:00:00Z', pending: 2 }] }] }))
const getInfrastructure = mock(async (): Promise<InfrastructureResponse> => ({ meta, instances: [{ instance_id: 'api-1', name: 'API east', role: 'api', metric_scope: 'host', cpu_percent: 27.5, memory_percent: null, observed_at: '2026-10-08T11:00:00Z', state: 'healthy' }], dependencies: [], slow_queries: { available: false, reset_at: null, items: [] } }))
const getAlerts = mock(async () => ({ items: [alert], next_cursor: null, meta }))
const getAlertRules = mock(async () => ([{ id: 'rule-1', name: 'Failure rate', threshold: 0.5, enabled: true, evaluation_window_seconds: 300, recovery_window_seconds: 600, updated_at: null }]))
const acknowledgeAlert = mock(async () => alert)
const silenceAlert = mock(async () => alert)
const updateAlertRule = mock(async () => ({ id: 'rule-1', name: 'Failure rate', threshold: 0.7, enabled: true, evaluation_window_seconds: 300, recovery_window_seconds: 600, updated_at: null }))
const replace = mock<(url: string, options: { scroll: boolean }) => void>(() => {})
let params = new URLSearchParams('tab=overview&keep=retained')

Object.assign(globalThis, {
  window: { setInterval: () => 1, clearInterval: () => {}, setTimeout: (callback: () => void) => setTimeout(callback, 0) },
  document: { visibilityState: 'visible', addEventListener: () => {}, removeEventListener: () => {} },
})

mock.module('next-intl', () => ({ useLocale: () => instanceLocale ?? 'en', useTranslations: () => translate }))
mock.module('next/navigation', () => ({ usePathname: () => '/dashboard/observability', useRouter: () => ({ replace }), useSearchParams: () => params }))
mock.module('lucide-react', () => {
  const Icon = () => null
  return { Activity: Icon, AlertTriangle: Icon, Bell: Icon, Boxes: Icon, CalendarIcon: Icon, Check: Icon, ChevronDown: Icon, ChevronRight: Icon, Clock3: Icon, Database: Icon, ExternalLink: Icon, Gauge: Icon, RefreshCw: Icon, Server: Icon, Workflow: Icon }
})
mock.module('recharts', () => {
  const Chart = ({ children }: React.PropsWithChildren) => <div>{children}</div>
  const Leaf = () => null
  return { Area: Leaf, AreaChart: Chart, Bar: Leaf, BarChart: Chart, CartesianGrid: Leaf, Line: Leaf, LineChart: Chart, ResponsiveContainer: Chart, Tooltip: Leaf, XAxis: Leaf, YAxis: Leaf }
})
mock.module('@/components/auth/permission-guard', () => ({ RoutePermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ hasPermission: (permission: string) => permission === 'admin:observability:manage' && canManageObservability }) }))
mock.module('@/components/layout/header', () => ({ Header: () => <header /> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/card', () => ({ Card: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>, CardContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>, CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>, CardHeader: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>, CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2> }))
mock.module('@/components/ui/sheet', () => ({ Sheet: ({ open, children, onOpenChange }: React.PropsWithChildren<{ open: boolean; onOpenChange: (open: boolean) => void }>) => open ? <div><button aria-label="close-run-detail" onClick={() => onOpenChange(false)}/>{children}</div> : null, SheetContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>, SheetDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>, SheetHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>, SheetTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2> }))
mock.module('@/components/ui/field', () => ({ Field: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>, FieldLabel: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
const RangePopoverContext = React.createContext<{ open: boolean; onOpenChange: (open: boolean) => void }>({ open: false, onOpenChange: () => {} })
mock.module('@/components/ui/popover', () => ({
  Popover: ({ children, open, onOpenChange }: React.PropsWithChildren<{ open: boolean; onOpenChange: (open: boolean) => void }>) => <RangePopoverContext.Provider value={{ open, onOpenChange }}>{children}</RangePopoverContext.Provider>,
  PopoverTrigger: ({ children, render }: React.PropsWithChildren<{ render: React.ReactElement<React.ButtonHTMLAttributes<HTMLButtonElement>> }>) => {
    const { open, onOpenChange } = React.useContext(RangePopoverContext)
    return React.cloneElement(render, { onClick: () => onOpenChange(!open) }, children)
  },
  PopoverContent: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => {
    const { open, onOpenChange } = React.useContext(RangePopoverContext)
    return open ? <div data-range-popover {...props}><button aria-label="dismiss-range" onClick={() => onOpenChange(false)} />{children}</div> : null
  },
}))
const MockCalendar: React.FC<{ selected?: DateRange; onSelect: (range?: DateRange) => void; defaultMonth?: Date; numberOfMonths: number; locale: { code?: string } }> = () => <div data-calendar-range />
mock.module('@/components/ui/calendar', () => ({ Calendar: MockCalendar }))
mock.module('@/components/ui/tabs', () => ({ Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>, TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>, TabsTrigger: ({ children }: React.PropsWithChildren<{ value: string }>) => <button>{children}</button> }))

mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string | number | null; onValueChange?: (value: string) => void }>) => (
    <div data-select-root data-selected-value={value == null ? '' : String(value)} onValueChange={onValueChange}>{children}</div>
  ),
  SelectTrigger: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button data-slot="select-trigger" {...props}>{children}</button>
  ),
  SelectValue: ({ children }: React.PropsWithChildren) => (
    <span data-slot="select-value">{children}</span>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value, onClick }: React.PropsWithChildren<{ value: string; onClick?: () => void }>) => (
    <div role="option" aria-selected={false} data-value={value} onClick={onClick}>{children}</div>
  ),
}))
mock.module('@/lib/chart-theme', () => ({ CHART_AXIS_COLOR: '#666', CHART_COLOR_ORDER: ['#123', '#456'], CHART_GRID_COLOR: '#ddd', CHART_HOVER_CURSOR: {}, CHART_TOOLTIP_STYLE: {} }))
mock.module('@/lib/utils', () => ({ formatTime: () => '11:00' }))
mock.module('@/lib/api/admin/observability', () => ({ observabilityApi: { getSummary, getRuns, getRun, getDependencies, getQueues, getInfrastructure, getAlerts, getAlertRules, acknowledgeAlert, silenceAlert, updateAlertRule } }))

// Import after registering mocks so the page exercises its real state and effects against deterministic service/UI boundaries.
const { default: ObservabilityPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<ObservabilityPage />) })
  return renderer!
}

beforeEach(() => {
  params = new URLSearchParams('tab=overview&keep=retained')
  instanceLocale = null
  canManageObservability = true
})

afterEach(() => {
  mock.clearAllMocks()
})

test('localizes every persisted agent run status in both locales', () => {
  for (const status of agentRunStatuses) {
    expect(enDashboard.dashboard.observability.status[status]).toBeTruthy()
    expect(zhDashboard.dashboard.observability.status[status]).toBeTruthy()
  }
})

test('renders the completing label and falls back safely for an unknown status', async () => {
  params = new URLSearchParams('tab=runs&period=24h')
  getRuns.mockResolvedValueOnce({
    items: [{ ...run, status: 'completing' }, { ...run, run_id: 'future-run', status: 'future_state' }],
    next_cursor: null,
    meta,
  })
  const renderer = await render()
  const labels = renderer.root.findAllByType('span').map((node) => node.children.join(''))
  expect(labels).toContain('status.completing')
  expect(labels).toContain('future_state')
  act(() => renderer.unmount())
})


test('opens the labeled range field with current window dates and only three footer presets', async () => {
  const renderer = await render()
  expect(renderer.root.findAllByType('label').find((node) => node.props.htmlFor === 'obs-range')!.children).toContain('filters.period')
  expect(rangeTrigger(renderer).children).toContain('periods.1h')
  expect(renderer.root.findAllByProps({ 'aria-label': 'filters.period' })).toHaveLength(0)
  openRange(renderer)
  expect(calendar(renderer).props.selected.from.toISOString()).toBe(new Date(meta.window_start).toISOString())
  expect(calendar(renderer).props.selected.to.toISOString()).toBe(new Date(meta.window_end).toISOString())
  expect(calendar(renderer).props.defaultMonth.toISOString()).toBe(new Date(meta.window_start).toISOString())
  expect(calendar(renderer).props.numberOfMonths).toBe(2)
  expect(calendar(renderer).props.mode).toBe('range')
  const footer = rangePopover(renderer).findAllByType('div').find((node) => node.props.className === 'space-y-2 border-t p-4')!
  expect(footer.findAllByType('button').map((node) => node.children.join(''))).toEqual(['periods.15m', 'periods.1h', 'periods.24h'])
  expect(getSummary).toHaveBeenCalledTimes(1)
  expect(replace).not.toHaveBeenCalled()
  act(() => renderer.unmount())
})

test('shows an explicit all-status label when the run status filter is empty', async () => {
  params = new URLSearchParams('tab=runs&period=24h')
  const renderer = await render()
  const statusSelect = renderer.root.findAllByProps({ 'data-select-root': true }).find(
    (select) => select.findAllByProps({ 'aria-label': 'filters.status' }).length > 0,
  )
  expect(statusSelect).toBeDefined()
  const trigger = statusSelect!.findByProps({ 'aria-label': 'filters.status' })
  expect(trigger.findByProps({ 'data-slot': 'select-value' }).children).toContain('filters.allStatuses')
  expect(statusSelect!.findByProps({ role: 'option', 'data-value': 'all' }).children).toContain('filters.allStatuses')
  act(() => renderer.unmount())
})
test('applies team filter changes only on submit and preserves unrelated URL parameters', async () => {
  const renderer = await render()
  expect(getSummary).toHaveBeenCalledWith({ period: '1h', team_id: undefined })
  const teamInput = renderer.root.findByProps({ id: 'obs-team' })
  act(() => teamInput.props.onChange({ target: { value: 'team-2' } }))
  expect(replace).not.toHaveBeenCalled()
  expect(getSummary).toHaveBeenCalledTimes(1)
  const teamForm = renderer.root.findByType('form')
  await act(async () => { teamForm.props.onSubmit({ preventDefault: () => {} }); await Promise.resolve() })
  expect(replace).toHaveBeenCalledWith('/dashboard/observability?tab=overview&keep=retained&team_id=team-2', { scroll: false })
  act(() => renderer.unmount())
})

test('applies run filters only when submitted', async () => {
  params = new URLSearchParams('tab=runs&period=24h')
  const renderer = await render()
  expect(getRuns).toHaveBeenCalledTimes(1)
  const runIdInput = renderer.root.findByProps({ 'aria-label': 'filters.runId' })
  act(() => runIdInput.props.onChange({ target: { value: 'run-42' } }))
  expect(getRuns).toHaveBeenCalledTimes(1)
  const runForm = renderer.root.findAllByType('form').find((form) => form.findAllByProps({ 'aria-label': 'filters.runId' }).length > 0)
  expect(runForm).toBeDefined()
  await act(async () => { runForm!.props.onSubmit({ preventDefault: () => {} }); await Promise.resolve() })
  expect(getRuns).toHaveBeenCalledTimes(2)
  expect(getRuns).toHaveBeenNthCalledWith(2, expect.objectContaining({ run_id: 'run-42', cursor: undefined, limit: 25 }))
  act(() => renderer.unmount())
})

test('uses cursor pages and fetches trace detail only after opening a run', async () => {
  params = new URLSearchParams('tab=runs&period=24h')
  getRuns.mockImplementationOnce(async () => ({ items: [run], next_cursor: 'opaque-cursor', meta }))
  getRuns.mockImplementationOnce(async () => ({ items: [], next_cursor: null, meta }))
  const renderer = await render()
  expect(getRuns).toHaveBeenCalledWith(expect.objectContaining({ period: '24h', cursor: undefined, limit: 25 }))
  expect(getRun).not.toHaveBeenCalled()
  const row = renderer.root.findAllByType('tr')[1]
  await act(async () => { row.props.onClick(); await Promise.resolve() })
  expect(getRun).toHaveBeenCalledWith('agent', 'failed-run')
  expect(renderer.root.findByType('h3').children).toContain('details.waterfall')
  expect(renderer.root.findAllByType('div').some((node) => node.children.some((child) => typeof child === 'string' && child.includes('details.traceTruncated')))).toBe(true)
  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('HTTP request'))).toBe(false)
  const rootToggle = renderer.root.findAllByType('button').find((button) => button.props['aria-expanded'] === false)
  expect(rootToggle).toBeDefined()
  await act(async () => { rootToggle!.props.onClick(); await Promise.resolve() })
  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('HTTP request'))).toBe(true)
  const expandedRoot = renderer.root.findAllByType('button').find((button) => button.props['aria-expanded'] === true)
  expect(expandedRoot).toBeDefined()
  await act(async () => { expandedRoot!.props.onClick(); await Promise.resolve() })
  expect(renderer.root.findAllByType('span').some((node) => node.children.includes('HTTP request'))).toBe(false)
  const loadMore = renderer.root.findAllByType('button').find((button) => button.children.includes('actions.loadMore'))
  expect(loadMore).toBeDefined()
  await act(async () => { loadMore!.props.onClick(); await Promise.resolve() })
  expect(getRuns).toHaveBeenNthCalledWith(2, expect.objectContaining({ cursor: 'opaque-cursor', limit: 25 }))
  act(() => renderer.unmount())
})

test('closing a pending trace request prevents late details from reopening the sheet', async () => {
  params = new URLSearchParams('tab=runs&period=24h')
  const pending = Promise.withResolvers<RunDetailResponse>()
  getRun.mockImplementationOnce(() => pending.promise)
  const renderer = await render()
  const row = renderer.root.findAllByType('tr')[1]
  await act(async () => { row.props.onClick(); await Promise.resolve() })
  const close = renderer.root.findByProps({ 'aria-label': 'close-run-detail' })
  act(() => close.props.onClick())
  expect(renderer.root.findAllByProps({ 'aria-label': 'close-run-detail' })).toHaveLength(0)

  await act(async () => {
    pending.resolve({ run, spans: [], trace: { complete: true, expired: false, truncated: false, recorded_count: 0 }, meta })
    await Promise.resolve()
  })
  expect(renderer.root.findAllByProps({ 'aria-label': 'close-run-detail' })).toHaveLength(0)
  act(() => renderer.unmount())
})

test('acknowledges an active alert and reloads the event list', async () => {
  params = new URLSearchParams('tab=alerts')
  const renderer = await render()
  const acknowledge = renderer.root.findAllByType('button').find((button) => button.children.includes('alerts.acknowledge'))
  expect(acknowledge).toBeDefined()
  await act(async () => { acknowledge!.props.onClick(); await Promise.resolve(); await Promise.resolve() })
  expect(acknowledgeAlert).toHaveBeenCalledWith('alert-1')
  expect(getAlerts).toHaveBeenCalledTimes(2)
  act(() => renderer.unmount())
})

test('silences incidents and saves threshold plus evaluation and recovery windows', async () => {
  params = new URLSearchParams('tab=alerts')
  const renderer = await render()
  const silence = renderer.root.findAllByType('button').find((button) => button.children.includes('alerts.silence'))
  expect(silence).toBeDefined()
  await act(async () => { silence!.props.onClick(); await Promise.resolve(); await Promise.resolve() })
  expect(silenceAlert).toHaveBeenCalledWith('alert-1', 3600)

  const evaluation = renderer.root.findByProps({ 'aria-label': 'alerts.evaluationWindow' })
  const recovery = renderer.root.findByProps({ 'aria-label': 'alerts.recoveryWindow' })
  const threshold = renderer.root.findAllByType('input').find((input) => input.props.type === 'number' && input.props.min === '0')
  expect(threshold?.props.max).toBe('1')
  expect(evaluation.props.min).toBe('60')
  expect(evaluation.props.max).toBe('604800')
  expect(recovery.props.min).toBe('60')
  expect(recovery.props.max).toBe('604800')
  act(() => { evaluation.props.onChange({ target: { value: '600' } }); recovery.props.onChange({ target: { value: '900' } }) })
  const save = renderer.root.findAllByType('button').find((button) => button.children.includes('actions.save'))
  expect(save).toBeDefined()
  await act(async () => { save!.props.onClick(); await Promise.resolve(); await Promise.resolve() })
  expect(updateAlertRule).toHaveBeenCalledWith('rule-1', { threshold: 0.5, enabled: true, evaluation_window_seconds: 600, recovery_window_seconds: 900 })
  act(() => renderer.unmount())
})
test('hides alert mutation controls for read-only observers', async () => {
  params = new URLSearchParams('tab=alerts')
  canManageObservability = false
  const renderer = await render()
  expect(renderer.root.findAllByType('button').some((button) => button.children.includes('alerts.acknowledge'))).toBe(false)
  expect(renderer.root.findAllByType('button').some((button) => button.children.includes('alerts.silence'))).toBe(false)
  expect(renderer.root.findAllByProps({ 'aria-label': 'alerts.silenceDuration' })).toHaveLength(0)
  expect(renderer.root.findAllByProps({ 'aria-label': 'alerts.evaluationWindow' })).toHaveLength(0)
  act(() => renderer.unmount())
})


test('does not start a queued view request after unmount', async () => {
  const renderer = await render()
  const pending = Promise.withResolvers<Awaited<ReturnType<typeof getSummary>>>()
  getSummary.mockImplementationOnce(() => pending.promise)
  const refresh = renderer.root.findAllByType('button').find((button) => button.children.includes('actions.refresh'))

  act(() => refresh!.props.onClick())
  expect(getSummary).toHaveBeenCalledTimes(2)

  params = new URLSearchParams('tab=runs')
  act(() => renderer.update(<ObservabilityPage />))
  expect(getRuns).not.toHaveBeenCalled()
  act(() => renderer.unmount())

  const browserWindow = window as unknown as {
    setTimeout: (callback: () => void, delay?: number) => number
  }
  const originalSetTimeout = browserWindow.setTimeout
  let deferredReload: (() => void) | undefined
  browserWindow.setTimeout = (callback) => { deferredReload = callback; return 1 }
  try {
    pending.resolve({ meta, agents: { submitted: 0, completed: 0, failed: 0, success_rate: null, p50_ms: null, p95_ms: null, first_token_p95_ms: null, tokens: 0 }, workflows: { submitted: 0, completed: 0, failed: 0, success_rate: null, p50_ms: null, p95_ms: null, tokens: 0 }, trend: [], issues: [] })
    await Promise.resolve()
    await Promise.resolve()
    expect(deferredReload).toBeUndefined()
    expect(getRuns).not.toHaveBeenCalled()
  } finally {
    browserWindow.setTimeout = originalSetTimeout
  }

  expect(getRuns).not.toHaveBeenCalled()
})


test('marks unresolved model metadata unavailable instead of displaying its UUID', async () => {
  params = new URLSearchParams('tab=dependencies')
  const missingId = 'ab4d78cd-07c5-4e59-b33e-e0a28aba0417'
  getDependencies.mockResolvedValueOnce({
    meta,
    models: [{ id: missingId, name: '', provider: null, provider_display_name: null, requests: 4, completed: 3, failed: 1, success_rate: 0.75, p50_ms: 500, p95_ms: 900, first_token_p95_ms: 250, tokens: 80, sample_count: 4 }],
    tools: [], retrieval: [],
  })
  const renderer = await render()
  const labels = renderer.root.findAllByType('strong').map((node) => node.children.join(''))
  expect(labels).toContain('status.unavailable')
  expect(labels).not.toContain(missingId)
  act(() => renderer.unmount())
})

for (const locale of ['en', 'zh'] as const) {
  test(`shows multiple API instances and distinguishes retained host samples in ${locale}`, async () => {
    instanceLocale = locale
    params = new URLSearchParams('tab=infrastructure')
    const messages = (locale === 'en' ? enDashboard : zhDashboard).dashboard.observability
    const states = ['healthy', 'stale', 'offline'] as const
    getInfrastructure.mockResolvedValueOnce({
      meta,
      instances: states.map((state, index) => ({ instance_id: `api-${index}`, name: `API region ${index}`, role: 'api', metric_scope: 'host', cpu_percent: 27.5 + index, memory_percent: null, observed_at: `2026-10-08T10:5${index}:00Z`, state })),
      dependencies: [], slow_queries: { available: false, reset_at: null, items: [] },
    })
    const renderer = await render()
    for (const [index, state] of states.entries()) {
      const card = renderer.root.findAllByType('article').find((node) => node.props['aria-label'] === `API region ${index}`)!
      expect(card.findAllByType('span').some((node) => node.children.includes(`api-${index}`))).toBe(true)
      expect(card.findAllByType('span').some((node) => node.children.includes(messages.status[state]))).toBe(true)
      const paragraphs = card.findAllByType('p').map((node) => node.children.join(''))
      expect(paragraphs.some((text) => text.includes(messages.infrastructure.scope.host))).toBe(true)
      expect(paragraphs.some((text) => text.includes(messages.infrastructure.lastObservedAt))).toBe(true)
      expect(paragraphs.includes(messages.infrastructure.retainedSample)).toBe(state !== 'healthy')
      expect(card.findAllByType('span').some((node) => node.children.join('').includes(`${27.5 + index}%`))).toBe(true)
    }
    act(() => renderer.unmount())
  })
}

function rangeTrigger(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('button').find((node) => node.props.id === 'obs-range')!
}

function rangePopover(renderer: ReactTestRenderer) {
  return renderer.root.findByProps({ 'data-range-popover': true })
}

function calendar(renderer: ReactTestRenderer) {
  return renderer.root.findByType(MockCalendar)
}

function openRange(renderer: ReactTestRenderer) {
  act(() => rangeTrigger(renderer).props.onClick())
}

function selectRange(renderer: ReactTestRenderer, selected?: DateRange) {
  act(() => calendar(renderer).props.onSelect(selected))
}

function rangeButton(renderer: ReactTestRenderer, label: string) {
  return rangePopover(renderer).findAllByType('button').find((node) => node.children.includes(label))!
}

function appliedQuery() {
  return new URLSearchParams(String(replace.mock.calls.at(-1)![0]).split('?')[1])
}

async function navigate(renderer: ReactTestRenderer, query: URLSearchParams) {
  params = query
  await act(async () => { renderer.update(<ObservabilityPage />); await Promise.resolve() })
}

test('partial and invalid drafts block apply; cancel and dismiss preserve applied queries and reopen current dates', async () => {
  const renderer = await render()
  openRange(renderer)
  const from = new Date(2026, 9, 8), to = new Date(2026, 9, 10)
  for (const draft of [undefined, { from }, { from: new Date(NaN), to }, { from: to, to: from }]) {
    selectRange(renderer, draft)
    expect(rangeButton(renderer, 'actions.apply').props.disabled).toBe(true)
    act(() => rangeButton(renderer, 'actions.apply').props.onClick())
    expect(replace).not.toHaveBeenCalled()
  }
  selectRange(renderer, { from, to })
  expect(rangeButton(renderer, 'actions.apply').props.disabled).toBe(false)
  expect(getSummary).toHaveBeenCalledTimes(1)
  expect(replace).not.toHaveBeenCalled()
  act(() => rangeButton(renderer, 'customRange.cancel').props.onClick())
  expect(renderer.root.findAllByProps({ 'data-range-popover': true })).toHaveLength(0)
  openRange(renderer)
  expect(calendar(renderer).props.selected.from.toISOString()).toBe(new Date(meta.window_start).toISOString())
  expect(calendar(renderer).props.selected.to.toISOString()).toBe(new Date(meta.window_end).toISOString())
  selectRange(renderer, { from, to })
  act(() => renderer.root.findByProps({ 'aria-label': 'dismiss-range' }).props.onClick())
  expect(getSummary).toHaveBeenCalledTimes(1)
  expect(replace).not.toHaveBeenCalled()
  expect(params.toString()).toBe('tab=overview&keep=retained')
  openRange(renderer)
  expect(calendar(renderer).props.selected.from.toISOString()).toBe(new Date(meta.window_start).toISOString())
  act(() => renderer.unmount())
})

test('applies inclusive whole local days only after Apply and reopens the actual persisted bounds', async () => {
  const renderer = await render()
  openRange(renderer)
  selectRange(renderer, { from: new Date(2026, 9, 8, 14, 30), to: new Date(2026, 9, 10, 8, 45) })
  expect(getSummary).toHaveBeenCalledTimes(1)
  expect(replace).not.toHaveBeenCalled()
  act(() => rangeButton(renderer, 'actions.apply').props.onClick())
  expect(renderer.root.findAllByProps({ 'data-range-popover': true })).toHaveLength(0)
  const applied = appliedQuery()
  const expected = { period: 'custom', start_time: new Date(2026, 9, 8).toISOString(), end_time: new Date(2026, 9, 10, 23, 59, 59, 999).toISOString().replace('.999Z', '.999999Z'), team_id: undefined }
  expect(applied.get('keep')).toBe('retained')
  expect(applied.get('tab')).toBe('overview')
  expect(applied.get('start_time')).toBe(expected.start_time)
  expect(applied.get('end_time')).toBe(expected.end_time)
  expect(getSummary).toHaveBeenCalledTimes(1)
  await navigate(renderer, applied)
  expect(getSummary).toHaveBeenLastCalledWith(expected)
  openRange(renderer)
  expect(calendar(renderer).props.selected.from.toISOString()).toBe(expected.start_time)
  expect(calendar(renderer).props.selected.to.toISOString()).toBe(new Date(expected.end_time).toISOString())
  selectRange(renderer, { from: new Date(2026, 9, 1), to: new Date(2026, 9, 2) })
  act(() => rangeButton(renderer, 'customRange.cancel').props.onClick())
  expect(getSummary).toHaveBeenCalledTimes(2)
  expect(params.get('end_time')).toBe(expected.end_time)
  act(() => renderer.unmount())
})

for (const scenario of [
  { month: 2, day: 8, hours: 23, start: '2026-03-08T05:00:00.000Z', end: '2026-03-09T03:59:59.999999Z' },
  { month: 10, day: 1, hours: 25, start: '2026-11-01T04:00:00.000Z', end: '2026-11-02T04:59:59.999999Z' },
  { month: 9, day: 8, hours: 24, start: '2026-10-08T04:00:00.000Z', end: '2026-10-09T03:59:59.999999Z' },
]) {
  test(`same-day selection includes every microsecond across a ${scenario.hours}-hour local day`, async () => {
    const originalTimezone = process.env.TZ
    process.env.TZ = 'America/New_York'
    let renderer: ReactTestRenderer | undefined
    try {
      renderer = await render()
      openRange(renderer)
      const day = new Date(2026, scenario.month, scenario.day, 12)
      selectRange(renderer, { from: day, to: day })
      expect(rangeButton(renderer, 'actions.apply').props.disabled).toBe(false)
      act(() => rangeButton(renderer!, 'actions.apply').props.onClick())
      const query = appliedQuery()
      expect(query.get('start_time')).toBe(scenario.start)
      expect(query.get('end_time')).toBe(scenario.end)
      expect((new Date(scenario.end).getTime() + 1 - new Date(scenario.start).getTime()) / 3600000).toBe(scenario.hours)
      await navigate(renderer, query)
      expect(getSummary).toHaveBeenLastCalledWith({ period: 'custom', start_time: scenario.start, end_time: scenario.end, team_id: undefined })
    } finally {
      if (renderer) act(() => renderer!.unmount())
      if (originalTimezone === undefined) delete process.env.TZ
      else process.env.TZ = originalTimezone
    }
  })
}

test('restored custom bounds survive tabs, paging and refresh; calendar apply resets paging; preset removes bounds', async () => {
  params = new URLSearchParams('period=custom&start_time=2026-10-08T10:00:00%2B02:00&end_time=2026-10-08T11:00:00%2B02:00&team_id=team-1&keep=retained')
  const expected = { period: 'custom', start_time: '2026-10-08T08:00:00.000Z', end_time: '2026-10-08T09:00:00.000Z', team_id: 'team-1' }
  const renderer = await render()
  expect(getSummary).toHaveBeenLastCalledWith(expected)
  const query = new URLSearchParams(params)
  query.set('tab', 'dependencies')
  await navigate(renderer, new URLSearchParams(query))
  expect(getDependencies).toHaveBeenLastCalledWith(expected)
  query.set('tab', 'runs')
  await navigate(renderer, new URLSearchParams(query))
  expect(getRuns).toHaveBeenLastCalledWith(expect.objectContaining({ ...expected, cursor: undefined }))
  getRuns.mockResolvedValueOnce({ items: [{ ...run, run_id: 'older-run', resource_name: 'Older run' }], next_cursor: 'tail-cursor', meta })
  await act(async () => { renderer.root.findAllByType('button').find((node) => node.children.includes('actions.loadMore'))!.props.onClick(); await Promise.resolve() })
  expect(getRuns).toHaveBeenLastCalledWith(expect.objectContaining({ ...expected, cursor: 'opaque-cursor' }))
  expect(renderer.root.findAllByType('tr')).toHaveLength(3)
  await act(async () => { renderer.root.findAllByType('button').find((node) => node.children.includes('actions.refresh'))!.props.onClick(); await Promise.resolve() })
  expect(getRuns).toHaveBeenLastCalledWith(expect.objectContaining({ ...expected, cursor: undefined }))
  expect(renderer.root.findAllByType('tr')).toHaveLength(2)
  getRuns.mockResolvedValueOnce({ items: [{ ...run, run_id: 'older-run', resource_name: 'Older run' }], next_cursor: 'tail-cursor', meta })
  await act(async () => { renderer.root.findAllByType('button').find((node) => node.children.includes('actions.loadMore'))!.props.onClick(); await Promise.resolve() })
  expect(getRuns).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: 'opaque-cursor' }))
  const requests = getRuns.mock.calls.length
  openRange(renderer)
  selectRange(renderer, { from: new Date(2026, 9, 7), to: new Date(2026, 9, 8) })
  expect(getRuns).toHaveBeenCalledTimes(requests)
  expect(renderer.root.findAllByType('tr')).toHaveLength(3)
  act(() => rangeButton(renderer, 'actions.apply').props.onClick())
  const custom = appliedQuery()
  await navigate(renderer, custom)
  expect(getRuns).toHaveBeenLastCalledWith(expect.objectContaining({ period: 'custom', start_time: custom.get('start_time'), end_time: custom.get('end_time'), team_id: 'team-1', cursor: undefined }))
  expect(renderer.root.findAllByType('tr')).toHaveLength(2)
  expect(renderer.root.findAllByType('td').some((node) => node.children.includes('Older run'))).toBe(false)
  openRange(renderer)
  act(() => rangeButton(renderer, 'periods.24h').props.onClick())
  const preset = appliedQuery()
  expect(preset.get('period')).toBe('24h')
  expect(preset.has('start_time')).toBe(false)
  expect(preset.has('end_time')).toBe(false)
  expect(preset.get('team_id')).toBe('team-1')
  expect(preset.get('tab')).toBe('runs')
  expect(preset.get('keep')).toBe('retained')
  expect(renderer.root.findAllByProps({ 'data-range-popover': true })).toHaveLength(0)
  await navigate(renderer, preset)
  expect(getRuns).toHaveBeenLastCalledWith(expect.objectContaining({ period: '24h', cursor: undefined, team_id: 'team-1' }))
  const lastRequest = (getRuns.mock.calls as unknown as [Record<string, unknown>][]).at(-1)![0]
  expect(lastRequest.start_time).toBeUndefined()
  expect(lastRequest.end_time).toBeUndefined()
  act(() => renderer.unmount())
})

test('legacy URLs preserve timezone-aware microseconds without rounding or rewriting their interval', async () => {
  params = new URLSearchParams({ period: 'custom', start_time: '2026-10-08T10:00:00.123456+02:00', end_time: '2026-10-08T11:00:00.999999+02:00' })
  const renderer = await render()
  expect(getSummary).toHaveBeenLastCalledWith({ period: 'custom', start_time: '2026-10-08T08:00:00.123456Z', end_time: '2026-10-08T09:00:00.999999Z', team_id: undefined })
  openRange(renderer)
  expect(calendar(renderer).props.selected.from.toISOString()).toBe('2026-10-08T08:00:00.123Z')
  expect(calendar(renderer).props.selected.to.toISOString()).toBe('2026-10-08T09:00:00.999Z')
  act(() => rangeButton(renderer, 'customRange.cancel').props.onClick())
  expect(params.get('end_time')).toBe('2026-10-08T11:00:00.999999+02:00')
  expect(replace).not.toHaveBeenCalled()
  act(() => renderer.unmount())
})

test('an exact sub-millisecond restored interval remains valid', async () => {
  params = new URLSearchParams({ period: 'custom', start_time: '2026-10-08T08:00:00.123456Z', end_time: '2026-10-08T08:00:00.123457Z' })
  const renderer = await render()
  expect(getSummary).toHaveBeenLastCalledWith({ period: 'custom', start_time: '2026-10-08T08:00:00.123456Z', end_time: '2026-10-08T08:00:00.123457Z', team_id: undefined })
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(0)
  act(() => renderer.unmount())
})

test('invalid restored custom URL remains correctable without silently requesting a preset window', async () => {
  params = new URLSearchParams('period=custom&start_time=2026-10-08T10:00&end_time=2026-10-08T11:00')
  const renderer = await render()
  expect(getSummary).not.toHaveBeenCalled()
  expect(rangeTrigger(renderer).props['aria-invalid']).toBe(true)
  expect(rangeTrigger(renderer).children).toContain('customRange.pickDate')
  expect(renderer.root.findByProps({ role: 'alert' }).children).toContain('customRange.invalid')
  openRange(renderer)
  expect(calendar(renderer).props.selected).toBeUndefined()
  expect(rangeButton(renderer, 'actions.apply').props.disabled).toBe(true)
  selectRange(renderer, { from: new Date(2026, 9, 8), to: new Date(2026, 9, 9) })
  expect(getSummary).not.toHaveBeenCalled()
  act(() => rangeButton(renderer, 'actions.apply').props.onClick())
  await navigate(renderer, appliedQuery())
  expect(getSummary).toHaveBeenCalledTimes(1)
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(0)
  act(() => renderer.unmount())
})

test('retains the legacy 7d URL while footer presets are limited to 15m, 1h and 24h', async () => {
  params = new URLSearchParams('period=7d&tab=dependencies&team_id=team-1')
  const renderer = await render()
  expect(getDependencies).toHaveBeenLastCalledWith({ period: '7d', team_id: 'team-1' })
  expect(rangeTrigger(renderer).children).toContain('periods.7d')
  openRange(renderer)
  expect(rangePopover(renderer).findAllByType('button').some((node) => node.children.includes('periods.7d'))).toBe(false)
  act(() => rangeButton(renderer, 'periods.15m').props.onClick())
  await navigate(renderer, appliedQuery())
  expect(getDependencies).toHaveBeenLastCalledWith({ period: '15m', team_id: 'team-1' })
  expect(params.get('tab')).toBe('dependencies')
  act(() => renderer.unmount())
})

for (const locale of ['en', 'zh'] as const) {
  test(`formats applied dates and preset buttons in ${locale} and passes the matching calendar locale`, async () => {
    instanceLocale = locale
    params = new URLSearchParams('period=custom&start_time=2026-10-08T08:00:00Z&end_time=2026-10-10T09:00:00Z')
    const renderer = await render()
    const dateLocale = locale === 'zh' ? zhCN : enUS
    const messages = (locale === 'en' ? enDashboard : zhDashboard).dashboard.observability
    const label = `${format(new Date(params.get('start_time')!), 'PPP', { locale: dateLocale })} – ${format(new Date(params.get('end_time')!), 'PPP', { locale: dateLocale })}`
    expect(rangeTrigger(renderer).children).toContain(label)
    openRange(renderer)
    expect(calendar(renderer).props.locale.code).toBe(dateLocale.code)
    expect(rangePopover(renderer).findAllByType('button').some((node) => node.children.includes(messages.periods['24h']))).toBe(true)
    act(() => rangeButton(renderer, messages.periods['24h']).props.onClick())
    await navigate(renderer, appliedQuery())
    expect(rangeTrigger(renderer).children).toContain(messages.periods['24h'])
    expect(getSummary).toHaveBeenLastCalledWith({ period: '24h', team_id: undefined })
    act(() => renderer.unmount())
  })
}
