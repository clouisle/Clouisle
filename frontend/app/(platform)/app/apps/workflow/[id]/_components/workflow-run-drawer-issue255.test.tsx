import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
type StreamHandlers = {
  onEvent: (event: Props) => void
  onError: (error: Error) => void
  onComplete: () => void
}

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign((props: Props) => jsx(name, props), { displayName: name })
const Button = component('Button')
const Input = component('Input')
const Textarea = component('Textarea')
const Tabs = component('Tabs')
const icons = Object.fromEntries([
  'Play', 'Bug', 'X', 'Loader2', 'CheckCircle2', 'XCircle', 'Clock', 'StopCircle',
  'ChevronDown', 'ChevronRight', 'Copy', 'Zap', 'Bot', 'Home', 'GitBranch', 'Wrench',
  'Code', 'FileText', 'MessageSquareText', 'RefreshCw', 'Infinity', 'Tags', 'Variable',
  'Combine', 'Braces', 'Link', 'Workflow', 'Sparkles',
].map((name) => [name, component(name)]))

let states: unknown[] = []
let refs: Array<{ current: unknown }> = []
let memos: Array<{ deps: unknown[]; value: unknown }> = []
let effects: Array<{ deps: unknown[]; cleanup?: () => void }> = []
let stateIndex = 0
let refIndex = 0
let memoIndex = 0
let effectIndex = 0
const changed = (before: unknown[] | undefined, after: unknown[]) =>
  !before || before.length !== after.length || before.some((value, index) => value !== after[index])

const hooks = {
  useState: <T,>(initial: T | (() => T)) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = typeof initial === 'function' ? (initial as () => T)() : initial
    return [states[index] as T, (value: T | ((previous: T) => T)) => {
      states[index] = typeof value === 'function' ? (value as (previous: T) => T)(states[index] as T) : value
    }] as const
  },
  useRef: <T,>(initial: T) => {
    const index = refIndex++
    refs[index] ??= { current: initial }
    return refs[index] as { current: T }
  },
  useMemo: <T,>(factory: () => T, deps: unknown[]) => {
    const index = memoIndex++
    if (!memos[index] || changed(memos[index].deps, deps)) memos[index] = { deps, value: factory() }
    return memos[index].value as T
  },
  useCallback: <T,>(callback: T, deps: unknown[]) => hooks.useMemo(() => callback, deps),
  useEffect: (effect: () => void | (() => void), deps: unknown[]) => {
    const index = effectIndex++
    if (!effects[index] || changed(effects[index].deps, deps)) {
      effects[index]?.cleanup?.()
      effects[index] = { deps, cleanup: effect() || undefined }
    }
  },
}

const runWorkflow = mock(async () => ({ run_id: 'run-1' }))
const debugWorkflow = mock(async () => ({ run_id: 'debug-1' }))
const cancelWorkflowRun = mock(async () => ({ cancelled: true }))
const closeStream = mock(() => {})
let streamHandlers: StreamHandlers | undefined
const streamWorkflowRun = mock((_id: string, handlers: StreamHandlers) => {
  streamHandlers = handlers
  return closeStream
})
const toast = { success: mock(() => {}), error: mock(() => {}), info: mock(() => {}) }

mock.module('react', () => ({ default: hooks, ...hooks }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => icons)
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api/client', () => ({
  ApiError: class ApiError extends Error {},
  getErrorMessage: () => 'request failed',
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Props, name: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== name)),
  getValidationSummaryEntries: (errors: Props, inline: string[]) => Object.entries(errors).filter(([key]) => !inline.includes(key)),
  mapValidationErrors: () => ({}),
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (field: string, message: unknown) => `${field}: ${message}`,
}))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: { runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun },
}))
for (const [path, exports] of [
  ['@/components/ui/button', { Button }],
  ['@/components/ui/input', { Input }],
  ['@/components/ui/label', { Label: component('Label') }],
  ['@/components/ui/textarea', { Textarea }],
  ['@/components/ui/scroll-area', { ScrollArea: component('ScrollArea') }],
  ['@/components/ui/tabs', {
    Tabs, TabsList: component('TabsList'), TabsTrigger: component('TabsTrigger'), TabsContent: component('TabsContent'),
  }],
  ['@/components/ui/field', { FieldError: component('FieldError') }],
] as const) mock.module(path, () => exports)
mock.module('./node-output-renderer', () => ({
  nodeStatusConfig: Object.fromEntries(['running', 'success', 'failed', 'skipped'].map((status) => [status, { icon: icons.Clock, className: status }])),
  renderNodeOutput: (_type: string, outputs: Props) => jsx('NodeOutput', { outputs }),
}))

const { WorkflowRunDrawer } = await import('./workflow-run-drawer')

const workflow = {
  id: 'workflow-1', status: 'published',
  definition: { nodes: [{ type: 'start', data: { parameters: [
    { name: 'name', type: 'string', required: true, defaultValue: 'Ada', description: 'Who' },
    { name: 'count', type: 'number', defaultValue: '2' },
    { name: 'enabled', type: 'boolean', defaultValue: 'false' },
    { name: 'items', type: 'array', defaultValue: '[1]' },
    { name: 'meta', type: 'object', defaultValue: '{"ok":true}' },
    { name: 'notes', type: 'paragraph', required: false },
  ] } }] },
}
const onClose = mock(() => {})
const onNodeTracesChange = mock(() => {})
const onDebugRunComplete = mock(() => {})

function render(overrides: Props = {}) {
  stateIndex = refIndex = memoIndex = effectIndex = 0
  return WorkflowRunDrawer({
    workflow: workflow as never,
    variables: [],
    open: true,
    onClose,
    onNodeTracesChange,
    onDebugRunComplete,
    ...overrides,
  }) as Node
}

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('type' in value)) return []
  const node = value as Node
  const rendered = typeof node.type === 'function' ? (node.type as (props: Props) => unknown)(node.props) : node
  if (rendered !== node) return descendants(rendered)
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  return text((value as Node).props.children)
}

const buttons = (tree: Node) => descendants(tree).filter((node) => node.type === 'Button')

beforeEach(() => {
  states = []
  refs = []
  memos = []
  effects = []
  streamHandlers = undefined
  for (const fn of [runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun, closeStream, onClose, onNodeTracesChange, onDebugRunComplete, toast.success, toast.error, toast.info]) fn.mockClear()
  runWorkflow.mockResolvedValue({ run_id: 'run-1' })
  debugWorkflow.mockResolvedValue({ run_id: 'debug-1' })
  cancelWorkflowRun.mockResolvedValue({ cancelled: true })
})

describe('workflow run drawer issue #255 coverage', () => {
  test('keeps navigation-visible state, extracted inputs, and close/publish actions visible', () => {
    let tree = render({ open: false })
    expect(tree.props.className).toContain('pointer-events-none')
    expect(descendants(tree).find((node) => node.type === 'Tabs')!.props.value).toBe('input')
    expect(text(tree)).toContain('Who')
    expect(descendants(tree).filter((node) => node.type === 'Input')).toHaveLength(2)
    expect(descendants(tree).filter((node) => node.type === 'Textarea')).toHaveLength(3)

    buttons(tree)[0].props.onClick()
    expect(onClose).toHaveBeenCalled()

    tree = render({ workflow: { ...workflow, status: 'draft' } as never })
    expect(buttons(tree).find((node) => text(node).includes('publishFirst'))!.props.disabled).toBe(true)
  })

  test('builds typed inputs and exposes loading controls while execution starts', async () => {
    let resolveRun!: (value: { run_id: string }) => void
    runWorkflow.mockImplementation(() => new Promise((resolve) => { resolveRun = resolve }))
    let tree = render()
    const controls = descendants(tree)
    const inputs = controls.filter((node) => node.type === 'Input')
    const textareas = controls.filter((node) => node.type === 'Textarea')
    const select = controls.find((node) => node.type === 'select')!

    inputs[0].props.onChange({ target: { value: 'Grace' } })
    inputs[1].props.onChange({ target: { value: '3' } })
    select.props.onChange({ target: { value: 'true' } })
    textareas[0].props.onChange({ target: { value: '[1,2]' } })
    textareas[1].props.onChange({ target: { value: '{"x":1}' } })
    textareas[2].props.onChange({ target: { value: 'hello' } })
    tree = render()

    const pending = buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    tree = render()
    expect(text(tree)).toContain('cancelRun')
    expect(descendants(tree).filter((node) => node.type === 'Input').every((node) => node.props.disabled)).toBe(true)
    expect(runWorkflow).toHaveBeenCalledWith('workflow-1', { inputs: {
      name: 'Grace', count: 3, enabled: true, items: [1, 2], meta: { x: 1 }, notes: 'hello',
    } })

    resolveRun({ run_id: 'run-typed' })
    await pending
    expect(streamWorkflowRun).toHaveBeenCalledWith('run-typed', expect.any(Object))
  })

  test('blocks required and malformed JSON inputs before calling the API', async () => {
    let tree = render()
    const controls = descendants(tree)
    controls.filter((node) => node.type === 'Input')[0].props.onChange({ target: { value: ' ' } })
    controls.filter((node) => node.type === 'Textarea')[0].props.onChange({ target: { value: '{}' } })
    controls.filter((node) => node.type === 'Textarea')[1].props.onChange({ target: { value: '[' } })
    tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    tree = render()

    expect(runWorkflow).not.toHaveBeenCalled()
    expect(text(tree)).toContain('required')
    expect(text(tree)).toContain('invalidJSON')
    expect(descendants(tree).find((node) => node.type === 'Tabs')!.props.value).toBe('input')
  })

  test('handles streamed output, success, traces, and debug completion callbacks', async () => {
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('debugDraft'))!.props.onClick()
    expect(debugWorkflow).toHaveBeenCalled()

    streamHandlers!.onEvent({ type: 'workflow_start', timestamp: '2026-01-01T12:00:00Z', data: {} })
    streamHandlers!.onEvent({ type: 'node_start', timestamp: '2026-01-01T12:00:01Z', data: { node_id: 'answer-1', node_type: 'answer', node_label: 'Answer' } })
    streamHandlers!.onEvent({ type: 'token', timestamp: '2026-01-01T12:00:02Z', data: { node_id: 'answer-1', token: 'Hello' } })
    streamHandlers!.onEvent({ type: 'node_complete', timestamp: '2026-01-01T12:00:03Z', data: { node_id: 'answer-1', node_type: 'answer', is_streaming: true, duration_ms: 12, outputs: { answer: 'Hello', usage: 7 } } })
    streamHandlers!.onEvent({ type: 'output', timestamp: '2026-01-01T12:00:03Z', data: { outputs: { final: 'Done' } } })
    streamHandlers!.onEvent({ type: 'workflow_complete', timestamp: '2026-01-01T12:00:04Z', data: { outputs: { final: 'Done' }, duration_ms: 4000 } })
    tree = render()

    expect(descendants(tree).find((node) => node.type === 'Tabs')!.props.value).toBe('result')
    expect(text(tree)).toContain('Hello')
    expect(text(tree)).toContain('4.000s')
    expect(text(tree)).toContain('7')
    expect(onNodeTracesChange).toHaveBeenLastCalledWith(expect.any(Map))

    streamHandlers!.onComplete()
    expect(onDebugRunComplete).toHaveBeenCalled()
  })

  test('shows safe workflow and stream failures and navigates to detail', async () => {
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    streamHandlers!.onEvent({ type: 'workflow_error', timestamp: '', data: { error: 'Traceback: secret' } })
    tree = render()
    expect(descendants(tree).find((node) => node.type === 'Tabs')!.props.value).toBe('detail')
    expect(text(tree)).toContain('unknownError')
    expect(text(tree)).not.toContain('secret')

    streamHandlers!.onError(new Error('socket'))
    tree = render()
    expect(text(tree)).toContain('streamConnectionFailed')
    expect(toast.error).toHaveBeenCalledWith('runDrawer.streamConnectionFailed')
  })

  test('stops active runs, closes effects, and reports both cancellation outcomes', async () => {
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    tree = render()
    await buttons(tree).find((node) => text(node).includes('cancelRun'))!.props.onClick()
    expect(cancelWorkflowRun).toHaveBeenCalledWith('run-1')
    expect(closeStream).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('runDrawer.cancelledRun')

    cancelWorkflowRun.mockResolvedValue({ cancelled: false })
    render()
    tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    tree = render()
    await buttons(tree).find((node) => text(node).includes('cancelRun'))!.props.onClick()
    expect(toast.info).toHaveBeenCalledWith('runDrawer.cannotCancelRun')
  })

  test('handles rejected execution and successful/failed clipboard effects', async () => {
    runWorkflow.mockRejectedValue(new Error('Failed to fetch internal detail'))
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    tree = render()
    expect(text(tree)).toContain('request failed')
    expect(toast.error).toHaveBeenCalledWith('runDrawer.runFailed')

    const writeText = mock(async () => {})
    globalThis.navigator = { clipboard: { writeText } } as never
    states[5] = 'success'
    states[6] = { answer: 'Copy me' }
    tree = render()
    await buttons(tree).find((node) => text(node).includes('copy'))!.props.onClick()
    expect(writeText).toHaveBeenCalledWith('Copy me')
    expect(toast.success).toHaveBeenCalledWith('editor.copiedToClipboard')

    writeText.mockRejectedValue(new Error('denied'))
    await buttons(tree).find((node) => text(node).includes('copy'))!.props.onClick()
    expect(toast.error).toHaveBeenCalledWith('editor.copyFailed')
  })
})
