import { expect, mock, test } from 'bun:test'
import { createElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const barChart = mock(() => null)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('recharts', () => ({
  BarChart: barChart,
  Bar: () => null,
  CartesianGrid: () => null,
  Cell: () => null,
  ResponsiveContainer: ({ children }: { children: ReactNode }) => children,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}))

test('passes only agents with activity to the chart', async () => {
  const { TopAgentsChart } = await import('./top-agents-chart')

  renderToStaticMarkup(createElement(TopAgentsChart, {
    data: [
      { agent_id: 'active', name: 'Active', icon: null, value: 12, team_name: 'Team A' },
      { agent_id: 'idle', name: 'Idle', icon: null, value: 0, team_name: 'Team B' },
    ],
    metric: 'conversation_count',
  }))

  expect(barChart).toHaveBeenCalledWith(
    expect.objectContaining({
      data: [expect.objectContaining({ agent_id: 'active' })],
    }),
    undefined,
  )
})
