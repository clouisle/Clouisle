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
  'Combine', 'Braces', 'Link', 'Workflow', 'Sparkles', 'Upload', 'FileIcon', 'ImageIcon',
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
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => icons)
mock.module('@/lib/utils', () => ({ formatDateTime: (value: unknown) => String(value), formatTime: (value: unknown) => String(value), cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api/client', () => ({
  ApiError: class ApiError extends Error {},
  getErrorMessage: () => 'request failed',
  api: {},
}))
mock.module('@/lib/api', () => ({ ApiError: class ApiError extends Error {} }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Props, name: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== name)),
  getValidationSummaryEntries: (errors: Props, inline: string[]) => Object.entries(errors).filter(([key]) => !inline.includes(key)),
  mapValidationErrors: () => ({}),
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (field: string, message: unknown) => `${field}: ${message}`,
}))
const getPendingPauseRequest = mock(async () => null)
const submitPauseRequest = mock(async () => ({ pause_request_id: 'pause-1', status: 'submitted' }))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: {
    runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun,
    getPendingPauseRequest,
    submitPauseRequest,
  },
}))
mock.module('@/components/chat/pause-request-actions', () => ({
  PauseRequestActions: (props: Props) => jsx('pause-request-actions', props),
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
  ['@/components/ui/alert', { Alert: component('Alert'), AlertDescription: component('AlertDescription') }],
  ['@/components/ui/tooltip', { Tooltip: component('Tooltip'), TooltipContent: component('TooltipContent'), TooltipTrigger: component('TooltipTrigger') }],
  ['@/components/ui/checkbox', { Checkbox: component('Checkbox') }],
  ['@/components/ui/select', {
    Select: component('Select'), SelectContent: component('SelectContent'),
    SelectItem: component('SelectItem'), SelectTrigger: component('SelectTrigger'), SelectValue: component('SelectValue'),
  }],
  ['@/lib/api/upload', { uploadApi: { uploadFile: mock(async () => ({ url: '/uploads/up.txt' })) } }],
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

async function flush() {
  for (let tick = 0; tick < 4; tick++) await Promise.resolve()
}

beforeEach(() => {
  states = []
  refs = []
  memos = []
  effects = []
  for (const fn of [runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun, closeStream, getPendingPauseRequest, submitPauseRequest, onClose, onNodeTracesChange, onDebugRunComplete, toast.success, toast.error, toast.info]) fn.mockClear()
  getPendingPauseRequest.mockResolvedValue(null)
  submitPauseRequest.mockResolvedValue({ pause_request_id: 'pause-1', status: 'submitted' })
  runWorkflow.mockResolvedValue({ run_id: 'run-1' })
  debugWorkflow.mockResolvedValue({ run_id: 'debug-1' })
  cancelWorkflowRun.mockResolvedValue({ cancelled: true })
})
test('renders file/image/files/images variables as upload controls, not text inputs', async () => {
  const fileWorkflow = {
    id: 'workflow-file', status: 'published',
    definition: { nodes: [{ type: 'start', data: { parameters: [
      { name: 'doc', type: 'file', required: true },
      { name: 'docs', type: 'files', required: true },
      { name: 'photo', type: 'image', required: true },
      { name: 'shots', type: 'images', required: true },
    ] } }] },
  }
  const tree = render({ workflow: fileWorkflow as never })
  const { FileUploadInput, MultiFileUploadInput } = await import('@/components/chat/variable-form')
  const deep = (value: unknown): Node[] => {
    if (Array.isArray(value)) return value.flatMap(deep)
    if (!value || typeof value !== 'object' || !('type' in value)) return []
    const node = value as Node
    if (node.type === FileUploadInput || node.type === MultiFileUploadInput) return [node]
    const renderedNode = typeof node.type === 'function' ? (node.type as (props: Props) => unknown)(node.props) : node
    if (renderedNode !== node) return deep(renderedNode)
    return [node, ...deep(node.props.children)]
  }
  const uploads = deep(tree).filter((node) => node.type === FileUploadInput || node.type === MultiFileUploadInput)
  const textInputs = deep(tree).filter((node) => node.type === 'Input')
  expect(uploads).toHaveLength(4)
  expect(textInputs).toHaveLength(0)
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
  test('cleans up the active stream when cancellation is rejected', async () => {
    cancelWorkflowRun.mockRejectedValue(new Error('server unavailable'))
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    tree = render()
    expect(buttons(tree).some((node) => text(node).includes('cancelRun'))).toBe(true)

    await buttons(tree).find((node) => text(node).includes('cancelRun'))!.props.onClick()
    tree = render()

    expect(cancelWorkflowRun).toHaveBeenCalledWith('run-1')
    expect(closeStream).toHaveBeenCalled()
    expect(buttons(tree).some((node) => text(node).includes('cancelRun'))).toBe(false)
    expect(toast.success).not.toHaveBeenCalledWith('runDrawer.cancelledRun')
    expect(toast.info).not.toHaveBeenCalledWith('runDrawer.cannotCancelRun')
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
  test('shows a safe failure when a draft debug run cannot start', async () => {
    debugWorkflow.mockRejectedValue(new Error('Traceback: secret'))
    const draft = { ...workflow, status: 'draft' } as never
    render({ workflow: draft })
    let tree = render({ workflow: draft })
    await buttons(tree).find((node) => text(node).includes('debugDraft'))!.props.onClick()
    await flush()
    tree = render({ workflow: draft })

    expect(text(tree)).toContain('runDrawer.executionFailed')
    expect(text(tree)).toContain('request failed')
    expect(text(tree)).not.toContain('secret')
    expect(toast.error).toHaveBeenCalledWith('runDrawer.debugFailed')
  })
  test('renders output and node trace details, including skipped and failed nodes', async () => {
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    streamHandlers!.onEvent({ type: 'node_start', timestamp: 'start', data: { node_id: 'node-1', node_type: 'llm', node_label: 'Lookup' } })
    streamHandlers!.onEvent({ type: 'node_error', timestamp: 'end', data: { node_id: 'node-1', error: 'Bad input' } })
    streamHandlers!.onEvent({ type: 'node_skip', timestamp: 'skip', data: { node_id: 'node-2', node_type: 'condition', node_label: 'Skipped' } })
    streamHandlers!.onEvent({ type: 'output', timestamp: 'out', data: { outputs: { answer: 'Result text' } } })
    streamHandlers!.onEvent({ type: 'workflow_complete', timestamp: 'done', data: { outputs: { answer: 'Result text' }, duration_ms: 1250 } })
    tree = render()
    expect(text(tree)).toContain('Result text')
    expect(text(tree)).toContain('1.250s')
    expect(text(tree)).toContain('outputSection')
    expect(text(tree)).toContain('answer')
    const tabs = descendants(tree).find((node) => node.type === 'Tabs')!
    tabs.props.onValueChange('trace')
    tree = render()
    expect(text(tree)).toContain('Lookup')
    expect(text(tree)).toContain('Skipped')
    const traceHeader = descendants(tree).find(
      (node) => node.type === 'div' && typeof node.props.onClick === 'function' && text(node).includes('Lookup')
    )!
    traceHeader.props.onClick()
    tree = render()
    expect(text(tree)).toContain('Bad input')
    expect(onNodeTracesChange).toHaveBeenLastCalledWith(expect.any(Map))
  })

  test('loads pause request after waiting and reports load or submit failures', async () => {
    getPendingPauseRequest.mockRejectedValueOnce(new Error('offline'))
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    streamHandlers!.onEvent({ type: 'workflow_waiting', timestamp: '', sequence: 4, data: {} })
    await Promise.resolve()
    tree = render()
    expect(getPendingPauseRequest).toHaveBeenCalledWith('workflow-1', 'run-1')
    expect(text(tree)).toContain('pauseLoadError')
    getPendingPauseRequest.mockResolvedValueOnce({ id: 'pause-2', request_type: 'approval' })
    streamHandlers!.onEvent({ type: 'workflow_waiting', timestamp: '', sequence: 5, data: {} })
    await Promise.resolve()
    tree = render()
    const pause = descendants(tree).find((node) => node.type === 'pause-request-actions')!
    expect(pause.props.workflowId).toBe('workflow-1')
    expect(pause.props.runId).toBe('run-1')
    expect(pause.props.pauseRequestId).toBe('pause-2')
    submitPauseRequest.mockRejectedValueOnce(new Error('offline'))
    await pause.props.onSubmit({ approved: true }, 'reviewed')
    await flush()
    tree = render()
    expect(submitPauseRequest).toHaveBeenCalledWith('workflow-1', 'run-1', 'pause-2', { approved: true }, 'reviewed')
    expect(descendants(tree).find((node) => node.type === 'pause-request-actions')!.props.error).toBe('runDrawer.pauseSubmitError')
  })
  test('refreshes pending approval and resumes the stream after submission', async () => {
    getPendingPauseRequest.mockResolvedValueOnce({ id: 'pause-1', request_type: 'approval' })
    render()
    let tree = render()
    await buttons(tree).find((node) => text(node).includes('startRun'))!.props.onClick()
    streamHandlers!.onEvent({ type: 'workflow_waiting', timestamp: 'waiting', sequence: 8, data: {} })
    await flush()
    tree = render()
    expect(descendants(tree).find((node) => node.type === 'Tabs')!.props.value).toBe('result')
    expect(getPendingPauseRequest).toHaveBeenCalledWith('workflow-1', 'run-1')
    expect(descendants(tree).find((node) => node.type === 'pause-request-actions')!.props.pauseRequestId).toBe('pause-1')

    getPendingPauseRequest.mockResolvedValueOnce({ id: 'pause-next', request_type: 'approval' })
    submitPauseRequest.mockResolvedValueOnce({ status: 'pending' })
    const pause = descendants(tree).find((node) => node.type === 'pause-request-actions')!
    await pause.props.onSubmit({ approved: false }, 'needs changes')
    await flush()
    tree = render()

    expect(submitPauseRequest).toHaveBeenCalledWith('workflow-1', 'run-1', 'pause-1', { approved: false }, 'needs changes')
    expect(getPendingPauseRequest).toHaveBeenCalledTimes(2)
    expect(descendants(tree).find((node) => node.type === 'pause-request-actions')!.props.pauseRequestId).toBe('pause-next')
    expect(streamWorkflowRun).toHaveBeenCalledTimes(1)

    submitPauseRequest.mockResolvedValueOnce({ status: 'submitted' })
    await descendants(tree).find((node) => node.type === 'pause-request-actions')!.props.onSubmit({ approved: true }, 'approved')
    await flush()
    tree = render()
    expect(submitPauseRequest).toHaveBeenLastCalledWith('workflow-1', 'run-1', 'pause-next', { approved: true }, 'approved')
    expect(streamWorkflowRun).toHaveBeenCalledTimes(2)
    expect(streamWorkflowRun).toHaveBeenLastCalledWith('run-1', expect.objectContaining({ fromSequence: 8 }))
    expect(descendants(tree).some((node) => node.type === 'pause-request-actions')).toBe(false)
    expect(buttons(tree).some((node) => text(node).includes('cancelRun'))).toBe(true)
  })
})
