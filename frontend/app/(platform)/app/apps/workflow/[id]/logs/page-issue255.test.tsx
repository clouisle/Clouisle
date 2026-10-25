import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign(function Component() {}, { displayName: name })
const push = mock(() => {})
const getWorkflow = mock(async () => workflow)
const getWorkflowRuns = mock(async () => ({ items: runs, total: 45 }))
const setters = Array.from({ length: 13 }, () => mock(() => {}))
let stateValues: unknown[] = []
let stateIndex = 0
let refIndex = 0
const refs: { current: unknown }[] = []
let effects: (() => void | Promise<void>)[] = []
let infiniteOptions: { hasMore: boolean; loading: boolean; onLoadMore: () => Promise<void> | undefined } | null = null

mock.module('react', () => ({
  useState: (initial: unknown) => [stateValues[stateIndex] ?? initial, setters[stateIndex++]],
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
  useRef: (initial: unknown) => {
    const index = refIndex++
    refs[index] ??= { current: initial }
    return refs[index]
  },
}))
mock.module('@/hooks/use-infinite-scroll', () => ({
  useInfiniteScroll: (options: { hasMore: boolean; loading: boolean; onLoadMore: () => Promise<void> | undefined }) => {
    infiniteOptions = options
    return { current: null }
  },
}))
const currentTeam: { id: string; role: string } | null = { id: 'team-1', role: 'admin' }
const currentUser: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam }),
}))
mock.module('@/hooks/use-permissions', () => ({
  usePermissions: () => ({ user: currentUser }),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next/navigation', () => ({ useParams: () => ({ id: 'workflow-1' }), useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Props) => values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('next/image', () => ({ default: component('Image') }))
mock.module('lucide-react', () => Object.fromEntries([
  'Calendar', 'Activity', 'ArrowLeft', 'ExternalLink', 'FileText',
  'LayoutGrid', 'GitBranch', 'CheckCircle', 'XCircle', 'Clock', 'Ban', 'AlertTriangle', 'Search', 'X', 'Loader2',
].map(name => [name, component(name)])))
for (const [path, names] of [
  ['@/components/ui/skeleton', ['Skeleton']],
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/table', ['Table', 'TableBody', 'TableCell', 'TableHead', 'TableHeader', 'TableRow']],
  ['@/components/ui/dropdown-menu', ['DropdownMenu', 'DropdownMenuContent', 'DropdownMenuItem', 'DropdownMenuTrigger']],
  ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/input', ['Input']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, component(name)])))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: unknown) => value }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflow, getWorkflowRuns } }))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({ WorkflowRunDrawer: component('WorkflowRunDrawer') }))

const workflow = { id: 'workflow-1', name: 'Coverage Flow', icon: null, team_id: 'team-1', created_by_id: 'user-1' }
const runs = [
  { id: 'success-run-123', status: 'success', trigger_type: 'manual', created_at: '2026-01-02T03:04:05Z', started_at: '2026-01-02T03:04:05Z', finished_at: '2026-01-02T03:04:07Z' },
  { id: 'failed-run-1234', status: 'failed', trigger_type: 'api', created_at: '2026-01-02T03:04:05Z' },
  { id: 'running-run-123', status: 'running', trigger_type: 'webhook', created_at: '2026-01-02T03:04:05Z' },
  { id: 'cancelled-run-1', status: 'cancelled', trigger_type: 'manual', created_at: '2026-01-02T03:04:05Z' },
  { id: 'timeout-run-123', status: 'timeout', trigger_type: 'manual', created_at: '2026-01-02T03:04:05Z' },
]

const { default: WorkflowLogsPage } = await import('./page')

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  return text((value as Node).props.children)
}

function render(values: unknown[]) {
  stateValues = values
  stateIndex = 0
  refIndex = 0
  refs.length = 0
  effects = []
  infiniteOptions = null
  return WorkflowLogsPage() as Node
}

beforeEach(() => {
  setters.forEach(setter => setter.mockClear())
  push.mockClear()
  getWorkflow.mockReset()
  getWorkflow.mockResolvedValue(workflow as never)
  getWorkflowRuns.mockReset()
  getWorkflowRuns.mockResolvedValue({ items: runs, total: 45 } as never)
})

test('loads workflow and filtered runs, including failure paths', async () => {
  render([workflow, false, [], 0, 1, false, false, null, '', 'failed', '30d', false, null])
  await effects[0]()
  expect(getWorkflow).toHaveBeenCalledWith('workflow-1')
  await effects[1]()
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({
    page: 1, pageSize: 20, status: 'failed', createdAfter: expect.any(String),
  }))

  getWorkflow.mockRejectedValueOnce(new Error('missing'))
  getWorkflowRuns.mockRejectedValueOnce(new Error('temporary'))
  render([workflow, false, [], 0, 1, false, false, null, '', 'all', 'all', false, null])
  await effects[0]()
  await effects[1]()
  expect(push).toHaveBeenCalledWith('/app/apps')
  expect(setters[1]).toHaveBeenCalledWith(false)
  expect(setters[5]).toHaveBeenCalledWith(false)
})

test('renders statuses, navigates, filters, loads more, and opens the run drawer', async () => {
  const tree = render([workflow, false, runs, 45, 2, false, false, null, 'needle', 'all', '7d', false, null])
  const nodes = descendants(tree)
  expect(text(tree)).toContain('completed')
  expect(text(tree)).toContain('failed')
  expect(text(tree)).toContain('running')
  const statusBadges = nodes.filter(node => node.type.name === 'StatusBadge')
    .map(node => (node.type as (props: Props) => Node)(node.props))
  expect(statusBadges.some(node => String(node.props.className).includes('yellow'))).toBe(true)
  expect(statusBadges.some(node => String(node.props.className).includes('orange'))).toBe(true)
  expect(text(tree)).toContain('2s')

  nodes.find(node => node.type.displayName === 'Input')!.props.onChange!({ target: { value: 'next' } })
  nodes.find(node => node.type === 'button')!.props.onClick!()
  expect(setters[8]).toHaveBeenCalledWith('next')
  expect(setters[8]).toHaveBeenCalledWith('')

  const selects = nodes.filter(node => node.type.displayName === 'Select')
  selects[0].props.onValueChange!('success')
  selects[0].props.onValueChange!(null)
  selects[1].props.onValueChange!('90d')
  expect(setters[9]).toHaveBeenCalledWith('success')
  expect(setters[10]).toHaveBeenCalledWith('90d')

  const rows = nodes.filter(node => node.type.displayName === 'TableRow' && typeof node.props.onClick === 'function')
  rows[0].props.onClick!()
  expect(setters[12]).toHaveBeenCalledWith('success-run-123')
  expect(setters[11]).toHaveBeenCalledWith(true)

  expect(infiniteOptions?.hasMore).toBe(true)
  await infiniteOptions?.onLoadMore()
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({ page: 3 }))

  const menuItems = nodes.filter(node => node.type.displayName === 'DropdownMenuItem' && typeof node.props.onClick === 'function')
  menuItems.forEach(node => node.props.onClick!())
  expect(push).toHaveBeenCalledWith('/app/apps/workflow/workflow-1')
  expect(push).toHaveBeenCalledWith('/app/apps/workflow/workflow-1/api')
  expect(push).toHaveBeenCalledWith('/app/apps/workflow/workflow-1/monitor')
})

test('renders empty, loading, icon, and drawer delete branches', () => {
  expect(text(render([workflow, false, [], 0, 1, true, false, null, '', 'all', 'all', false, null]))).not.toContain('noRuns')
  expect(text(render([workflow, false, [], 0, 1, false, false, null, '', 'all', 'all', false, null]))).toContain('noRuns')
  expect(render([null, true, [], 0, 1, false, false, null, '', 'all', 'all', false, null])).toBeDefined()

  const tree = render([{ ...workflow, icon: 'https://example.com/icon.png' }, false, runs, 45, 2, false, false, null, '', 'all', 'all', true, 'success-run-123'])
  const drawer = descendants(tree).find(node => node.type.displayName === 'WorkflowRunDrawer')!
  drawer.props.onOpenChange!(false)
  drawer.props.onDelete!()
  expect(setters[11]).toHaveBeenCalledWith(false)
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({ page: 1 }))
})
