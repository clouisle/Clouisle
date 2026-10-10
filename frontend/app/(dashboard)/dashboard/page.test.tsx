import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { TimeRange } from '@/components/dashboard/time-range-selector'
import type { DashboardTrends } from '@/lib/api/admin/dashboard'

type Trend = DashboardTrends['data'][number]
const trend = (date: string, tokens: number, new_conversations = 0, messages = 0): Trend => ({ date, new_users: 0, active_users: 0, new_conversations, messages, tokens })
type Agent = { agent_id: string; name: string }
type Workflow = { total_runs: number }
const stats = { total_users: 1 }
const getStats = mock<() => Promise<typeof stats>>(() => Promise.resolve(stats))
const getTrends = mock<(range?: TimeRange) => Promise<{ data: Trend[] }>>(() => Promise.resolve({ data: [trend('2026-01-01', 2)] }))
const getModelDistribution = mock<(params: { time_range: TimeRange }) => Promise<object[]>>(() => Promise.resolve([]))
const getTeamTokenUsage = mock<(params: { limit: number; time_range: TimeRange }) => Promise<object[]>>(() => Promise.resolve([]))
const getTopAgents = mock<(params: { limit: number; metric: string; time_range: TimeRange }) => Promise<Agent[]>>(() => Promise.resolve([]))
const getWorkflowSummary = mock<(params: { time_range: TimeRange }) => Promise<Workflow | null>>(() => Promise.resolve(null))
const getTOTPStats = mock<() => Promise<unknown>>(() => Promise.resolve({ enabled_users: 1 }))
const push = mock<(url: string, options: { scroll: boolean }) => void>(() => {})
let params = new URLSearchParams()

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }), useSearchParams: () => params }))
mock.module('lucide-react', () => ({ Loader2: () => <span data-icon="loader" />, RefreshCw: () => null }))
mock.module('@/lib/api/admin/dashboard', () => ({ dashboardApi: { getStats, getTrends, getModelDistribution, getTeamTokenUsage, getTopAgents, getWorkflowSummary } }))
mock.module('@/lib/api/admin/users', () => ({ adminTOTPApi: { getStats: getTOTPStats } }))
mock.module('@/components/auth/permission-guard', () => ({ RoutePermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/components/layout/header', () => ({ Header: () => <header /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
const MockTabs = ({ children }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) => <div>{children}</div>
mock.module('@/components/ui/tabs', () => ({
  Tabs: MockTabs,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren<{ value: string }>) => <button>{children}</button>,
}))
const MockTimeRangeSelector = ({ invalid }: { value: TimeRange; onChange: (value: TimeRange) => void; invalid: boolean }) => <div data-time-range>{invalid && <p role="alert">invalid range</p>}</div>
mock.module('@/components/dashboard/time-range-selector', () => ({ TimeRangeSelector: MockTimeRangeSelector }))
const TabResult = (props: { 'data-tab': string }) => <div data-tab={props['data-tab']} />
mock.module('./_components/overview-tab', () => ({ OverviewTab: (props: object) => <TabResult data-tab="overview" {...props} /> }))
mock.module('./_components/models-tab', () => ({ ModelsTab: (props: object) => <TabResult data-tab="models" {...props} /> }))
mock.module('./_components/analytics-tab', () => ({ AnalyticsTab: (props: object) => <TabResult data-tab="analytics" {...props} /> }))

// Load after mocks: static imports would load the page before its service/UI boundaries are replaced.
const { default: DashboardPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
let renderer: ReactTestRenderer | undefined

async function render() {
  await act(async () => { renderer = create(<DashboardPage />) })
  return renderer!
}
async function navigate(query: URLSearchParams) {
  params = query
  await act(async () => { renderer!.update(<DashboardPage />) })
}
async function followPush() {
  await navigate(new URLSearchParams(push.mock.calls.at(-1)![0].split('?')[1]))
}
async function tab(value: string) {
  act(() => renderer!.root.findByType(MockTabs).props.onValueChange(value))
  await followPush()
}
async function range(value: TimeRange) {
  act(() => renderer!.root.findByType(MockTimeRangeSelector).props.onChange(value))
  await followPush()
}
async function refresh() {
  await act(async () => renderer!.root.findByProps({ 'aria-label': 'actions.refresh' }).props.onClick())
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  mock.clearAllMocks()
  getStats.mockResolvedValue(stats)
  getTrends.mockResolvedValue({ data: [trend('2026-01-01', 2)] })
  getModelDistribution.mockResolvedValue([])
  getTeamTokenUsage.mockResolvedValue([])
  getTopAgents.mockResolvedValue([])
  getWorkflowSummary.mockResolvedValue(null)
  getTOTPStats.mockResolvedValue({ enabled_users: 1 })
  params = new URLSearchParams()
})

test('loads global and TOTP statistics once and tolerates optional TOTP failure', async () => {
  const pending = deferred<typeof stats>()
  getStats.mockReturnValueOnce(pending.promise)
  getTOTPStats.mockRejectedValueOnce(new Error('unavailable'))
  await render()
  expect(renderer!.root.findByProps({ 'data-icon': 'loader' })).toBeDefined()
  await act(async () => pending.resolve(stats))
  const overview = renderer!.root.findByProps({ 'data-tab': 'overview' })
  expect(getTrends).toHaveBeenCalledWith('30d')
  expect(overview.props.stats).toEqual(stats)
  expect(overview.props.totpStats).toBeNull()
  expect(getStats).toHaveBeenCalledTimes(1)
  expect(getTOTPStats).toHaveBeenCalledTimes(1)
  await range('7d')
  expect(getStats).toHaveBeenCalledTimes(1)
  expect(getTOTPStats).toHaveBeenCalledTimes(1)
})

test('keeps the loading fallback when common statistics fail', async () => {
  getStats.mockRejectedValueOnce(new Error('offline'))
  await render()
  expect(renderer!.root.findByProps({ 'data-icon': 'loader' })).toBeDefined()
})

test('derives conversation, message, and token summaries from all trend buckets in the selected range', async () => {
  params = new URLSearchParams('tab=analytics&time_range=7d')
  getTrends.mockResolvedValueOnce({ data: [trend('first', 12, 2, 4), trend('last', 30, 5, 7)] })
  await render()
  expect(getTrends).toHaveBeenCalledWith('7d')
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.activitySummary).toEqual({ conversations: 7, messages: 11, tokens: 42 })
})

test('restores a models URL immediately and handles each independent models failure', async () => {
  params = new URLSearchParams('tab=models&time_range=90d')
  getModelDistribution.mockRejectedValueOnce(new Error('models'))
  getTeamTokenUsage.mockRejectedValueOnce(new Error('teams'))
  getTopAgents.mockRejectedValueOnce(new Error('agents'))
  getTrends.mockRejectedValueOnce(new Error('trends'))
  await render()
  expect(getTrends).toHaveBeenCalledTimes(1)
  expect(getTrends).toHaveBeenCalledWith('90d')
  expect(getModelDistribution).toHaveBeenCalledWith({ time_range: '90d' })
  expect(getTeamTokenUsage).toHaveBeenCalledWith({ limit: 10, time_range: '90d' })
  expect(renderer!.root.findByProps({ 'data-tab': 'models' }).props).toMatchObject({ modelData: [], teamTokenData: [], topAgentsData: [], trendsData: [], isLoading: false })
})

test('preserves custom URL timestamps, tab and other filters through every request and refresh', async () => {
  const custom = { start_time: '2026-10-08T10:00:00.123456+02:00', end_time: '2026-10-09T11:00:00.999999+02:00' }
  params = new URLSearchParams({ tab: 'models', time_range: 'custom', ...custom, team_id: 'team-1', keep: 'retained' })
  await render()
  expect(renderer!.root.findByType(MockTimeRangeSelector).props.value).toEqual(custom)
  expect(getTrends).toHaveBeenLastCalledWith(custom)
  expect(getModelDistribution).toHaveBeenLastCalledWith({ time_range: custom })
  expect(getTeamTokenUsage).toHaveBeenLastCalledWith({ limit: 10, time_range: custom })
  expect(getTopAgents).toHaveBeenLastCalledWith({ limit: 10, metric: 'total_tokens', time_range: custom })
  await tab('analytics')
  expect(params.get('team_id')).toBe('team-1')
  expect(params.get('keep')).toBe('retained')
  expect(params.get('start_time')).toBe(custom.start_time)
  expect(params.get('end_time')).toBe(custom.end_time)
  expect(getWorkflowSummary).toHaveBeenLastCalledWith({ time_range: custom })
  expect(getTopAgents).toHaveBeenLastCalledWith({ limit: 10, metric: 'conversation_count', time_range: custom })
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('message_count'))
  expect(getTopAgents).toHaveBeenLastCalledWith({ limit: 10, metric: 'message_count', time_range: custom })
  await refresh()
  expect(getWorkflowSummary).toHaveBeenCalledTimes(2)
  expect(getTopAgents).toHaveBeenLastCalledWith({ limit: 10, metric: 'message_count', time_range: custom })
  expect(getStats).toHaveBeenCalledTimes(2)
  expect(params.get('end_time')).toBe(custom.end_time)
  await tab('overview')
  expect(getTrends).toHaveBeenLastCalledWith(custom)
  await range('all')
  expect(params.get('time_range')).toBe('all')
  expect(params.has('start_time')).toBe(false)
  expect(params.has('end_time')).toBe(false)
  expect(params.get('tab')).toBe('overview')
  expect(params.get('keep')).toBe('retained')
  expect(getTrends).toHaveBeenLastCalledWith('all')
})

test('applies generated full-day microsecond bounds and preserves them in URL requests', async () => {
  params = new URLSearchParams('tab=overview&keep=retained')
  await render()
  const custom = { start_time: '2026-03-08T05:00:00.000Z', end_time: '2026-03-09T03:59:59.999999Z' }
  await range(custom)
  expect(params.get('time_range')).toBe('custom')
  expect(params.get('start_time')).toBe(custom.start_time)
  expect(params.get('end_time')).toBe(custom.end_time)
  expect(params.get('keep')).toBe('retained')
  expect(getTrends).toHaveBeenLastCalledWith(custom)
})

test('accepts exactly ordered microseconds even when JavaScript dates have the same millisecond', async () => {
  const custom = { start_time: '2026-10-08T10:00:00.123456+02:00', end_time: '2026-10-08T08:00:00.123457Z' }
  params = new URLSearchParams({ time_range: 'custom', ...custom })
  await render()
  expect(renderer!.root.findByType(MockTimeRangeSelector).props.invalid).toBe(false)
  expect(getTrends).toHaveBeenCalledWith(custom)
})

for (const query of [
  'time_range=custom',
  'time_range=custom&start_time=2026-10-08T10:00:00Z',
  'time_range=custom&start_time=2026-10-08T10:00&end_time=2026-10-09T10:00',
  'time_range=custom&start_time=2026-02-30T10:00:00Z&end_time=2026-03-02T10:00:00Z',
  'time_range=custom&start_time=2026-10-09T10:00:00Z&end_time=2026-10-08T10:00:00Z',
  'time_range=custom&start_time=2026-10-08T10:00:00.123456Z&end_time=2026-10-08T10:00:00.123456Z',
  'time_range=custom&start_time=2026-10-08T10:00:00.123457Z&end_time=2026-10-08T10:00:00.123456Z',
  'time_range=custom&start_time=2026-10-08T10:00:00.1234567Z&end_time=2026-10-09T10:00:00Z',
  'time_range=7d&start_time=2026-10-08T10:00:00Z&end_time=2026-10-09T10:00:00Z',
  'time_range=unknown',
]) {
  test(`keeps an invalid URL visible and correctable without fetching a substitute period: ${query}`, async () => {
    params = new URLSearchParams(`${query}&tab=analytics&keep=retained`)
    await render()
    expect(renderer!.root.findByType(MockTimeRangeSelector).props.invalid).toBe(true)
    expect(renderer!.root.findByProps({ role: 'alert' })).toBeDefined()
    expect(getWorkflowSummary).not.toHaveBeenCalled()
    expect(getTopAgents).not.toHaveBeenCalled()
    expect(getTrends).not.toHaveBeenCalled()
    await range('7d')
    expect(params.get('keep')).toBe('retained')
    expect(params.get('tab')).toBe('analytics')
    expect(params.has('start_time')).toBe(false)
    expect(renderer!.root.findByType(MockTimeRangeSelector).props.invalid).toBe(false)
    expect(getWorkflowSummary).toHaveBeenLastCalledWith({ time_range: '7d' })
  })
}

test('refreshes a previously fetched tab and invalidates inactive tab caches', async () => {
  await render()
  await tab('models')
  await tab('analytics')
  await tab('overview')
  expect(getTrends).toHaveBeenCalledTimes(3)
  await refresh()
  expect(getTrends).toHaveBeenCalledTimes(4)
  await tab('models')
  expect(getModelDistribution).toHaveBeenCalledTimes(2)
  await tab('analytics')
  expect(getWorkflowSummary).toHaveBeenCalledTimes(2)
  expect(getTopAgents.mock.calls.filter(([request]) => request.metric === 'conversation_count')).toHaveLength(2)
})

test('invalidates every cached tab when changing a range, including when returning to an earlier preset', async () => {
  await render()
  await tab('models')
  await tab('analytics')
  await range('7d')
  await range('30d')
  await tab('overview')
  expect(getTrends).toHaveBeenCalledTimes(6)
  await tab('models')
  expect(getModelDistribution).toHaveBeenCalledTimes(2)
  expect(getTrends).toHaveBeenCalledTimes(7)
})

test('keeps separate overview and model trends when returning to a cached tab', async () => {
  getTrends.mockResolvedValueOnce({ data: [trend('overview', 10)] }).mockResolvedValueOnce({ data: [trend('models', 20)] })
  await render()
  await tab('models')
  expect(renderer!.root.findByProps({ 'data-tab': 'models' }).props.trendsData).toEqual([trend('models', 20)])
  await tab('overview')
  expect(renderer!.root.findByProps({ 'data-tab': 'overview' }).props.trendsData).toEqual([trend('overview', 10)])
})

test('rejects older overview range responses and retains the newest loading state', async () => {
  const old = deferred<{ data: Trend[] }>(), latest = deferred<{ data: Trend[] }>()
  getTrends.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise)
  await render()
  await range('7d')
  await act(async () => old.resolve({ data: [trend('old', 99)] }))
  expect(renderer!.root.findByProps({ 'data-tab': 'overview' }).props).toMatchObject({ trendsData: [], isLoading: true })
  await act(async () => latest.resolve({ data: [trend('latest', 7)] }))
  expect(renderer!.root.findByProps({ 'data-tab': 'overview' }).props).toMatchObject({ trendsData: [trend('latest', 7)], isLoading: false })
})

test('ignores models responses after leaving the tab and after applying a newer range', async () => {
  const oldModels = deferred<object[]>(), oldTeams = deferred<object[]>(), oldAgents = deferred<Agent[]>(), oldTrends = deferred<{ data: Trend[] }>()
  params = new URLSearchParams('tab=models')
  getModelDistribution.mockReturnValueOnce(oldModels.promise)
  getTeamTokenUsage.mockReturnValueOnce(oldTeams.promise)
  getTopAgents.mockReturnValueOnce(oldAgents.promise)
  getTrends.mockReturnValueOnce(oldTrends.promise)
  await render()
  await tab('overview')
  await range('7d')
  await tab('models')
  getModelDistribution.mockClear()
  await act(async () => {
    oldModels.resolve([{ model: 'old', count: 99 }])
    oldTeams.resolve([{ name: 'old', total_tokens: 99 }])
    oldAgents.resolve([{ agent_id: 'old', name: 'old' }])
    oldTrends.resolve({ data: [trend('old', 99)] })
  })
  expect(renderer!.root.findByProps({ 'data-tab': 'models' }).props).toMatchObject({ modelData: [], teamTokenData: [], topAgentsData: [], trendsData: [trend('2026-01-01', 2)], isLoading: false })
  await tab('overview')
  await tab('models')
  expect(getModelDistribution).not.toHaveBeenCalled()
})

test('a pending request from a previous tab does not populate its cache or replace another tab trends', async () => {
  const old = deferred<{ data: Trend[] }>()
  getTrends.mockReturnValueOnce(old.promise).mockResolvedValueOnce({ data: [trend('models', 20)] }).mockResolvedValueOnce({ data: [trend('fresh', 30)] })
  await render()
  await tab('models')
  await act(async () => old.resolve({ data: [trend('stale', 99)] }))
  expect(renderer!.root.findByProps({ 'data-tab': 'models' }).props.trendsData).toEqual([trend('models', 20)])
  await tab('overview')
  expect(getTrends).toHaveBeenCalledTimes(3)
  expect(renderer!.root.findByProps({ 'data-tab': 'overview' }).props.trendsData).toEqual([trend('fresh', 30)])
})

test('protects workflow and agent results across analytics range and metric transitions', async () => {
  params = new URLSearchParams('tab=analytics')
  const oldWorkflow = deferred<Workflow | null>(), oldAgents = deferred<Agent[]>(), metricAgents = deferred<Agent[]>()
  getWorkflowSummary.mockReturnValueOnce(oldWorkflow.promise).mockResolvedValueOnce({ total_runs: 7 })
  getTopAgents.mockReturnValueOnce(oldAgents.promise).mockReturnValueOnce(metricAgents.promise).mockResolvedValueOnce([{ agent_id: 'latest', name: 'latest' }])
  await render()
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('message_count'))
  await range('7d')
  await act(async () => {
    oldWorkflow.resolve({ total_runs: 99 })
    oldAgents.resolve([{ agent_id: 'old', name: 'old' }])
    metricAgents.resolve([{ agent_id: 'old-metric', name: 'old-metric' }])
  })
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props).toMatchObject({ workflowData: { total_runs: 7 }, topAgentsData: [{ agent_id: 'latest', name: 'latest' }], currentMetric: 'message_count', isLoading: false, isLoadingAgents: false })
})

test('ignores an initial analytics agent response after a newer metric completes and keeps workflow data', async () => {
  params = new URLSearchParams('tab=analytics')
  const first = deferred<Agent[]>(), second = deferred<Agent[]>()
  getWorkflowSummary.mockResolvedValueOnce({ total_runs: 4 })
  getTopAgents.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockResolvedValueOnce([{ agent_id: 'tokens', name: 'tokens' }])
  await render()
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('message_count'))
  await act(async () => first.resolve([{ agent_id: 'stale', name: 'stale' }]))
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.isLoadingAgents).toBe(true)
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('total_tokens'))
  await act(async () => second.resolve([{ agent_id: 'stale-message', name: 'stale-message' }]))
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props).toMatchObject({ workflowData: { total_runs: 4 }, topAgentsData: [{ agent_id: 'tokens', name: 'tokens' }], currentMetric: 'total_tokens', isLoadingAgents: false })
  expect(getWorkflowSummary).toHaveBeenCalledTimes(1)
  getTopAgents.mockRejectedValueOnce(new Error('unavailable'))
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('message_count'))
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props).toMatchObject({ topAgentsData: [], isLoadingAgents: false })
})

test('ignores analytics responses after leaving the tab and reloads on return', async () => {
  params = new URLSearchParams('tab=analytics')
  const workflow = deferred<Workflow | null>(), agents = deferred<Agent[]>()
  getWorkflowSummary.mockReturnValueOnce(workflow.promise).mockResolvedValueOnce({ total_runs: 5 })
  getTopAgents.mockReturnValueOnce(agents.promise).mockResolvedValueOnce([{ agent_id: 'fresh', name: 'fresh' }])
  await render()
  await tab('overview')
  await act(async () => { workflow.resolve({ total_runs: 99 }); agents.resolve([{ agent_id: 'stale', name: 'stale' }]) })
  await tab('analytics')
  expect(getWorkflowSummary).toHaveBeenCalledTimes(2)
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props).toMatchObject({ workflowData: { total_runs: 5 }, topAgentsData: [{ agent_id: 'fresh', name: 'fresh' }] })
})

test('manual refresh invalidates pending common and interval requests', async () => {
  await render()
  const oldStats = deferred<typeof stats>(), latestStats = deferred<typeof stats>(), oldTrends = deferred<{ data: Trend[] }>(), latestTrends = deferred<{ data: Trend[] }>()
  getStats.mockReturnValueOnce(oldStats.promise).mockReturnValueOnce(latestStats.promise)
  getTrends.mockReturnValueOnce(oldTrends.promise).mockReturnValueOnce(latestTrends.promise)
  await refresh()
  await refresh()
  await act(async () => { latestStats.resolve({ total_users: 7 }); latestTrends.resolve({ data: [trend('fresh', 7)] }) })
  await act(async () => { oldStats.resolve({ total_users: 99 }); oldTrends.resolve({ data: [trend('stale', 99)] }) })
  expect(renderer!.root.findByProps({ 'data-tab': 'overview' }).props).toMatchObject({ stats: { total_users: 7 }, trendsData: [trend('fresh', 7)], isLoading: false })
})

test('refetches a metric after a failed replacement instead of reusing its obsolete fetched flag', async () => {
  params = new URLSearchParams('tab=analytics')
  getTopAgents.mockResolvedValueOnce([{ agent_id: 'first', name: 'first' }]).mockRejectedValueOnce(new Error('unavailable')).mockResolvedValueOnce([{ agent_id: 'new', name: 'new' }])
  await render()
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('message_count'))
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.topAgentsData).toEqual([])
  await act(async () => renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.onMetricChange('conversation_count'))
  expect(getTopAgents).toHaveBeenCalledTimes(3)
  expect(renderer!.root.findByProps({ 'data-tab': 'analytics' }).props.topAgentsData).toEqual([{ agent_id: 'new', name: 'new' }])
})

test('invalid URL navigation cancels an in-flight valid range and clears its displayed results', async () => {
  const pending = deferred<{ data: Trend[] }>()
  getTrends.mockReturnValueOnce(pending.promise)
  await render()
  await navigate(new URLSearchParams('time_range=custom&start_time=invalid&end_time=invalid'))
  await act(async () => pending.resolve({ data: [trend('stale', 99)] }))
  expect(renderer!.root.findByType(MockTimeRangeSelector).props.invalid).toBe(true)
  expect(renderer!.root.findByProps({ 'data-tab': 'overview' }).props).toMatchObject({ trendsData: [], isLoading: false })
  expect(getTrends).toHaveBeenCalledTimes(1)
  await range('30d')
  expect(getTrends).toHaveBeenCalledTimes(2)
})
