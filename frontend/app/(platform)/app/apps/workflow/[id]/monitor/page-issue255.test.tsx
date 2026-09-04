import React, { type ComponentProps, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock(() => {})
const getWorkflow = mock(() => Promise.resolve({ id: 'workflow-1', name: 'Daily report', icon: null }))
const getWorkflowStats = mock(() => Promise.resolve({
  total_runs: 10, success_count: 7, failed_count: 2, timeout_count: 1,
  avg_duration_ms: 1500, last_run_at: null,
}))
const getWorkflowTrends = mock(() => Promise.resolve({ data: [{ date: '2026-07-22', runs: 10, success: 7, failed: 2 }] }))
const getWorkflowRuns = mock(() => Promise.resolve({ items: [{
  id: 'run-1', status: 'success', created_at: '2026-07-22T00:00:00Z', total_duration_ms: 1500,
}] }))

const passthrough = ({ children, ...props }: { children?: ReactNode } & Record<string, unknown>) => <div {...props}>{children}</div>
const Icon = (props: ComponentProps<'i'>) => <i {...props} />

mock.module('next/navigation', () => ({
  useParams: () => ({ id: 'workflow-1' }),
  useRouter: () => ({ push }),
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('next/image', () => ({ default: (props: ComponentProps<'img'>) => <span {...props} /> }))
mock.module('lucide-react', () => ({
  Activity: Icon, TrendingUp: Icon, Clock: Icon, CheckCircle2: Icon, XCircle: Icon,
  AlertTriangle: Icon, Zap: Icon, ArrowLeft: Icon, RefreshCw: Icon, BarChart3: Icon,
  Loader2: Icon, ExternalLink: Icon, FileText: Icon, LayoutGrid: Icon, GitBranch: Icon,
}))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: { getWorkflow, getWorkflowStats, getWorkflowTrends, getWorkflowRuns },
}))
mock.module('@/components/ui/card', () => ({
  Card: passthrough, CardContent: passthrough, CardDescription: passthrough,
  CardHeader: passthrough, CardTitle: passthrough,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/select', () => ({
  Select: passthrough, SelectContent: passthrough, SelectItem: passthrough,
  SelectTrigger: passthrough, SelectValue: passthrough,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: passthrough, DropdownMenuContent: passthrough,
  DropdownMenuItem: ({ children, ...props }: ComponentProps<'button'>) => <button {...props}>{children}</button>,
  DropdownMenuTrigger: passthrough,
}))
mock.module('recharts', () => ({
  AreaChart: passthrough, Area: passthrough, BarChart: passthrough, Bar: passthrough,
  LineChart: passthrough, Line: passthrough, XAxis: passthrough, YAxis: passthrough,
  CartesianGrid: passthrough, Tooltip: passthrough, ResponsiveContainer: passthrough, Legend: passthrough,
}))
mock.module('@/lib/chart-theme', () => ({
  CHART_AXIS_COLOR: '#111', CHART_COLOR_ORDER: Array(9).fill('#222'),
  CHART_GRID_COLOR: '#333', CHART_HOVER_CURSOR: false,
}))

const { default: WorkflowMonitorPage } = await import('./page')
let view: ReactTestRenderer | undefined

async function render() {
  await act(async () => {
    view = create(<WorkflowMonitorPage />)
    await Promise.all([getWorkflow(), getWorkflowStats(), getWorkflowTrends(), getWorkflowRuns()])
  })
  return view!
}

function text(node: ReactTestInstance) {
  return node.children.filter((child): child is string => typeof child === 'string').join('')
}

beforeEach(() => {
  push.mockClear()
  for (const api of [getWorkflow, getWorkflowStats, getWorkflowTrends, getWorkflowRuns]) api.mockClear()
})

afterEach(() => {
  act(() => view?.unmount())
  view = undefined
  mock.restore()
})

describe('WorkflowMonitorPage', () => {
  test('loads monitor data and invokes period, refresh, and navigation callbacks', async () => {
    const page = await render()

    expect(getWorkflowTrends).toHaveBeenCalledWith('workflow-1', '7d')
    expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', { page: 1, pageSize: 5 })
    expect(page.root.findAllByType('p').some((node) => text(node) === 'Daily report')).toBe(true)

    const select = page.root.findByProps({ value: '7d' })
    await act(async () => select.props.onValueChange('30d'))
    expect(getWorkflowTrends).toHaveBeenLastCalledWith('workflow-1', '30d')

    const buttons = page.root.findAllByType('button')
    await act(async () => buttons.at(-1)!.props.onClick())
    expect(getWorkflow).toHaveBeenCalledTimes(4)

    act(() => buttons[0].props.onClick())
    act(() => buttons[1].props.onClick())
    act(() => buttons[2].props.onClick())
    act(() => buttons[3].props.onClick())
    expect(push.mock.calls).toEqual([
      ['/app/apps'],
      ['/app/apps/workflow/workflow-1'],
      ['/app/apps/workflow/workflow-1/api'],
      ['/app/apps/workflow/workflow-1/logs'],
    ])
  })

  test('logs a rejected monitor request and settles refresh state', async () => {
    const failure = new Error('stats unavailable')
    const error = mock(() => {})
    console.error = error
    getWorkflowStats.mockRejectedValueOnce(failure)

    await act(async () => {
      view = create(<WorkflowMonitorPage />)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(error).toHaveBeenCalledWith('Failed to fetch monitor data:', failure)
    expect(view!.root.findByType('i').props.className).toContain('animate-spin')
  })
})
