import { describe, expect, mock, test } from 'bun:test'
import { createElement, isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const Tooltip = () => null

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => `dashboard.${key}`,
}))

mock.module('recharts', () => ({
  BarChart: ({ children }: { children: ReactNode }) => children,
  Bar: ({ children }: { children: ReactNode }) => children,
  CartesianGrid: () => null,
  Cell: () => null,
  ResponsiveContainer: ({ children }: { children: ReactNode }) => children,
  Tooltip,
  XAxis: () => null,
  YAxis: () => null,
}))

const { AgentPerformanceChart } = await import('./agent-performance-chart')

type TooltipContent = (props: {
  active?: boolean
  payload?: Array<{ payload: unknown }>
}) => ReactNode

function findElement(node: ReactNode, type: unknown): ReactElement | undefined {
  if (!isValidElement(node)) return undefined
  if (node.type === type) return node

  for (const child of Array.isArray(node.props.children) ? node.props.children : [node.props.children]) {
    const found = findElement(child, type)
    if (found) return found
  }
}

function textContent(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!isValidElement(node)) return ''
  const children = Array.isArray(node.props.children) ? node.props.children : [node.props.children]
  return children.map(textContent).join('')
}

function getTooltipContent(metric: 'conversation_count' | 'message_count' | 'total_tokens'): TooltipContent {
  const chart = (AgentPerformanceChart.type as (props: {
    data: Array<{ agent_id: string, name: string, icon: string | null, value: number, team_name: string }>
    metric: 'conversation_count' | 'message_count' | 'total_tokens'
    onMetricChange: () => void
  }) => ReactNode)({
    data: [{ agent_id: 'agent-1', name: 'Agent One', icon: null, value: 1, team_name: 'Platform' }],
    metric,
    onMetricChange: () => {},
  })
  const tooltip = findElement(chart, Tooltip)

  expect(tooltip).toBeDefined()
  return tooltip!.props.content
}

describe('AgentPerformanceChart states', () => {
  test('renders loading and no-data states', () => {
    const loading = renderToStaticMarkup(createElement(AgentPerformanceChart, {
      data: [], metric: 'message_count', onMetricChange: () => {}, isLoading: true,
    }))
    const empty = renderToStaticMarkup(createElement(AgentPerformanceChart, {
      data: [], metric: 'message_count', onMetricChange: () => {},
    }))

    expect(loading).toContain('dashboard.common.loading')
    expect(empty).toContain('dashboard.common.noData')
  })
})

describe('AgentPerformanceChart tooltip', () => {
  test('formats token values at million, thousand, and base thresholds', () => {
    const content = getTooltipContent('total_tokens')

    expect(textContent(content({ active: true, payload: [{ payload: { name: 'Million', value: 1_200_000, team_name: 'AI', icon: null } }] }))).toContain('dashboard.metrics.tokenUsage: 1.2M')
    expect(textContent(content({ active: true, payload: [{ payload: { name: 'Thousand', value: 2_500, team_name: 'AI', icon: null } }] }))).toContain('dashboard.metrics.tokenUsage: 2.5K')
    expect(textContent(content({ active: true, payload: [{ payload: { name: 'Small', value: 999, team_name: 'AI', icon: null } }] }))).toContain('dashboard.metrics.tokenUsage: 999')
  })

  test.each([
    ['conversation_count', 'dashboard.metrics.conversationCount'],
    ['message_count', 'dashboard.metrics.messageCount'],
  ] as const)('uses the %s label and locale-formats values', (metric, label) => {
    const content = getTooltipContent(metric)

    expect(textContent(content({
      active: true,
      payload: [{ payload: { name: 'Agent One', value: 12_345, team_name: 'Platform', icon: null } }],
    }))).toContain(`${label}: 12,345`)
  })

  test('renders URL, emoji, and fallback icons and hides inactive tooltips', () => {
    const content = getTooltipContent('message_count')
    const urlTooltip = content({ active: true, payload: [{ payload: { name: 'URL', value: 1, team_name: 'AI', icon: '/agent.png' } }] })
    const emojiTooltip = content({ active: true, payload: [{ payload: { name: 'Emoji', value: 1, team_name: 'AI', icon: '🤖' } }] })
    const fallbackTooltip = content({ active: true, payload: [{ payload: { name: 'Fallback', value: 1, team_name: 'AI', icon: null } }] })

    expect(findElement(urlTooltip, 'img')?.props.src).toBe('/agent.png')
    expect(textContent(emojiTooltip)).toContain('🤖')
    expect(textContent(fallbackTooltip)).toContain('Fallback')
    expect(content({ active: false, payload: [{ payload: {} }] })).toBeNull()
    expect(content({ active: true, payload: [] })).toBeNull()
  })
})
