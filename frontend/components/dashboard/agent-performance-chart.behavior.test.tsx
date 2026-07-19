import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

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
  BarChart: ({ children, data }: { children: React.ReactNode; data: Array<{ name: string }> }) => <div>{data.map(({ name }) => name).join(',')}{children}</div>,
  Bar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Cell: () => null,
}))

import { AgentPerformanceChart } from './agent-performance-chart'

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

describe('AgentPerformanceChart behavior', () => {
  const onMetricChange = mock(() => {})

  test('renders the loading state before evaluating empty data', () => {
    const renderer = render(
      <AgentPerformanceChart data={[]} metric="conversation_count" onMetricChange={onMetricChange} isLoading />
    )

    expect(text(renderer)).toContain('common.loading')
    expect(text(renderer)).not.toContain('common.noData')
  })

  test('renders no-data state for an empty data boundary', () => {
    const renderer = render(
      <AgentPerformanceChart data={[]} metric="message_count" onMetricChange={onMetricChange} />
    )

    expect(text(renderer)).toContain('common.noData')
    expect(text(renderer)).toContain('metrics.messageCount')
  })

  test('renders agent data and reports a metric change', () => {
    const renderer = render(
      <AgentPerformanceChart
        data={[{ agent_id: 'agent-1', name: 'Researcher', icon: null, value: 1500, team_name: 'Core' }]}
        metric="total_tokens"
        onMetricChange={onMetricChange}
      />
    )

    expect(text(renderer)).toContain('Researcher')
    act(() => renderer.root.findAllByType('button').find(button => button.children.includes('metrics.messageCount'))!.props.onClick())
    expect(onMetricChange).toHaveBeenCalledWith('message_count')
  })
})
