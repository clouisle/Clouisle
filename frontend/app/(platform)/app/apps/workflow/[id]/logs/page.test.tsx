import React from 'react'
import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const push = mock(() => undefined)
const router = { push }
const getWorkflow = mock(async () => workflow)
const getWorkflowRuns = mock(async () => pageOne)

const workflow = {
  id: 'workflow-1',
  name: 'Coverage workflow',
  icon: null,
  definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
  variables: [],
  status: 'published',
  visibility: 'private',
  version: 1,
  trigger_type: 'manual',
  trigger_config: {},
  run_count: 21,
  success_count: 20,
  fail_count: 1,
  team_id: 'team-1',
  created_by_id: 'user-1',
  created_at: '2026-01-01T00:00:00.000Z',
  updated_at: '2026-01-01T00:00:00.000Z',
}
const run = {
  id: 'run-123456789-secret-free',
  workflow_id: workflow.id,
  trigger_type: 'manual',
  is_debug: false,
  status: 'success',
  created_at: '2026-01-02T00:00:00.000Z',
  started_at: '2026-01-02T00:00:00.000Z',
  finished_at: '2026-01-02T00:00:02.000Z',
  total_duration_ms: 2000,
  executed_nodes: 1,
  total_nodes: 1,
  error_message: null,
}
const pageOne = { items: [run], total: 21, page: 1, page_size: 20, pages: 2 }

mock.module('next/navigation', () => ({ useParams: () => ({ id: workflow.id }), useRouter: () => router }))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflow, getWorkflowRuns } }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('next/image', () => ({ default: (props: Record<string, unknown>) => <img alt="" {...props} /> }))
const icon = (name: string) => {
  const Icon = (props: Record<string, unknown>) => <i data-icon={name} {...props} />
  Icon.displayName = name
  return Icon
}
mock.module('lucide-react', () => ({
  Calendar: icon('Calendar'), Activity: icon('Activity'), ChevronLeft: icon('ChevronLeft'),
  ChevronRight: icon('ChevronRight'), ArrowLeft: icon('ArrowLeft'), ExternalLink: icon('ExternalLink'),
  FileText: icon('FileText'), LayoutGrid: icon('LayoutGrid'), GitBranch: icon('GitBranch'),
  CheckCircle: icon('CheckCircle'), XCircle: icon('XCircle'), Clock: icon('Clock'), Ban: icon('Ban'),
  AlertTriangle: icon('AlertTriangle'), Search: icon('Search'), X: icon('X'), Loader2: icon('Loader2'),
}))

const children = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/skeleton', () => ({ Skeleton: (props: Record<string, unknown>) => <div data-skeleton {...props} /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children: content, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{content}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: children }))
mock.module('@/components/ui/table', () => ({ Table: children, TableBody: children, TableCell: children, TableHead: children, TableHeader: children, TableRow: children }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: children, DropdownMenuContent: children, DropdownMenuItem: children, DropdownMenuTrigger: children }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children: content, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) => <section data-select={value} data-change={onValueChange}>{content}</section>,
  SelectContent: children, SelectItem: children, SelectTrigger: children, SelectValue: children,
}))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({
  WorkflowRunDrawer: (props: Record<string, unknown>) => <aside data-drawer {...props} />,
}))

let WorkflowLogsPage: React.ComponentType

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
}
let currentRenderer: ReactTestRenderer | null = null

async function render() {
  await act(async () => { currentRenderer = create(<WorkflowLogsPage />) })
  return currentRenderer!
}

function text(renderer: ReactTestRenderer) {
  return JSON.stringify(renderer.toJSON())
}

beforeAll(async () => {
  ({ default: WorkflowLogsPage } = await import('./page'))
})

beforeEach(() => {
  push.mockClear()
  getWorkflow.mockClear()
  getWorkflowRuns.mockClear()
  getWorkflow.mockImplementation(async () => workflow)
  getWorkflowRuns.mockImplementation(async () => pageOne)
})

afterEach(async () => {
  if (currentRenderer) {
    await act(async () => {
      currentRenderer?.unmount()
    })
    currentRenderer = null
  }
})
describe('WorkflowLogsPage', () => {
  test('shows loading, then renders safe run state and opens its detail drawer', async () => {
    let resolveWorkflow!: (value: typeof workflow) => void
    getWorkflow.mockImplementationOnce(() => new Promise((resolve) => { resolveWorkflow = resolve }))
    const renderer = await render()
    expect(renderer.root.findAllByProps({ 'data-icon': 'Loader2' })).toHaveLength(1)

    await act(async () => resolveWorkflow(workflow))
    await flush()
    expect(getWorkflowRuns).toHaveBeenCalledWith(workflow.id, { page: 1, pageSize: 20, status: undefined, search: undefined, createdAfter: undefined })
    expect(text(renderer)).toContain('run-1234')
    expect(text(renderer)).toContain('completed')
    expect(text(renderer)).not.toContain('secret-free')

    act(() => renderer.root.findAll((node) => node.props.className === 'cursor-pointer')[0].props.onClick())
    const drawer = renderer.root.findByProps({ 'data-drawer': true })
    expect(drawer.props.runId).toBe(run.id)
    expect(drawer.props.open).toBe(true)

    await act(async () => drawer.props.onDelete())
    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 1 }))
  })

  test('filters, searches, paginates, recovers after a run error, and renders empty state', async () => {
    const renderer = await render()
    const selects = () => renderer.root.findAll((node) => node.type === 'section' && node.props['data-select'])

    getWorkflowRuns.mockRejectedValueOnce(new Error('temporary secret-token failure'))
    await act(async () => selects()[0].props['data-change']('failed'))
    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ status: 'failed', page: 1 }))
    expect(text(renderer)).not.toContain('temporary secret-token failure')

    getWorkflowRuns.mockResolvedValueOnce({ ...pageOne, items: [] })
    const input = renderer.root.findByProps({ placeholder: 'searchRunIdPlaceholder' })
    await act(async () => input.props.onChange({ target: { value: ' run-needle ' } }))
    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ status: 'failed', search: 'run-needle' }))
    expect(text(renderer)).toContain('noRuns')

    getWorkflowRuns.mockResolvedValueOnce(pageOne)
    await act(async () => selects()[1].props['data-change']('7d'))
    const dateRequest = getWorkflowRuns.mock.calls.at(-1)?.[1]
    expect(dateRequest.createdAfter).toBeString()
    expect(Date.now() - new Date(dateRequest.createdAfter as string).getTime()).toBeGreaterThan(6 * 24 * 60 * 60 * 1000)

    const next = renderer.root.findAllByType('button').find((node) => node.children.includes('next'))!
    await act(async () => next.props.onClick())
    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 2 }))
    expect(renderer.root.findAllByType('span').some((node) => node.children.join('') === '2 / 2')).toBe(true)
  })

  test('redirects when workflow loading fails and does not request runs', async () => {
    getWorkflow.mockRejectedValueOnce(new Error('private backend detail'))
    const renderer = await render()
    await flush()

    expect(push).toHaveBeenCalledWith('/app/apps')
    expect(getWorkflowRuns).not.toHaveBeenCalled()
    expect(text(renderer)).not.toContain('private backend detail')
  })
})
