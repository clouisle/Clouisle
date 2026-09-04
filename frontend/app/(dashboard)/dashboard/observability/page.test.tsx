import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getOverview = mock(() => Promise.resolve({}))
const getThroughput = mock(() => Promise.resolve({}))
const getSystemHealth = mock(() => Promise.resolve({}))
const getSystemTrend = mock(() => Promise.resolve({}))
const getSlowQueries = mock(() => Promise.resolve({}))
const getWorkers = mock(() => Promise.resolve({}))
let tab = 'overview'
const translate = (key: string) => key

Object.assign(globalThis, {
  window: {
    setInterval: () => 1,
    clearInterval: () => {},
  },
})

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => translate }))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push: mock(() => {}) }),
  useSearchParams: () => ({ get: () => tab }),
}))
mock.module('lucide-react', () => ({ RefreshCw: () => null }))
mock.module('@/components/auth/permission-guard', () => ({
  RoutePermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/layout/header', () => ({ Header: () => <header /> }))
mock.module('@/components/dashboard/time-range-selector', () => ({ TimeRangeSelector: () => null }))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))
mock.module('@/lib/api/admin/observability', () => ({
  observabilityApi: {
    getOverview,
    getThroughput,
    getSystemHealth,
    getSystemTrend,
    getSlowQueries,
    getWorkers,
    getAgents: mock(() => Promise.resolve({ items: [] })),
    getWorkflows: mock(() => Promise.resolve({ items: [] })),
    getTimeouts: mock(() => Promise.resolve({})),
    getTokens: mock(() => Promise.resolve({})),
  },
}))
mock.module('./_components/observability-panels', () => ({
  AgentsPanel: () => null,
  ErrorState: () => null,
  HealthPanel: () => <div data-panel="health" />,
  ObservabilitySkeleton: () => null,
  OverviewPanel: () => <div data-panel="overview" />,
  SlowQueriesPanel: () => null,
  ThroughputPanel: () => null,
  TimeoutsPanel: () => null,
  TokensPanel: () => null,
  WorkersPanel: () => null,
  WorkflowsPanel: () => null,
}))
mock.module('./tab-data', () => ({ hasTabData: () => true }))

const { default: ObservabilityPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<ObservabilityPage />)
  })
  return renderer!
}

afterEach(() => {
  mock.clearAllMocks()
  tab = 'overview'
})

test('loads overview and throughput data for the initial observability tab', async () => {
  const renderer = await render()

  expect(getOverview).toHaveBeenCalledWith('30d')
  expect(getThroughput).toHaveBeenCalledWith({ time_range: '30d' })
  expect(renderer.root.findByProps({ 'data-panel': 'overview' })).toBeDefined()
  act(() => renderer.unmount())
})

test('loads health data when the URL selects the health tab', async () => {
  tab = 'health'
  const renderer = await render()

  expect(getSystemHealth).toHaveBeenCalled()
  expect(getSlowQueries).toHaveBeenCalledWith({ page_size: 10 })
  expect(renderer.root.findByProps({ 'data-panel': 'health' })).toBeDefined()
  act(() => renderer.unmount())
})
