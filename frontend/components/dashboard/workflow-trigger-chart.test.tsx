import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

let tooltipActive = false
let tooltipPayload: unknown[] | undefined

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string) => key === 'triggers.manual' ? 'Manual' : key,
    { has: (key: string) => key === 'triggers.manual' },
  ),
}))

mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

mock.module('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Cell: () => null,
  Tooltip: ({ content }: { content: (props: { active?: boolean; payload?: unknown[] }) => React.ReactNode }) => (
    <div>{content({ active: tooltipActive, payload: tooltipPayload })}</div>
  ),
}))

import { WorkflowTriggerChart } from './workflow-trigger-chart'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function render(data: { type: string; count: number }[] | undefined, isLoading = false) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<WorkflowTriggerChart data={data!} isLoading={isLoading} />)
  })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  tooltipActive = false
  tooltipPayload = undefined
  mock.restore()
})

describe('WorkflowTriggerChart', () => {
  test('renders loading and empty states', () => {
    expect(JSON.stringify(render([], true).toJSON())).toContain('common.loading')
    expect(JSON.stringify(render([]).toJSON())).toContain('common.noData')
  })

  test('formats tooltip counts, percentages, and trigger labels', () => {
    tooltipActive = true
    tooltipPayload = [{ payload: { type: 'manual', count: 1500 } }]
    const renderer = render([{ type: 'manual', count: 1500 }, { type: 'webhook', count: 500 }])

    expect(JSON.stringify(renderer.toJSON())).toContain('Manual')
    expect(JSON.stringify(renderer.toJSON())).toContain('1.5K')
    expect(JSON.stringify(renderer.toJSON())).toContain('75.00')
    expect(JSON.stringify(renderer.toJSON())).toContain('%')

    tooltipPayload = [{ payload: { type: 'unknown', count: 1000000 } }]
    act(() => renderer.update(<WorkflowTriggerChart data={[{ type: 'unknown', count: 1000000 }]} />))
    expect(JSON.stringify(renderer.toJSON())).toContain('unknown')
    expect(JSON.stringify(renderer.toJSON())).toContain('1.0M')
  })

  test('hides inactive tooltips and handles a zero total', () => {
    const renderer = render([{ type: 'manual', count: 0 }])
    expect(JSON.stringify(renderer.toJSON())).not.toContain('common.percentage')

    tooltipActive = true
    tooltipPayload = [{ payload: { type: 'manual', count: 0 } }]
    act(() => renderer.update(<WorkflowTriggerChart data={[{ type: 'manual', count: 0 }]} />))
    expect(JSON.stringify(renderer.toJSON())).toContain('0')
    expect(JSON.stringify(renderer.toJSON())).toContain('%')
  })
})
