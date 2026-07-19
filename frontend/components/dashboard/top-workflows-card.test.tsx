import { describe, expect, mock, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { count: string }) => {
    if (key === 'common.loading') return 'Loading'
    if (key === 'common.noData') return 'No data'
    if (key === 'common.runCount') return `${values?.count} runs`
    return key
  },
}))

const { TopWorkflowsCard } = await import('./top-workflows-card')

function renderCard(
  data: Array<{ workflow_id: string; name: string; run_count: number; success_rate: number }>,
  isLoading = false,
) {
  return renderToStaticMarkup(<TopWorkflowsCard data={data} isLoading={isLoading} />)
}

describe('TopWorkflowsCard', () => {
  test('shows a loading state before rendering workflow data', () => {
    const html = renderCard([], true)

    expect(html).toContain('Loading')
    expect(html).not.toContain('No data')
  })

  test('shows an empty state when no workflows are available', () => {
    const html = renderCard([])

    expect(html).toContain('No data')
  })

  test('renders workflows with abbreviated runs and success-rate thresholds', () => {
    const html = renderCard([
      { workflow_id: 'high', name: 'High success', run_count: 1_500, success_rate: 90 },
      { workflow_id: 'medium', name: 'Medium success', run_count: 1_000_000, success_rate: 70 },
      { workflow_id: 'low', name: 'Low success', run_count: 42, success_rate: 69.9 },
    ])

    expect(html).toContain('High success')
    expect(html).toContain('1.5K runs')
    expect(html).toContain('1.0M runs')
    expect(html).toContain('42 runs')
    expect(html).toContain('90.0%')
    expect(html).toContain('70.0%')
    expect(html).toContain('69.9%')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('data-variant="secondary"')
    expect(html).toContain('data-variant="destructive"')
  })
})
