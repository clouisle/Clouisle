import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const stats = { total_users: 1 }
const getStats = mock(() => Promise.resolve(stats))
const getTrends = mock(() => Promise.resolve({ data: [{ date: '2026-01-01', tokens: 2 }] }))
const getModelDistribution = mock(() => Promise.resolve([]))
const getTeamTokenUsage = mock(() => Promise.resolve([]))
const getTopAgents = mock(() => Promise.resolve([]))
const getWorkflowSummary = mock(() => Promise.resolve(null))
const getTOTPStats = mock<() => Promise<unknown>>(() => Promise.resolve({ enabled_users: 1 }))
const push = mock(() => {})
let tab = 'overview'

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: () => tab }),
}))
mock.module('lucide-react', () => ({ Loader2: () => <span data-icon="loader" />, RefreshCw: () => null }))
mock.module('@/lib/api/admin/dashboard', () => ({
  dashboardApi: {
    getStats,
    getTrends,
    getModelDistribution,
    getTeamTokenUsage,
    getTopAgents,
    getWorkflowSummary,
  },
}))
mock.module('@/lib/api/admin/users', () => ({ adminTOTPApi: { getStats: getTOTPStats } }))
mock.module('@/components/auth/permission-guard', () => ({
  RoutePermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/layout/header', () => ({ Header: () => <header /> }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, onValueChange }: React.PropsWithChildren<{ onValueChange: (value: string) => void }>) => (
    <div data-tabs onClick={() => onValueChange('analytics')}>{children}</div>
  ),
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))
mock.module('@/components/dashboard/time-range-selector', () => ({
  TimeRangeSelector: ({ onChange }: { onChange: (value: '7d') => void }) => (
    <button data-time-range onClick={() => onChange('7d')} />
  ),
}))
mock.module('./_components/overview-tab', () => ({
  OverviewTab: (props: object) => <div data-tab="overview" {...props} />,
}))
mock.module('./_components/models-tab', () => ({
  ModelsTab: (props: object) => <div data-tab="models" {...props} />,
}))
mock.module('./_components/analytics-tab', () => ({
  AnalyticsTab: (props: object) => <div data-tab="analytics" {...props} />,
}))

const { default: DashboardPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<DashboardPage />)
  })
  return renderer!
}

const unmount = (renderer: ReactTestRenderer) => act(() => renderer.unmount())

const resetApiMocks = () => {
  getStats.mockResolvedValue(stats)
  getTrends.mockResolvedValue({ data: [{ date: '2026-01-01', tokens: 2 }] })
  getModelDistribution.mockResolvedValue([])
  getTeamTokenUsage.mockResolvedValue([])
  getTopAgents.mockResolvedValue([])
  getWorkflowSummary.mockResolvedValue(null)
  getTOTPStats.mockResolvedValue({ enabled_users: 1 })
}

afterEach(() => {
  mock.clearAllMocks()
  resetApiMocks()
  tab = 'overview'
})

test('shows loading, tolerates optional TOTP failure, and renders overview data', async () => {
  let resolveStats!: (value: typeof stats) => void
  getStats.mockImplementation(() => new Promise(resolve => { resolveStats = resolve }))
  getTOTPStats.mockRejectedValue(new Error('unavailable'))
  let renderer!: ReactTestRenderer

  act(() => {
    renderer = create(<DashboardPage />)
  })
  expect(renderer.root.findByProps({ 'data-icon': 'loader' })).toBeDefined()

  await act(async () => resolveStats(stats))
  const overview = renderer.root.findByProps({ 'data-tab': 'overview' })
  expect(getTrends).toHaveBeenCalledWith('30d')
  expect(overview.props.stats).toEqual(stats)
  expect(overview.props.totpStats).toBeNull()
  unmount(renderer)
})

test('keeps the loading fallback when common statistics fail', async () => {
  getStats.mockRejectedValue(new Error('offline'))
  const renderer = await render()

  expect(renderer.root.findByProps({ 'data-icon': 'loader' })).toBeDefined()
  unmount(renderer)
})

test('loads every models result and handles individual failures', async () => {
  tab = 'models'
  getModelDistribution.mockRejectedValueOnce(new Error('models'))
  getTeamTokenUsage.mockRejectedValueOnce(new Error('teams'))
  getTopAgents.mockRejectedValueOnce(new Error('agents'))
  getTrends.mockRejectedValueOnce(new Error('trends'))
  const renderer = await render()

  const models = renderer.root.findByProps({ 'data-tab': 'models' })
  expect(getModelDistribution).toHaveBeenCalledWith({ time_range: '30d' })
  expect(getTeamTokenUsage).toHaveBeenCalledWith({ limit: 10, time_range: '30d' })
  expect(models.props).toMatchObject({
    modelData: [],
    teamTokenData: [],
    topAgentsData: [],
    trendsData: [{ date: '2026-01-01', tokens: 2 }],
    isLoading: false,
  })
  unmount(renderer)
})

test('changes tabs, updates the URL, and refreshes analytics', async () => {
  const renderer = await render()

  await act(async () => renderer.root.findByProps({ 'data-tabs': true }).props.onClick())
  expect(push).toHaveBeenCalledWith('?tab=analytics', { scroll: false })
  expect(renderer.root.findByProps({ 'data-tab': 'analytics' })).toBeDefined()

  getWorkflowSummary.mockClear()
  await act(async () => renderer.root.findAllByType('button').at(-1)!.props.onClick())
  expect(getWorkflowSummary).toHaveBeenCalledWith({ time_range: '30d' })
  unmount(renderer)
})

test('changes time range and handles analytics metric success and failure', async () => {
  tab = 'analytics'
  const renderer = await render()

  await act(async () => renderer.root.findByProps({ 'data-time-range': true }).props.onClick())
  expect(getStats).toHaveBeenCalled()

  let analytics = renderer.root.findByProps({ 'data-tab': 'analytics' })
  getTopAgents.mockResolvedValueOnce([{ id: 'agent-1' }])
  await act(async () => analytics.props.onMetricChange('message_count'))
  analytics = renderer.root.findByProps({ 'data-tab': 'analytics' })
  expect(analytics.props.currentMetric).toBe('message_count')
  expect(analytics.props.topAgentsData).toEqual([{ id: 'agent-1' }])

  getTopAgents.mockRejectedValueOnce(new Error('agents'))
  await act(async () => analytics.props.onMetricChange('total_tokens'))
  expect(renderer.root.findByProps({ 'data-tab': 'analytics' }).props.isLoadingAgents).toBe(false)
  unmount(renderer)
})
