import { describe, expect, it, mock } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => true }),
}))

mock.module('recharts', () => {
  const passthrough = ({ children }: { children?: React.ReactNode }) => <>{children}</>

  return {
    ResponsiveContainer: passthrough,
    PieChart: passthrough,
    Pie: ({ data }: { data: Array<{ status: string; count: number }> }) => (
      <output data-testid="chart-data">{JSON.stringify(data)}</output>
    ),
    Cell: () => null,
    Tooltip: () => null,
  }
})

const { WorkflowStatusChart } = await import('./workflow-status-chart')

describe('WorkflowStatusChart', () => {
  it('renders the loading state instead of chart data', () => {
    const markup = renderToStaticMarkup(<WorkflowStatusChart data={[{ status: 'success', count: 3 }]} isLoading />)

    expect(markup).toContain('common.loading')
    expect(markup).not.toContain('chart-data')
  })

  it('renders the empty state for an empty distribution', () => {
    const markup = renderToStaticMarkup(<WorkflowStatusChart data={[]} />)

    expect(markup).toContain('common.noData')
    expect(markup).not.toContain('chart-data')
  })

  it('passes populated status data to the chart', () => {
    const data = [{ status: 'success', count: 1200 }, { status: 'failed', count: 5 }]
    const markup = renderToStaticMarkup(<WorkflowStatusChart data={data} />)

    expect(markup).toContain('analytics.workflowStatus')
    expect(markup).toContain('data-testid="chart-data"')
    expect(markup).toContain('status&quot;:&quot;success')
    expect(markup).toContain('count&quot;:1200')
  })
})
