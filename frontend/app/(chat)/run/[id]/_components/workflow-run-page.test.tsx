import { describe, expect, mock, test } from 'bun:test'
import { WorkflowRunPage } from './workflow-run-page'

const states: unknown[] = []
let stateIndex = 0
let effectIndex = 0
const effects: Array<() => void> = []
const setState = (i: number) => (value: unknown) => {
  states[i] = typeof value === 'function' ? (value as (o: unknown) => unknown)(states[i]) : value
}

mock.module('react', () => ({
  useState: (initial: unknown) => {
    const i = stateIndex++
    if (states.length <= i) states[i] = initial
    return [states[i], setState(i)]
  },
  useEffect: (effect: () => void) => { effects[effectIndex++] = effect },
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (cb: unknown) => cb,
  useRef: (value: unknown) => ({ current: value }),
}))
mock.module('react/jsx-runtime', () => ({
  jsx: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  jsxs: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push: mock(() => {}) }) }))
mock.module('next/image', () => ({ default: () => null }))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  AlertCircle: () => null, CheckCircle2: () => null, ChevronDown: () => null, Circle: () => null, GitBranch: () => null, Loader2: () => null,
  PanelLeft: () => null, PanelLeftClose: () => null, Play: () => null, RotateCcw: () => null, SkipForward: () => null,
  Square: () => null, SquarePlay: () => null, XCircle: () => null,
}))
mock.module('@/hooks/use-workflow-run', () => ({ useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false, runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }) }))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error { code = 0 },
}))
mock.module('@/components/ui/button', () => ({ Button: (p: Record<string, unknown>) => ({ type: 'button', props: p }) }))
mock.module('@/components/ui/alert', () => ({ Alert: (p: Record<string, unknown>) => ({ type: 'div', props: p }), AlertDescription: (p: Record<string, unknown>) => ({ type: 'div', props: p }), AlertTitle: (p: Record<string, unknown>) => ({ type: 'h5', props: p }) }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: (p: Record<string, unknown>) => ({ type: 'div', props: p }), CollapsibleContent: (p: Record<string, unknown>) => ({ type: 'div', props: p }), CollapsibleTrigger: (p: Record<string, unknown>) => ({ type: 'button', props: p }) }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: (p: Record<string, unknown>) => ({ type: 'tooltip', props: p }),
  TooltipContent: (p: Record<string, unknown>) => ({ type: 'tooltip-content', props: p }),
  TooltipTrigger: (p: Record<string, unknown>) => ({ type: 'button', props: p }),
}))
mock.module('@/components/chat', () => ({ ExecutionTimeline: () => null, VariableForm: () => null, useVariableForm: () => ({ values: {}, setValues: mock(() => {}), fieldErrors: {}, validate: () => true }) }))
mock.module('@/lib/workflow/run-adapter', () => ({ jwtWorkflowRunAdapter: { getWorkflow: mock(async () => ({ id: 'wf-1', name: 'Flow', description: '', icon: '', definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } }, variables: [], status: 'draft', visibility: 'private', version: 1, trigger_type: 'manual', trigger_config: {}, run_count: 0, success_count: 0, fail_count: 0, team_id: '', created_by_id: '', created_at: '', updated_at: '', embed_config: null, run_page_config: { presentation_mode: 'simple' } })), createRunApi: () => ({ runWorkflow: mock(async () => ({ run_id: 'r1' })), streamWorkflowRun: mock(() => () => {}), cancelWorkflowRun: mock(async () => {}) }), loadHistory: mock(async () => []), loadRunDetail: mock(async () => ({ run: { id: 'r1', status: 'success' }, nodes: [] })), saveRun: mock(() => {}) } }))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables: () => [] }))
mock.module('@/lib/utils', () => ({ cn: (...v: unknown[]) => v.filter(Boolean).join(' ') }))

;(globalThis as unknown as { window: unknown }).window = globalThis.window ?? ({ addEventListener: () => {}, removeEventListener: () => {} } as unknown)

mock.module('./workflow-result-renderer', () => ({ WorkflowResultRenderer: () => null }))
mock.module('@/components/chat/message', () => ({ TextWithCitations: () => null }))
const renderNodeOutputMock = mock(() => ({ type: 'div', props: { children: 'trace-output-rendered' } }))
mock.module('@/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer', () => ({
  renderNodeOutput: renderNodeOutputMock,
}))

type FakeNode = { type: unknown; props: Record<string, unknown> }

const collectText = (node: unknown): string => {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(collectText).join('')
  if (typeof node === 'object' && 'props' in (node as Record<string, unknown>)) {
    return collectText((node as FakeNode).props.children)
  }
  return ''
}

const descendants = (node: unknown): FakeNode[] => {
  if (node == null || typeof node !== 'object') return []
  if (!('props' in (node as Record<string, unknown>))) return []
  const children = (node as FakeNode).props.children
  const list: FakeNode[] = []
  if (children != null) {
    const arr = Array.isArray(children) ? children : [children]
    for (const child of arr) {
      if (child != null && typeof child === 'object' && 'props' in (child as Record<string, unknown>)) {
        list.push(child as FakeNode, ...descendants(child))
      }
    }
  }
  return list
}

describe('WorkflowRunPage', () => {
  test('renders loading state initially', () => {
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    const tree = WorkflowRunPage({ id: 'wf-1' })
    expect(tree).toBeDefined()
    effects.forEach((e) => e())
  })

  test('renders after workflow loads', async () => {
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    const tree = WorkflowRunPage({ id: 'wf-1' })
    effects.forEach((e) => e())
    await Promise.resolve()
    await Promise.resolve()
    expect(tree).toBeDefined()
  })

  test('renders with a running workflow and pending run state', async () => {
    mock.module('@/hooks/use-workflow-run', () => ({
      useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: true, runId: 'r1', status: 'running', outputs: null, submittedInputs: {}, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
    }))
    const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')
    stateIndex = 0
    effectIndex = 0
    states.length = 0
    const tree = Reloaded({ id: 'wf-1' })
    effects.forEach((e) => e())
    await Promise.resolve()
    expect(tree).toBeDefined()
  })

  test('renders the live workspace view with a finished run', async () => {
    mock.module('@/hooks/use-workflow-run', () => ({
      useWorkflowRun: () => ({ messages: [{ id: 'm1', role: 'assistant', parts: [{ type: 'text', text: 'answer' }] }], executionState: { nodes: new Map([[1, { id: 'n1', type: 'start', output: null, status: 'success' }]]), outputs: { answer: 'ok' } }, isStreaming: false, runId: 'r1', status: 'success', outputs: { answer: 'ok' }, submittedInputs: { query: 'hi' }, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
    }))
    const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')
    stateIndex = 0
    effectIndex = 0
    states.splice(0)
    states[0] = { id: 'wf-1', name: 'Flow' }
    states[1] = false
    states[2] = null
    states[3] = []
    states[4] = false
    states[5] = false
    states[6] = 'live'
    states[7] = false
    states[8] = false
    states[9] = null
    states[10] = null
    states[11] = []
    const tree = Reloaded({ id: 'wf-1' })
    effects.forEach((e) => e())
    await Promise.resolve()
    expect(tree).toBeDefined()
  })

  test('renders the history workspace view with run details', async () => {
    mock.module('@/hooks/use-workflow-run', () => ({
      useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false, runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
    }))
    const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')
    stateIndex = 0
    effectIndex = 0
    states.splice(0)
    states[0] = { id: 'wf-1', name: 'Flow' }
    states[1] = false
    states[2] = null
    states[3] = [{ id: 'run-9', workflow_id: 'wf-1', trigger_type: 'manual', is_debug: false, status: 'success', created_at: '2026-01-01T00:00:00Z', started_at: null, finished_at: null, total_duration_ms: 10, executed_nodes: 1, total_nodes: 1, error_message: null }]
    states[4] = false
    states[5] = false
    states[6] = 'history'
    states[7] = true
    states[8] = false
    states[9] = null
    states[10] = null
    states[11] = []
    const tree = Reloaded({ id: 'wf-1' })
    effects.forEach((e) => e())
    await Promise.resolve()
    expect(tree).toBeDefined()
  })

  test('renders history trace as a vertical timeline', async () => {
    mock.module('@/hooks/use-workflow-run', () => ({
      useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false, runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
    }))
    const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')
    stateIndex = 0
    effectIndex = 0
    states.splice(0)
    states[0] = { id: 'wf-1', name: 'Flow' }
    states[1] = false
    states[2] = null
    states[3] = [{ id: 'run-9', workflow_id: 'wf-1', trigger_type: 'manual', is_debug: false, status: 'success', created_at: '2026-01-01T00:00:00Z', started_at: null, finished_at: null, total_duration_ms: 10, executed_nodes: 1, total_nodes: 1, error_message: null }]
    states[4] = false
    states[5] = false
    states[6] = 'history'
    states[7] = true
    states[8] = false
    states[9] = null
    states[10] = { id: 'run-9', status: 'success' }
    // 故意乱序输入，验证按 execution_order 从上到下排序
    states[11] = [
      { id: 'n2', run_id: 'run-9', node_id: 'fu', node_type: 'file_to_url', node_name: '转URL', execution_order: 2, status: 'failed', error_message: 'boom', inputs: { url: 'http://x' }, outputs: null, retry_count: 0 },
      { id: 'n1', run_id: 'run-9', node_id: 'start', node_type: 'start', node_name: '开始节点', execution_order: 1, status: 'success', error_message: null, inputs: { query: 'hi' }, outputs: { answer: 'ok' }, retry_count: 0 },
    ]
    const tree = Reloaded({ id: 'wf-1' })
    effects.forEach((e) => e())
    await Promise.resolve()

    const text = collectText(tree)
    expect(text).toContain('showTrace')
    expect(text).toContain('开始节点')
    expect(text).toContain('转URL')
    expect(text).toContain('nodeStatus.success')
    expect(text).toContain('nodeStatus.failed')
    expect(text).toContain('boom')
    // 乱序输入 → 按 execution_order 升序渲染
    expect(text.indexOf('开始节点')).toBeLessThan(text.indexOf('转URL'))
    // 节点详情：输入 JSON + 类型化输出渲染
    expect(text).toContain('showDetails')
    expect(text).toContain('"query"')
    expect(text).toContain('trace-output-rendered')

    expect(renderNodeOutputMock).toHaveBeenCalledWith('start', { answer: 'ok' }, expect.any(Function))
    expect(renderNodeOutputMock).not.toHaveBeenCalledWith('file_to_url', null, expect.any(Function))

    const nodes = descendants(tree)
    const classNameOf = (n: FakeNode) => typeof n.props.className === 'string' ? n.props.className : ''
    // 2 个节点之间 1 条竖向线段；2 个状态圆点（h-6 w-6 特征，避开圆角按钮）
    expect(nodes.filter((n) => classNameOf(n).includes('w-px')).length).toBe(1)
    expect(nodes.filter((n) => classNameOf(n).includes('rounded-full border bg-background')).length).toBe(2)
  })
})
