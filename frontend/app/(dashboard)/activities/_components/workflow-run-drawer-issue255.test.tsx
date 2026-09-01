import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign((props: Props) => jsx(name, props), { displayName: name })

let states: unknown[] = []
let effects: unknown[][] = []
let stateIndex = 0
let effectIndex = 0
const hooks = {
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = initial
    return [states[index] as T, (value: T | ((previous: T) => T)) => {
      states[index] = typeof value === 'function' ? (value as (previous: T) => T)(states[index] as T) : value
    }] as const
  },
  useEffect: (effect: () => void, deps: unknown[]) => {
    const index = effectIndex++
    if (!effects[index] || effects[index].some((value, i) => value !== deps[i])) {
      effects[index] = deps
      effect()
    }
  },
}

const getWorkflowRun = mock(async () => ({}))
const getRunNodeExecutions = mock(async () => [])
const renderNodeOutput = mock(() => 'rendered node output')
const deleteWorkflowRun = mock(async () => {})
const toast = { success: mock(() => {}) }
let allowed = true

mock.module('react', () => ({ default: hooks, ...hooks }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: component('Fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: component('Fragment') }))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => Object.fromEntries(['CheckCircle', 'XCircle', 'Clock', 'Loader', 'Ban', 'AlertTriangle', 'ChevronDown', 'ChevronRight', 'SkipForward', 'Trash2'].map((name) => [name, component(name)])))
mock.module('@/lib/api', () => ({ workflowsApi: { getWorkflowRun, getRunNodeExecutions, deleteWorkflowRun } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => allowed }) }))
mock.module('@/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer', () => ({ renderNodeOutput }))
for (const [path, names] of [
  ['@/components/ui/sheet', ['Sheet', 'SheetContent', 'SheetDescription', 'SheetHeader', 'SheetTitle']],
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/tabs', ['Tabs', 'TabsContent', 'TabsList', 'TabsTrigger']],
  ['@/components/ui/alert', ['Alert', 'AlertDescription', 'AlertTitle']],
  ['@/components/ui/separator', ['Separator']],
  ['@/components/ui/alert-dialog', ['AlertDialog', 'AlertDialogAction', 'AlertDialogCancel', 'AlertDialogContent', 'AlertDialogDescription', 'AlertDialogFooter', 'AlertDialogHeader', 'AlertDialogTitle']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component(name)])))

const { WorkflowRunDrawer } = await import('./workflow-run-drawer')
const onOpenChange = mock(() => {})
const onDelete = mock(() => {})
const run = {
  id: 'run-complete-123', workflow_id: 'wf-1', trigger_type: 'manual', is_debug: true,
  status: 'failed', inputs: { prompt: 'hello' }, outputs: null, depth: 0,
  created_at: '2026-01-02T03:04:00Z', started_at: '2026-01-02T03:04:01Z', finished_at: '2026-01-02T03:05:06Z',
  total_nodes: 2, executed_nodes: 2, failed_nodes: 1, skipped_nodes: 0, total_duration_ms: 65_000,
  total_token_usage: { input: 1200, output: 34 }, error_message: 'node failed', error_node_id: 'node-2',
}
const node = {
  id: 'node-1', run_id: run.id, node_id: 'fetch', node_name: 'Fetch', node_type: 'agent', execution_order: 0,
  status: 'success', execution_duration_ms: 500, total_tokens: 12, prompt_tokens: 9, completion_tokens: 3,
  model_used: 'team-model', inputs: { query: 'hello' }, config_snapshot: { message: 'Research {{query}}' },
  outputs: { response: 'Complete' }, error_message: null,
}

function render(overrides: Props = {}) {
  stateIndex = effectIndex = 0
  return WorkflowRunDrawer({ runId: 'run-complete-123', open: true, onOpenChange, onDelete, ...overrides }) as Node
}
function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('type' in value)) return []
  const current = value as Node
  const rendered = typeof current.type === 'function' ? (current.type as (props: Props) => unknown)(current.props) : current
  if (rendered !== current) return descendants(rendered)
  return [current, ...descendants(current.props.children)]
}
function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  return text((value as Node).props.children)
}
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  states = []
  effects = []
  allowed = true
  for (const fn of [getWorkflowRun, getRunNodeExecutions, renderNodeOutput, deleteWorkflowRun, toast.success, onOpenChange, onDelete]) fn.mockClear()
  getWorkflowRun.mockResolvedValue(run as never)
  getRunNodeExecutions.mockResolvedValue([node] as never)
  deleteWorkflowRun.mockResolvedValue(undefined)
})

describe('dashboard workflow run drawer issue #255 coverage', () => {
  test('loads and renders detailed failed-run data and closes from the action row', async () => {
    render()
    expect(getWorkflowRun).toHaveBeenCalledWith('run-complete-123')
    expect(getRunNodeExecutions).toHaveBeenCalledWith('run-complete-123')
    await flush()

    const tree = render()
    expect(text(tree)).toContain('run-complete-123')
    expect(text(tree)).toContain('1m 5s')
    expect(text(tree)).toContain('1,234')
    expect(text(tree)).toContain('node failed')
    expect(text(tree)).toContain('runDrawer.trace')

    const traceToggle = descendants(tree).find((item) => item.type === 'button' && item.props['aria-expanded'] === false)!
    traceToggle.props.onClick()
    const trace = descendants(render())
    expect(trace.some((item) => item.type === 'pre' && text(item).includes('"query": "hello"'))).toBe(true)
    expect(trace.some((item) => item.type === 'pre' && text(item).includes('Research {{query}}'))).toBe(true)
    expect(renderNodeOutput).toHaveBeenCalledWith('agent', { response: 'Complete' }, expect.any(Function))

    descendants(tree).find((item) => item.type === 'Button' && text(item).includes('close'))!.props.onClick()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('keeps the trace tab informative when the run has no persisted node executions', async () => {
    getRunNodeExecutions.mockResolvedValue([])
    render()
    await flush()

    const tree = render()
    expect(text(tree)).toContain('noNodeExecutions')
    expect(descendants(tree).some((item) => item.type === 'button' && item.props['aria-expanded'] !== undefined)).toBe(false)
  })

  test('confirms deletion and reports success through every parent callback', async () => {
    render()
    await flush()
    let tree = render()
    descendants(tree).find((item) => item.type === 'Button' && text(item).includes('deleteRun'))!.props.onClick()
    tree = render()
    expect(descendants(tree).find((item) => item.type === 'AlertDialog')!.props.open).toBe(true)

    await descendants(tree).find((item) => item.type === 'AlertDialogAction')!.props.onClick()
    expect(deleteWorkflowRun).toHaveBeenCalledWith('run-complete-123')
    expect(toast.success).toHaveBeenCalledWith('runDetail.deleteSuccess')
    expect(onDelete).toHaveBeenCalled()
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(states[3]).toBe(false)
  })

  test('keeps failed requests safe and hides deletion without permission', async () => {
    const error = new Error('network down')
    const consoleError = mock(() => {})
    console.error = consoleError
    getWorkflowRun.mockRejectedValue(error)
    allowed = false

    render()
    await flush()
    const tree = render()
    expect(consoleError).toHaveBeenCalledWith('Failed to load run details:', error)
    expect(descendants(tree).some((item) => item.type === 'Button' && text(item).includes('deleteRun'))).toBe(false)

    deleteWorkflowRun.mockRejectedValue(error)
    states[0] = run
    states[1] = [node]
    states[2] = false
    states[3] = true
    const dialogTree = render()
    await descendants(dialogTree).find((item) => item.type === 'AlertDialogAction')!.props.onClick()
    expect(consoleError).toHaveBeenCalledWith('Failed to delete run:', error)
    expect(onDelete).not.toHaveBeenCalled()
    expect(states[3]).toBe(false)
  })
})
