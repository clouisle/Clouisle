import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign((props: Props) => jsx(name, props), { displayName: name })
let states: unknown[] = [], effects: unknown[][] = [], stateIndex = 0, effectIndex = 0
const hooks = {
  useState: <T,>(initial: T) => { const i = stateIndex++; if (!(i in states)) states[i] = initial; return [states[i] as T, (value: T | ((old: T) => T)) => { states[i] = typeof value === 'function' ? (value as (old: T) => T)(states[i] as T) : value }] as const },
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void, deps: unknown[]) => { const i = effectIndex++; if (!effects[i] || effects[i].some((v, x) => v !== deps[x])) { effects[i] = deps; effect() } },
}
const getAllWorkflowRuns = mock(async () => ({ items: [], total: 0 }))
const getWorkflows = mock(async () => ({ items: [] }))
const deleteWorkflowRun = mock(async () => {})
const getTeams = mock(async () => ({ items: [] }))
const getUsers = mock(async () => ({ items: [] }))
const toast = { success: mock(() => {}) }
let search = ''
const setSearch = mock((value: string) => { search = value })
let allowed = true

mock.module('react', () => ({ default: hooks, ...hooks }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: component('Fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: component('Fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Props) => values ? `${key}:${Object.values(values).join('/')}` : key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => Object.fromEntries(['Search', 'Workflow', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'Trash2', 'MoreHorizontal', 'CheckCircle', 'XCircle', 'Clock', 'Loader', 'Ban', 'AlertTriangle'].map((name) => [name, component(name)])))
mock.module('@/lib/api', () => ({ workflowsApi: { getAllWorkflowRuns, getWorkflows, deleteWorkflowRun } }))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => allowed }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [search, setSearch] }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: unknown) => value }))
mock.module('./workflow-run-drawer', () => ({ WorkflowRunDrawer: component('WorkflowRunDrawer') }))
for (const [path, names] of [
  ['@/components/ui/input', ['Input']], ['@/components/ui/button', ['Button']], ['@/components/ui/badge', ['Badge']], ['@/components/ui/checkbox', ['Checkbox']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/table', ['Table', 'TableBody', 'TableCell', 'TableHead', 'TableHeader', 'TableRow']],
  ['@/components/ui/alert-dialog', ['AlertDialog', 'AlertDialogAction', 'AlertDialogCancel', 'AlertDialogContent', 'AlertDialogDescription', 'AlertDialogFooter', 'AlertDialogHeader', 'AlertDialogTitle']],
  ['@/components/ui/dropdown-menu', ['DropdownMenu', 'DropdownMenuContent', 'DropdownMenuItem', 'DropdownMenuTrigger']],
  ['@/components/ui/data-table-faceted-filter', ['DataTableFacetedFilter']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component(name)])))

const { WorkflowRunsTable } = await import('./workflow-runs-table')
const runs = [
  { id: 'run-123456789', workflow_id: 'wf-1', workflow_name: 'Importer', status: 'success', trigger_type: 'manual', triggered_by_name: 'Ada', is_debug: false, created_at: '2026-01-02T03:04:00Z', total_duration_ms: 65_000, executed_nodes: 2, total_nodes: 2 },
  { id: 'run-987654321', workflow_id: 'wf-2', workflow_name: 'Exporter', status: 'failed', trigger_type: 'cron', triggered_by_name: null, is_debug: false, created_at: '2026-01-03T03:04:00Z', total_duration_ms: null, executed_nodes: 1, total_nodes: 2 },
]
function render() { stateIndex = effectIndex = 0; return WorkflowRunsTable() as Node }
function descendants(value: unknown): Node[] { if (Array.isArray(value)) return value.flatMap(descendants); if (!value || typeof value !== 'object' || !('type' in value)) return []; const node = value as Node; const rendered = typeof node.type === 'function' ? (node.type as (props: Props) => unknown)(node.props) : node; if (rendered !== node) return descendants(rendered); return [node, ...descendants(node.props.children)] }
function text(value: unknown): string { if (typeof value === 'string' || typeof value === 'number') return String(value); if (Array.isArray(value)) return value.map(text).join(''); if (!value || typeof value !== 'object' || !('props' in value)) return ''; return text((value as Node).props.children) }
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  states = []; effects = []; search = ''; allowed = true
  for (const fn of [getAllWorkflowRuns, getWorkflows, deleteWorkflowRun, getTeams, getUsers, toast.success, setSearch]) fn.mockClear()
  getAllWorkflowRuns.mockResolvedValue({ items: runs, total: 42 } as never)
  getWorkflows.mockResolvedValue({ items: [{ id: 'wf-1', name: 'Importer' }] } as never)
  getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core' }] } as never)
  getUsers.mockResolvedValue({ items: [{ id: 'user-1', username: 'ada' }] } as never)
  deleteWorkflowRun.mockResolvedValue(undefined)
})

describe('dashboard workflow runs table issue #255 coverage', () => {
  test('loads rows and drives search, selection, detail, filters, and pagination callbacks', async () => {
    render(); await flush(); let tree = render()
    expect(getAllWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 20 }))
    expect(text(tree)).toContain('Importer')
    expect(text(tree)).toContain('1m 5s')

    const checkboxes = descendants(tree).filter((n) => n.type === 'Checkbox')
    descendants(tree).find((n) => n.type === 'TableRow' && String(n.props.className).includes('cursor-pointer'))!.props.onClick()
    checkboxes[1].props.onCheckedChange()
    tree = render()
    expect(text(tree)).toContain('deleteSelected:1')
    expect(descendants(tree).find((n) => n.type === 'WorkflowRunDrawer')!.props.runId).toBe('run-123456789')

    descendants(tree).find((n) => n.type === 'Input')!.props.onChange({ target: { value: 'import' } })
    expect(setSearch).toHaveBeenCalledWith('import')
    expect(states[2]).toBe(1)

    const filters = descendants(tree).filter((n) => n.type === 'DataTableFacetedFilter')
    filters[0].props.onSelectionChange(new Set(['team-1']))
    filters.at(-1)!.props.onSearchChange('ada')
    expect(states[10]).toEqual(['team-1'])
    expect(states[15]).toBe('ada')

    descendants(tree).find((n) => n.type === 'Select')!.props.onValueChange('50')
    expect(states[3]).toBe(50)
    expect(states[2]).toBe(1)
  })

  test('selects all, deletes selected rows, reloads, and resets filters', async () => {
    render(); await flush(); let tree = render()
    descendants(tree).find((n) => n.type === 'Checkbox')!.props.onCheckedChange()
    tree = render()
    expect((states[5] as Set<string>).size).toBe(2)
    descendants(tree).find((n) => n.type === 'Button' && text(n).includes('deleteSelected'))!.props.onClick()
    tree = render()
    await descendants(tree).find((n) => n.type === 'AlertDialogAction')!.props.onClick()
    expect(deleteWorkflowRun).toHaveBeenCalledTimes(2)
    expect(toast.success).toHaveBeenCalledWith('runDetail.deleteSuccess')
    expect((states[5] as Set<string>).size).toBe(0)
    expect(states[6]).toBe(false)

    search = 'active'; states[10] = ['team-1']; tree = render()
    descendants(tree).find((n) => n.type === 'Button' && text(n).includes('reset'))!.props.onClick()
    expect(setSearch).toHaveBeenCalledWith('')
    expect(states.slice(10, 15)).toEqual([[], [], [], [], []])
  })

  test('renders safe empty/error states without privileged actions', async () => {
    const error = new Error('offline'); const consoleError = mock(() => {}); console.error = consoleError
    allowed = false; getAllWorkflowRuns.mockRejectedValue(error); getTeams.mockRejectedValue(error); getUsers.mockRejectedValue(error)
    render(); await flush(); const tree = render()
    expect(consoleError).toHaveBeenCalled()
    expect(text(tree)).toContain('noData')
    expect(descendants(tree).some((n) => n.type === 'Button' && text(n).includes('deleteSelected'))).toBe(false)
  })
})
