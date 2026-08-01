import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const push = mock()
const getPublicAgent = mock()
const getConversations = mock()
const getConversation = mock()
const deleteConversation = mock()
const updateConversation = mock()
const uploadFileWithProgress = mock()
const convertBackendMessages = mock((messages: unknown[]) => messages.map((message, index) => ({ id: `converted-${index}`, role: 'user', content: String(message) })))
const sendMessage = mock()
const regenerate = mock()
const editMessage = mock()
const switchVersion = mock()
const stop = mock()
const resetChat = mock()
const setMessages = mock()
const setConversationId = mock()
const validateVariables = mock(() => true)
const toastError = mock()
const disconnect = mock()
const observe = mock()
const historyPush = mock()
const historyReplace = mock()
let token: string | null = 'token'
let query = new URLSearchParams()
let chatState = {
  messages: [] as Array<Record<string, unknown>>,
  isLoading: false,
  isStreaming: false,
  conversationId: null as string | null,
}
let chatOptions: { onConversationChange?: () => void } = {}
let variableValues: Record<string, unknown> = {}
let chatContainerProps: Record<string, unknown> = {}
let chatInputProps: Record<string, unknown> = {}
let observerCallback: IntersectionObserverCallback | undefined
const router = { push }
const searchParams = { get: (key: string) => query.get(key), toString: () => query.toString() }
const translate = (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key

class ApiError extends Error {
  constructor(public code: number, message = 'request failed', public data?: unknown) {
    super(message)
  }
}

mock.module('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
}))
mock.module('next/link', () => ({ default: ({ children, href }: React.PropsWithChildren<{ href: string }>) => <a href={href}>{children}</a> }))
mock.module('next/image', () => ({ default: ({ alt, src }: { alt: string; src: string }) => <img alt={alt} src={src} /> }))
mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('sonner', () => ({ toast: { error: toastError } }))
mock.module('@/lib/api', () => ({
  ApiError,
  agentsApi: {
    chatStream: mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() })),
    getConversation: mock(() => Promise.resolve({ messages: [] })),
    editMessageStream: mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() })),
    regenerateStream: mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() })),
    getMessageVersions: mock(() => Promise.resolve([])),
    switchMessageVersion: mock(() => Promise.resolve()),
  },
  publicAgentsApi: { getPublicAgent, getConversations, getConversation, deleteConversation, updateConversation },
  uploadApi: { uploadFileWithProgress },
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/utils/message-converter', () => ({ convertBackendMessages }))
mock.module('@/hooks/use-chat', () => ({
  useChat: (options: { onConversationChange?: () => void }) => {
    chatOptions = options
    return {
      ...chatState, sendMessage, regenerate, editMessage, switchVersion, stop, reset: resetChat,
      setMessages, setConversationId,
    }
  },
}))

function element(tag: keyof React.JSX.IntrinsicElements) {
  return function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
}
const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
const conditional = ({ children, open = true }: React.PropsWithChildren<{ open?: boolean }>) => open ? <>{children}</> : null
mock.module('lucide-react', () => ({
  Loader2: element('i'), LogIn: element('i'), ArrowLeft: element('i'), AlertCircle: element('i'),
  SquarePen: element('i'), PanelLeftClose: element('i'), PanelLeft: element('i'), MessageSquare: element('i'),
  Trash2: element('i'), MoreHorizontal: element('i'), Sparkles: element('i'), Pencil: element('i'),
  ChevronDown: element('i'), ChevronUp: element('i'),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/alert', () => ({ Alert: element('section'), AlertDescription: element('p'), AlertTitle: element('h1') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: conditional, DialogContent: passthrough, DialogDescription: element('p'), DialogFooter: passthrough,
  DialogHeader: passthrough, DialogTitle: element('h2'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: passthrough, DropdownMenuContent: passthrough, DropdownMenuItem: element('button'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/resizable', () => ({ ResizableHandle: element('div'), ResizablePanel: passthrough, ResizablePanelGroup: passthrough }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: passthrough, CollapsibleContent: passthrough, CollapsibleTrigger: element('button') }))
mock.module('@/components/chat/code-preview-canvas', () => ({ CodePreviewCanvas: ({ onClose }: { onClose: () => void }) => <button data-preview onClick={onClose}>preview</button> }))
mock.module('@/components/chat', () => ({
  ChatContainer: (props: Record<string, unknown>) => {
    chatContainerProps = props
    return <div data-chat-container>{props.messages instanceof Array && props.messages.length > 0 ? 'messages' : props.emptyState as React.ReactNode}</div>
  },
  ChatInput: (props: Record<string, unknown>) => {
    chatInputProps = props
    return <button data-chat-input onClick={() => (props.onSubmit as (message: string) => void)('typed message')}>input</button>
  },
  VariableForm: ({ onChange }: { onChange: (values: Record<string, unknown>) => void }) => <button data-variable-form onClick={() => onChange({ required: 'filled' })}>variables</button>,
  useVariableForm: () => ({ values: variableValues, setValues: (values: Record<string, unknown>) => { variableValues = values }, fieldErrors: {}, validate: validateVariables }),
}))

mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement } & Record<string, unknown>) =>
    render ? React.cloneElement(render, { ...props, ...(children !== undefined ? { children } : {}) }) : <button {...props}>{children}</button>,
}))

const { default: PublicChatPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const agent = {
  id: 'agent-1', name: 'Safe Agent', description: 'Helpful description', opening_message: '',
  icon: '', avatar_url: '', suggested_questions: ['First question', 'Second question'], variables: [],
  enable_vision: false, enable_file_upload: false, file_upload_config: undefined, hide_tool_calls: false, hide_message_actions: false, hide_reasoning: false,
  created_by: { username: 'owner' },
}
const conversations = [
  { id: 'conv-1', title: 'First chat' },
  { id: 'conv-2', title: null },
]
let renderer: ReactTestRenderer | undefined

function render(params: Promise<{ id: string }> = Promise.resolve({ id: 'agent-1' })) {
  act(() => { renderer = create(<PublicChatPage params={params} />, { createNodeMock: () => ({}) }) })
  return renderer!
}
async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
}
function output() { return JSON.stringify(renderer!.toJSON()) }
function nodeText(node: ReactTestRenderer['root']): string {
  return node.children.map((child) => typeof child === 'string' ? child : nodeText(child)).join('')
}
function buttons(text: string) {
  return renderer!.root.findAllByType('button').filter((node) => nodeText(node) === text)
}
async function click(text: string, index = 0) {
  await act(async () => { await buttons(text)[index].props.onClick({ stopPropagation: mock() }) })
}

beforeEach(() => {
  token = 'token'
  query = new URLSearchParams()
  chatState = { messages: [], isLoading: false, isStreaming: false, conversationId: null }
  variableValues = {}
  chatContainerProps = {}
  chatInputProps = {}
  observerCallback = undefined
  for (const fn of [push, getPublicAgent, getConversations, getConversation, deleteConversation, updateConversation, uploadFileWithProgress, convertBackendMessages, sendMessage, regenerate, editMessage, switchVersion, stop, resetChat, setMessages, setConversationId, validateVariables, toastError, disconnect, observe, historyPush, historyReplace]) fn.mockReset()
  validateVariables.mockReturnValue(true)
  convertBackendMessages.mockImplementation((messages: unknown[]) => messages.map((message, index) => ({ id: `converted-${index}`, role: 'user', content: String(message) })))
  getPublicAgent.mockResolvedValue(agent)
  getConversations.mockResolvedValue({ items: conversations, total: 2 })
  getConversation.mockResolvedValue({ messages: ['backend message'] })
  deleteConversation.mockResolvedValue(undefined)
  updateConversation.mockResolvedValue(undefined)
  sendMessage.mockResolvedValue(undefined)
  uploadFileWithProgress.mockResolvedValue({ url: 'https://files.example.test/safe.pdf' })

  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: mock(() => token) } })
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { innerWidth: 1024, history: { pushState: historyPush, replaceState: historyReplace } },
  })
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { title: '' } })
  Object.defineProperty(globalThis, 'IntersectionObserver', {
    configurable: true,
    value: class {
      constructor(callback: IntersectionObserverCallback) { observerCallback = callback }
      observe = observe
      disconnect = disconnect
    },
  })
})
afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
})

describe('PublicChatPage', () => {
  test('shows loading, login, and safe missing-agent states', async () => {
    let resolveParams: ((value: { id: string }) => void) | undefined
    render(new Promise((resolve) => { resolveParams = resolve }))
    expect(output()).toContain('animate-spin')
    await act(async () => { resolveParams!({ id: 'agent-1' }) })
    await flush()
    expect(getPublicAgent).toHaveBeenCalledWith('agent-1')

    act(() => renderer!.unmount())
    token = null
    render()
    await flush()
    expect(output()).toContain('loginRequired')
    expect(renderer!.root.findByType('a').props.href).toBe('/login?redirect=/chat/agent-1')
    expect(getPublicAgent).toHaveBeenCalledTimes(1)

    act(() => renderer!.unmount())
    token = 'token'
    getPublicAgent.mockRejectedValueOnce(new ApiError(404, 'secret upstream detail'))
    render()
    await flush()
    expect(output()).toContain('agentNotFound')
    expect(output()).not.toContain('secret upstream detail')
    await click('backToHome')
    expect(push).toHaveBeenCalledWith('/')
  })

  test('loads the agent and URL conversation, wires message actions, and cleans up observers', async () => {
    query = new URLSearchParams('conversation=conv-1&source=share')
    render()
    await flush()

    expect(getPublicAgent).toHaveBeenCalledWith('agent-1')
    expect(getConversations).toHaveBeenCalledWith('agent-1', { page: 1, pageSize: 5 })
    expect(getConversation).toHaveBeenCalledWith('conv-1')
    expect(convertBackendMessages).toHaveBeenCalledWith(['backend message'])
    expect(setMessages).toHaveBeenCalledWith([{ id: 'converted-0', role: 'user', content: 'backend message' }])
    expect(setConversationId).toHaveBeenCalledWith('conv-1')
    expect(document.title).toBe('Safe Agent')
    expect(chatContainerProps.onRegenerate).toBe(regenerate)
    expect(chatContainerProps.onEditMessage).toBe(editMessage)
    expect(chatContainerProps.onSwitchVersion).toBe(switchVersion)
    expect(chatInputProps.onStop).toBe(stop)
  })

  test('selects, resets, paginates, renames, and deletes conversations', async () => {
    getConversations
      .mockResolvedValueOnce({ items: Array.from({ length: 5 }, (_, index) => ({ id: `conv-${index + 1}`, title: `Chat ${index + 1}` })), total: 6 })
      .mockResolvedValueOnce({ items: [{ id: 'conv-6', title: 'Chat 6' }], total: 6 })
    render()
    await flush()

    const chat2 = renderer!.root.findAllByType('div').find((node) => nodeText(node).includes('Chat 2') && node.props.onClick)!
    await act(async () => chat2.props.onClick())
    expect(getConversation).toHaveBeenCalledWith('conv-2')
    expect(setConversationId).toHaveBeenCalledWith('conv-2')
    expect(historyPush).toHaveBeenCalledWith({}, '', '/chat/agent-1?conversation=conv-2')

    await act(async () => observerCallback!([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver))
    expect(getConversations).toHaveBeenLastCalledWith('agent-1', { page: 2, pageSize: 5 })
    expect(output()).toContain('Chat 6')

    await click('rename', 1)
    const titleInput = renderer!.root.findByProps({ id: 'title' })
    act(() => titleInput.props.onChange({ target: { value: ' Renamed chat ' } }))
    await click('save')
    expect(updateConversation).toHaveBeenCalledWith('conv-2', { title: 'Renamed chat' })
    expect(output()).toContain('Renamed chat')

    chatState.conversationId = 'conv-2'
    await click('delete', 1)
    await click('confirmDeleteConversation')
    expect(deleteConversation).toHaveBeenCalledWith('conv-2')

    await act(async () => (chatOptions.onConversationChange?.()))
    expect(getConversations).toHaveBeenCalledWith('agent-1', { page: 1, pageSize: 5 })

    const newChat = renderer!.root.findAllByProps({ 'aria-label': 'newChat' })[0]
    act(() => newChat.props.onClick())
    expect(resetChat).toHaveBeenCalled()
    expect(historyPush).toHaveBeenLastCalledWith({}, '', '/chat/agent-1')
    act(() => renderer!.unmount())
    expect(disconnect).toHaveBeenCalled()
    renderer = undefined
  })

  test('sends suggested and option messages while enforcing variable validation', async () => {
    getPublicAgent.mockResolvedValueOnce({
      ...agent,
      variables: [{ name: 'required', type: 'string', required: true, hidden: false }],
    })
    validateVariables.mockReturnValueOnce(false).mockReturnValue(true)
    render()
    await flush()

    await click('First question')
    expect(sendMessage).not.toHaveBeenCalled()
    expect(nodeText(renderer!.root)).toContain('0/1')

    await act(async () => (chatContainerProps.onSelectOption as (option: string) => void)('Selected option'))
    expect(sendMessage).toHaveBeenCalledWith('Selected option', undefined, undefined)

    await act(async () => (chatInputProps.onSubmit as (message: string) => Promise<void>)('   '))
    expect(sendMessage).toHaveBeenCalledTimes(1)
  })

  test('converts image attachments and uploads documents with progress', async () => {
    getPublicAgent.mockResolvedValueOnce({ ...agent, enable_vision: true, enable_file_upload: true })
    class MockFileReader {
      result: string | ArrayBuffer | null = null
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      readAsDataURL(file: File) {
        this.result = `data:${file.type};base64,c2FmZQ==`
        this.onload?.()
      }
    }
    Object.defineProperty(globalThis, 'FileReader', { configurable: true, value: MockFileReader })
    render()
    await flush()

    const image = { id: 'image', name: 'safe.png', size: 4, type: 'image/png', file: new File(['safe'], 'safe.png', { type: 'image/png' }), isDocument: false }
    const documentFile = { id: 'doc', name: 'safe.pdf', size: 4, type: 'application/pdf', file: new File(['safe'], 'safe.pdf', { type: 'application/pdf' }), isDocument: true }
    uploadFileWithProgress.mockImplementationOnce(async (_file, _category, onProgress) => {
      onProgress({ percent: 50 })
      return { url: 'https://files.example.test/safe.pdf' }
    })
    act(() => (chatInputProps.onFilesChange as (files: unknown[]) => void)([image, documentFile]))
    await act(async () => (chatInputProps.onSubmit as (message: string) => Promise<void>)('with files'))

    expect(uploadFileWithProgress).toHaveBeenCalledTimes(1)
    expect(uploadFileWithProgress.mock.calls[0][0]).toBe(documentFile.file)
    expect(uploadFileWithProgress.mock.calls[0][1]).toBe('documents')
    expect(sendMessage).toHaveBeenCalledWith(
      'with files',
      [{ type: 'image_url', url: 'data:image/png;base64,c2FmZQ==' }],
      [{ filename: 'safe.pdf', url: 'https://files.example.test/safe.pdf', size: 4, mime_type: 'application/pdf' }],
    )
  })

  test('reports allowed upload types without leaking upload failures', async () => {
    const consoleError = console.error
    console.error = mock()
    getPublicAgent.mockResolvedValueOnce({ ...agent, enable_file_upload: true })
    uploadFileWithProgress.mockRejectedValueOnce(new ApiError(1001, 'private storage failure', { allowed: ['pdf', 'txt'] }))
    render()
    await flush()
    const documentFile = { id: 'doc', name: 'bad.exe', size: 4, type: 'application/octet-stream', file: new File(['bad'], 'bad.exe'), isDocument: true }

    await act(async () => (chatInputProps.onSubmit as (message: string, files: unknown[]) => Promise<void>)('upload', [documentFile]))
    expect(toastError).toHaveBeenCalledWith('invalidFileTypeWithAllowed:{"allowed":"pdf, txt"}')
    expect(sendMessage).toHaveBeenCalledWith('upload', undefined, undefined)
    expect(output()).not.toContain('private storage failure')
    console.error = consoleError
  })

  test('clears invalid conversation queries and handles generic agent failures safely', async () => {
    query = new URLSearchParams('conversation=missing&source=share')
    getConversation.mockRejectedValueOnce(new Error('private conversation detail'))
    const consoleError = console.error
    console.error = mock()
    render()
    await flush()
    expect(historyReplace).toHaveBeenCalledWith({}, '', '/chat/agent-1?source=share')
    expect(output()).not.toContain('private conversation detail')
    act(() => renderer!.unmount())

    getPublicAgent.mockRejectedValueOnce(new Error('private agent detail'))
    render()
    await flush()
    expect(output()).toContain('loadError')
    expect(output()).not.toContain('private agent detail')
    console.error = consoleError
  })

  test('suppresses URL reload after selecting and reports conversation action failures', async () => {
    const consoleError = console.error
    console.error = mock()
    query = new URLSearchParams('conversation=conv-2')
    getConversation
      .mockResolvedValueOnce({ messages: [] })
      .mockRejectedValueOnce(new Error('select failed'))
    render()
    await flush()

    const firstChat = renderer!.root.findAllByType('div').find((node) => nodeText(node).includes('First chat') && node.props.onClick)!
    await act(async () => firstChat.props.onClick())
    expect(getConversation).toHaveBeenCalledWith('conv-1')
    expect(console.error).toHaveBeenCalledWith('Failed to load conversation:', expect.any(Error))

    getConversation.mockResolvedValueOnce({ messages: [] })
    await act(async () => firstChat.props.onClick())
    await flush()
    expect(getConversation).toHaveBeenCalledTimes(3)

    updateConversation.mockRejectedValueOnce(new Error('rename failed'))
    await click('rename')
    const titleInput = renderer!.root.findByProps({ id: 'title' })
    act(() => titleInput.props.onChange({ target: { value: 'Failure' } }))
    await act(async () => titleInput.props.onKeyDown({ key: 'Enter', nativeEvent: { isComposing: false }, preventDefault: mock() }))
    expect(console.error).toHaveBeenCalledWith('Failed to rename conversation:', expect.any(Error))

    deleteConversation.mockRejectedValueOnce(new Error('delete failed'))
    await click('delete')
    await click('confirmDeleteConversation')
    expect(toastError).toHaveBeenCalledWith('deleteConversationFailed')
    console.error = consoleError
  })

  test('cleans delete selection when the dialog closes and ignores invalid upload types without allowed values', async () => {
    const consoleError = console.error
    console.error = mock()
    getPublicAgent.mockResolvedValueOnce({ ...agent, enable_file_upload: true })
    uploadFileWithProgress.mockRejectedValueOnce(new ApiError(1001))
    render()
    await flush()

    await click('delete')
    const deleteDialog = renderer!.root.findAll((node) => node.props.open === true && node.props.onOpenChange)[0]
    act(() => deleteDialog.props.onOpenChange(false))
    expect(buttons('confirmDeleteConversation')).toHaveLength(0)

    const documentFile = { id: 'doc', name: 'bad.exe', size: 3, type: 'application/octet-stream', file: new File(['bad'], 'bad.exe'), isDocument: true }
    await act(async () => (chatInputProps.onSubmit as (message: string, files: unknown[]) => Promise<void>)('upload', [documentFile]))
    expect(toastError).toHaveBeenCalledWith('invalidFileType')
    console.error = consoleError
  })
})
