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
const uploadFileMock = mock(async () => ({ url: '/uploads/up.txt' }))
const streamWorkflowRun = mock(() => mock(() => {}))
const getPendingPauseRequest = mock(async () => null)
const submitPauseRequest = mock(async () => ({ pause_request_id: 'pause-1', status: 'submitted' }))
const pauseRequestActions = (props: Record<string, unknown>) => ({ type: 'pause-request-actions', props })
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
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => ({
  Play: element, Bug: element, X: element, Loader2: element, CheckCircle2: element, XCircle: element,
  Clock: element, StopCircle: element, ChevronDown: element, ChevronRight: element, Copy: element,
  Zap: element, Bot: element, Home: element, GitBranch: element, Wrench: element, Code: element,
  FileText: element, MessageSquareText: element, RefreshCw: element, Infinity: element, Tags: element,
  Variable: element, Combine: element, Braces: element, Link: element, Workflow: element, Sparkles: element,
  Upload: element, FileIcon: element, ImageIcon: element,
}))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: unknown) => String(value), formatTime: (value: unknown) => String(value), cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api/client', () => ({
  ApiError: class ApiError extends Error {},
  getErrorMessage: (key: string) => key,
  api: {},
}))
mock.module('@/lib/api', () => ({ ApiError: class ApiError extends Error {} }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun, getPendingPauseRequest, submitPauseRequest } }))
mock.module('@/components/chat/pause-request-actions', () => ({ PauseRequestActions: pauseRequestActions }))
mock.module('./node-output-renderer', () => ({
  nodeStatusConfig: {
    running: { icon: element, className: 'running' },
    success: { icon: element, className: 'success' },
    failed: { icon: element, className: 'failed' },
    skipped: { icon: element, className: 'skipped' },
  },
  renderNodeOutput: (_type: string, outputs: unknown) => jsx('output', { children: JSON.stringify(outputs) }),
}))

for (const path of ['button', 'input', 'label', 'textarea', 'scroll-area', 'field', 'alert']) {
  mock.module(`@/components/ui/${path}`, () => ({
    Button: element, Input: element, Label: element, Textarea: element, ScrollArea: element, FieldError: element, Alert: element, AlertDescription: element,
  }))
}
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element }))
mock.module('@/components/ui/select', () => ({
  Select: element, SelectContent: element, SelectItem: element, SelectTrigger: element, SelectValue: element,
}))
mock.module('@/lib/api/upload', () => ({ uploadApi: { uploadFile: uploadFileMock } }))
mock.module('@/components/ui/tabs', () => ({ Tabs: element, TabsList: element, TabsTrigger: element, TabsContent: element }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element,
  TooltipContent: element,
  TooltipTrigger: (props: Props) => (props.render as Node) ?? element(props),
}))

const { WorkflowRunDrawer } = await import('./workflow-run-drawer')
const { FileUploadInput, MultiFileUploadInput } = await import('@/components/chat/variable-form')

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
  uploadFileMock.mockClear()
  streamWorkflowRun.mockClear()
  getPendingPauseRequest.mockClear()
  submitPauseRequest.mockClear()
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

test('renders file, image, files, images, select and checkbox inputs and submits upload URLs', async () => {
  const variables = [
    { name: 'attachment', type: 'file', required: true, description: 'Upload a document' },
    { name: 'photo', type: 'image', required: false },
    { name: 'docs', type: 'files', required: true },
    { name: 'shots', type: 'images', required: false },
    { name: 'choice', type: 'select', required: true, options: ['a', 'b'] },
    { name: 'agree', type: 'checkbox', required: false, description: 'Agree to terms' },
    { name: 'flag', type: 'boolean', required: false, default: true },
    { name: 'tags', type: 'array', required: false, default: ['x'] },
    { name: 'meta', type: 'object', required: false, default: { ok: true } },
    { name: 'emptyArr', type: 'array', required: false, default: [] },
  ] as never
  const workflow = { id: 'workflow-1', status: 'published', definition: { nodes: [] } } as never

  // 展开 FileUploadInput/MultiFileUploadInput 内部节点（其余组件保持不可穿透）
  const deep = (value: unknown): Node[] => {
    if (Array.isArray(value)) return value.flatMap(deep)
    if (!value || typeof value !== 'object' || !('props' in value)) return []
    const node = value as Node
    if (node.type === FileUploadInput || node.type === MultiFileUploadInput) {
      return deep((node.type as (props: Record<string, unknown>) => unknown)(node.props))
    }
    return [node, ...deep(node.props.children)]
  }

  let tree = settle({ variables, workflow })
  const nodes = deep(tree)

  // 文件/图片/多文件/多图/下拉/复选框 不再渲染为文本输入框
  expect(nodes.filter((node) => node.type === 'Input')).toHaveLength(0)
  const singleUploadButtons = nodes.filter((node) =>
    typeof node.props.onClick === 'function' && text(node.props.children).trim() === 'selectFile')
  expect(singleUploadButtons).toHaveLength(1) // file
  const imageUploadButtons = nodes.filter((node) =>
    typeof node.props.onClick === 'function' && text(node.props.children).trim() === 'selectImage')
  expect(imageUploadButtons).toHaveLength(1) // image
  const multiUploadButtons = nodes.filter((node) =>
    typeof node.props.onClick === 'function' && text(node.props.children).trim() === 'selectFiles')
  expect(multiUploadButtons).toHaveLength(1) // files
  const multiImageButtons = nodes.filter((node) =>
    typeof node.props.onClick === 'function' && text(node.props.children).trim() === 'selectImages')
  expect(multiImageButtons).toHaveLength(1) // images
  // 单/多、普通/图片 四种隐藏文件输入各一个，且图片字段限制为 image/*
  const oneFile = nodes.filter((node) => node.type === 'input' && node.props.type === 'file' && node.props.accept === '*' && !node.props.multiple)
  const oneImage = nodes.filter((node) => node.type === 'input' && node.props.type === 'file' && node.props.accept === 'image/*' && !node.props.multiple)
  const multiFiles = nodes.filter((node) => node.type === 'input' && node.props.type === 'file' && node.props.multiple && node.props.accept === '*')
  const multiImages = nodes.filter((node) => node.type === 'input' && node.props.type === 'file' && node.props.multiple && node.props.accept === 'image/*')
  expect(oneFile).toHaveLength(1)
  expect(oneImage).toHaveLength(1)
  expect(multiFiles).toHaveLength(1)
  expect(multiImages).toHaveLength(1)

  // 拖拽进入显示拖放层，离开后消失（覆盖层有背景，不会与按钮文字重叠）
  const dropZone = nodes.find((node) => typeof node.props.onDrop === 'function')!
  dropZone.props.onDragEnter({ preventDefault() {}, stopPropagation() {} })
  tree = render({ variables, workflow })
  expect(deep(tree).some((node) => text(node.props.children).trim() === 'dropFiles')).toBe(true)
  dropZone.props.onDragLeave({ preventDefault() {}, stopPropagation() {} })
  tree = render({ variables, workflow })
  expect(deep(tree).some((node) => text(node.props.children).trim() === 'dropFiles')).toBe(false)

  // 下拉渲染选项与占位符
  const select = nodes.find((node) => node.type === 'select')!
  expect(text(select.props.children)).toContain('selectPlaceholder')
  expect(text(select.props.children)).toContain('a')
  expect(text(select.props.children)).toContain('b')
  select.props.onChange({ target: { value: 'b' } })

  // 复选框
  const checkbox = nodes.find((node) => node.type === 'input' && node.props.type === 'checkbox')!
  checkbox.props.onChange({ target: { checked: true } })

  // 单文件上传 → URL 透传
  uploadFileMock.mockResolvedValueOnce({ url: '/uploads/att.txt' })
  await (oneFile[0].props.onChange as (event: unknown) => Promise<void>)({ target: { files: [new File(['x'], 'doc.txt')] } })

  // 多文件上传 → URL 数组
  uploadFileMock.mockResolvedValueOnce({ url: '/uploads/d1.txt' }).mockResolvedValueOnce({ url: '/uploads/d2.txt' })
  await (multiFiles[0].props.onChange as (event: unknown) => Promise<void>)({ target: { files: [new File(['x'], 'a.txt'), new File(['y'], 'b.txt')] } })

  tree = render({ variables, workflow })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()

  expect(uploadFileMock).toHaveBeenCalledWith(expect.any(File), 'workflow-input')
  expect(runWorkflow).toHaveBeenCalledWith('workflow-1', { inputs: {
    attachment: '/uploads/att.txt',
    docs: ['/uploads/d1.txt', '/uploads/d2.txt'],
    choice: 'b',
    agree: true,
    flag: true,
    tags: ['x'],
    meta: { ok: true },
  } })
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

test('disables run actions while a file upload is pending', () => {
  let tree = settle({ variables: [
    { name: 'attachment', type: 'file', required: false },
    { name: 'photos', type: 'images', required: false },
  ] })
  const uploadInputs = descendants(tree).filter((node) => typeof node.props.onUploadingChange === 'function')
  expect(uploadInputs.length).toBe(2) // file + images

  // 上传开始：计数 +1 → 运行/调试按钮禁用
  uploadInputs.forEach((node) => node.props.onUploadingChange(true))
  tree = render()
  expect(button(tree, 'runDrawer.startRun').props.disabled).toBe(true)
  expect(button(tree, 'runDrawer.debugDraft').props.disabled).toBe(true)

  // 上传完成：计数归零 → 恢复可用
  uploadInputs.forEach((node) => node.props.onUploadingChange(false))
  tree = render()
  expect(button(tree, 'runDrawer.startRun').props.disabled).toBe(false)
  expect(button(tree, 'runDrawer.debugDraft').props.disabled).toBe(false)
})

test('renders the pause request form while waiting, submits, and reconnects the stream', async () => {
  const pauseRequest = {
    id: 'pause-1',
    node_id: 'pause-1',
    node_name: 'Pause',
    mode: 'variables',
    title: 'Fill docs',
    input_variables: [
      { name: 'docs', label: 'Docs', type: 'files', required: true },
      { name: 'items', label: 'Items', type: 'array', required: false },
    ],
    approver_ids: ['u-1'],
    approver_names: ['alice'],
    can_submit: true,
  }
  getPendingPauseRequest.mockResolvedValueOnce(pauseRequest)

  let tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }

  handlers.onEvent({ type: 'workflow_start', sequence: 1, timestamp: '2026-01-02T03:04:05Z', data: {} })
  handlers.onEvent({ type: 'workflow_waiting', sequence: 3, timestamp: '2026-01-02T03:04:06Z', data: {} })
  await new Promise((resolve) => setTimeout(resolve, 0))

  tree = render({ variables: [] })

  // 等待状态：请求表单已加载，取消按钮可用
  expect(getPendingPauseRequest).toHaveBeenCalledWith('workflow-1', 'run-1')
  const panel = find(tree, (node) => node.type === pauseRequestActions)
  expect(panel.props.request).toEqual(pauseRequest)
  expect(button(tree, 'runDrawer.cancelRun')).toBeDefined()

  // 提交请求 → 重连流（从已消费序列号之后继续），旧流被关闭
  submitPauseRequest.mockResolvedValueOnce({ pause_request_id: 'pause-1', status: 'submitted' })
  const previousClose = streamWorkflowRun.mock.results[0]?.value
  await (panel.props.onSubmit as (values: Record<string, unknown>, comment?: string) => Promise<void>)(
    { docs: ['/uploads/a.pdf'], items: [1, 2] },
    'done',
  )

  expect(submitPauseRequest).toHaveBeenCalledWith(
    'workflow-1', 'run-1', 'pause-1',
    { docs: ['/uploads/a.pdf'], items: [1, 2] },
    'done',
  )
  expect(streamWorkflowRun).toHaveBeenCalledTimes(2)
  expect(streamWorkflowRun.mock.calls[1][0]).toBe('run-1')
  expect((streamWorkflowRun.mock.calls[1][1] as { fromSequence: number }).fromSequence).toBe(3)
  expect(previousClose).toHaveBeenCalledTimes(1)

  tree = render({ variables: [] })
  // 恢复运行：不再渲染请求面板，取消按钮仍在（运行中）
  expect(descendants(tree).some((node) => node.type === pauseRequestActions)).toBe(false)
  expect(button(tree, 'runDrawer.cancelRun')).toBeDefined()
})

test('keeps the pause form waiting when a require-all submission is not yet resolved', async () => {
  const pauseRequest = {
    id: 'pause-1',
    node_id: 'pause-1',
    node_name: 'Pause',
    mode: 'variables',
    title: 'Fill',
    input_variables: [{ name: 't', label: 'T', type: 'text', required: true }],
    approver_ids: ['u-1'],
    approver_names: ['alice'],
    can_submit: true,
  }
  getPendingPauseRequest
    .mockResolvedValueOnce(pauseRequest)
    .mockResolvedValueOnce({ ...pauseRequest, can_submit: false })
  submitPauseRequest.mockResolvedValueOnce({ pause_request_id: 'pause-1', status: 'pending' })

  let tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }
  handlers.onEvent({ type: 'workflow_waiting', sequence: 2, timestamp: '2026-01-02T03:04:06Z', data: {} })
  await new Promise((resolve) => setTimeout(resolve, 0))

  tree = render({ variables: [] })
  const panel = find(tree, (node) => node.type === pauseRequestActions)

  await (panel.props.onSubmit as (values: Record<string, unknown>) => Promise<void>)({ t: 'x' })
  // 让 submit -> refresh 的异步链完成
  await new Promise((resolve) => setTimeout(resolve, 0))

  expect(submitPauseRequest).toHaveBeenCalledTimes(1)
  // 未解析：不重连流，仅刷新请求（can_submit 变为 false 说明请求已更新）
  expect(streamWorkflowRun).toHaveBeenCalledTimes(1)
  tree = render({ variables: [] })
  const refreshedPanel = find(tree, (node) => node.type === pauseRequestActions)
  expect(refreshedPanel.props.request.can_submit).toBe(false)
})

test('pause request load failure shows the error and waiting state stays', async () => {
  getPendingPauseRequest.mockRejectedValueOnce(new Error('offline'))

  let tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }
  handlers.onEvent({ type: 'workflow_waiting', sequence: 1, timestamp: 't', data: {} })
  await new Promise((resolve) => setTimeout(resolve, 0))

  tree = render({ variables: [] })
  expect(text(tree)).toContain('runDrawer.pauseLoadError')
  expect(descendants(tree).some((node) => node.type === pauseRequestActions)).toBe(false)
})

test('pause request load with no pending request shows the waiting hint', async () => {
  getPendingPauseRequest.mockResolvedValueOnce(null)

  let tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }
  handlers.onEvent({ type: 'workflow_waiting', sequence: 1, timestamp: 't', data: {} })
  await new Promise((resolve) => setTimeout(resolve, 0))

  tree = render({ variables: [] })
  expect(text(tree)).toContain('runDrawer.pauseWaiting')
})

test('pause submission failure keeps the waiting state and reports the error', async () => {
  const pauseRequest = {
    id: 'pause-1', node_id: 'pause-1', node_name: 'Pause', mode: 'variables',
    title: 'Fill', input_variables: [], approver_ids: ['u-1'],
    approver_names: ['alice'], can_submit: true,
  }
  getPendingPauseRequest.mockResolvedValueOnce(pauseRequest)
  submitPauseRequest.mockRejectedValueOnce(new Error('network'))

  let tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }
  handlers.onEvent({ type: 'workflow_waiting', sequence: 1, timestamp: 't', data: {} })
  await new Promise((resolve) => setTimeout(resolve, 0))

  tree = render({ variables: [] })
  const panel = find(tree, (node) => node.type === pauseRequestActions)
  await (panel.props.onSubmit as (values: Record<string, unknown>) => Promise<void>)({ price: 1 })
  await new Promise((resolve) => setTimeout(resolve, 0))

  // 提交失败：请求面板仍在，错误传给面板；不重连流
  tree = render({ variables: [] })
  const failedPanel = find(tree, (node) => node.type === pauseRequestActions)
  expect(failedPanel.props.error).toBe('runDrawer.pauseSubmitError')
  expect(streamWorkflowRun).toHaveBeenCalledTimes(1)
})

test('waiting run can be cancelled from the drawer footer', async () => {
  const pauseRequest = {
    id: 'pause-1', node_id: 'pause-1', node_name: 'Pause', mode: 'variables',
    title: 'Fill', input_variables: [], approver_ids: ['u-1'],
    approver_names: ['alice'], can_submit: true,
  }
  getPendingPauseRequest.mockResolvedValueOnce(pauseRequest)

  let tree = settle({ variables: [] })
  await (button(tree, 'runDrawer.startRun').props.onClick as () => Promise<void>)()
  const handlers = streamWorkflowRun.mock.calls[0][1] as { onEvent: (event: unknown) => void }
  handlers.onEvent({ type: 'workflow_waiting', sequence: 1, timestamp: 't', data: {} })
  await new Promise((resolve) => setTimeout(resolve, 0))

  tree = render({ variables: [] })
  await (button(tree, 'runDrawer.cancelRun').props.onClick as () => Promise<void>)()

  expect(cancelWorkflowRun).toHaveBeenCalledWith('run-1')
  expect(toast.success).toHaveBeenCalledWith('runDrawer.cancelledRun')
})
