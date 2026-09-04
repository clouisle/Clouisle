import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const SelectContext = React.createContext<(value: string) => void>(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => true }),
}))

mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: { children: React.ReactNode; variant?: string }) => <span data-variant={variant}>{children}</span>,
}))

mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (value: string) => void }) => (
    <SelectContext.Provider value={onValueChange}>{children}</SelectContext.Provider>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => {
    const onValueChange = React.useContext(SelectContext)
    return <button onClick={() => onValueChange(value)}>{children}</button>
  },
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

mock.module('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children, data }: { children: React.ReactNode; data: Array<{ name: string }> }) => <div>{data.map(item => item.name).join(',')}{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Cell: () => null,
}))

import { AgentPerformanceChart } from './agent-performance-chart'
import { TeamTokenUsageChart } from './team-token-usage-chart'
import { TopWorkflowsCard } from './top-workflows-card'
import { WorkflowStatusChart } from './workflow-status-chart'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

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

function text(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

describe('dashboard analytics widgets', () => {
  test('shows workflow loading, empty, and ranked data with success-rate variants', () => {
    expect(text(render(<TopWorkflowsCard data={[]} isLoading />))).toContain('common.loading')
    expect(text(render(<TopWorkflowsCard data={[]} />))).toContain('common.noData')

    const renderer = render(<TopWorkflowsCard data={[
      { workflow_id: 'one', name: 'Import', run_count: 1200, success_rate: 95 },
      { workflow_id: 'two', name: 'Retry', run_count: 3, success_rate: 65 },
    ]} />)
    expect(text(renderer)).toContain('Import')
    expect(text(renderer)).toContain('common.runCount')
    expect(renderer.root.findAllByProps({ 'data-variant': 'default' })).toHaveLength(1)
    expect(renderer.root.findAllByProps({ 'data-variant': 'destructive' })).toHaveLength(1)
  })

  test('renders status and team chart loading, filtered-empty, and data states', () => {
    expect(text(render(<WorkflowStatusChart data={[]} isLoading />))).toContain('common.loading')
    expect(text(render(<WorkflowStatusChart data={[]} />))).toContain('common.noData')
    expect(text(render(<WorkflowStatusChart data={[{ status: 'completed', count: 8 }]} />))).toContain('analytics.workflowStatus')

    expect(text(render(<TeamTokenUsageChart data={[{ team_id: 'idle', name: 'Idle', total_tokens: 0, conversations: 0, messages: 0 }]} />))).toContain('common.noData')
    const team = render(<TeamTokenUsageChart data={[{ team_id: 'core', name: 'Core', total_tokens: 1500, conversations: 2, messages: 5 }]} />)
    expect(text(team)).toContain('Core')
  })

  test('reports metric selection payload while retaining loading, empty, and data content', () => {
    const onMetricChange = mock(() => {})
    expect(text(render(<AgentPerformanceChart data={[]} metric="conversation_count" onMetricChange={onMetricChange} isLoading />))).toContain('common.loading')

    const empty = render(<AgentPerformanceChart data={[]} metric="conversation_count" onMetricChange={onMetricChange} />)
    expect(text(empty)).toContain('common.noData')
    act(() => empty.root.findAllByType('button').find(button => button.children.includes('metrics.tokenUsage'))!.props.onClick())
    expect(onMetricChange).toHaveBeenCalledWith('total_tokens')

    const data = render(<AgentPerformanceChart
      data={[{ agent_id: 'a1', name: 'Researcher', icon: null, value: 42, team_name: 'Core' }]}
      metric="message_count"
      onMetricChange={onMetricChange}
    />)
    expect(text(data)).toContain('Researcher')
  })
})
