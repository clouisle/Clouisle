import { describe, expect, it, mock } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => ({
    'models.tokenTrend': 'Token trend',
    'models.tokenTrendDesc': 'Token usage over time',
    'common.loading': 'Loading',
    'common.noData': 'No data',
    'common.tokenUsage': 'Token usage',
  })[key] ?? key,
}))

mock.module('recharts', () => {
  const passthrough = ({ children }: { children?: React.ReactNode }) => <>{children}</>

  return {
    ResponsiveContainer: passthrough,
    AreaChart: passthrough,
    Area: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: ({ content }: { content: (props: { active: boolean; payload: Array<{ payload: { date: string }; value: number }> }) => React.ReactNode }) => <>{[
      { date: '2026-07-20', value: 1_500 },
      { date: '2026-07-21', value: 1_000_000 },
      { date: '2026-07-22', value: 0 },
    ].map(({ date, value }) => content({ active: true, payload: [{ payload: { date }, value }] }))}</>,
  }
})

const { TokenTrendChart } = await import('./token-trend-chart')

describe('TokenTrendChart', () => {
  it('renders loading before chart data', () => {
    const markup = renderToStaticMarkup(<TokenTrendChart data={[]} isLoading />)

    expect(markup).toContain('Loading')
    expect(markup).not.toContain('No data')
    expect(markup).not.toContain('colorTokens')
  })

  it('renders empty state without trend data', () => {
    const markup = renderToStaticMarkup(<TokenTrendChart data={[]} />)

    expect(markup).toContain('No data')
    expect(markup).not.toContain('colorTokens')
  })

  it('renders chart tooltip with abbreviated token values', () => {
    const markup = renderToStaticMarkup(<TokenTrendChart data={[{ date: '2026-07-20', tokens: 1_500 }]} />)

    expect(markup).toContain('2026-07-20')
    expect(markup).toContain('Token usage: 1.5K')
    expect(markup).toContain('Token usage: 1.0M')
    expect(markup).toContain('Token usage: 0')
  })
})
