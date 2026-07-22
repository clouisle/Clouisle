import { afterEach, describe, expect, mock, test } from 'bun:test'
import React, { type ReactNode } from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import type { DashboardStats } from '@/lib/api/admin/dashboard'

globalThis.IS_REACT_ACT_ENVIRONMENT = true
Object.assign(globalThis, {
  window: { matchMedia: () => ({ matches: true }) },
})

const passthrough = ({ children }: { children?: ReactNode }) => <div>{children}</div>
passthrough.displayName = 'Passthrough'
const chart = (name: string) => {
  const Component = (props: Record<string, unknown>) => (
    <div data-chart={name} data-props={JSON.stringify(props)} />
  )
  Component.displayName = name
  return Component
}

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('@/components/ui/card', () => ({
  Card: passthrough,
  CardContent: passthrough,
  CardDescription: passthrough,
  CardHeader: passthrough,
  CardTitle: passthrough,
}))
mock.module('lucide-react', () => ({
  Activity: passthrough,
  Bot: passthrough,
  Building2: passthrough,
  Clock: passthrough,
  Coins: passthrough,
  Database: passthrough,
  MessageSquare: passthrough,
  ShieldAlert: passthrough,
  ShieldCheck: passthrough,
  TrendingUp: passthrough,
  UserPlus: passthrough,
  Users: passthrough,
  Workflow: passthrough,
}))
mock.module('recharts', () => ({
  Area: chart('area'),
  AreaChart: passthrough,
  CartesianGrid: chart('grid'),
  Legend: chart('legend'),
  ResponsiveContainer: passthrough,
  XAxis: chart('x-axis'),
  YAxis: chart('y-axis'),
  Tooltip: ({ content }: { content: React.ReactElement }) => (
    <>{content}{React.cloneElement(content, {
      active: true,
      label: '2026-07-22',
      payload: [
        { name: 'Tokens', value: 1_500_000, color: '#123', payload: {} },
        { name: 'Status', value: 'ready', color: '#456', payload: {} },
      ],
    })}</>
  ),
}))
mock.module('@/components/dashboard/model-distribution-chart', () => ({ ModelDistributionChart: chart('models') }))
mock.module('@/components/dashboard/team-token-usage-chart', () => ({ TeamTokenUsageChart: chart('teams') }))
mock.module('@/components/dashboard/token-trend-chart', () => ({ TokenTrendChart: chart('token-trend') }))
mock.module('@/components/dashboard/model-details-card', () => ({ ModelDetailsCard: chart('model-details') }))
mock.module('@/components/dashboard/top-agents-chart', () => ({ TopAgentsChart: chart('top-agents') }))
mock.module('@/components/dashboard/workflow-status-chart', () => ({ WorkflowStatusChart: chart('workflow-status') }))
mock.module('@/components/dashboard/workflow-trigger-chart', () => ({ WorkflowTriggerChart: chart('workflow-trigger') }))
mock.module('@/components/dashboard/top-workflows-card', () => ({ TopWorkflowsCard: chart('top-workflows') }))
mock.module('@/components/dashboard/agent-performance-chart', () => ({
  AgentPerformanceChart: ({ onMetricChange, ...props }: { onMetricChange: (metric: 'total_tokens') => void }) => (
    <button data-chart="agent-performance" data-props={JSON.stringify(props)} onClick={() => onMetricChange('total_tokens')} />
  ),
}))

const { AnalyticsTab } = await import('./analytics-tab')
const { ModelsTab } = await import('./models-tab')
const { OverviewTab } = await import('./overview-tab')

const renderers: ReactTestRenderer[] = []
afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(element: React.ReactElement) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(element) })
  renderers.push(renderer!)
  return renderer!
}

const stats = (overrides: Partial<DashboardStats['overview']> = {}): DashboardStats => ({
  overview: {
    total_users: 25,
    total_teams: 4,
    total_agents: 3,
    total_workflows: 2,
    total_knowledge_bases: 1,
    total_conversations: 5,
    total_messages: 2_000,
    total_tokens: 3_000_000,
    ...overrides,
  },
  active_users: { dau: 12, wau: 1_200, mau: 1_500_000 },
  growth: { new_users_30d: 7, new_conversations_30d: 8 },
})

const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())
const chartProps = (renderer: ReactTestRenderer, name: string) => JSON.parse(
  renderer.root.find((node) => node.props['data-chart'] === name).props['data-props'],
)

describe('dashboard tabs', () => {
  test('AnalyticsTab renders summaries and forwards metric changes', () => {
    const changes: string[] = []
    const renderer = render(<AnalyticsTab
      stats={stats()}
      workflowData={{
        total_runs: 1_200,
        success_rate: 98.25,
        avg_duration_ms: 61_000,
        status_distribution: [{ status: 'completed', count: 4 }],
        trigger_type_distribution: [{ type: 'manual', count: 3 }],
        top_workflows: [{ workflow_id: 'w1', name: 'Flow', run_count: 2, success_rate: 100 }],
      }}
      topAgentsData={[{ agent_id: 'a1', name: 'Agent One', icon: null, value: 9, team_name: 'Team' }]}
      isLoading={false}
      isLoadingAgents
      currentMetric="conversation_count"
      onMetricChange={(metric) => changes.push(metric)}
    />)

    expect(text(renderer)).toContain('1.2K')
    expect(text(renderer)).toContain('98.3%')
    expect(text(renderer)).toContain('1.0m')
    expect(text(renderer)).toContain('Agent One')
    expect(chartProps(renderer, 'agent-performance')).toMatchObject({ metric: 'conversation_count', isLoading: true })
    act(() => renderer.root.findByType('button').props.onClick())
    expect(changes).toEqual(['total_tokens'])
  })

  test('AnalyticsTab renders null-data and zero-denominator defaults', () => {
    const renderer = render(<AnalyticsTab
      stats={stats({ total_conversations: 0, total_messages: 0, total_tokens: 0 })}
      workflowData={null}
      topAgentsData={[]}
      isLoading={false}
      isLoadingAgents={false}
      currentMetric="message_count"
      onMetricChange={() => {}}
    />)

    expect(text(renderer)).toContain('N/A')
    expect(chartProps(renderer, 'workflow-status').data).toEqual([])
    expect(chartProps(renderer, 'workflow-trigger').data).toEqual([])
    expect(chartProps(renderer, 'top-workflows').data).toEqual([])
  })

  test('ModelsTab forwards chart data and only shows meaningful top-agent data', () => {
    const modelData = [{ model: 'opus', count: 4, percentage: 100 }]
    const teamTokenData = [{ team_id: 't1', name: 'Team', total_tokens: 20, conversations: 2, messages: 4 }]
    const trendsData = [{ date: '2026-07-22', tokens: 20 }]
    const topAgentsData = [{ agent_id: 'a1', name: 'Agent', icon: null, value: 5, team_name: 'Team' }]
    const renderer = render(<ModelsTab
      stats={stats()}
      modelData={modelData}
      teamTokenData={teamTokenData}
      topAgentsData={topAgentsData}
      trendsData={trendsData}
      isLoading={false}
    />)

    expect(text(renderer)).toContain('3.0M')
    expect(text(renderer)).toContain('1.5K')
    expect(chartProps(renderer, 'models').data).toEqual(modelData)
    expect(chartProps(renderer, 'teams').data).toEqual(teamTokenData)
    expect(chartProps(renderer, 'token-trend').data).toEqual(trendsData)
    expect(chartProps(renderer, 'top-agents')).toMatchObject({ data: topAgentsData, metric: 'total_tokens', isLoading: false })

    const empty = render(<ModelsTab
      stats={stats({ total_messages: 0 })}
      modelData={[]}
      teamTokenData={[]}
      topAgentsData={[{ ...topAgentsData[0], value: 0 }]}
      trendsData={[]}
      isLoading={false}
    />)
    expect(empty.root.findAll((node) => node.props['data-chart'] === 'top-agents')).toHaveLength(0)
  })

  test('ModelsTab keeps the top-agent skeleton while loading', () => {
    const renderer = render(<ModelsTab
      stats={stats()}
      modelData={[]}
      teamTokenData={[]}
      topAgentsData={[]}
      trendsData={[]}
      isLoading
    />)
    expect(chartProps(renderer, 'top-agents').isLoading).toBe(true)
    expect(text(renderer)).toContain('animate-pulse')
  })

  test('OverviewTab renders tooltip, 2FA, and password-expiration branches', () => {
    const dashboardStats = stats()
    dashboardStats.password_expiration = { expired_count: 2, expiring_soon_count: 3, force_change_count: 4 }
    const renderer = render(<OverviewTab
      stats={dashboardStats}
      trendsData={[{ date: '2026-07-22', new_users: 1, active_users: 2, new_conversations: 3, messages: 4, tokens: 5 }]}
      isLoading={false}
      totpStats={{ total_users: 20, totp_enabled: 10, adoption_rate: 50.05 }}
    />)

    expect(text(renderer)).toContain('1.5M')
    expect(text(renderer)).toContain('ready')
    expect(text(renderer)).toContain('50.0')
    expect(text(renderer)).toContain('dashboard.home.passwordExpiration.expired')
    expect(text(renderer)).toContain('dashboard.home.passwordExpiration.expiringSoon')
    expect(text(renderer)).toContain('dashboard.home.passwordExpiration.forceChange')

    const allGoodStats = stats()
    allGoodStats.password_expiration = { expired_count: 0, expiring_soon_count: 0, force_change_count: 0 }
    const allGood = render(<OverviewTab stats={allGoodStats} trendsData={[]} isLoading totpStats={null} />)
    expect(text(allGood)).toContain('dashboard.home.passwordExpiration.allGood')
    expect(text(allGood)).toContain('animate-pulse')
    expect(text(allGood)).not.toContain('dashboard.home.stats.twoFactorAuth')
  })
})
