import { describe, expect, mock, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

let pieData: Array<{ model: string; count?: number; percentage: number }> = []

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  PieChart: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Pie: ({ data, children }: { data: typeof pieData; children: React.ReactNode }) => {
    pieData = data
    return <>{children}</>
  },
  Cell: () => null,
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

  test('uses the unknown label for unnamed models', () => {
    const html = render({ data: [{ model: '', count: 0, percentage: 0 }] })

    expect(html).toContain('common.unknown')
    expect(html).toContain('common.usageCount: 0')
    expect(html).toContain('common.percentage: 0.00%')
  })
})
