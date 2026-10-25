import React from 'react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const push = mock(() => undefined)
const router = { push }
const currentTeam: { id: string; role: string } | null = { id: 'team-1', role: 'admin' }
const currentUser: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam }),
}))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({ user: currentUser }),
}))
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
  Calendar: icon('Calendar'), Activity: icon('Activity'), ArrowLeft: icon('ArrowLeft'), ExternalLink: icon('ExternalLink'),
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
const originalIntersectionObserver = globalThis.IntersectionObserver

class TestIntersectionObserver {
  static instances: TestIntersectionObserver[] = []
  readonly root = null
  readonly rootMargin = ''
  readonly thresholds: number[] = []
  private readonly callback: IntersectionObserverCallback

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    TestIntersectionObserver.instances.push(this)
  }

  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return [] }

  trigger(isIntersecting: boolean) {
    this.callback(
      [{ isIntersecting } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    )
  }
}

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
  Object.assign(globalThis, { IntersectionObserver: TestIntersectionObserver })
  ;({ default: WorkflowLogsPage } = await import('./page'))
})

afterAll(() => {
  Object.assign(globalThis, { IntersectionObserver: originalIntersectionObserver })
})

beforeEach(() => {
  TestIntersectionObserver.instances = []
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

  test('filters, searches, loads more when the sentinel intersects, recovers after a run error, and renders empty state', async () => {
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
    await flush()

    const secondRun = { ...run, id: 'run-two-123456789' }
    getWorkflowRuns.mockResolvedValueOnce({ items: [secondRun], total: 2, page: 2, page_size: 20, pages: 1 })
    const observer = TestIntersectionObserver.instances.at(-1)!
    await act(async () => { observer.trigger(true) })
    await flush()

    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 2 }))
    expect(text(renderer)).toContain('run-two-')
  })

  test('keeps loaded runs after a next-page failure and retries manually', async () => {
    getWorkflowRuns.mockImplementation(async () => ({ ...pageOne, total: 41 }))
    const renderer = await render()
    await flush()

    getWorkflowRuns.mockRejectedValueOnce(new Error('temporary next-page failure'))
    const observer = TestIntersectionObserver.instances.at(-1)!
    await act(async () => { observer.trigger(true) })
    await flush()

    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 2 }))
    expect(text(renderer)).toContain('run-1234')
    expect(text(renderer)).not.toContain('temporary next-page failure')

    const secondRun = { ...run, id: 'run-retried-123456789' }
    getWorkflowRuns.mockResolvedValueOnce({ items: [secondRun], total: 2, page: 2, page_size: 20, pages: 1 })
    const retry = renderer.root.findAllByType('button').find((node) => node.children.includes('retry'))!
    await act(async () => retry.props.onClick())
    await flush()

    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 2 }))
    expect(text(renderer)).toContain('run-retr')
  })

  test('shows a manual retry when the initial run load fails', async () => {
    getWorkflowRuns.mockRejectedValueOnce(new Error('initial run failure'))
    const renderer = await render()
    await flush()
    await flush()

    expect(text(renderer)).toContain('loadFailed')
    expect(text(renderer)).not.toContain('initial run failure')

    const retry = renderer.root.findAllByType('button').find((node) => node.children.includes('retry'))!
    await act(async () => retry.props.onClick())
    await flush()

    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 1 }))
    expect(text(renderer)).toContain('run-1234')
  })

  test('stops auto-paging when a next page returns no new runs', async () => {
    getWorkflowRuns.mockImplementation(async (_id: string, options: { page?: number }) =>
      options.page === 2
        ? { items: [], total: 41, page: 2, page_size: 20, pages: 1 }
        : { ...pageOne, total: 41 }
    )
    const renderer = await render()
    await flush()

    const observer = TestIntersectionObserver.instances.at(-1)!
    await act(async () => { observer.trigger(true) })
    await flush()

    expect(getWorkflowRuns).toHaveBeenLastCalledWith(workflow.id, expect.objectContaining({ page: 2 }))
    expect(text(renderer)).toContain('run-1234')

    const callCount = getWorkflowRuns.mock.calls.length
    await flush()
    expect(getWorkflowRuns.mock.calls.length).toBe(callCount)
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
