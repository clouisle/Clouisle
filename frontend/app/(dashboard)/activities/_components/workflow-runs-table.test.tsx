import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const getAllWorkflowRuns = mock()
const getWorkflows = mock(() => Promise.resolve({ items: [] }))
const deleteWorkflowRun = mock(async () => {})
const getTeams = mock(() => Promise.resolve({ items: [] }))
const getUsers = mock(() => Promise.resolve({ items: [] }))
const success = mock()

const element = (tag: string) => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  Component.displayName = tag
  return Component
}

function text(value: React.ReactNode): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(value)) return text(value.props.children)
  return ''
}

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/lib/api', () => ({
  workflowsApi: { getAllWorkflowRuns, getWorkflows, deleteWorkflowRun },
}))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
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
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement } & Record<string, unknown>) =>
    render ? React.cloneElement(render, { ...props, ...(children !== undefined ? { children } : {}) }) : <button {...props}>{children}</button>,
}))
mock.module('./workflow-run-drawer', () => ({
  WorkflowRunDrawer: ({ runId, open }: { runId: string; open: boolean }) =>
    open ? <aside role="dialog" aria-label={`run-${runId}`} /> : null,
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Search', 'Workflow', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'Trash2',
  'MoreHorizontal', 'CheckCircle', 'XCircle', 'Clock', 'Loader', 'Ban', 'AlertTriangle', 'Copy',
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
  deleteWorkflowRun.mockClear()
  getTeams.mockReset().mockResolvedValue({ items: [] })
  getUsers.mockReset().mockResolvedValue({ items: [] })
  success.mockClear()
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

  test('applies faceted filters, searches users, changes page size, and resets filters', async () => {
    getAllWorkflowRuns.mockResolvedValue({ items: [], total: 40 })
    getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core' }] })
    getWorkflows.mockResolvedValue({ items: [{ id: 'workflow-1', name: 'Daily report' }] })
    getUsers.mockResolvedValue({ items: [{ id: 'user-1', username: 'Ada' }] })
    const renderer = await render()

    const filters = renderer.root.findAllByType('button').filter((button) => button.props.onSelectionChange)
    await act(async () => filters.find((button) => button.props.title === 'common.team')!.props.onSelectionChange(new Set(['team-1'])))
    await act(async () => filters.find((button) => button.props.title === 'activities.filters.workflow')!.props.onSelectionChange(new Set(['workflow-1'])))
    await act(async () => filters.find((button) => button.props.title === 'activities.filters.status')!.props.onSelectionChange(new Set(['failed'])))
    await act(async () => filters.find((button) => button.props.title === 'activities.filters.triggerType')!.props.onSelectionChange(new Set(['cron'])))
    await act(async () => filters.find((button) => button.props.title === 'activities.filters.triggeredBy')!.props.onSearchChange('ada'))
    expect(getUsers).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'ada' }))
    await act(async () => filters.find((button) => button.props.title === 'activities.filters.triggeredBy')!.props.onSelectionChange(new Set(['user-1'])))

    expect(getAllWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({
      teamId: ['team-1'], workflowId: ['workflow-1'], status: ['failed'], triggerType: ['cron'], userId: ['user-1'],
    }))

    await act(async () => renderer.root.findByType('select').props.onValueChange('50'))
    expect(getAllWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 50 }))

    await act(async () => renderer.root.findAllByType('button').find((button) => text(button.props.children).includes('common.reset'))!.props.onClick())
    expect(getAllWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({
      page: 1, pageSize: 50, teamId: undefined, workflowId: undefined, status: undefined, triggerType: undefined, userId: undefined,
    }))
  })

  test('filters data, opens the selected run drawer, and deletes selected runs', async () => {
    getAllWorkflowRuns.mockResolvedValue({
      items: [
        {
          id: 'run-12345678', workflow_id: 'workflow-1', workflow_name: 'Daily report', status: 'success',
          trigger_type: 'manual', created_at: '2026-01-01T10:00:00Z', total_duration_ms: 1200,
          executed_nodes: 1, total_nodes: 1,
        },
        {
          id: 'run-87654321', workflow_id: 'workflow-2', workflow_name: 'Nightly sync', status: 'failed',
          trigger_type: 'cron', created_at: '2026-01-01T10:01:00Z', total_duration_ms: 61000,
          executed_nodes: 1, total_nodes: 2, triggered_by_name: 'ops',
        },
      ],
      total: 2,
    })
    const renderer = await render()

    expect(renderer.root.findAllByType('span').some((node) => node.children.includes('Daily report'))).toBe(true)
    await act(async () => renderer.root.findAllByType('input').find((node) => node.props.placeholder === 'activities.filters.workflow')!.props.onChange({ target: { value: 'report' } }))
    expect(getAllWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'report' }))

    act(() => renderer.root.findAllByType('tr')[1].props.onClick())
    expect(renderer.root.findByProps({ role: 'dialog' }).props['aria-label']).toBe('run-run-12345678')

    const checkboxes = renderer.root.findAllByType('input').filter((node) => node.props.onCheckedChange)
    act(() => checkboxes[0]!.props.onCheckedChange())
    await act(async () => renderer.root.findAllByType('button').find((button) => text(button.props.children).includes('deleteSelected'))!.props.onClick())
    await act(async () => renderer.root.findAllByType('button').filter((button) => button.children.includes('common.delete')).at(-1)!.props.onClick())

    expect(deleteWorkflowRun).toHaveBeenCalledWith('run-12345678')
    expect(deleteWorkflowRun).toHaveBeenCalledWith('run-87654321')
    expect(success).toHaveBeenCalledWith('activities.runDetail.deleteSuccess')
  })
})
