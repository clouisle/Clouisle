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
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  AlertCircle: () => null, GitBranch: () => null, Loader2: () => null, PanelLeft: () => null,
  PanelLeftClose: () => null, Play: () => null, RotateCcw: () => null, Square: () => null, SquarePlay: () => null,
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
mock.module('@/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer', () => ({ renderNodeOutput: () => null }))

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
})
