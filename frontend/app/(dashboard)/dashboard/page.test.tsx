import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const getStats = mock(() => Promise.resolve({ total_users: 1 }))
const getTrends = mock(() => Promise.resolve({ data: [] }))
const getTOTPStats = mock(() => Promise.resolve(null))
const push = mock(() => {})
let tab = 'overview'

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({ get: () => tab }),
}))
mock.module('lucide-react', () => ({ Loader2: () => null, RefreshCw: () => null }))
mock.module('@/lib/api/admin/dashboard', () => ({
  dashboardApi: {
    getStats,
    getTrends,
    getModelDistribution: mock(() => Promise.resolve([])),
    getTeamTokenUsage: mock(() => Promise.resolve([])),
    getTopAgents: mock(() => Promise.resolve([])),
    getWorkflowSummary: mock(() => Promise.resolve(null)),
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
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))
mock.module('@/components/dashboard/time-range-selector', () => ({ TimeRangeSelector: () => null }))
mock.module('./_components/overview-tab', () => ({
  OverviewTab: () => <div data-tab="overview" />,
}))
mock.module('./_components/models-tab', () => ({ ModelsTab: () => <div data-tab="models" /> }))
mock.module('./_components/analytics-tab', () => ({
  AnalyticsTab: () => <div data-tab="analytics" />,
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

afterEach(() => {
  mock.clearAllMocks()
  tab = 'overview'
})

test('loads dashboard statistics and the overview data for the initial tab', async () => {
  const renderer = await render()

  expect(getStats).toHaveBeenCalled()
  expect(getTrends).toHaveBeenCalledWith('30d')
  expect(renderer.root.findByProps({ 'data-tab': 'overview' })).toBeDefined()
  act(() => renderer.unmount())
})

test('loads model data when the URL selects the models tab', async () => {
  tab = 'models'
  const renderer = await render()

  expect(renderer.root.findByProps({ 'data-tab': 'models' })).toBeDefined()
  act(() => renderer.unmount())
})
