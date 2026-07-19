import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const getAllWorkflowRuns = mock()
const getWorkflows = mock(() => Promise.resolve({ items: [] }))
const getTeams = mock(() => Promise.resolve({ items: [] }))
const getUsers = mock(() => Promise.resolve({ items: [] }))

const element = (tag: string) => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  Component.displayName = tag
  return Component
}

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success: mock() } }))
mock.module('@/lib/api', () => ({
  workflowsApi: { getAllWorkflowRuns, getWorkflows, deleteWorkflowRun: mock() },
}))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => false }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: <T,>(value: T) => value }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('input') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'), SelectContent: element('div'), SelectItem: element('option'),
  SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element('div'), AlertDialogAction: element('button'), AlertDialogCancel: element('button'),
  AlertDialogContent: element('div'), AlertDialogDescription: element('p'), AlertDialogFooter: element('footer'),
  AlertDialogHeader: element('header'), AlertDialogTitle: element('h2'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'),
  DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('./workflow-run-drawer', () => ({
  WorkflowRunDrawer: ({ runId, open }: { runId: string; open: boolean }) =>
    open ? <aside role="dialog" aria-label={`run-${runId}`} /> : null,
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Search', 'Workflow', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'Trash2',
  'MoreHorizontal', 'CheckCircle', 'XCircle', 'Clock', 'Loader', 'Ban', 'AlertTriangle',
].map((name) => [name, element('svg')])))

const { WorkflowRunsTable } = await import('./workflow-runs-table')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<WorkflowRunsTable />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  getAllWorkflowRuns.mockReset()
  getWorkflows.mockReset().mockResolvedValue({ items: [] })
  getTeams.mockReset().mockResolvedValue({ items: [] })
  getUsers.mockReset().mockResolvedValue({ items: [] })
})

describe('WorkflowRunsTable', () => {
  test('keeps its table landmark and loading state visible while runs load', async () => {
    getAllWorkflowRuns.mockImplementation(() => new Promise(() => {}))
    const renderer = await render()

    expect(renderer.root.findByType('table')).toBeDefined()
    expect(JSON.stringify(renderer.toJSON())).toContain('common.loading')
    expect(renderer.root.findAllByType('input').some((node) => node.props.placeholder === 'activities.filters.workflow')).toBe(true)
  })

  test('shows empty results for successful and failed loads', async () => {
    getAllWorkflowRuns.mockResolvedValueOnce({ items: [], total: 0 })
    expect(JSON.stringify((await render()).toJSON())).toContain('activities.noData')

    const error = spyOn(console, 'error').mockImplementation(() => {})
    getAllWorkflowRuns.mockRejectedValueOnce(new Error('unavailable'))
    expect(JSON.stringify((await render()).toJSON())).toContain('activities.noData')
    expect(error).toHaveBeenCalledWith('Failed to load workflow runs:', expect.any(Error))
  })

  test('filters data and opens the selected run drawer', async () => {
    getAllWorkflowRuns.mockResolvedValue({
      items: [{
        id: 'run-12345678', workflow_id: 'workflow-1', workflow_name: 'Daily report', status: 'success',
        trigger_type: 'manual', created_at: '2026-01-01T10:00:00Z', total_duration_ms: 1200,
        executed_nodes: 1, total_nodes: 1,
      }], total: 1,
    })
    const renderer = await render()

    expect(renderer.root.findAllByType('span').some((node) => node.children.includes('Daily report'))).toBe(true)
    await act(async () => renderer.root.findAllByType('input').find((node) => node.props.placeholder === 'activities.filters.workflow')!.props.onChange({ target: { value: 'report' } }))
    expect(getAllWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'report' }))

    act(() => renderer.root.findAllByType('tr')[1].props.onClick())
    expect(renderer.root.findByProps({ role: 'dialog' }).props['aria-label']).toBe('run-run-12345678')
  })
})
