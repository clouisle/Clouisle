import { describe, expect, it, mock } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('recharts', () => {
  const passthrough = ({ children }: { children?: React.ReactNode }) => <>{children}</>

  return {
    ResponsiveContainer: passthrough,
    BarChart: passthrough,
    Bar: passthrough,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Cell: ({ fill }: { fill: string }) => <output data-testid="bar-color">{fill}</output>,
  }
})

const { TeamTokenUsageChart } = await import('./team-token-usage-chart')

describe('TeamTokenUsageChart', () => {
  it('renders loading before data', () => {
    const markup = renderToStaticMarkup(
      <TeamTokenUsageChart data={[{ team_id: 'team-1', name: 'Platform', total_tokens: 2, conversations: 1, messages: 1 }]} isLoading />
    )

    expect(markup).toContain('common.loading')
    expect(markup).not.toContain('bar-color')
  })

  it('renders empty state when all teams have zero token usage', () => {
    const markup = renderToStaticMarkup(
      <TeamTokenUsageChart data={[{ team_id: 'team-1', name: 'Platform', total_tokens: 0, conversations: 1, messages: 1 }]} />
    )

    expect(markup).toContain('common.noData')
    expect(markup).not.toContain('bar-color')
  })

  it('filters zero usage teams and renders a bar for each remaining team', () => {
    const markup = renderToStaticMarkup(
      <TeamTokenUsageChart data={[
        { team_id: 'team-1', name: 'Platform', total_tokens: 1200, conversations: 2, messages: 3 },
        { team_id: 'team-2', name: 'Empty', total_tokens: 0, conversations: 0, messages: 0 },
        { team_id: 'team-3', name: 'Research', total_tokens: 2_000_000, conversations: 5, messages: 8 },
      ]} />
    )

    expect(markup).toContain('models.teamRanking')
    expect((markup.match(/data-testid="bar-color"/g) ?? [])).toHaveLength(2)
  })
})
