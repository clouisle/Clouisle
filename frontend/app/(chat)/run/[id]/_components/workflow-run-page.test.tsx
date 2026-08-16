import { describe, expect, mock, test } from 'bun:test'
import { WorkflowRunPage } from './workflow-run-page'

const states: unknown[] = []
const refs: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
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
  useRef: (value: unknown) => {
    const i = refIndex++
    if (refs.length <= i) refs[i] = { current: value }
    return refs[i]
  },
}))
mock.module('react/jsx-runtime', () => ({
  jsx: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  jsxs: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  Fragment: Symbol.for('react.fragment'),
}))
let searchParams = new URLSearchParams()
const replaceMock = mock(() => {})
mock.module('next/navigation', () => ({ useRouter: () => ({ push: mock(() => {}), replace: replaceMock }), useSearchParams: () => searchParams }))
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
const buttonMock = (p: Record<string, unknown>) => ({ type: 'button', props: p })
mock.module('@/components/ui/button', () => ({ Button: buttonMock }))
mock.module('@/components/ui/alert', () => ({ Alert: (p: Record<string, unknown>) => ({ type: 'div', props: p }), AlertDescription: (p: Record<string, unknown>) => ({ type: 'div', props: p }), AlertTitle: (p: Record<string, unknown>) => ({ type: 'h5', props: p }) }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: (p: Record<string, unknown>) => ({ type: 'div', props: p }), CollapsibleContent: (p: Record<string, unknown>) => ({ type: 'div', props: p }), CollapsibleTrigger: (p: Record<string, unknown>) => ({ type: 'button', props: p }) }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: (p: Record<string, unknown>) => ({ type: 'tooltip', props: p }),
  TooltipContent: (p: Record<string, unknown>) => ({ type: 'tooltip-content', props: p }),
  TooltipTrigger: (p: Record<string, unknown>) => ({ type: 'button', props: p }),
}))
mock.module('@/components/chat', () => ({ ExecutionTimeline: () => null, VariableForm: () => null, useVariableForm: () => ({ values: {}, setValues: mock(() => {}), fieldErrors: {}, validate: () => true, reset: mock(() => {}) }) }))
mock.module('@/lib/workflow/run-adapter', () => ({ jwtWorkflowRunAdapter: { getWorkflow: mock(async () => ({ id: 'wf-1', name: 'Flow', description: '', icon: '', definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } }, variables: [], status: 'draft', visibility: 'private', version: 1, trigger_type: 'manual', trigger_config: {}, run_count: 0, success_count: 0, fail_count: 0, team_id: '', created_by_id: '', created_at: '', updated_at: '', embed_config: null, run_page_config: { presentation_mode: 'simple' } })), createRunApi: () => ({ runWorkflow: mock(async () => ({ run_id: 'r1' })), streamWorkflowRun: mock(() => () => {}), cancelWorkflowRun: mock(async () => {}) }), loadHistory: mock(async () => []), loadRunDetail: mock(async () => ({ run: { id: 'r1', status: 'success' }, nodes: [] })), saveRun: mock(() => {}) } }))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables: () => [] }))
mock.module('@/lib/utils', () => ({ cn: (...v: unknown[]) => v.filter(Boolean).join(' ') }))

;(globalThis as unknown as { window: unknown }).window = globalThis.window ?? ({ addEventListener: () => {}, removeEventListener: () => {} } as unknown)

mock.module('./workflow-result-renderer', () => ({ WorkflowResultRenderer: () => null }))
mock.module('@/components/chat/pause-request-actions', () => ({ PauseRequestActions: (p: Record<string, unknown>) => ({ type: 'pause-request-actions', props: p }) }))
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
    refIndex = 0
    effectIndex = 0
    states.length = 0
    refs.length = 0
    const tree = WorkflowRunPage({ id: 'wf-1' })
    expect(tree).toBeDefined()
    effects.forEach((e) => e())
  })

  test('renders after workflow loads', async () => {
    stateIndex = 0
    refIndex = 0
    effectIndex = 0
    states.length = 0
    refs.length = 0
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
    refIndex = 0
    effectIndex = 0
    states.length = 0
    refs.length = 0
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
    refIndex = 0
    effectIndex = 0
    states.splice(0)
    refs.splice(0)
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
    refIndex = 0
    effectIndex = 0
    states.splice(0)
    refs.splice(0)
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

  test('loads and resumes an approval from a waiting history run', async () => {
    const workflow = {
      id: 'wf-1',
      name: 'Flow',
      description: '',
      icon: null,
      definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
      variables: [],
      status: 'published',
      visibility: 'private',
      version: 1,
      trigger_type: 'manual',
      trigger_config: {},
      run_count: 1,
      success_count: 0,
      fail_count: 0,
      team_id: '',
      created_by_id: '',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      run_page_config: { presentation_mode: 'simple' },
    }
    const waitingRun = {
      id: 'run-waiting',
      workflow_id: 'wf-1',
      trigger_type: 'manual',
      is_debug: false,
      status: 'waiting',
      inputs: {},
      outputs: null,
      depth: 0,
      created_at: '2026-01-01T00:00:00Z',
      total_nodes: 2,
      executed_nodes: 1,
      failed_nodes: 0,
      skipped_nodes: 0,
      total_token_usage: {},
    }
    const pauseRequest = {
      id: 'pause-request-1',
      node_id: 'pause-1',
      node_name: 'Approval',
      mode: 'approval',
      title: 'Review',
      input_variables: [],
      approver_ids: ['u-alice'],
      approver_names: ['alice'],
      can_submit: true,
    }
    const getPendingPauseRequest = mock(async () => pauseRequest)
    const submitPauseRequest = mock(async () => ({ pause_request_id: 'pause-request-1', status: 'submitted' }))
    const loadRunDetail = mock(async () => ({
      run: { ...waitingRun, status: 'success' },
      nodes: [],
    }))
    const adapter = {
      getWorkflow: mock(async () => workflow),
      createRunApi: () => ({
        runWorkflow: mock(async () => ({ run_id: 'unused' })),
        streamWorkflowRun: mock(() => () => {}),
        cancelWorkflowRun: mock(async () => {}),
      }),
      loadHistory: mock(async () => []),
      loadRunDetail,
      getPendingPauseRequest,
      submitPauseRequest,
      saveRun: mock(() => {}),
    }

    stateIndex = 0

    refIndex = 0
    effectIndex = 0
    effects.length = 0
    states.splice(0)
    refs.splice(0)
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = []
    states[4] = false
    states[5] = false
    states[6] = 'history'
    states[7] = true
    states[8] = false
    states[9] = null
    states[10] = waitingRun
    states[11] = []
    states[12] = null
    states[13] = null
    states[14] = false
    states[15] = null

    WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    effects.forEach((effect) => effect())
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(getPendingPauseRequest).toHaveBeenCalledWith('wf-1', 'run-waiting')

    stateIndex = 0

    refIndex = 0
    effectIndex = 0
    effects.length = 0
    states[6] = 'history'
    states[10] = waitingRun
    states[12] = pauseRequest
    let tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    const isPausePanel = (node: FakeNode) =>
      typeof node.type === 'function' && node.type.name === 'PauseRequestActions'
    const panel = descendants(tree).find(isPausePanel)
    expect(panel?.props.request).toEqual(pauseRequest)
    expect(panel?.props.canSubmit).toBe(true)
    expect(panel?.props.approverNames).toEqual(['alice'])

    ;(panel?.props.onSubmit as (values: Record<string, unknown>, comment?: string) => void)(
      { decision: 'approved' },
      'Looks good',
    )
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(submitPauseRequest).toHaveBeenCalledWith(
      'wf-1',
      'run-waiting',
      'pause-request-1',
      { decision: 'approved' },
      'Looks good',
    )

    stateIndex = 0

    refIndex = 0
    effectIndex = 0
    effects.length = 0
    WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    effects.forEach((effect) => effect())
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(loadRunDetail).toHaveBeenCalledWith('wf-1', 'run-waiting')

    stateIndex = 0

    refIndex = 0
    effectIndex = 0
    effects.length = 0
    tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    expect(collectText(tree)).toContain('status.success')
    expect(descendants(tree).some(isPausePanel)).toBe(false)
  })

  test('disables the pause panel for non-approvers', async () => {
    const workflow = {
      id: 'wf-1',
      name: 'Flow',
      description: '',
      icon: null,
      definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
      variables: [],
      status: 'published',
      visibility: 'private',
      version: 1,
      trigger_type: 'manual',
      trigger_config: {},
      run_count: 1,
      success_count: 0,
      fail_count: 0,
      team_id: '',
      created_by_id: '',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      run_page_config: { presentation_mode: 'simple' },
    }
    const waitingRun = {
      id: 'run-waiting',
      workflow_id: 'wf-1',
      trigger_type: 'manual',
      is_debug: false,
      status: 'waiting',
      inputs: {},
      outputs: null,
      depth: 0,
      created_at: '2026-01-01T00:00:00Z',
      total_nodes: 2,
      executed_nodes: 1,
      failed_nodes: 0,
      skipped_nodes: 0,
      total_token_usage: {},
    }
    const pauseRequest = {
      id: 'pause-request-1',
      node_id: 'pause-1',
      node_name: 'Approval',
      mode: 'approval',
      title: 'Review',
      input_variables: [],
      approver_ids: ['u-alice'],
      approver_names: ['alice'],
      can_submit: false,
    }
    const adapter = {
      getWorkflow: mock(async () => workflow),
      createRunApi: () => ({
        runWorkflow: mock(async () => ({ run_id: 'unused' })),
        streamWorkflowRun: mock(() => () => {}),
        cancelWorkflowRun: mock(async () => {}),
      }),
      loadHistory: mock(async () => []),
      loadRunDetail: mock(async () => ({ run: waitingRun, nodes: [] })),
      getPendingPauseRequest: mock(async () => pauseRequest),
      submitPauseRequest: mock(async () => {}),
      saveRun: mock(() => {}),
    }

    stateIndex = 0

    refIndex = 0
    effectIndex = 0
    effects.length = 0
    states.splice(0)
    refs.splice(0)
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = []
    states[4] = false
    states[5] = false
    states[6] = 'history'
    states[7] = true
    states[8] = false
    states[9] = null
    states[10] = waitingRun
    states[11] = []
    states[12] = null
    states[13] = null
    states[14] = false
    states[15] = null

    WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    effects.forEach((effect) => effect())
    await new Promise((resolve) => setTimeout(resolve, 0))

    stateIndex = 0

    refIndex = 0
    effectIndex = 0
    effects.length = 0
    states[6] = 'history'
    states[10] = waitingRun
    states[12] = pauseRequest
    const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    const isPausePanel = (node: FakeNode) =>
      typeof node.type === 'function' && node.type.name === 'PauseRequestActions'
    const panel = descendants(tree).find(isPausePanel)
    expect(panel?.props.canSubmit).toBe(false)
    expect(panel?.props.approverNames).toEqual(['alice'])

    const submitButton = descendants(tree).find(
      (node) => typeof node.props.onClick === 'function' && node.props.children?.includes?.('run.pause.approve'),
    )
    expect(submitButton).toBeUndefined()
  })

  test('renders history trace as a vertical timeline', async () => {
    mock.module('@/hooks/use-workflow-run', () => ({
      useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false, runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
    }))
    const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')
    stateIndex = 0
    refIndex = 0
    effectIndex = 0
    states.splice(0)
    refs.splice(0)
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

    // Keep the Agent chat page shell: floating controls, no fixed top bar.
    const header = descendants(tree).find((n) => n.type === 'header')!
    expect(header.props.className).toContain('absolute inset-x-0 top-0')
    expect(header.props.className).not.toContain('border-b')

    const toggle = descendants(tree).find((n) => n.props['aria-label'] === 'closeHistory')!
    expect(toggle.props.className).toContain('h-9 w-9 rounded-full')
    expect(toggle.props.className).toContain('bg-background/80')

    const historyHeading = descendants(tree).find((n) => n.props.id === 'workflow-history-heading')!
    expect(historyHeading.props.className).toContain('px-4 pb-1 pt-3')

    expect(renderNodeOutputMock).toHaveBeenCalledWith('start', { answer: 'ok' }, expect.any(Function))
    expect(renderNodeOutputMock).not.toHaveBeenCalledWith('file_to_url', null, expect.any(Function))

    const nodes = descendants(tree)
    const classNameOf = (node: FakeNode) => typeof node.props.className === 'string' ? node.props.className : ''
    // 2 个节点之间 1 条竖向线段；2 个状态圆点（h-6 w-6 特征，避开 Header 分隔线）。
    expect(nodes.filter((node) => classNameOf(node).includes('absolute bottom-0 left-[11px]')).length).toBe(1)
    expect(nodes.filter((node) => classNameOf(node).includes('rounded-full border bg-background')).length).toBe(2)
  })

  test('hides trace details in embed mode', async () => {
    mock.module('@/hooks/use-workflow-run', () => ({
      useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false, runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
    }))
    const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')
    stateIndex = 0
    refIndex = 0
    effectIndex = 0
    states.splice(0)
    refs.splice(0)
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
    states[11] = [
      { id: 'n1', run_id: 'run-9', node_id: 'start', node_type: 'start', node_name: '开始节点', execution_order: 1, status: 'failed', error_message: 'boom', inputs: { query: 'hi' }, outputs: { answer: 'ok' }, retry_count: 0 },
    ]
    const tree = Reloaded({ id: 'wf-1', embedMode: true })
    effects.forEach((e) => e())
    await Promise.resolve()

    const text = collectText(tree)
    // 时间线骨架仍在，但节点 inputs/outputs/error 详情不渲染（embed 快照不暴露原始数据）
    expect(text).toContain('showTrace')
    expect(text).toContain('开始节点')
    expect(text).not.toContain('showDetails')
    expect(text).not.toContain('boom')
    expect(text).not.toContain('"query"')
  })
})


test('shows a login notice for pause steps on embedded runs without pause support', async () => {
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 0,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
    embed_config: { show_header: false, show_history: false, allow_new: false },
  }
  const waitingRun = {
    id: 'run-embed-waiting',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'waiting',
    inputs: {},
    outputs: null,
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 2,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory: mock(async () => []),
    loadRunDetail: mock(async () => ({ run: waitingRun, nodes: [] })),
    saveRun: mock(() => {}),
    // Embed adapters deliberately omit the pause methods.
  }

  stateIndex = 0

  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.splice(0)
  refs.splice(0)
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = []
  states[4] = false
  states[5] = false
  states[6] = 'history'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = waitingRun
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never, embedMode: true })
  effects.forEach((effect) => effect())
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(collectText(tree)).toContain('pause.embedNotice')
})


test('shows a waiting-for-review notice when the viewer is not an approver', async () => {
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 0,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
  }
  const waitingRun = {
    id: 'run-waiting-2',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'waiting',
    inputs: {},
    outputs: null,
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 2,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory: mock(async () => []),
    loadRunDetail: mock(async () => ({ run: waitingRun, nodes: [] })),
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => {}),
    saveRun: mock(() => {}),
  }

  stateIndex = 0

  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.splice(0)
  refs.splice(0)
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = []
  states[4] = false
  states[5] = false
  states[6] = 'history'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = waitingRun
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(collectText(tree)).toContain('pause.waitingForReview')
})


test('deep-links to a waiting run via the ?run= param', async () => {
  searchParams = new URLSearchParams({ run: 'run-deep' })
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 0,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
  }
  const waitingRun = {
    id: 'run-deep',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'waiting',
    inputs: {},
    outputs: null,
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 2,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const loadRunDetail = mock(async () => ({ run: waitingRun, nodes: [] }))
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory: mock(async () => []),
    loadRunDetail,
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => {}),
    saveRun: mock(() => {}),
  }

  stateIndex = 0

  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.splice(0)
  refs.splice(0)
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = []
  states[4] = false
  states[5] = false
  states[6] = 'form'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = null
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())
  await new Promise((resolve) => setTimeout(resolve, 0))

  // The first pass wrote ?run= into state; a second render runs the detail
  // loading effect against it.
  stateIndex = 0
  refIndex = 0
  effectIndex = 0
  effects.length = 0
  WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(loadRunDetail).toHaveBeenCalledWith('wf-1', 'run-deep')
  searchParams = new URLSearchParams()
})


test('does not re-arm the ?run= deep link after the detail loads (refresh must not loop)', async () => {
  mock.module('@/hooks/use-workflow-run', () => ({
    useWorkflowRun: () => ({ messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false, runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null, isCancelling: false, start: mock(async () => {}), stop: mock(async () => {}), reset: mock(() => {}) }),
  }))
  const { WorkflowRunPage: Reloaded } = await import('./workflow-run-page')

  searchParams = new URLSearchParams({ run: 'run-success' })
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 1,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
  }
  const successRun = {
    id: 'run-success',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'success',
    inputs: {},
    outputs: { answer: 'ok' },
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 1,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const loadRunDetail = mock(async () => ({ run: successRun, nodes: [] }))
  const loadHistory = mock(async () => [successRun])
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory,
    loadRunDetail,
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => {}),
    saveRun: mock(() => {}),
  }

  stateIndex = 0

  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.splice(0)
  refs.splice(0)
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = []
  states[4] = false
  states[5] = false
  states[6] = 'form'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = null
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  // Simulate a refresh: each pass re-renders with the state the previous
  // pass's effects wrote, like React committing state updates. The resuming
  // effect must consume the ?run= deep link exactly once; otherwise the
  // deep-link effect re-arms it, reloading the run detail and history on
  // every pass and leaving the sidebar stuck on its loading spinner.
  let tree: unknown = null
  for (let pass = 0; pass < 4; pass++) {
    stateIndex = 0
    refIndex = 0
    effectIndex = 0
    effects.length = 0
    tree = Reloaded({ id: 'wf-1', adapter: adapter as never })
    effects.forEach((effect) => effect())
    await new Promise((resolve) => setTimeout(resolve, 0))
  }

  expect(loadRunDetail).toHaveBeenCalledTimes(1)
  // The harness re-runs every registered effect per pass, so the mount-time
  // loadHistory runs 4x; the extra call is the one the resuming effect fires
  // when the deep link settles. A re-armed deep link would add more.
  expect(loadHistory).toHaveBeenCalledTimes(5)
  expect(collectText(tree)).toContain('run-success')
  searchParams = new URLSearchParams()
})


test('syncs the URL with ?run= when a history item is selected', async () => {
  searchParams = new URLSearchParams({ type: 'workflow' })
  replaceMock.mockClear()
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 0,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
  }
  const historyRun = {
    id: 'run-h1',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'success',
    inputs: {},
    outputs: null,
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 1,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const loadRunDetail = mock(async () => ({ run: historyRun, nodes: [] }))
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory: mock(async () => [historyRun]),
    loadRunDetail,
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => {}),
    saveRun: mock(() => {}),
  }

  stateIndex = 0

  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.splice(0)
  refs.splice(0)
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = [historyRun]
  states[4] = false
  states[5] = false
  states[6] = 'history'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = null
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())
  await new Promise((resolve) => setTimeout(resolve, 0))

  const itemButton = descendants(tree).find(
    (node) => node.type === 'button' && String(collectText(node)).includes('run-h1'),
  )
  expect(itemButton).toBeDefined()
  ;(itemButton!.props.onClick as () => void)()
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(loadRunDetail).toHaveBeenCalledWith('wf-1', 'run-h1')
  expect(replaceMock).toHaveBeenCalledWith('/run/wf-1?type=workflow&run=run-h1', { scroll: false })
  searchParams = new URLSearchParams()
})


test('rerunning from a history record does not re-trigger the ?run= deep link', () => {
  searchParams = new URLSearchParams({ type: 'workflow', run: 'run-h1' })
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 1,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
  }
  const historyRun = {
    id: 'run-h1',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'success',
    inputs: { query: 'hi' },
    outputs: null,
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 1,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory: mock(async () => [historyRun]),
    loadRunDetail: mock(async () => ({ run: historyRun, nodes: [] })),
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => ({ status: 'submitted' })),
    saveRun: mock(() => {}),
  }

  stateIndex = 0
  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.length = 0
  refs.length = 0
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = [historyRun]
  states[4] = false
  states[5] = false
  states[6] = 'history'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = historyRun
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())

  const rerunButton = descendants(tree).find(
    (node) => node.type === buttonMock && String(collectText(node)).includes('runAgain'),
  )
  expect(rerunButton).toBeDefined()
  ;(rerunButton!.props.onClick as () => void)()

  // URL 尚未移除 ?run= 时重渲染（模拟 router.replace 异步落地前的窗口）：
  // 深链 effect 不得重新武装，否则视图被拉回 history（"原地刷新"）。
  stateIndex = 0
  refIndex = 0
  effectIndex = 0
  effects.length = 0
  WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())

  expect(states[6]).toBe('form')
  expect(states[15]).toBeNull()
  searchParams = new URLSearchParams()
})

test('starting a new run from history does not re-trigger the ?run= deep link', () => {
  searchParams = new URLSearchParams({ type: 'workflow', run: 'run-h1' })
  const workflow = {
    id: 'wf-1',
    name: 'Flow',
    description: '',
    icon: null,
    definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    variables: [],
    status: 'published',
    visibility: 'private',
    version: 1,
    trigger_type: 'manual',
    trigger_config: {},
    run_count: 1,
    success_count: 1,
    fail_count: 0,
    team_id: '',
    created_by_id: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    run_page_config: { presentation_mode: 'simple' },
  }
  const historyRun = {
    id: 'run-h1',
    workflow_id: 'wf-1',
    trigger_type: 'manual',
    is_debug: false,
    status: 'success',
    inputs: {},
    outputs: null,
    depth: 0,
    created_at: '2026-01-01T00:00:00Z',
    total_nodes: 1,
    executed_nodes: 1,
    failed_nodes: 0,
    skipped_nodes: 0,
    total_token_usage: {},
  }
  const adapter = {
    getWorkflow: mock(async () => workflow),
    createRunApi: () => ({
      runWorkflow: mock(async () => ({ run_id: 'unused' })),
      streamWorkflowRun: mock(() => () => {}),
      cancelWorkflowRun: mock(async () => {}),
    }),
    loadHistory: mock(async () => [historyRun]),
    loadRunDetail: mock(async () => ({ run: historyRun, nodes: [] })),
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => ({ status: 'submitted' })),
    saveRun: mock(() => {}),
  }

  stateIndex = 0
  refIndex = 0
  effectIndex = 0
  effects.length = 0
  states.length = 0
  refs.length = 0
  states[0] = workflow
  states[1] = false
  states[2] = null
  states[3] = [historyRun]
  states[4] = false
  states[5] = false
  states[6] = 'history'
  states[7] = true
  states[8] = false
  states[9] = null
  states[10] = historyRun
  states[11] = []
  states[12] = null
  states[13] = null
  states[14] = false
  states[15] = null

  const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())

  // 新建运行按钮渲染在 TooltipTrigger 的 render prop 里（descendants 只遍历 children）
  const newRunTrigger = descendants(tree).find((node) => {
    const render = node.props.render as FakeNode | undefined
    return render && render.type === buttonMock && render.props['aria-label'] === 'newRun'
  })
  expect(newRunTrigger).toBeDefined()
  replaceMock.mockClear()
  ;(newRunTrigger!.props.onClick as () => void)()
  expect(replaceMock).toHaveBeenCalledWith('/run/wf-1?type=workflow', { scroll: false })

  stateIndex = 0
  refIndex = 0
  effectIndex = 0
  effects.length = 0
  WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
  effects.forEach((effect) => effect())

  expect(states[6]).toBe('form')
  expect(states[15]).toBeNull()
  searchParams = new URLSearchParams()
})
