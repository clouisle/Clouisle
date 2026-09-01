import { beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'

type StateSetter<T> = (value: T | ((previous: T) => T)) => void

type HookOptions = {
  agentId: string
  conversationId?: string
  variables?: Record<string, unknown>
  onConversationChange?: (id: string) => void
  onError?: (error: { code?: number; message: string }) => void
  onStreamStart?: () => void
  onStreamEnd?: () => void
  api?: import('./use-chat').ChatStreamApi
}

type HookResult = ReturnType<typeof import('./use-chat').useChat>
type ChatMessage = HookResult['messages'][number]

let stateSlots: unknown[] = []
let refSlots: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
let options: HookOptions
let result: HookResult
let useChat: typeof import('./use-chat').useChat
let renderScheduled = false
let renderWaiters: Array<() => void> = []
type StreamEvent = { event: string; data: unknown }
type StreamEventSource = StreamEvent | Promise<StreamEvent> | (() => Promise<StreamEvent>)
let streamEvents: StreamEventSource[] = []

const chatStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const editMessageStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const regenerateStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const getConversation = mock(() => Promise.resolve({ messages: [] }))
const getMessageVersions = mock(() => Promise.resolve<Array<{ id: string }>>([]))
const switchMessageVersion = mock(() => Promise.resolve())
const getRunStatus = mock(() => Promise.resolve())
const getRunEvents = mock(() => Promise.resolve([]))
const postRunInput = mock(() => Promise.resolve())
const stopRun = mock(() => Promise.resolve())
const agentsApi = {
  chatStream,
  startRun: undefined,
  streamRun: undefined,
  editMessageStream,
  regenerateStream,
  getConversation,
  getMessageVersions,
  switchMessageVersion,
  getRunStatus,
  getRunEvents,
  postRunInput,
  stopRun,
}

mock.module('@/lib/api', () => ({
  agentsApi,
  publicAgentsApi: agentsApi,
  async *parseSSEStream() {
    for (const event of streamEvents) {
      yield await (typeof event === 'function' ? event() : event)
    }
  },
}))

mock.module('@/lib/api/client', () => ({
  getErrorMessage: (key: string) => `api.${key}`,
}))

mock.module('@/lib/utils/message-converter', () => ({
  convertBackendMessages: (messages: ChatMessage[]) => messages,
}))

mock.module('@/lib/utils/tool-result', () => ({
  parseToolResultOutput: (output: unknown) => output,
  shouldDisplayMediaResultInBody: () => true,
}))

function renderHookHarness() {
  stateIndex = 0
  refIndex = 0
  // This deliberately drives the mocked React dispatcher rather than rendering a component.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  result = useChat(options)
}

function scheduleRender() {
  if (renderScheduled) return
  renderScheduled = true
  queueMicrotask(() => {
    renderScheduled = false
    renderHookHarness()
    const waiters = renderWaiters
    renderWaiters = []
    for (const resolve of waiters) resolve()
  })
}

const reactInternals = { H: null, A: null, T: null, S: null, V: null, recentlyCreatedOwnerStacks: 0 }
const reactHelpers = {
  __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: reactInternals,
  createElement: () => null,
  act: (callback: () => unknown) => callback(),
  createContext: () => ({ Provider: () => null, Consumer: () => null }),
  forwardRef: (component: unknown) => component,
  memo: (component: unknown) => component,
  useContext: () => ({}),
  useEffect: () => undefined,
  useLayoutEffect: () => undefined,
  useMemo: <T>(factory: () => T) => factory(),
}

mock.module('react', () => ({
  default: reactHelpers,
  ...reactHelpers,
  useState<T>(initial: T): [T, StateSetter<T>] {
    const index = stateIndex++
    if (stateSlots.length <= index) stateSlots[index] = initial
    return [
      stateSlots[index] as T,
      (value) => {
        const previous = stateSlots[index] as T
        stateSlots[index] = typeof value === 'function'
          ? (value as (current: T) => T)(previous)
          : value
        scheduleRender()
      },
    ]
  },
  useRef<T>(initial: T) {
    const index = refIndex++
    if (!refSlots[index]) refSlots[index] = { current: initial }
    return refSlots[index] as { current: T }
  },
  useCallback<T>(callback: T) {
    return callback
  },
}))

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))

beforeAll(async () => {
  ;({ useChat } = await import('./use-chat'))
})

beforeEach(() => {
  stateSlots = []
  refSlots = []
  renderWaiters = []
  for (const apiMock of [
    chatStream,
    editMessageStream,
    regenerateStream,
    getConversation,
    getMessageVersions,
    switchMessageVersion,
    getRunStatus,
    getRunEvents,
    postRunInput,
    stopRun,
  ]) apiMock.mockReset()
  getConversation.mockResolvedValue({ messages: [] })
  getMessageVersions.mockResolvedValue([])
  switchMessageVersion.mockResolvedValue()
  getRunEvents.mockResolvedValue([])
  postRunInput.mockResolvedValue({ status: 'running' })
  stopRun.mockResolvedValue({ status: 'stopping' })
  streamEvents = []
  options = { agentId: 'agent-1' }
  renderHookHarness()
})

function deferred<T>() {
  return Promise.withResolvers<T>()
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

function waitForRender(): Promise<void> {
  const waiter = Promise.withResolvers<void>()
  renderWaiters.push(waiter.resolve)
  return waiter.promise
}

async function waitForParts(predicate: (parts: ChatMessage['parts']) => boolean) {
  while (!predicate(result.messages[1]?.parts ?? [])) {
    await waitForRender()
  }
}

describe('useChat', () => {
  it('moves through loading and streaming before finalizing the conversation', async () => {
    const response = deferred<Response>()
    const releaseStream = deferred<StreamEvent>()
    const onConversationChange = mock()
    const onStreamStart = mock()
    const onStreamEnd = mock()
    options = { agentId: 'agent-1', onConversationChange, onStreamStart, onStreamEnd }
    renderHookHarness()

    chatStream.mockReturnValue({
      stream: response.promise,
      abort: mock(),
    })

    const sending = result.sendMessage('  Hello  ')
    await flush()
    expect(result.status).toBe('loading')
    expect(result.isLoading).toBe(true)
    expect(result.messages.map((message) => message.role)).toEqual(['user', 'assistant'])
    expect(result.messages[0].parts[0]).toMatchObject({ type: 'text', text: 'Hello' })

    const terminalData = {
      version_number: 2,
      version_count: 3,
      usage: {
        prompt_tokens: 1200,
        completion_tokens: 34,
        total_tokens: 1234,
        cache_read_tokens: 900,
        cache_creation_tokens: 100,
      },
      timing: { first_token_ms: 250, duration_ms: 1234, tokens_per_second: 12.5 },
    }

    streamEvents = [
      { event: 'message_start', data: { conversation_id: 'conversation-1', message_id: 'message-1', user_message_id: 'user-message-1' } },
      { event: 'content_delta', data: { delta: 'Hi there' } },
      releaseStream.promise,
      { event: 'message_end', data: terminalData },
    ]
    response.resolve(new Response())
    await flush()

    expect(result.status).toBe('streaming')
    expect(result.isStreaming).toBe(true)
    expect(onStreamStart).toHaveBeenCalledTimes(1)

    releaseStream.resolve({ event: 'message_end', data: terminalData })
    await sending

    expect(result.status).toBe('idle')
    expect(result.conversationId).toBe('conversation-1')
    expect(onConversationChange).toHaveBeenCalledWith('conversation-1')
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.messages[0].id).toBe('user-message-1')
    expect(result.messages[1]).toMatchObject({
      id: 'message-1',
      versionNumber: 2,
      versionCount: 3,
      metadata: {
        isLoading: false,
        isError: false,
        usage: terminalData.usage,
        timing: terminalData.timing,
      },
    })
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'Hi there', state: 'done' })
  })
  it('reconciles the optimistic user ID from durable start before message_start', async () => {
    const userMessageId = '11111111-1111-1111-1111-111111111111'
    const runEvent = (sequence: number, type: string, payload: Record<string, unknown>) => ({
      event: type,
      data: { run_id: 'run-1', sequence, timestamp: '2026-08-31T00:00:00Z', type, payload },
    })
    const startRun = mock(async () => ({
      run_id: 'run-1',
      conversation_id: 'conversation-1',
      user_message_id: userMessageId,
      status: 'queued' as const,
      stream_url: '/agents/agent-1/chat/runs/run-1/stream',
    }))
    const streamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
    const durableApi = {
      ...agentsApi,
      startRun,
      streamRun,
    } as unknown as NonNullable<HookOptions['api']>
    options = { agentId: 'agent-1', api: durableApi }
    renderHookHarness()
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'run_end', { status: 'completed' }),
    ]

    await result.sendMessage('question')

    expect(startRun).toHaveBeenCalledWith('agent-1', expect.objectContaining({ message: 'question' }))
    expect(result.messages[0]).toMatchObject({ id: userMessageId, role: 'user' })
    expect(result.messages[0].metadata?.pendingPersistence).toBeUndefined()
  })


  it('stops an active stream, aborts it, and preserves partial output as stopped', async () => {
    const blocked = deferred<void>()
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const abort = mock(() => blocked.reject(abortError))
    const onStreamEnd = mock()
    options = { agentId: 'agent-1', onStreamEnd }
    renderHookHarness()
    streamEvents = [
      { event: 'content_delta', data: { delta: 'partial' } },
      blocked.promise.then(() => ({ event: 'message_end', data: {} })),
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort })

    const sending = result.sendMessage('question')
    await flush()
    await new Promise((resolve) => setTimeout(resolve, 0))
    result.stop()
    await sending

    expect(abort).toHaveBeenCalledTimes(1)
    expect(result.status).toBe('idle')
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.messages[1].metadata).toMatchObject({ isLoading: false, isManuallyStopped: true })
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'partial', state: 'done' })
    expect(result.messages[1].parts).toContainEqual({ type: 'stopped' })
  })

  it('reset aborts active work and clears messages, conversation, and status', async () => {
    const blocked = deferred<void>()
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const abort = mock(() => blocked.reject(abortError))
    options = { agentId: 'agent-1', conversationId: 'conversation-1' }
    renderHookHarness()
    result.setConversationId('conversation-1')
    await flush()
    streamEvents = [blocked.promise.then(() => ({ event: 'message_end', data: {} }))]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort })

    const sending = result.sendMessage('question')
    await flush()
    result.reset()
    await sending

    expect(abort).toHaveBeenCalledTimes(1)
    expect(result.messages).toEqual([])
    expect(result.conversationId).toBeNull()
    expect(result.status).toBe('idle')
    expect(result.error).toBeNull()
  })

  it('surfaces HTTP failures through the callback and assistant message boundary', async () => {
    const onError = mock()
    options = { agentId: 'agent-1', onError }
    renderHookHarness()
    chatStream.mockReturnValue({
      stream: Promise.resolve(new Response('{}', { status: 503 })),
      abort: mock(),
    })

    await result.sendMessage('question')

    expect(result.status).toBe('idle')
    expect(onError).toHaveBeenCalledWith({ message: 'errors.serverErrorDescription' })
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      metadata: {
        isLoading: false,
        isError: true,
        errorMessage: 'errors.unknown',
        preservedPartialProgress: false,
      },
    })
    expect(result.messages[1].parts).toEqual([
      { type: 'text', text: 'errors.unknown', state: 'done' },
    ])
  })

  it('keeps streamed progress when the agent reports an error', async () => {
    const onError = mock()
    options = { agentId: 'agent-1', onError }
    renderHookHarness()
    streamEvents = [
      { event: 'content_delta', data: { delta: 'partial answer' } },
      { event: 'error', data: { code: 6103, msg: 'quota exhausted', quota_type: 'output' } },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    expect(onError).toHaveBeenCalledWith({ code: 6103, message: 'quota exhausted', quotaType: 'output' })
    expect(result.messages[1].metadata).toMatchObject({
      isError: true,
      errorMessage: 'errors.quotaExceeded',
      preservedPartialProgress: true,
    })
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'partial answer', state: 'done' })
    expect(result.messages[1].parts).toContainEqual({ type: 'task', taskType: 'generating', state: 'completed' })
  })

  it('renders structured user input requests split across stream chunks', async () => {
    streamEvents = [
      { event: 'content_delta', data: { delta: 'Before <user_input_request><question>Pick one</question>' } },
      { event: 'content_delta', data: { delta: '<options><option>A</option><option>B</option></options></user_input_request> after' } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'Before  after', state: 'done' })
    expect(result.messages[1].parts).toContainEqual({
      type: 'user-input-request',
      question: 'Pick one',
      options: ['A', 'B'],
      state: 'pending',
    })
  })

  it('renders tool status before slow arguments and result arrive', async () => {
    const releaseArguments = deferred<StreamEvent>()
    const releaseResult = deferred<StreamEvent>()
    streamEvents = [
      {
        event: 'tool_call',
        data: {
          tool_call_id: 'tool-1',
          tool_name: 'write',
          tool_display_name: 'Write',
          arguments: {},
        },
      },
      releaseArguments.promise,
      {
        event: 'tool_call',
        data: {
          tool_call_id: 'tool-1',
          tool_name: 'write',
          tool_display_name: 'Write',
          arguments: { path: 'notes.txt', content: 'hello' },
        },
      },
      releaseResult.promise,
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    const sending = result.sendMessage('write the file')
    await waitForParts((parts) => parts.some((part) => (
      part.type === 'tool-call'
      && part.toolCallId === 'tool-1'
      && part.state === 'running'
      && Object.keys(part.input).length === 0
    )))

    expect(result.messages[1].parts).toContainEqual({
      type: 'tool-call',
      toolCallId: 'tool-1',
      toolName: 'write',
      toolDisplayName: 'Write',
      input: {},
      state: 'running',
    })

    releaseArguments.resolve({
      event: 'tool_call',
      data: {
        tool_call_id: 'tool-1',
        tool_name: 'write',
        tool_display_name: 'Write',
        arguments: { path: 'notes.txt', content: 'hello' },
      },
    })
    await waitForParts((parts) => parts.some((part) => (
      part.type === 'tool-call'
      && part.toolCallId === 'tool-1'
      && part.state === 'running'
      && part.input.path === 'notes.txt'
    )))

    expect(result.messages[1].parts).toContainEqual({
      type: 'tool-call',
      toolCallId: 'tool-1',
      toolName: 'write',
      toolDisplayName: 'Write',
      input: { path: 'notes.txt', content: 'hello' },
      state: 'running',
    })

    releaseResult.resolve({
      event: 'tool_result',
      data: {
        tool_call_id: 'tool-1',
        tool_name: 'write',
        tool_display_name: 'Write',
        result: 'written',
        is_error: false,
      },
    })
    await sending

    expect(result.messages[1].parts).toContainEqual(expect.objectContaining({
      type: 'tool-call',
      toolCallId: 'tool-1',
      input: { path: 'notes.txt', content: 'hello' },
      state: 'done',
    }))
    expect(result.messages[1].parts).toContainEqual(expect.objectContaining({
      type: 'tool-result',
      toolCallId: 'tool-1',
      output: 'written',
    }))
  })

  it('keeps alternating reasoning, text, and tool occurrences in stream order', async () => {
    const releaseAfterFirstTool = deferred<StreamEvent>()
    streamEvents = [
      { event: 'reasoning_start', data: {} },
      { event: 'reasoning_delta', data: { delta: 'Reasoning A' } },
      { event: 'reasoning_end', data: {} },
      { event: 'content_delta', data: { delta: 'Answer A' } },
      { event: 'tool_call', data: { tool_call_id: 'tool-a', tool_name: 'lookup', tool_display_name: 'Lookup A', arguments: { q: 'a' } } },
      releaseAfterFirstTool.promise,
      { event: 'tool_result', data: { tool_call_id: 'tool-a', tool_name: 'lookup', tool_display_name: 'Lookup A', result: 'Result A', is_error: false } },
      { event: 'reasoning_start', data: {} },
      { event: 'reasoning_delta', data: { delta: 'Reasoning B' } },
      { event: 'reasoning_end', data: {} },
      { event: 'content_delta', data: { delta: 'Answer B' } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    const sending = result.sendMessage('question')
    await waitForParts((parts) => parts.map((part) => part.type).join(',') === 'reasoning,task,text,tool-call')

    expect(result.messages[1].parts.map((part) => part.type)).toEqual([
      'reasoning',
      'task',
      'text',
      'tool-call',
    ])
    expect(result.messages[1].parts[0]).toMatchObject({ type: 'reasoning', text: 'Reasoning A' })
    expect(result.messages[1].parts[2]).toMatchObject({ type: 'text', text: 'Answer A' })

    releaseAfterFirstTool.resolve({ event: 'stream_pause', data: {} })
    await sending

    const parts = result.messages[1].parts
    expect(parts.map((part) => part.type)).toEqual([
      'reasoning',
      'task',
      'text',
      'tool-call',
      'tool-result',
      'reasoning',
      'text',
    ])
    expect(parts.filter((part) => part.type === 'reasoning').map((part) => part.text)).toEqual([
      'Reasoning A',
      'Reasoning B',
    ])
    expect(parts.filter((part) => part.type === 'text').map((part) => part.text)).toEqual([
      'Answer A',
      'Answer B',
    ])
    expect(parts.filter((part) => part.type === 'tool-call').map((part) => part.toolCallId)).toEqual(['tool-a'])
    expect(parts.find((part) => part.type === 'tool-call')).toMatchObject({ state: 'done' })
  })
  it('keeps late and orphan tool results without dropping their occurrences', async () => {
    streamEvents = [
      { event: 'tool_call', data: { tool_call_id: 'late-tool', tool_name: 'lookup', arguments: {} } },
      { event: 'content_delta', data: { delta: 'Text between call and result' } },
      { event: 'tool_result', data: { tool_call_id: 'late-tool', tool_name: 'lookup', result: 'late result', is_error: false } },
      { event: 'tool_result', data: { tool_call_id: 'orphan-tool', tool_name: 'lookup', result: 'orphan result', is_error: true } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    const parts = result.messages[1].parts
    expect(parts.map((part) => part.type)).toEqual([
      'tool-call',
      'tool-result',
      'task',
      'text',
      'tool-result',
    ])
    expect(parts[0]).toMatchObject({ type: 'tool-call', toolCallId: 'late-tool', state: 'done' })
    expect(parts[1]).toMatchObject({ type: 'tool-result', toolCallId: 'late-tool', output: 'late result' })
    expect(parts[4]).toMatchObject({ type: 'tool-result', toolCallId: 'orphan-tool', isError: true })
  })


  it('renders reasoning, RAG, compression, tools, media, truncation, and iteration markers', async () => {
    streamEvents = [
      { event: 'rag_start', data: {} },
      { event: 'reasoning_start', data: {} },
      { event: 'reasoning_delta', data: { delta: 'think' } },
      { event: 'reasoning_end', data: {} },
      { event: 'rag_context', data: { contexts: [{ document_id: 'doc-1', document_name: 'Doc', content: 'chunk', kb_id: 'kb-1', kb_name: 'KB', score: 0.8 }] } },
      { event: 'compression_start', data: {} },
      { event: 'compression_end', data: { before_tokens: 20, after_tokens: 10 } },
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'sea', tool_display_name: 'sea', arguments: {} } },
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', arguments: { q: 'coverage' } } },
      { event: 'tool_call', data: { tool_call_id: 'tool-2', tool_name: 'lookup', tool_display_name: 'Lookup', arguments: {} } },
      { event: 'tool_result', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', result: { ok: true }, is_error: false } },
      { event: 'tool_result', data: { tool_call_id: 'tool-2', tool_name: 'lookup', tool_display_name: 'Lookup', result: 'failed', is_error: true } },
      { event: 'media_result', data: { kind: 'image', url: '/cat.png' } },
      { event: 'output_truncated', data: {} },
      { event: 'iteration_cap_reached', data: { content: 'Reached limit' } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    const parts = result.messages[1].parts
    expect(parts.map((part) => part.type)).toContain('reasoning')
    expect(parts).toContainEqual(expect.objectContaining({ type: 'source-document', documentId: 'doc-1' }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'task', taskType: 'compression', state: 'completed' }))
    const reasoningIndex = parts.findIndex((part) => part.type === 'reasoning')
    const compressionIndex = parts.findIndex((part) => part.type === 'task' && part.taskType === 'compression')
    const toolIndex = parts.findIndex((part) => part.type === 'tool-call')
    expect(reasoningIndex).toBeLessThan(compressionIndex)
    expect(compressionIndex).toBeLessThan(toolIndex)
    expect(parts).toContainEqual(expect.objectContaining({ type: 'tool-call', toolCallId: 'tool-1', state: 'done' }))
    expect(parts.filter((part) => part.type === 'tool-call' && part.toolCallId === 'tool-1')).toHaveLength(1)
    expect(parts).toContainEqual(expect.objectContaining({
      type: 'tool-call',
      toolCallId: 'tool-1',
      toolName: 'search',
      input: { q: 'coverage' },
    }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'tool-call', toolCallId: 'tool-2', state: 'error' }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'tool-result', toolCallId: 'tool-2', isError: true }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'media-result' }))
    expect(parts).toContainEqual({ type: 'truncated' })
    expect(parts).toContainEqual({ type: 'iteration-cap-reached' })
    expect(parts).toContainEqual({ type: 'text', text: 'Reached limit', state: 'done' })
  })
  it('preserves defined tool-call fields when a duplicate tool_call omits them', async () => {
    streamEvents = [
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', arguments: { q: 'a' } } },
      // Duplicate tool_call omits tool_display_name -> must not clobber the existing value
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', arguments: { q: 'b' } } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    const parts = result.messages[1].parts
    expect(parts.filter((part) => part.type === 'tool-call' && part.toolCallId === 'tool-1')).toHaveLength(1)
    expect(parts).toContainEqual(expect.objectContaining({
      type: 'tool-call',
      toolCallId: 'tool-1',
      toolDisplayName: 'Search',
      input: { q: 'b' },
      state: 'done',
    }))
  })

  it('preserves a terminal tool-call state when a duplicate tool_call arrives after the result', async () => {
    streamEvents = [
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', arguments: {} } },
      { event: 'tool_result', data: { tool_call_id: 'tool-1', tool_name: 'search', result: 'boom', is_error: true } },
      // Duplicate tool_call carries state 'running' -> must not regress the terminal 'error' state
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', arguments: {} } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    const parts = result.messages[1].parts
    expect(parts.filter((part) => part.type === 'tool-call' && part.toolCallId === 'tool-1')).toHaveLength(1)
    expect(parts).toContainEqual(expect.objectContaining({
      type: 'tool-call',
      toolCallId: 'tool-1',
      state: 'error',
    }))
  })

  it('finalizes a stream that closes without a terminal event', async () => {
    streamEvents = [
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', arguments: {} } },
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    expect(result.status).toBe('idle')
    expect(result.messages[1].metadata).toMatchObject({ isLoading: false, isManuallyStopped: false })
    expect(result.messages[1].parts).toContainEqual({
      type: 'tool-call',
      toolCallId: 'tool-1',
      toolName: 'search',
      toolDisplayName: 'Search',
      input: {},
      state: 'done',
    })
  })

  it('sends image and file attachments in the request and user message', async () => {
    streamEvents = [{ event: 'message_end', data: {} }]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage(
      'with attachments',
      [{ url: '/image.png' }],
      [{ filename: 'notes.txt', url: '/notes.txt', size: 12, mimeType: 'text/plain' }]
    )

    expect(chatStream).toHaveBeenCalledWith('agent-1', expect.objectContaining({
      message: 'with attachments',
      images: [{ url: '/image.png' }],
      file_urls: [{ filename: 'notes.txt', url: '/notes.txt', size: 12, mimeType: 'text/plain' }],
    }))
    expect(result.messages[0].parts).toEqual([
      { type: 'text', text: 'with attachments' },
      { type: 'image', url: '/image.png' },
      { type: 'file', filename: 'notes.txt', size: 12 },
    ])
  })

  it('ignores blank messages and concurrent sends before invoking the API', async () => {
    const pending = deferred<Response>()
    chatStream.mockReturnValue({ stream: pending.promise, abort: mock() })

    await result.sendMessage('   ')
    expect(chatStream).not.toHaveBeenCalled()

    const sending = result.sendMessage('first')
    await flush()
    await result.sendMessage('second')
    expect(chatStream).toHaveBeenCalledTimes(1)

    pending.reject(new Error('network unavailable'))
    await sending
  })

  it('constructs requests with conversation context and variables', async () => {
    options = { agentId: 'agent-1', conversationId: 'conversation-1', variables: { locale: 'en' } }
    renderHookHarness()
    result.setConversationId('conversation-1')
    await flush()
    streamEvents = [{ event: 'message_end', data: {} }]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('  contextual question  ')

    expect(chatStream).toHaveBeenCalledWith('agent-1', {
      message: 'contextual question',
      images: undefined,
      file_urls: undefined,
      conversation_id: 'conversation-1',
      variables: { locale: 'en' },
    })
  })

  it('switches a valid message version and reloads the conversation', async () => {
    const messageId = '11111111-1111-1111-1111-111111111111'
    const reloaded = [{ id: 'version-2', role: 'assistant', parts: [{ type: 'text', text: 'new' }] }] as ChatMessage[]
    options = { agentId: 'agent-1', conversationId: 'conversation-1' }
    renderHookHarness()
    result.setConversationId('conversation-1')
    await flush()
    result.setMessages([{ id: messageId, role: 'assistant', parts: [] }] as ChatMessage[])
    await flush()
    getMessageVersions.mockResolvedValue([{ id: 'version-1' }, { id: 'version-2' }])
    getConversation.mockResolvedValue({ messages: reloaded })

    await result.switchVersion(messageId, 4)
    expect(switchMessageVersion).not.toHaveBeenCalled()

    await result.switchVersion(messageId, 1)

    expect(switchMessageVersion).toHaveBeenCalledWith('agent-1', messageId, 'version-2')
    expect(getConversation).toHaveBeenCalledWith('conversation-1')
    expect(result.messages).toEqual(reloaded)

    await result.switchVersion('missing', 0)
    expect(switchMessageVersion).toHaveBeenCalledTimes(1)
  })

  it('edits a user message, streams its replacement, and reloads authoritative history', async () => {
    const userId = '11111111-1111-1111-1111-111111111111'
    const onStreamStart = mock()
    const onStreamEnd = mock()
    const reloaded = [
      { id: userId, role: 'user', parts: [{ type: 'text', text: 'edited' }], versionNumber: 2 },
      { id: 'assistant-2', role: 'assistant', parts: [{ type: 'text', text: 'replacement' }] },
    ] as ChatMessage[]
    options = { agentId: 'agent-1', conversationId: 'conversation-1', onStreamStart, onStreamEnd }
    renderHookHarness()
    result.setConversationId('conversation-1')
    result.setMessages([
      { id: userId, role: 'user', parts: [{ type: 'text', text: 'original' }] },
      { id: 'assistant-old', role: 'assistant', parts: [{ type: 'text', text: 'stale' }] },
    ] as ChatMessage[])
    await flush()
    streamEvents = [
      { event: 'message_start', data: { message_id: 'assistant-2', edited_message_id: userId, edited_version_number: 2, edited_version_count: 2 } },
      { event: 'content_delta', data: { delta: 'replace' } },
      { event: 'content_delta', data: { delta: 'ment' } },
      { event: 'message_end', data: {} },
    ]
    editMessageStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
    getConversation.mockResolvedValue({ messages: reloaded })

    await result.editMessage(userId, 'edited')

    expect(editMessageStream).toHaveBeenCalledWith('agent-1', userId, 'edited')
    expect(onStreamStart).toHaveBeenCalledTimes(1)
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.messages).toEqual(reloaded)
    expect(result.status).toBe('idle')

    await result.editMessage('temporary-id', 'ignored')
    await result.editMessage('assistant-2', 'ignored')
    expect(editMessageStream).toHaveBeenCalledTimes(1)
  })
  it('does not route an unsaved user message to the UUID-only edit endpoint', async () => {
    result.setMessages([
      {
        id: 'user-pending',
        role: 'user',
        parts: [{ type: 'text', text: 'original' }],
        metadata: { pendingPersistence: true },
      },
    ] as ChatMessage[])
    await flush()

    await result.editMessage('user-pending', 'updated')

    expect(editMessageStream).not.toHaveBeenCalled()
    expect(result.messages).toHaveLength(1)
    expect(result.messages[0].parts).toEqual([{ type: 'text', text: 'original' }])
  })


  it('renders the complete assistant stream while an edited response is in progress', async () => {
    const userId = '11111111-1111-1111-1111-111111111111'
    const reload = deferred<{ messages: ChatMessage[] }>()
    const messageEnd = deferred<StreamEvent>()
    const messageEndRequested = deferred<void>()
    const reloadStarted = deferred<void>()
    options = { agentId: 'agent-1', conversationId: 'conversation-1' }
    renderHookHarness()
    result.setConversationId('conversation-1')
    result.setMessages([
      { id: userId, role: 'user', parts: [{ type: 'text', text: 'original' }] },
      { id: 'assistant-old', role: 'assistant', parts: [{ type: 'text', text: 'stale' }] },
    ] as ChatMessage[])
    await flush()

    streamEvents = [
      { event: 'message_start', data: { message_id: 'assistant-edited', edited_message_id: userId } },
      { event: 'rag_start', data: {} },
      { event: 'reasoning_start', data: {} },
      { event: 'reasoning_delta', data: { delta: 'reconsidering' } },
      { event: 'reasoning_end', data: {} },
      { event: 'rag_context', data: { contexts: [{ document_id: 'doc-1', document_name: 'Doc', content: 'chunk', kb_id: 'kb-1', kb_name: 'KB', score: 0.8 }] } },
      { event: 'compression_start', data: {} },
      { event: 'compression_end', data: { before_tokens: 20, after_tokens: 10 } },
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', arguments: { q: 'edited' } } },
      { event: 'tool_result', data: { tool_call_id: 'tool-1', tool_name: 'search', tool_display_name: 'Search', result: { ok: true }, is_error: false } },
      { event: 'media_result', data: { kind: 'image', url: '/edited.png' } },
      { event: 'content_delta', data: { delta: 'updated answer' } },
      { event: 'output_truncated', data: {} },
      { event: 'iteration_cap_reached', data: { content: 'Reached limit' } },
      () => {
        messageEndRequested.resolve()
        return messageEnd.promise
      },
    ]
    editMessageStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
    getConversation.mockImplementation(() => {
      reloadStarted.resolve()
      return reload.promise
    })

    const editing = result.editMessage(userId, 'edited')
    await messageEndRequested.promise

    let assistant = result.messages.find(message => message.id === 'assistant-edited')
    expect(result.status).toBe('streaming')
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'reasoning', text: 'reconsidering', state: 'done' }))
    expect(assistant?.parts).toContainEqual({ type: 'text', text: 'updated answer', state: 'streaming' })
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'tool-call', toolCallId: 'tool-1', state: 'done' }))

    messageEnd.resolve({ event: 'message_end', data: { usage: { total_tokens: 30 }, timing: { duration_ms: 50 } } })
    await reloadStarted.promise
    await flush()
    assistant = result.messages.find(message => message.id === 'assistant-edited')
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'reasoning', text: 'reconsidering', state: 'done' }))
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'source-document', documentId: 'doc-1' }))
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'task', taskType: 'compression', state: 'completed' }))
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'tool-call', toolCallId: 'tool-1', state: 'done' }))
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'tool-result', toolCallId: 'tool-1' }))
    expect(assistant?.parts).toContainEqual(expect.objectContaining({ type: 'media-result' }))
    expect(assistant?.parts).toContainEqual({ type: 'text', text: 'updated answer', state: 'done' })
    expect(assistant?.parts).toContainEqual({ type: 'truncated' })
    expect(assistant?.parts).toContainEqual({ type: 'iteration-cap-reached' })
    expect(assistant?.metadata).toMatchObject({
      isLoading: false,
      usage: { total_tokens: 30 },
      timing: { duration_ms: 50 },
    })

    reload.resolve({ messages: result.messages })
    await editing
  })

  it('recovers authoritative messages after an edit stream error', async () => {
    const userId = '11111111-1111-1111-1111-111111111111'
    const onError = mock()
    const recovered = [{ id: userId, role: 'user', parts: [{ type: 'text', text: 'original' }] }] as ChatMessage[]
    options = { agentId: 'agent-1', conversationId: 'conversation-1', onError }
    renderHookHarness()
    result.setConversationId('conversation-1')
    result.setMessages(recovered)
    await flush()
    streamEvents = [{ event: 'error', data: { code: 429, msg: 'try later', quota_type: 'usage' } }]
    editMessageStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
    getConversation.mockResolvedValue({ messages: recovered })

    await result.editMessage(userId, 'edited')

    expect(onError).toHaveBeenCalledWith({ code: 429, message: 'try later', quotaType: 'usage' })
    expect(getConversation).toHaveBeenCalledWith('conversation-1')
    expect(result.messages).toEqual(recovered)
    expect(result.status).toBe('idle')
  })

  it('marks edit-stream compression as errored when the stream fails', async () => {
    const userId = '11111111-1111-1111-1111-111111111111'
    const reloadStarted = deferred<void>()
    const reload = deferred<{ messages: ChatMessage[] }>()
    const reloaded = [{ id: userId, role: 'user', parts: [{ type: 'text', text: 'edited' }] }] as ChatMessage[]
    options = { agentId: 'agent-1', conversationId: 'conversation-1' }
    renderHookHarness()
    result.setConversationId('conversation-1')
    result.setMessages([
      { id: userId, role: 'user', parts: [{ type: 'text', text: 'original' }] },
    ] as ChatMessage[])
    await flush()
    streamEvents = [
      { event: 'message_start', data: { message_id: 'assistant-failed', edited_message_id: userId } },
      { event: 'compression_start', data: {} },
      { event: 'error', data: { code: 429, msg: 'try later', quota_type: 'usage' } },
    ]
    editMessageStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
    getConversation.mockImplementation(() => {
      reloadStarted.resolve()
      return reload.promise
    })

    const editing = result.editMessage(userId, 'edited')
    await reloadStarted.promise
    await flush()

    const failed = result.messages.find((message) => message.id === 'assistant-failed')
    expect(failed?.parts).toContainEqual({ type: 'task', taskType: 'compression', state: 'error' })

    reload.resolve({ messages: reloaded })
    await editing
  })

  it('preserves the edit-stream error code across the history reload', async () => {
    const userId = '11111111-1111-1111-1111-111111111111'
    const onError = mock()
    // The backend persisted the failed edit round (empty assistant message),
    // but BackendMessage conversion does not carry the SSE error code.
    const reloaded = [
      { id: userId, role: 'user', parts: [{ type: 'text', text: 'edited' }] },
      { id: 'assistant-failed', role: 'assistant', parts: [], metadata: { isError: true } },
    ] as ChatMessage[]
    options = { agentId: 'agent-1', conversationId: 'conversation-1', onError }
    renderHookHarness()
    result.setConversationId('conversation-1')
    result.setMessages([
      { id: userId, role: 'user', parts: [{ type: 'text', text: 'original' }] },
    ] as ChatMessage[])
    await flush()
    streamEvents = [
      { event: 'message_start', data: { message_id: 'assistant-failed', edited_message_id: userId } },
      { event: 'error', data: { code: 429, msg: 'try later', quota_type: 'usage' } },
    ]
    editMessageStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
    getConversation.mockResolvedValue({ messages: reloaded })

    await result.editMessage(userId, 'edited')

    expect(onError).toHaveBeenCalledWith({ code: 429, message: 'try later', quotaType: 'usage' })
    expect(getConversation).toHaveBeenCalledWith('conversation-1')
    const failed = result.messages.find((message) => message.id === 'assistant-failed')
    expect(failed?.metadata).toMatchObject({ isError: true, errorCode: 429 })
    expect(result.status).toBe('idle')
  })

  it('resends text and images when regenerating an unsaved assistant', async () => {
    result.setMessages([
      {
        id: 'user-temporary',
        role: 'user',
        parts: [{ type: 'text', text: 'retry me' }, { type: 'image', url: '/dummy.png' }],
      },
      { id: 'assistant-temporary', role: 'assistant', parts: [] },
    ] as ChatMessage[])
    await flush()
    streamEvents = [{ event: 'message_end', data: {} }]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.regenerate('assistant-temporary')

    expect(regenerateStream).not.toHaveBeenCalled()
    expect(chatStream).toHaveBeenCalledWith('agent-1', expect.objectContaining({
      message: 'retry me',
      images: [{ type: 'image_url', url: '/dummy.png' }],
    }))
  })

  it('preserves partial regeneration progress when the stream reports an error', async () => {
    const messageId = '22222222-2222-2222-2222-222222222222'
    const onError = mock()
    options = { agentId: 'agent-1', onError }
    renderHookHarness()
    result.setMessages([{ id: messageId, role: 'assistant', parts: [{ type: 'text', text: 'old' }] }] as ChatMessage[])
    await flush()
    streamEvents = [
      { event: 'content_delta', data: { delta: 'partial retry' } },
      { event: 'error', data: { code: 6105, msg: 'vision unavailable' } },
    ]
    regenerateStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.regenerate(messageId)

    expect(onError).toHaveBeenCalledWith({ code: 6105, message: 'vision unavailable', quotaType: undefined })
    expect(result.messages[0].metadata).toMatchObject({
      isLoading: false,
      isError: true,
      errorMessage: 'errors.modelVisionNotSupported',
      preservedPartialProgress: true,
    })
    expect(result.messages[0].parts).toContainEqual({ type: 'text', text: 'partial retry', state: 'done' })
  })

  it('regenerates a saved assistant across message, tool, media, and version boundaries', async () => {
    const messageId = '22222222-2222-2222-2222-222222222222'
    const onStreamStart = mock()
    const onStreamEnd = mock()
    options = { agentId: 'agent-1', onStreamStart, onStreamEnd }
    renderHookHarness()
    result.setMessages([
      { id: 'user-1', role: 'user', parts: [{ type: 'text', text: 'question' }] },
      { id: messageId, role: 'assistant', parts: [{ type: 'text', text: 'old' }], metadata: { isError: true } },
      { id: 'descendant', role: 'user', parts: [{ type: 'text', text: 'stale branch' }] },
    ] as ChatMessage[])
    await flush()
    streamEvents = [
      { event: 'message_start', data: { message_id: 'version-2', version_number: 2, version_count: 2 } },
      { event: 'content_delta', data: { delta: 'new answer' } },
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'lookup', arguments: { q: 'safe dummy' } } },
      { event: 'tool_result', data: { tool_call_id: 'tool-1', tool_name: 'lookup', result: { ok: true }, is_error: false } },
      { event: 'media_result', data: { kind: 'image', url: '/dummy.png' } },
      { event: 'message_end', data: { version_number: 3, version_count: 3, usage: { total_tokens: 4 } } },
    ]
    regenerateStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.regenerate(messageId)

    expect(regenerateStream).toHaveBeenCalledWith('agent-1', messageId, {})
    expect(onStreamStart).toHaveBeenCalledTimes(1)
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.messages).toHaveLength(2)
    expect(result.messages[1]).toMatchObject({
      id: 'version-2',
      versionNumber: 3,
      versionCount: 3,
      metadata: { isLoading: false, isError: false, usage: { total_tokens: 4 } },
    })
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'new answer', state: 'done' })
    expect(result.messages[1].parts).toContainEqual(expect.objectContaining({ type: 'tool-call', state: 'done' }))
    expect(result.messages[1].parts).toContainEqual(expect.objectContaining({ type: 'media-result' }))
  })

  it('submits steering to the active run and commits the queued user message', async () => {
    const release = deferred<StreamEvent>()
    const runEvent = (sequence: number, type: string, payload: Record<string, unknown>) => ({
      event: type,
      data: { run_id: 'run-1', sequence, timestamp: '2026-08-31T00:00:00Z', type, payload },
    })
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      release.promise,
      runEvent(4, 'run_end', { status: 'completed', message_id: 'assistant-1' }),
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    const sending = result.sendMessage('initial')
    await flush()
    await result.sendMessage('steer this run')

    expect(postRunInput).not.toHaveBeenCalled()
    expect(result.messages.find((message) => message.metadata?.runInputState === 'queued')).toMatchObject({
      role: 'user',
      parts: [{ type: 'text', text: 'steer this run' }],
    })

    release.resolve(runEvent(3, 'input_accepted', {
      kind: 'steer',
      content: 'steer this run',
      sequence: 1,
    }))
    await sending

    expect(postRunInput).toHaveBeenCalledWith('agent-1', 'run-1', expect.objectContaining({
      delivery: 'steer',
      content: 'steer this run',
    }))

    expect(result.messages.find((message) => message.metadata?.runInputSequence === 1)?.metadata).toMatchObject({
      runInputState: 'committed',
      runInputKind: 'steer',
    })
  })
  it('creates a user message when a replayed input acceptance has no local pending row', async () => {
    const runEvent = (sequence: number, type: string, payload: Record<string, unknown>) => ({
      event: type,
      data: {
        run_id: 'run-1',
        sequence,
        timestamp: '2026-08-31T00:00:00Z',
        message_id: type === 'input_accepted' ? 'assistant-1' : undefined,
        type,
        payload,
      },
    })
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      runEvent(3, 'input_accepted', { kind: 'steer', content: 'replayed instruction', sequence: 1 }),
      runEvent(4, 'run_end', { status: 'completed', message_id: 'assistant-1' }),
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    expect(result.messages).toContainEqual(expect.objectContaining({
      id: 'run-input-run-1-1',
      role: 'user',
      parts: [{ type: 'text', text: 'replayed instruction' }],
      metadata: expect.objectContaining({ runInputState: 'committed', runInputKind: 'steer', runInputSequence: 1 }),
    }))
    expect(result.messages.find((message) => message.id === 'assistant-1')?.metadata).not.toHaveProperty('runInputState')
  })


  it('deduplicates replayed run envelopes before assistant parts and message end effects', async () => {
    const runEvent = (sequence: number, type: string, payload: Record<string, unknown>) => ({
      event: type,
      data: { run_id: 'run-1', sequence, timestamp: '2026-08-31T00:00:00Z', type, payload },
    })
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      runEvent(3, 'content_delta', { delta: 'once' }),
      runEvent(3, 'content_delta', { delta: 'once' }),
      runEvent(4, 'tool_call', { tool_call_id: 'tool-1', tool_name: 'lookup', arguments: {} }),
      runEvent(4, 'tool_call', { tool_call_id: 'tool-1', tool_name: 'lookup', arguments: {} }),
      runEvent(5, 'tool_result', { tool_call_id: 'tool-1', tool_name: 'lookup', result: 'done', is_error: false }),
      runEvent(5, 'tool_result', { tool_call_id: 'tool-1', tool_name: 'lookup', result: 'done', is_error: false }),
      runEvent(6, 'message_end', {}),
      runEvent(6, 'message_end', {}),
      runEvent(7, 'run_end', { status: 'completed', message_id: 'assistant-1' }),
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })

    await result.sendMessage('question')

    const assistant = result.messages.find((message) => message.id === 'assistant-1')!
    expect(assistant.parts.filter((part) => part.type === 'text' && part.text === 'once')).toHaveLength(1)
    expect(assistant.parts.filter((part) => part.type === 'tool-call' && part.toolCallId === 'tool-1')).toHaveLength(1)
    expect(assistant.parts.filter((part) => part.type === 'tool-result' && part.toolCallId === 'tool-1')).toHaveLength(1)
    expect(assistant.metadata).toMatchObject({ isLoading: false, isError: false })
  })

  it('waits for server run_end before completing a durable stop', async () => {
    const release = deferred<StreamEvent>()
    const abort = mock()
    const runEvent = (sequence: number, type: string, payload: Record<string, unknown>) => ({
      event: type,
      data: { run_id: 'run-1', sequence, timestamp: '2026-08-31T00:00:00Z', type, payload },
    })
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      runEvent(3, 'content_delta', { delta: 'partial' }),
      release.promise,
    ]
    chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort })

    const sending = result.sendMessage('question')
    await flush()
    const stopping = result.stop()
    await flush()

    expect(stopRun).toHaveBeenCalledWith('agent-1', 'run-1')
    expect(result.runStatus).toBe('stopping')
    expect(result.status).toBe('streaming')
    expect(abort).not.toHaveBeenCalled()

    release.resolve(runEvent(4, 'run_end', { status: 'stopped', message_id: 'assistant-1' }))
    await stopping
    await sending

    expect(result.runStatus).toBe('stopped')
    expect(result.status).toBe('idle')
    expect(result.messages.find((message) => message.id === 'assistant-1')?.parts).toContainEqual({ type: 'stopped' })
  })
})
