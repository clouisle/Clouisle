import { beforeEach, describe, expect, mock, test } from 'bun:test'

interface Node { type: unknown; props: Record<string, unknown> }
const jsx = (type: unknown, props: Record<string, unknown>): Node => ({ type, props })
const component = (name: string) => Object.assign(() => null, { displayName: name })
const Button = component('Button')
const ChatContainer = component('ChatContainer')
const ChatInput = component('ChatInput')
const PendingAskUserForm = component('PendingAskUserForm')
let states: unknown[] = []
let stateIndex = 0
let variableForm: Record<string, unknown>
let chat: Record<string, unknown>
let chatOptions: { onError: () => void } | undefined
let errorKey: string | null = null
const sendMessage = mock(() => Promise.resolve())
const uploadFile = mock(() => Promise.resolve({ url: '/uploaded.txt' }))
const toastError = mock(() => undefined)
const validate = mock(() => true)
const resetVariables = mock(() => undefined)
const reset = mock(() => undefined)
const regenerate = mock(() => undefined)
const switchVersion = mock(() => undefined)
const submitAskUser = mock(() => Promise.resolve())
const stop = mock(() => undefined)
class ApiError extends Error {
  constructor(public code: number, message: string, public data?: unknown) { super(message) }
}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = initial
    return [states[index] as T, (value: T | ((current: T) => T)) => {
      states[index] = typeof value === 'function' ? (value as (current: T) => T)(states[index] as T) : value
    }] as const
  },
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
}))
mock.module('lucide-react', () => ({
  RotateCcw: component('RotateCcw'), Sparkles: component('Sparkles'), AlertCircle: component('AlertCircle'),
  X: component('X'), ChevronUp: component('ChevronUp'), ChevronDown: component('ChevronDown'),
}))
mock.module('sonner', () => ({ toast: { error: toastError } }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: component('Collapsible'), CollapsibleContent: component('CollapsibleContent'),
  CollapsibleTrigger: component('CollapsibleTrigger'),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/api', () => ({ ApiError, uploadApi: { uploadFileWithProgress: uploadFile } }))
mock.module('@/components/chat', () => ({
  ChatContainer, ChatInput, PendingAskUserForm, VariableForm: component('VariableForm'), useVariableForm: () => variableForm,
}))
mock.module('@/hooks/use-chat', () => ({
  useChat: (options: { onError: () => void }) => { chatOptions = options; return chat },
  getErrorMsgKey: () => errorKey,
}))

const { AgentPreviewPanel } = await import('./agent-preview-panel')
const baseAgent = {
  id: 'agent-1', variables: [], suggested_questions: ['First?', 'Second?', 'Third?', 'Ignored?'],
 enable_attachments: false, hide_tool_calls: false, hide_message_actions: false, hide_reasoning: false,
} as never

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children), ...descendants(node.props.emptyState)]
}
function render(agent = baseAgent) {
  stateIndex = 0
  return AgentPreviewPanel({ agent }) as Node
}
const find = (tree: Node, type: unknown) => descendants(tree).filter((node) => node.type === type)
const text = (value: unknown): string => Array.isArray(value) ? value.map(text).join('')
  : value && typeof value === 'object' ? text((value as Node).props?.children)
    : typeof value === 'string' || typeof value === 'number' ? String(value) : ''
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  states = []
  variableForm = {
    values: {}, setValues: mock(() => undefined), needsInput: false, isValid: true,
    fieldErrors: {}, validate, reset: resetVariables,
  }
  chat = {
    messages: [], error: null, isLoading: false, isStreaming: false, sendMessage,
    regenerate, switchVersion, stop, reset, pendingAskUserToolCallId: null, submitAskUser,
  }
  errorKey = null
  sendMessage.mockClear()
  uploadFile.mockReset()
  uploadFile.mockResolvedValue({ url: '/uploaded.txt' })
  toastError.mockClear()
  validate.mockReset()
  validate.mockReturnValue(true)
  resetVariables.mockClear()
  reset.mockClear()
  regenerate.mockClear()
  switchVersion.mockClear()
  submitAskUser.mockClear()
  stop.mockClear()
  Object.defineProperty(globalThis, 'FileReader', { configurable: true, value: class {
    result: string | null = null
    onload: (() => void) | null = null
    readAsDataURL() { this.result = 'data:image/png;base64,aW1hZ2U='; this.onload?.() }
  } })
})

describe('AgentPreviewPanel', () => {
  test('gates invalid submissions, then sends suggested prompts', async () => {
    variableForm = { ...variableForm, needsInput: true, isValid: false }
    validate.mockReturnValue(false)
    let tree = render({ ...baseAgent, variables: [{ name: 'topic', type: 'text', required: true }] } as never)
    const input = find(tree, ChatInput)[0]
    await (input.props.onSubmit as (message: string) => Promise<void>)('   ')
    await (input.props.onSubmit as (message: string) => Promise<void>)('blocked')
    expect(sendMessage).not.toHaveBeenCalled()
    expect(validate).toHaveBeenCalledTimes(1)
    expect(input.props.placeholder).toBe('chat.variables.fillRequired')
    expect(text(tree)).toContain('0/1')

    variableForm = { ...variableForm, needsInput: false, isValid: true }
    tree = render()
    const container = find(tree, ChatContainer)[0]
    const questions = descendants(container.props.emptyState).filter((node) => node.type === 'button')
    expect(questions).toHaveLength(3)
    await (questions[0].props.onClick as () => Promise<void>)()
    await flush()
    expect(sendMessage.mock.calls.map((call) => call[0])).toEqual(['First?'])
  })

  test('places pending ask_user above the preview composer', async () => {
    chat = {
      ...chat,
      messages: [{
        id: 'ask-message',
        role: 'assistant',
        parts: [{
          type: 'tool-call',
          toolCallId: 'ask-1',
          toolName: 'ask_user',
          input: { questions: [{ id: 'target', question: 'Where?', options: ['cloud'] }] },
          state: 'pending',
        }],
      }],
      pendingAskUserToolCallId: 'ask-1',
    }
    const tree = render()
    const pending = find(tree, PendingAskUserForm)[0]
    const container = find(tree, ChatContainer)[0]

    expect(pending.props).toMatchObject({
      messages: chat.messages,
      pendingToolCallId: 'ask-1',
      disabled: false,
      onSubmit: submitAskUser,
    })
    expect(container.props.pendingAskUserToolCallId).toBeUndefined()
    expect(container.props.onSubmitAskUser).toBeUndefined()
    await (pending.props.onSubmit as (toolCallId: string, answer: { answers: Record<string, unknown>; skipped?: boolean }) => Promise<void>)('ask-1', { answers: { target: 'cloud' } })
    expect(submitAskUser).toHaveBeenCalledWith('ask-1', { answers: { target: 'cloud' } })
  })

  test('converts images and uploads documents with progress before sending', async () => {
    const image = { id: 'image', name: 'photo.png', size: 5, type: 'image/png', file: new File(['img'], 'photo.png') }
    const document = { id: 'doc', name: 'notes.txt', size: 9, type: 'text/plain', file: new File(['notes'], 'notes.txt'), isDocument: true }
    const agent = { ...baseAgent, enable_attachments: true } as never
    let tree = render(agent)
    ;(find(tree, ChatInput)[0].props.onFilesChange as (files: unknown[]) => void)([image, document])
    tree = render(agent)
    const pending = (find(tree, ChatInput)[0].props.onSubmit as (message: string) => Promise<void>)('Analyze')
    await flush()
    ;(uploadFile.mock.calls[0][2] as (value: { percent: number }) => void)({ percent: 42 })
    await pending

    expect(uploadFile).toHaveBeenCalledWith(document.file, 'documents', expect.any(Function))
    expect(sendMessage).toHaveBeenCalledWith('Analyze', [
      { type: 'image_url', url: 'data:image/png;base64,aW1hZ2U=' },
    ], [{ filename: 'notes.txt', url: '/uploaded.txt', size: 9, mime_type: 'text/plain' }])
    tree = render(agent)
    expect(find(tree, ChatInput)[0].props.files).toEqual([])
    expect(find(tree, ChatInput)[0].props.isUploading).toBe(false)
  })

  test('reports upload validation failures and still submits text', async () => {
    const document = { id: 'doc', name: 'bad.exe', size: 2, type: 'application/x-msdownload', file: new File(['x'], 'bad.exe'), isDocument: true }
    uploadFile.mockRejectedValue(new ApiError(1001, 'invalid', { allowed: ['pdf', 'txt'] }))
    const tree = render({ ...baseAgent, enable_attachments: true } as never)
    const originalError = console.error
    console.error = mock(() => undefined)
    try {
      await (find(tree, ChatInput)[0].props.onSubmit as (message: string, files: unknown[]) => Promise<void>)('Read', [document])
    } finally {
      console.error = originalError
    }
    expect(toastError).toHaveBeenCalledWith('common.invalidFileTypeWithAllowed:{"allowed":"pdf, txt"}')
    expect(sendMessage).toHaveBeenCalledWith('Read', undefined, undefined)
  })

  test('localizes chat errors, dismisses them, and delegates reset controls', () => {
    chat = { ...chat, error: { message: 'quota', quotaType: 'output' } }
    errorKey = 'quotaExceeded'
    let tree = render()
    chatOptions?.onError()
    tree = render()
    expect(text(tree)).toContain('errors.quotaExceeded:{"type":"errors.quotaTypeOutput"}')
    const close = descendants(tree).find((node) => node.type === 'button')!
    ;(close.props.onClick as () => void)()
    tree = render()
    expect(text(tree)).not.toContain('errors.quotaExceeded')

    const container = find(tree, ChatContainer)[0]
    ;(container.props.onRegenerate as () => void)()
    ;(container.props.onSwitchVersion as () => void)()
    ;(find(tree, ChatInput)[0].props.onStop as () => void)()
    ;(find(tree, Button)[0].props.onClick as () => void)()
    expect([regenerate, switchVersion, stop, reset, resetVariables].map((fn) => fn.mock.calls.length)).toEqual([1, 1, 1, 1, 1])
  })
})
