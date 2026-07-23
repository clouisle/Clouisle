import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign(function Component() {}, { displayName: name })
const push = mock(() => {})
const getWorkflow = mock(async () => workflow)
const getWorkflowRuns = mock(async () => ({ items: runs, total: 45 }))
const setters = Array.from({ length: 11 }, () => mock(() => {}))
let stateValues: unknown[] = []
let stateIndex = 0
let effects: (() => void | Promise<void>)[] = []

mock.module('react', () => ({
  useState: (initial: unknown) => [stateValues[stateIndex] ?? initial, setters[stateIndex++]],
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
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
  'Calendar', 'Activity', 'ChevronLeft', 'ChevronRight', 'ArrowLeft', 'ExternalLink', 'FileText',
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

const workflow = { id: 'workflow-1', name: 'Coverage Flow', icon: null }
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
  effects = []
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
  render([workflow, false, [], 0, 1, false, '', 'failed', '30d', false, null])
  await effects[0]()
  expect(getWorkflow).toHaveBeenCalledWith('workflow-1')
  await effects[1]()
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({
    page: 1, pageSize: 20, status: 'failed', createdAfter: expect.any(String),
  }))

  getWorkflow.mockRejectedValueOnce(new Error('missing'))
  getWorkflowRuns.mockRejectedValueOnce(new Error('temporary'))
  render([workflow, false, [], 0, 1, false, '', 'all', 'all', false, null])
  await effects[0]()
  await effects[1]()
  expect(push).toHaveBeenCalledWith('/app/apps')
  expect(setters[1]).toHaveBeenCalledWith(false)
  expect(setters[5]).toHaveBeenCalledWith(false)
})

test('renders statuses, navigates, filters, paginates, and opens the run drawer', () => {
  const tree = render([workflow, false, runs, 45, 2, false, 'needle', 'all', '7d', false, null])
  const nodes = descendants(tree)
  expect(text(tree)).toContain('completed')
  expect(text(tree)).toContain('failed')
  expect(text(tree)).toContain('running')
  const statusBadges = nodes.filter(node => node.type.name === 'StatusBadge')
    .map(node => (node.type as (props: Props) => Node)(node.props))
  expect(statusBadges.some(node => String(node.props.className).includes('yellow'))).toBe(true)
  expect(statusBadges.some(node => String(node.props.className).includes('orange'))).toBe(true)
  expect(text(tree)).toContain('2s')
  expect(text(tree)).toContain('2 / 3')

  nodes.find(node => node.type.displayName === 'Input')!.props.onChange!({ target: { value: 'next' } })
  nodes.find(node => node.type === 'button')!.props.onClick!()
  expect(setters[6]).toHaveBeenCalledWith('next')
  expect(setters[6]).toHaveBeenCalledWith('')

  const selects = nodes.filter(node => node.type.displayName === 'Select')
  selects[0].props.onValueChange!('success')
  selects[0].props.onValueChange!(null)
  selects[1].props.onValueChange!('90d')
  expect(setters[7]).toHaveBeenCalledWith('success')
  expect(setters[8]).toHaveBeenCalledWith('90d')

  const rows = nodes.filter(node => node.type.displayName === 'TableRow' && typeof node.props.onClick === 'function')
  rows[0].props.onClick!()
  expect(setters[10]).toHaveBeenCalledWith('success-run-123')
  expect(setters[9]).toHaveBeenCalledWith(true)

  const buttons = nodes.filter(node => node.type.displayName === 'Button' && typeof node.props.onClick === 'function')
  buttons.at(-2)!.props.onClick!()
  buttons.at(-1)!.props.onClick!()
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({ page: 1 }))
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({ page: 3 }))

  const menuItems = nodes.filter(node => node.type.displayName === 'DropdownMenuItem' && typeof node.props.onClick === 'function')
  menuItems.forEach(node => node.props.onClick!())
  expect(push).toHaveBeenCalledWith('/app/apps/workflow/workflow-1')
  expect(push).toHaveBeenCalledWith('/app/apps/workflow/workflow-1/api')
  expect(push).toHaveBeenCalledWith('/app/apps/workflow/workflow-1/monitor')
})

test('renders empty, loading, icon, and drawer delete branches', () => {
  expect(text(render([workflow, false, [], 0, 1, true, '', 'all', 'all', false, null]))).not.toContain('noRuns')
  expect(text(render([workflow, false, [], 0, 1, false, '', 'all', 'all', false, null]))).toContain('noRuns')
  expect(render([null, true, [], 0, 1, false, '', 'all', 'all', false, null])).toBeDefined()

  const tree = render([{ ...workflow, icon: 'https://example.com/icon.png' }, false, runs, 45, 2, false, '', 'all', 'all', true, 'success-run-123'])
  const drawer = descendants(tree).find(node => node.type.displayName === 'WorkflowRunDrawer')!
  drawer.props.onOpenChange!(false)
  drawer.props.onDelete!()
  expect(setters[9]).toHaveBeenCalledWith(false)
  expect(getWorkflowRuns).toHaveBeenCalledWith('workflow-1', expect.objectContaining({ page: 2 }))
})
