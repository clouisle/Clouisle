import { describe, expect, mock, test } from 'bun:test'
import { WorkflowRunPage } from './workflow-run-page'

const states: unknown[] = []
let stateIndex = 0
let effectIndex = 0
const effects: Array<() => void> = []
let runHook = {
  messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false,
  runId: null as string | null, status: 'idle', outputs: null, submittedInputs: null,
  error: null, isCancelling: false, start: mock(async (_values: Record<string, unknown>) => {}),
  stop: mock(async () => {}), resume: mock(() => {}), reset: mock(() => {}),
}
const setState = (index: number) => (value: unknown) => {
  states[index] = typeof value === 'function'
    ? (value as (previous: unknown) => unknown)(states[index])
    : value
}

mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (states.length <= index) states[index] = initial
    return [states[index], setState(index)]
  },
  useEffect: (effect: () => void) => { effects[effectIndex++] = effect },
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (callback: unknown) => callback,
  useRef: (value: unknown) => ({ current: value }),
}))
mock.module('react/jsx-runtime', () => ({
  jsx: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  jsxs: (type: unknown, props: Record<string, unknown> = {}) => ({ type, props }),
  Fragment: Symbol.for('react.fragment'),
}))
const replace = mock(() => {})
const push = mock(() => {})
mock.module('next/navigation', () => ({
  useRouter: () => ({ push, replace }),
  useSearchParams: () => new URLSearchParams(),
}))
mock.module('next/image', () => ({ default: () => null }))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => Object.fromEntries(
  ['AlertCircle', 'CheckCircle2', 'ChevronDown', 'Circle', 'GitBranch', 'Loader2', 'PanelLeft', 'PanelLeftClose', 'Play', 'RotateCcw', 'SkipForward', 'Square', 'SquarePlay', 'XCircle'].map((name) => [name, () => null]),
))
mock.module('@/hooks/use-workflow-run', () => ({
  useWorkflowRun: () => runHook,
}))
mock.module('@/lib/api', () => ({ ApiError: class ApiError extends Error { code = 0 } }))
const Button = (props: Record<string, unknown>) => ({ type: 'button', props })
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/alert', () => ({ Alert: (props: Record<string, unknown>) => ({ type: 'div', props }), AlertDescription: (props: Record<string, unknown>) => ({ type: 'div', props }), AlertTitle: (props: Record<string, unknown>) => ({ type: 'h5', props }) }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: (props: Record<string, unknown>) => ({ type: 'div', props }), CollapsibleContent: (props: Record<string, unknown>) => ({ type: 'div', props }), CollapsibleTrigger: (props: Record<string, unknown>) => ({ type: 'button', props }) }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: (props: Record<string, unknown>) => ({ type: 'div', props }), TooltipContent: (props: Record<string, unknown>) => ({ type: 'div', props }), TooltipTrigger: (props: Record<string, unknown>) => ({ type: 'button', props }) }))
mock.module('@/components/chat', () => ({ ExecutionTimeline: () => null, VariableForm: () => null, useVariableForm: () => ({ values: {}, setValues: mock(() => {}), fieldErrors: {}, validate: () => true, reset: mock(() => {}) }) }))
mock.module('@/lib/workflow/run-adapter', () => ({ jwtWorkflowRunAdapter: {}, createRunApi: () => ({}), loadHistory: mock(async () => []), loadRunDetail: mock(async () => ({ run: {}, nodes: [] })) }))
mock.module('@/lib/utils/extract-variables', () => ({ extractVariables: () => [] }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('./workflow-result-renderer', () => ({ WorkflowResultRenderer: () => null }))
mock.module('@/components/chat/pause-request-actions', () => ({ PauseRequestActions: () => null }))
mock.module('@/components/chat/message', () => ({ TextWithCitations: () => null }))

const walk = (node: unknown): Array<{ type: unknown; props: Record<string, unknown> }> => {
  if (node == null || typeof node !== 'object' || !('props' in node)) return []
  const item = node as { type: unknown; props: Record<string, unknown> }
  const children = item.props.children
  return [item, ...(Array.isArray(children) ? children : [children]).flatMap(walk)]
}
const text = (node: unknown): string => {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (typeof node === 'object' && 'props' in node) return text((node as { props: Record<string, unknown> }).props.children)
  return ''
}
const resetHookState = () => {
  stateIndex = 0
  effectIndex = 0
  effects.length = 0
  states.length = 0
}
const resetRunHook = () => {
  runHook = {
    messages: [], executionState: { nodes: new Map(), outputs: null }, isStreaming: false,
    runId: null, status: 'idle', outputs: null, submittedInputs: null, error: null,
    isCancelling: false, start: mock(async (_values: Record<string, unknown>) => {}),
    stop: mock(async () => {}), resume: mock(() => {}), reset: mock(() => {}),
  }
}
const workflow = {
  id: 'wf-1', name: 'Flow', description: '', icon: null,
  definition: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } }, variables: [],
  status: 'published', visibility: 'private', version: 1, trigger_type: 'manual', trigger_config: {},
  run_count: 0, success_count: 0, fail_count: 0, team_id: '', created_by_id: '', created_at: '', updated_at: '',
  run_page_config: { presentation_mode: 'simple' }, embed_config: null,
}

describe('WorkflowRunPage additional behavior coverage', () => {
  test('starts a run with validated form values and switches to the live result', async () => {
    resetHookState()
    resetRunHook()
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = []
    states[4] = false
    states[5] = false
    states[6] = 'form'
    const values = { query: 'hello' }
    let submittedValues: Record<string, unknown> | undefined
    const start = mock(async (inputs: Record<string, unknown>) => { submittedValues = inputs })
    runHook = { ...runHook, start }
    mock.module('@/components/chat', () => ({ ExecutionTimeline: () => null, VariableForm: () => null, useVariableForm: () => ({ values, setValues: mock(() => {}), fieldErrors: {}, validate: mock(() => true), reset: mock(() => {}) }) }))
    const adapter = { getWorkflow: mock(async () => workflow), createRunApi: () => ({}) }
    const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    expect(text(tree)).toContain('startRun')
    const startButton = walk(tree).find((node) => node.type === Button && text(node).includes('startRun'))
    await (startButton!.props.onClick as () => Promise<void>)()
    expect(submittedValues).toEqual(values)
    expect(states[6]).toBe('live')
  })

  test('shows the missing-workflow message and navigates home from the error action', () => {
    resetHookState()
    states[1] = false
    states[2] = new Error('Workflow unavailable')
    const tree = WorkflowRunPage({ id: 'wf-1', adapter: { getWorkflow: mock(async () => null), createRunApi: () => ({}) } as never })
    expect(text(tree)).toContain('Workflow unavailable')
    const back = walk(tree).find((node) => node.type === Button && text(node).includes('backToHome'))
    expect(back).toBeDefined()
    ;(back!.props.onClick as () => void)()
    expect(push).toHaveBeenCalledWith('/')
  })

  test('shows a recoverable error when a selected history run detail cannot be loaded', async () => {
    resetHookState()
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = [{
      id: 'run-broken', workflow_id: 'wf-1', trigger_type: 'manual', is_debug: false,
      status: 'failed', inputs: {}, outputs: null, depth: 0, created_at: '',
      total_nodes: 1, executed_nodes: 0, failed_nodes: 1, skipped_nodes: 0, total_token_usage: {},
    }]
    states[4] = false
    states[6] = 'history'
    states[7] = true
    states[10] = null
    const adapter = {
      getWorkflow: mock(async () => workflow),
      createRunApi: () => ({ runWorkflow: mock(async () => ({})), streamWorkflowRun: mock(() => () => {}), cancelWorkflowRun: mock(async () => {}) }),
      loadHistory: mock(async () => []),
      loadRunDetail: mock(async () => { throw new Error('detail unavailable') }),
      getPendingPauseRequest: mock(async () => null),
      submitPauseRequest: mock(async () => ({})),
      saveRun: mock(() => {}),
    }

    const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    const historyItem = walk(tree).find((node) => node.type === 'button' && text(node).includes('run-broken'))
    expect(historyItem).toBeDefined()
    await (historyItem!.props.onClick as () => Promise<void>)()

    stateIndex = 0
    effectIndex = 0
    effects.length = 0
    const refreshed = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    expect(text(refreshed)).toContain('historyDetailError')
    expect(adapter.loadRunDetail).toHaveBeenCalledWith('wf-1', 'run-broken')
  })

  test('retains the history list and reports a cancellation failure for a waiting history run', async () => {
    resetHookState()
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = [{ id: 'run-waiting', workflow_id: 'wf-1', trigger_type: 'manual', is_debug: false, status: 'waiting', inputs: {}, outputs: null, depth: 0, created_at: '', total_nodes: 1, executed_nodes: 0, failed_nodes: 0, skipped_nodes: 0, total_token_usage: {} }]
    states[4] = false
    states[6] = 'history'
    states[7] = true
    states[10] = { id: 'run-waiting', status: 'waiting', inputs: {}, outputs: null, created_at: '' }
    const cancelWorkflowRun = mock(async () => { throw new Error('cannot cancel') })
    const adapter = {
      getWorkflow: mock(async () => workflow),
      createRunApi: () => ({ runWorkflow: mock(async () => ({})), streamWorkflowRun: mock(() => () => {}), cancelWorkflowRun }),
      getPendingPauseRequest: mock(async () => null),
      submitPauseRequest: mock(async () => ({})),
      saveRun: mock(() => {}),
    }

    const tree = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    const cancel = walk(tree).find((node) => node.type === Button && text(node).includes('cancel'))
    expect(cancel).toBeDefined()
    await (cancel!.props.onClick as () => Promise<void>)()

    stateIndex = 0
    effectIndex = 0
    effects.length = 0
    const refreshed = WorkflowRunPage({ id: 'wf-1', adapter: adapter as never })
    expect(text(refreshed)).toContain('cancelFailed')
    expect(text(refreshed)).toContain('run-waiting')
    expect(cancelWorkflowRun).toHaveBeenCalledWith('run-waiting')
  })
  test('shows the live run error and preserves the form view after start fails', () => {
    resetHookState()
    resetRunHook()
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = []
    states[4] = false
    states[5] = false
    states[6] = 'live'
    runHook = { ...runHook, error: 'execution failed' }

    const tree = WorkflowRunPage({ id: 'wf-1', adapter: { getWorkflow: mock(async () => workflow), createRunApi: () => ({}) } as never })

    expect(text(tree)).toContain('execution failed')
    expect(text(tree)).toContain('runFailed')
    expect(text(tree)).not.toContain('noResult')
  })

  test('renders a successful historical result from selected run outputs', () => {
    resetHookState()
    resetRunHook()
    states[0] = workflow
    states[1] = false
    states[2] = null
    states[3] = []
    states[4] = false
    states[6] = 'history'
    states[7] = true
    states[10] = {
      id: 'run-output', status: 'success', inputs: {}, outputs: { answer: 'forty two' },
      created_at: '', error_message: null,
    }

    const tree = WorkflowRunPage({ id: 'wf-1', adapter: { getWorkflow: mock(async () => workflow), createRunApi: () => ({}) } as never })

    expect(text(tree)).toContain('historyResult')
    expect(text(tree)).toContain('status.success')
    expect(text(tree)).toContain('run-output')
  })


})
