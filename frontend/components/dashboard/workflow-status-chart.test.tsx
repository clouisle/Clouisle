import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const translations: Record<string, string> = {
  'analytics.workflowStatus': 'Workflow status',
  'analytics.workflowStatusDesc': 'Workflow status description',
  'common.count': 'Count',
  'common.percentage': 'Percentage',
  'status.active': 'Active',
}

let tooltipProps: { active?: boolean; payload?: Array<{ payload: unknown }> } = {}

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string) => translations[key] ?? key,
    { has: (key: string) => key in translations }
  ),
}))

mock.module('recharts', () => ({
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  PieChart: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Pie: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Cell: () => null,
  Legend: () => null,
  Tooltip: ({ content }: { content: (props: typeof tooltipProps) => React.ReactNode }) => <>{content(tooltipProps)}</>,
}))

mock.module('lucide-react', () => ({ CheckCircle2: () => null }))

mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children?: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children?: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children?: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children?: React.ReactNode }) => <h2>{children}</h2>,
}))

const { WorkflowStatusChart } = await import('./workflow-status-chart')

const renderTooltip = (
  data: Array<{ status: string; count: number }>,
  tooltipData = data[0],
  active = true
) => {
  tooltipProps = { active, payload: tooltipData ? [{ payload: tooltipData }] : [] }
  return renderToStaticMarkup(<WorkflowStatusChart data={data} />)
}

describe('WorkflowStatusChart tooltip', () => {
  test('formats large counts and translated status labels', () => {
    expect(renderTooltip([{ status: 'active', count: 1_500_000 }])).toContain('Active</div><div class="text-sm space-y-1"><div>Count: 1.5M</div><div class="font-medium">Percentage: 100.00%')
    expect(renderTooltip([{ status: 'active', count: 1_500 }])).toContain('Count: 1.5K')
  })

  test('falls back to the raw status and formats a zero-total tooltip', () => {
    expect(renderTooltip([{ status: 'unmapped', count: 0 }])).toContain('unmapped</div><div class="text-sm space-y-1"><div>Count: 0</div><div class="font-medium">Percentage: 0%')
  })

  test('omits the tooltip when Recharts marks it inactive', () => {
    const markup = renderTooltip([{ status: 'active', count: 1 }], undefined, false)

    expect(markup).not.toContain('Count:')
    expect(markup).not.toContain('Percentage:')
  })
})
