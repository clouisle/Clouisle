import { describe, expect, mock, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

let labelLineValue: unknown
let pieData: Array<{ model: string; count?: number; percentage: number }> = []

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PieChart: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Pie: ({
    data,
    label,
    labelLine,
    children,
  }: {
    data: typeof pieData
    label: (entry: { name?: string; percent?: number }) => string
    labelLine: unknown
    children: React.ReactNode
  }) => {
    pieData = data
    labelLineValue = labelLine
    return (
      <>
        {pieData.map((entry, index) => (
          <div key={index}>label:{label({ name: entry.model, percent: (entry.percentage || 0) / 100 })}</div>
        ))}
        {children}
      </>
    )
  },
  Cell: () => null,
  Legend: ({ formatter }: { formatter: (value: string) => string }) => (
    <>{pieData.map((payload, index) => <div key={index}>{formatter(payload.model)}</div>)}</>
  ),
  Tooltip: ({ content }: { content: (props: unknown) => React.ReactNode }) => (
    <>{pieData.map((payload, index) => <div key={index}>{content({ active: true, payload: [{ payload }] })}</div>)}</>
  ),
}))

const { ModelDistributionChart } = await import('./model-distribution-chart')

const render = (props: React.ComponentProps<typeof ModelDistributionChart>) =>
  renderToStaticMarkup(<ModelDistributionChart {...props} />)

describe('ModelDistributionChart', () => {
  test('shows a loading state before distribution data arrives', () => {
    const html = render({ data: [], isLoading: true })

    expect(html).toContain('charts.modelDistribution')
    expect(html).toContain('charts.modelDistributionDesc')
    expect(html).toContain('common.loading')
    expect(html).not.toContain('common.noData')
  })

  test('shows an empty state without distribution data', () => {
    const html = render({ data: [] })

    expect(html).toContain('common.noData')
    expect(html).not.toContain('common.loading')
  })

  test('renders model data and formats tooltip usage counts', () => {
    const html = render({
      data: [
        { model: 'small', count: 999, percentage: 1 },
        { model: 'thousand', count: 1234, percentage: 12.345 },
        { model: 'million', count: 2345678, percentage: 86.655 },
      ],
    })

    expect(html).toContain('small')
    expect(html).toContain('thousand')
    expect(html).toContain('million')
    expect(html).toContain('common.usageCount: 999')
    expect(html).toContain('common.usageCount: 1.2K')
    expect(html).toContain('common.usageCount: 2.3M')
    expect(html).toContain('common.percentage: 12.35%')
  })

  test('renders leader-line labels only for major sectors', () => {
    const html = render({
      data: [
        { model: 'major', count: 900, percentage: 97 },
        { model: 'minor', count: 100, percentage: 3 },
      ],
    })

    expect(html).toContain('label:major')
    expect(html).not.toContain('label:minor')
    expect(labelLineValue).toEqual({ stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1 })
  })

  test('uses the full UUID in tooltips while preserving the short chart label', () => {
    const fullUuid = '550e8400-e29b-41d4-a716-446655440000'
    const html = render({
      data: [{ model: fullUuid, count: 12, percentage: 100 }],
    })

    expect(html).toContain('models.deletedModel · 550e8400')
    expect(html).toContain(fullUuid)
  })

  test('uses the unknown label for unnamed models', () => {
    const html = render({ data: [{ model: '', count: 0, percentage: 0 }] })

    expect(html).toContain('common.unknown')
    expect(html).toContain('common.usageCount: 0')
    expect(html).toContain('common.percentage: 0.00%')
  })

  test('hides leader-line labels for minor sectors', () => {
    const html = render({ data: [{ model: 'minor-only', count: 5, percentage: 5 }] })

    expect(html).toContain('label:')
    expect(html).not.toContain('label:minor-only')
  })
})
