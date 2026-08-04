import { beforeEach, expect, mock, test } from 'bun:test'

interface Node {
  type: unknown
  props: Record<string, unknown>
}

const jsx = (type: unknown, props: Record<string, unknown> = {}): Node => ({ type, props })
const element = function Element() {}
const runWorkflow = mock(async () => ({ run_id: 'run-1' }))
const debugWorkflow = mock(async () => ({ run_id: 'debug-1' }))
const cancelWorkflowRun = mock(async () => ({ cancelled: true }))
const streamWorkflowRun = mock(() => mock(() => {}))
const writeText = mock(async () => {})
const toast = { success: mock(() => {}), error: mock(() => {}), info: mock(() => {}) }
globalThis.navigator = { clipboard: { writeText } } as never

let hooks: unknown[] = []
let dependencies: (unknown[] | undefined)[] = []
let cursor = 0

function changed(previous: unknown[] | undefined, next: unknown[] | undefined) {
  return !previous || !next || previous.length !== next.length || next.some((value, index) => !Object.is(value, previous[index]))
}

const React = {
  useState<T>(initial: T) {
    const index = cursor++
    if (!(index in hooks)) hooks[index] = initial
    return [hooks[index] as T, (value: T | ((current: T) => T)) => {
      hooks[index] = typeof value === 'function' ? (value as (current: T) => T)(hooks[index] as T) : value
    }] as const
  },
  useMemo<T>(factory: () => T, deps: unknown[]) {
    const index = cursor++
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      hooks[index] = factory()
    }
    return hooks[index] as T
  },
  useCallback<T>(callback: T, deps: unknown[]) {
    const index = cursor++
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      hooks[index] = callback
    }
    return hooks[index] as T
  },
  useRef<T>(initial: T) {
    const index = cursor++
    if (!(index in hooks)) hooks[index] = { current: initial }
    return hooks[index] as { current: T }
  },
  useEffect(effect: () => void, deps?: unknown[]) {
    const index = cursor++
    if (changed(dependencies[index], deps)) {
      dependencies[index] = deps
      effect()
    }
  },
}

mock.module('react', () => React)
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => ({
  Play: element, Bug: element, X: element, Loader2: element, CheckCircle2: element, XCircle: element,
  Clock: element, StopCircle: element, ChevronDown: element, ChevronRight: element, Copy: element,
  Zap: element, Bot: element, Home: element, GitBranch: element, Wrench: element, Code: element,
  FileText: element, MessageSquareText: element, RefreshCw: element, Infinity: element, Tags: element,
  Variable: element, Combine: element, Braces: element, Link: element, Workflow: element, Sparkles: element,
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api/client', () => ({
  ApiError: class ApiError extends Error {},
  getErrorMessage: (key: string) => key,
}))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun } }))
mock.module('./node-output-renderer', () => ({
  nodeStatusConfig: {
    running: { icon: element, className: 'running' },
    success: { icon: element, className: 'success' },
    failed: { icon: element, className: 'failed' },
    skipped: { icon: element, className: 'skipped' },
  },
  renderNodeOutput: (_type: string, outputs: unknown) => jsx('output', { children: JSON.stringify(outputs) }),
}))

for (const path of ['button', 'input', 'label', 'textarea', 'scroll-area', 'field']) {
  mock.module(`@/components/ui/${path}`, () => ({
    Button: element, Input: element, Label: element, Textarea: element, ScrollArea: element, FieldError: element,
  }))
}
mock.module('@/components/ui/tabs', () => ({ Tabs: element, TabsList: element, TabsTrigger: element, TabsContent: element }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element,
  TooltipContent: element,
  TooltipTrigger: (props: Props) => (props.render as Node) ?? element(props),
}))

const { WorkflowRunDrawer } = await import('./workflow-run-drawer')

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (value && typeof value === 'object' && 'props' in value) return text((value as Node).props.children)
  return ''
}

const variables = [
  { name: 'requiredText', type: 'string', required: true },
  { name: 'count', type: 'number', required: false, default: '2' },
  { name: 'enabled', type: 'boolean', required: false, default: 'true' },
  { name: 'items', type: 'array', required: false },
  { name: 'config', type: 'object', required: false },
] as never
const workflow = { id: 'workflow-1', status: 'published', definition: { nodes: [] } } as never
const baseProps = { workflow, variables, open: true, onClose: mock(() => {}) }

function render(overrides: Record<string, unknown> = {}) {
  cursor = 0
  return WorkflowRunDrawer({ ...baseProps, ...overrides } as never) as Node
}

function settle(overrides: Record<string, unknown> = {}) {
  render(overrides)
  return render(overrides)
}

function find(tree: Node, predicate: (node: Node) => boolean) {
  const matches = descendants(tree).filter(predicate)
  expect(matches).toHaveLength(1)
  return matches[0]
}

function button(tree: Node, label: string) {
  return find(tree, node => typeof node.props.onClick === 'function' && text(node.props.children).includes(label))
}

beforeEach(() => {
  hooks = []
  dependencies = []
  cursor = 0
  runWorkflow.mockClear()
  debugWorkflow.mockClear()
  cancelWorkflowRun.mockClear()
  streamWorkflowRun.mockClear()
  writeText.mockClear()
  toast.success.mockClear()
  toast.error.mockClear()
  toast.info.mockClear()
})

test('validates and converts workflow inputs before opening the run stream', async () => {
  let tree = settle()
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  tree = render()

  expect(runWorkflow).not.toHaveBeenCalled()
  expect(text(tree)).toContain('requiredText*required')
  expect(find(tree, node => node.props.placeholder === 'runDrawer.inputPlaceholder:requiredText').props['aria-invalid']).toBe(true)

  const values: Record<string, string> = {
    requiredText: 'hello', count: '3.5', enabled: 'false', items: '[1,"two"]', config: '{"mode":"safe"}',
  }
  for (const [name, value] of Object.entries(values)) {
    tree = render()
    const control = find(tree, node => node.props.placeholder === `runDrawer.inputPlaceholder:${name}`
      || (name === 'enabled' && node.type === 'select')
      || (name === 'items' && node.props.placeholder === 'runDrawer.inputJsonPlaceholder:varTypes.array')
      || (name === 'config' && node.props.placeholder === 'runDrawer.inputJsonPlaceholder:varTypes.object'))
    ;(control.props.onChange as (event: unknown) => void)({ target: { value } })
  }

  tree = render()
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()

  expect(runWorkflow).toHaveBeenCalledWith('workflow-1', { inputs: {
    requiredText: 'hello', count: 3.5, enabled: false, items: [1, 'two'], config: { mode: 'safe' },
  } })
  expect(streamWorkflowRun).toHaveBeenCalledWith('run-1', expect.objectContaining({ onEvent: expect.any(Function) }))
})

test('renders streamed answer output, completion metadata, traces, and clipboard feedback', async () => {
  const onNodeTracesChange = mock(() => {})
  let tree = settle({ variables: [], onNodeTracesChange })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }

  handlers.onEvent({ type: 'workflow_start', timestamp: '2026-01-02T03:04:05Z', data: {} })
  handlers.onEvent({ type: 'node_start', timestamp: '2026-01-02T03:04:06Z', data: { node_id: 'answer-1', node_type: 'answer', node_label: 'Answer' } })
  handlers.onEvent({ type: 'token', timestamp: '2026-01-02T03:04:07Z', data: { node_id: 'answer-1', token: 'Hello ' } })
  handlers.onEvent({ type: 'token', timestamp: '2026-01-02T03:04:08Z', data: { node_id: 'answer-1', token: 'world' } })
  handlers.onEvent({ type: 'node_complete', timestamp: '2026-01-02T03:04:09Z', data: { node_id: 'answer-1', node_type: 'answer', is_streaming: true, outputs: { answer: 'Hello world', usage: { prompt_tokens: 3, completion_tokens: 4, total_tokens: 7 } }, duration_ms: 12 } })
  handlers.onEvent({ type: 'workflow_complete', timestamp: '2026-01-02T03:04:10Z', data: { outputs: { answer: 'Hello world' }, duration_ms: 1500 } })
  tree = render({ variables: [], onNodeTracesChange })

  expect(text(tree)).toContain('Hello world')
  expect(text(tree)).toContain('1.500s')
  expect(text(tree)).toContain('7')
  expect(text(tree)).toContain('Answer')
  expect(onNodeTracesChange.mock.calls.at(-1)?.[0].get('answer-1')).toMatchObject({
    status: 'success',
    streamingContent: 'Hello world',
    tokens: { prompt: 3, completion: 4, total: 7 },
  })

  await (button(tree, 'copy').props.onClick as () => Promise<void>)()
  expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Hello world')
  expect(toast.success).toHaveBeenCalledWith('editor.copiedToClipboard')
})

test('sanitizes stream errors, supports debug completion, and cancels an active run', async () => {
  const onDebugRunComplete = mock(() => {})
  let tree = settle({ variables: [], onDebugRunComplete })
  await (button(tree, 'runDrawer.debugDraft').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as {
    onEvent: (event: unknown) => void
    onComplete: () => void
  }

  handlers.onEvent({ type: 'workflow_error', timestamp: '2026-01-02T03:04:05Z', data: { error: 'HTTP 500\nTraceback: secret' } })
  tree = render({ variables: [], onDebugRunComplete })
  expect(text(tree)).toContain('runDrawer.unknownError')
  expect(text(tree)).not.toContain('Traceback: secret')

  handlers.onComplete()
  expect(onDebugRunComplete).toHaveBeenCalledTimes(1)

  hooks = []
  dependencies = []
  tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  tree = render({ variables: [] })
  await (button(tree, 'runDrawer.cancelRun').props.onClick as () => Promise<void>)()

  expect(cancelWorkflowRun).toHaveBeenCalledWith('run-1')
  expect(toast.success).toHaveBeenCalledWith('runDrawer.cancelledRun')
  expect(streamWorkflowRun.mock.results.at(-1)?.value).toHaveBeenCalledTimes(1)
})
