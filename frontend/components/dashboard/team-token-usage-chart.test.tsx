import { describe, expect, mock, test } from 'bun:test'
import { isValidElement, type ReactNode } from 'react'

const Recharts = {
  BarChart: () => null,
  Bar: () => null,
  CartesianGrid: () => null,
  Cell: () => null,
  ResponsiveContainer: () => null,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('recharts', () => Recharts)

const { TeamTokenUsageChart } = await import('./team-token-usage-chart')

type ElementWithProps = { type: unknown; props: Record<string, unknown> }

function findElement(node: ReactNode, type: unknown): ElementWithProps | undefined {
  if (!isValidElement(node)) return undefined
  if (node.type === type) return node as ElementWithProps

  for (const child of [node.props.children].flat()) {
    const found = findElement(child, type)
    if (found) return found
  }
}

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!isValidElement(node)) return ''
  return [node.props.children].flat().map(textContent).join('')
}

const team = {
  team_id: 'team-1',
  name: 'Platform',
  total_tokens: 1_500,
  conversations: 12_345,
  messages: 67_890,
}

describe('TeamTokenUsageChart', () => {
  test('shows loading before evaluating token usage data', () => {
    const chart = TeamTokenUsageChart({ data: [], isLoading: true })

    expect(textContent(chart)).toContain('common.loading')
  })

  test('shows no-data when every team has zero token usage', () => {
    const chart = TeamTokenUsageChart({ data: [{ ...team, total_tokens: 0 }] })

    expect(textContent(chart)).toContain('common.noData')
  })

  test('filters zero usage and formats active tooltip values', () => {
    const chart = TeamTokenUsageChart({
      data: [{ ...team, total_tokens: 0 }, team],
    })
    const barChart = findElement(chart, Recharts.BarChart)
    const tooltip = findElement(chart, Recharts.Tooltip)

    expect(barChart?.props.data).toEqual([team])
    expect(tooltip).toBeDefined()

    const content = tooltip?.props.content as (props: {
      active?: boolean
      payload?: Array<{ payload: typeof team }>
    }) => ReactNode

    expect(content({ active: false, payload: [{ payload: team }] })).toBeNull()
    expect(content({ active: true, payload: [] })).toBeNull()
    expect(textContent(content({ active: true, payload: [{ payload: team }] }))).toContain('1.5K')
    expect(textContent(content({ active: true, payload: [{ payload: { ...team, total_tokens: 1_000_000 } }] }))).toContain('1.0M')
    expect(textContent(content({ active: true, payload: [{ payload: { ...team, total_tokens: 999 } }] }))).toContain('999')
  })
})
