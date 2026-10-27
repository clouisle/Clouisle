import { afterEach, beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'

import type { ChatMessage, MessagePart } from '@/components/chat'
import type { ChatStreamApi, UseChatReturn } from './use-chat'

type StateSetter<T> = (value: T | ((previous: T) => T)) => void

type HookOptions = {
  agentId: string
  conversationId?: string
  variables?: Record<string, unknown>
  onConversationChange?: (id: string) => void
  onError?: (error: { code?: number; message: string }) => void
  onStreamStart?: () => void
  onStreamEnd?: () => void
  api?: ChatStreamApi
  initialMessages?: ChatMessage[]
}

type HookResult = UseChatReturn
type StreamEvent = { event: string; data: unknown }
type StreamEventSource = StreamEvent | Promise<StreamEvent> | (() => Promise<StreamEvent>)

let stateSlots: unknown[] = []
let refSlots: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
let options: HookOptions
let result: HookResult
let useChat: typeof import('./use-chat').useChat
let pendingEffects: Array<() => void | (() => void)> = []
let cleanups: Array<() => void> = []
let renderScheduled = false
let renderWaiters: Array<() => void> = []
let streamEvents: StreamEventSource[] = []

const chatStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const editMessageStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const regenerateStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const getConversation = mock(() => Promise.resolve({ messages: [] }))
const getMessageVersions = mock(() => Promise.resolve<Array<{ id: string }>>([]))
const switchMessageVersion = mock(() => Promise.resolve())
const getRunStatus = mock(() => Promise.resolve())
const getRunEvents = mock(() => Promise.resolve([]))
const streamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const postRunInput = mock(() => Promise.resolve())
const postRunAnswer = mock(() => Promise.resolve({ status: 'queued' }))
const stopRun = mock(() => Promise.resolve())

const agentsApi = {
  chatStream,
  startRun: undefined,
  streamRun,
  editMessageStream,
  regenerateStream,
  getConversation,
  getMessageVersions,
  switchMessageVersion,
  getRunStatus,
  getRunEvents,
  postRunInput,
  postRunAnswer,
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
  extractToolCitationSources: () => [],
  shouldDisplayMediaResultInBody: () => true,
}))

const reactInternals = { H: null, A: null, T: null, S: null, V: null, recentlyCreatedOwnerStacks: 0 }
const reactHelpers = {
  __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: reactInternals,
  createElement: () => null,
  act: (callback: () => unknown) => callback(),
  createContext: () => ({ Provider: () => null, Consumer: () => null }),
  forwardRef: (component: unknown) => component,
  memo: (component: unknown) => component,
  useContext: () => ({}),
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
  useEffect(effect: () => void | (() => void)) {
    pendingEffects.push(effect)
  },
}))

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))

function renderHookHarness() {
  stateIndex = 0
  refIndex = 0
  pendingEffects = []
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

function runEffects() {
  const pending = pendingEffects
  pendingEffects = []
  for (const effect of pending) {
    const cleanup = effect()
    if (typeof cleanup === 'function') cleanups.push(cleanup)
  }
}

function unmount() {
  const pending = cleanups
  cleanups = []
  for (const cleanup of pending) cleanup()
}

const storage = new Map<string, string>()
const listeners = new Map<string, () => void>()
const originalWindow = globalThis.window
const storageKey = 'clouisle:agent-run:agent-1:conversation-1'

beforeAll(async () => {
  ;({ useChat } = await import('./use-chat'))
})

beforeEach(() => {
  stateSlots = []
  refSlots = []
  cleanups = []
  renderWaiters = []
  pendingEffects = []
  for (const apiMock of [
    chatStream,
    editMessageStream,
    regenerateStream,
    getConversation,
    getMessageVersions,
    switchMessageVersion,
    getRunStatus,
    getRunEvents,
    streamRun,
    postRunInput,
    postRunAnswer,
    stopRun,
  ]) apiMock.mockReset()

  chatStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
  editMessageStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
  regenerateStream.mockReturnValue({ stream: Promise.resolve(new Response()), abort: mock() })
  getConversation.mockResolvedValue({ messages: [] })
  getMessageVersions.mockResolvedValue([])
  switchMessageVersion.mockResolvedValue()
  getRunStatus.mockResolvedValue({})
  getRunEvents.mockResolvedValue([])
  postRunInput.mockResolvedValue({ status: 'running' })
  postRunAnswer.mockResolvedValue({ status: 'queued' })
  stopRun.mockResolvedValue({ status: 'stopping' })
  streamEvents = []
  storage.clear()
  listeners.clear()
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      sessionStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => storage.set(key, value),
        removeItem: (key: string) => storage.delete(key),
      },
      addEventListener: (type: string, listener: () => void) => listeners.set(type, listener),
      removeEventListener: (type: string) => listeners.delete(type),
      requestAnimationFrame: (callback: () => void) => {
        queueMicrotask(callback)
        return 1
      },
      cancelAnimationFrame: () => undefined,
    },
  })
  options = { agentId: 'agent-1' }
})

afterEach(() => {
  Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow })
})

function deferred<T>() {
  return Promise.withResolvers<T>()
}

async function flush() {
  for (let i = 0; i < 6; i += 1) await Promise.resolve()
}

async function waitFor(predicate: () => boolean) {
  for (let attempt = 0; attempt < 100 && !predicate(); attempt += 1) await flush()
  expect(predicate()).toBe(true)
}

function runEvent(sequence: number, type: string, payload: Record<string, unknown>, messageId?: string) {
  return {
    event: type,
    data: {
      run_id: 'run-1',
      sequence,
      timestamp: '2026-10-27T00:00:00Z',
      ...(messageId ? { message_id: messageId } : {}),
      type,
      payload,
    },
  }
}

function customApi(overrides: Partial<ChatStreamApi>): ChatStreamApi {
  return { ...agentsApi, ...overrides } as unknown as ChatStreamApi
}

describe('useChat failure and lifecycle actions', () => {
  it('surfaces a durable run start failure on the assistant message exactly once', async () => {
    const onError = mock()
    const onStreamEnd = mock()
    const startRun = mock(async () => {
      throw new Error('network unavailable')
    })
    options = {
      agentId: 'agent-1',
      api: customApi({ startRun, streamRun }),
      onError,
      onStreamEnd,
    }
    renderHookHarness()

    await result.sendMessage('hello')
    await flush()

    expect(startRun).toHaveBeenCalledTimes(1)
    expect(streamRun).not.toHaveBeenCalled()
    expect(onError).toHaveBeenCalledWith({ message: 'network unavailable' })
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.status).toBe('idle')
    expect(result.runId).toBeNull()
    expect(result.messages).toHaveLength(2)
    expect(result.messages[1].metadata).toMatchObject({
      isLoading: false,
      isError: true,
      errorMessage: 'errors.networkError',
      preservedPartialProgress: false,
    })
    expect(result.messages[1].parts).toEqual([
      { type: 'text', text: 'errors.networkError', state: 'done' },
    ])
  })

  it('marks a failed terminal run as errored while keeping streamed progress', async () => {
    const onError = mock()
    options = { agentId: 'agent-1', onError }
    renderHookHarness()
    streamEvents = [
      { event: 'run_start', data: { status: 'running', run_id: 'run-1' } },
      { event: 'content_delta', data: { delta: 'partial answer' } },
      { event: 'run_end', data: { status: 'failed', msg: 'Tool execution failed' } },
    ]

    await result.sendMessage('question')
    await flush()

    expect(result.status).toBe('idle')
    expect(result.runStatus).toBe('failed')
    expect(result.runId).toBeNull()
    expect(result.messages[1].metadata).toMatchObject({
      isLoading: false,
      isError: true,
      errorMessage: 'Tool execution failed',
      preservedPartialProgress: true,
    })
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'partial answer', state: 'done' })
  })

  it('restores run and UI status when the stop request fails', async () => {
    const onError = mock()
    const release = deferred<StreamEvent>()
    options = { agentId: 'agent-1', onError }
    renderHookHarness()
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      runEvent(3, 'content_delta', { delta: 'partial' }),
      release.promise,
    ]
    stopRun.mockRejectedValue(new Error('stop request lost'))

    const sending = result.sendMessage('question')
    for (let attempt = 0; attempt < 10 && result.runStatus !== 'running'; attempt += 1) await flush()
    expect(result.status).toBe('streaming')

    await result.stop()
    await flush()

    expect(stopRun).toHaveBeenCalledWith('agent-1', 'run-1')
    expect(onError).toHaveBeenCalledWith({ message: 'stop request lost' })
    expect(result.error).toEqual({ message: 'stop request lost' })
    expect(result.runStatus).toBe('running')
    expect(result.status).toBe('streaming')
    expect(result.messages[1].metadata).toMatchObject({ isLoading: true })

    release.resolve(runEvent(4, 'run_end', { status: 'completed', message_id: 'assistant-1' }))
    await sending
    await flush()
    expect(result.status).toBe('idle')
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'partial', state: 'done' })
  })

  it('stops locally and aborts the late subscription when no stop endpoint exists', async () => {
    const onStreamEnd = mock()
    const startDeferred = deferred<{ run_id: string; conversation_id: string; user_message_id: string; status: 'queued'; stream_url: string }>()
    const abortRun = mock()
    const startRun = mock(() => startDeferred.promise)
    const lateStreamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: abortRun }))
    options = {
      agentId: 'agent-1',
      api: customApi({ startRun, streamRun: lateStreamRun, stopRun: undefined }),
      onStreamEnd,
    }
    renderHookHarness()
    streamEvents = [{ event: 'content_delta', data: { delta: 'late answer' } }]

    const sending = result.sendMessage('hello')
    await flush()
    expect(result.status).toBe('loading')

    await result.stop()
    await flush()

    expect(stopRun).not.toHaveBeenCalled()
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.status).toBe('idle')
    expect(result.messages[1].metadata).toMatchObject({ isLoading: false, isManuallyStopped: true })
    expect(result.messages[1].parts).toContainEqual({ type: 'stopped' })

    startDeferred.resolve({
      run_id: 'run-1',
      conversation_id: 'conversation-1',
      user_message_id: 'user-1',
      status: 'queued',
      stream_url: '/agents/agent-1/chat/runs/run-1/stream',
    })
    await sending
    await flush()

    expect(lateStreamRun).toHaveBeenCalledTimes(1)
    expect(abortRun).toHaveBeenCalledTimes(1)
    expect(result.status).toBe('idle')
    expect(result.messages[1].parts).not.toContainEqual({ type: 'text', text: 'late answer', state: 'streaming' })
  })

  it('drops a run that starts after reset instead of streaming into cleared state', async () => {
    const startDeferred = deferred<{ run_id: string; conversation_id: string; user_message_id: string; status: 'queued'; stream_url: string }>()
    const abortRun = mock()
    const startRun = mock(() => startDeferred.promise)
    const lateStreamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: abortRun }))
    options = { agentId: 'agent-1', api: customApi({ startRun, streamRun: lateStreamRun }) }
    renderHookHarness()
    streamEvents = [{ event: 'content_delta', data: { delta: 'unexpected' } }]

    const sending = result.sendMessage('hello')
    await flush()
    result.reset()
    await flush()

    expect(result.status).toBe('idle')
    expect(result.messages).toEqual([])

    startDeferred.resolve({
      run_id: 'run-1',
      conversation_id: 'conversation-1',
      user_message_id: 'user-1',
      status: 'queued',
      stream_url: '/agents/agent-1/chat/runs/run-1/stream',
    })
    await sending
    await flush()

    expect(abortRun).toHaveBeenCalledTimes(1)
    expect(result.status).toBe('idle')
    expect(result.messages).toEqual([])
  })

  it('aborts in-flight work and releases listeners on unmount', async () => {
    const startDeferred = deferred<{ run_id: string; conversation_id: string; user_message_id: string; status: 'queued'; stream_url: string }>()
    const abortRun = mock()
    const startRun = mock(() => startDeferred.promise)
    const lateStreamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: abortRun }))
    const onStreamStart = mock()
    const onStreamEnd = mock()
    options = { agentId: 'agent-1', api: customApi({ startRun, streamRun: lateStreamRun }), onStreamStart, onStreamEnd }
    renderHookHarness()

    const sending = result.sendMessage('hello')
    await flush()
    runEffects()
    expect(listeners.has('focus')).toBe(true)

    unmount()
    expect(listeners.has('focus')).toBe(false)

    startDeferred.resolve({
      run_id: 'run-1',
      conversation_id: 'conversation-1',
      user_message_id: 'user-1',
      status: 'queued',
      stream_url: '/agents/agent-1/chat/runs/run-1/stream',
    })
    await sending
    await flush()

    expect(abortRun).toHaveBeenCalledTimes(1)
    expect(onStreamStart).not.toHaveBeenCalled()
    expect(onStreamEnd).not.toHaveBeenCalled()
    expect(result.messages[1].parts).toEqual([])
  })

  it('clears a spinner after a failed status read and recovers on the next focus', async () => {
    const onError = mock()
    storage.set(storageKey, JSON.stringify({ runId: 'run-1', lastSequence: 2 }))
    getRunStatus.mockRejectedValueOnce(new Error('status unavailable'))
    getConversation.mockRejectedValueOnce(new Error('history unavailable'))
    options = { agentId: 'agent-1', conversationId: 'conversation-1', onError }
    renderHookHarness()

    runEffects()
    await flush()

    expect(getRunStatus).toHaveBeenCalledWith('agent-1', 'run-1')
    expect(result.status).toBe('idle')
    expect(result.runStatus).toBeNull()
    expect(result.pendingAskUserToolCallId).toBeNull()
    expect(storage.has(storageKey)).toBe(true)

    getRunStatus.mockResolvedValueOnce({ id: 'run-1', status: 'completed' })
    listeners.get('focus')?.()
    await flush()

    expect(getRunStatus).toHaveBeenCalledTimes(2)
    expect(getConversation).toHaveBeenCalledWith('conversation-1')
    expect(storage.has(storageKey)).toBe(false)
    expect(result.status).toBe('idle')
    expect(result.runId).toBeNull()
    expect(result.runStatus).toBe('completed')
  })

  it('ignores corrupted or incomplete stored run snapshots', async () => {
    storage.set(storageKey, '{not json')
    options = { agentId: 'agent-1', conversationId: 'conversation-1' }
    renderHookHarness()
    runEffects()
    await flush()

    expect(getRunStatus).not.toHaveBeenCalled()
    expect(result.status).toBe('idle')

    storage.set(storageKey, JSON.stringify({ runId: 7, lastSequence: 1 }))
    result.reconnect()
    await flush()

    expect(getRunStatus).not.toHaveBeenCalled()
  })

  it('reports version switch failures without mutating the conversation', async () => {
    const messageId = '22222222-2222-2222-2222-222222222222'
    const logged = mock()
    const originalError = console.error
    console.error = logged as unknown as typeof console.error
    try {
      options = {
        agentId: 'agent-1',
        initialMessages: [
          { id: messageId, role: 'assistant', parts: [{ type: 'text', text: 'stale answer' }], createdAt: new Date() },
        ],
      }
      renderHookHarness()
      getMessageVersions.mockRejectedValue(new Error('versions unavailable'))

      await result.switchVersion(messageId, 0)
      await flush()

      expect(switchMessageVersion).not.toHaveBeenCalled()
      expect(logged).toHaveBeenCalledWith('Failed to switch version:', new Error('versions unavailable'))
      expect(result.messages[0].parts).toEqual([{ type: 'text', text: 'stale answer' }])

      getMessageVersions.mockResolvedValue([{ id: 'version-1' }, { id: 'version-2' }])
      switchMessageVersion.mockRejectedValue(new Error('switch unavailable'))

      await result.switchVersion(messageId, 1)
      await flush()

      expect(switchMessageVersion).toHaveBeenCalledWith('agent-1', messageId, 'version-2')
      expect(getConversation).not.toHaveBeenCalled()
      expect(result.messages[0].parts).toEqual([{ type: 'text', text: 'stale answer' }])

      await result.switchVersion('unknown-message', 0)
      expect(getMessageVersions).toHaveBeenCalledTimes(2)
    } finally {
      console.error = originalError
    }
  })

  it('refuses edit and regenerate actions that target the wrong message or an active run', async () => {
    const userId = '11111111-1111-1111-1111-111111111111'
    const assistantId = '22222222-2222-2222-2222-222222222222'
    options = {
      agentId: 'agent-1',
      initialMessages: [
        { id: 'assistant-unsaved', role: 'assistant', parts: [{ type: 'text', text: 'streamed' }], createdAt: new Date() },
        { id: userId, role: 'user', parts: [{ type: 'text', text: 'question' }], createdAt: new Date() },
        { id: assistantId, role: 'assistant', parts: [{ type: 'text', text: 'stale answer' }], createdAt: new Date() },
      ],
    }
    renderHookHarness()

    await result.regenerate('assistant-unsaved')
    await result.regenerate(userId)
    await result.regenerate('unknown-message-id')
    await result.editMessage(assistantId, 'rewritten')
    await result.editMessage('user-unsaved', 'rewritten')

    expect(editMessageStream).not.toHaveBeenCalled()
    expect(regenerateStream).not.toHaveBeenCalled()
    expect(chatStream).not.toHaveBeenCalled()

    streamEvents = [deferred<StreamEvent>().promise]
    const sending = result.sendMessage('active run')
    await flush()

    await result.editMessage(userId, 'blocked')
    await result.regenerate(assistantId)
    await result.editMessage(assistantId, 'blocked')
    await result.regenerate('33333333-3333-3333-3333-333333333333')
    await result.switchVersion(assistantId, 0)

    expect(editMessageStream).not.toHaveBeenCalled()
    expect(regenerateStream).not.toHaveBeenCalled()
    expect(getMessageVersions).not.toHaveBeenCalled()

    result.reset()
    void sending
  })

  it('rejects answers when no run is waiting, the question is stale, or answering is unavailable', async () => {
    renderHookHarness()
    await expect(result.submitAskUser('call-ask', { answers: {}, skipped: true }))
      .rejects.toThrow('No active run to answer')

    const release = deferred<StreamEvent>()
    options = { agentId: 'agent-1', api: customApi({ postRunAnswer: undefined }) }
    renderHookHarness()
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      runEvent(3, 'tool_call', { tool_call_id: 'call-ask', tool_name: 'ask_user', arguments: { questions: [] } }),
      runEvent(4, 'run_status', { status: 'waiting', pending_tool_call_id: 'call-ask', pending_tool_name: 'ask_user', pending_tool_input: { questions: [] } }),
      release.promise,
    ]

    const sending = result.sendMessage('deploy')
    for (let attempt = 0; attempt < 20 && result.pendingAskUserToolCallId !== 'call-ask'; attempt += 1) await flush()
    expect(result.runStatus).toBe('waiting')

    await expect(result.submitAskUser('other-call', { answers: {}, skipped: true }))
      .rejects.toThrow('This question is no longer awaiting an answer')
    await expect(result.submitAskUser('call-ask', { answers: {}, skipped: true }))
      .rejects.toThrow('Answer submission is not available')
    expect(postRunAnswer).not.toHaveBeenCalled()

    const messageCount = result.messages.length
    await result.sendMessage('second question')
    expect(chatStream).toHaveBeenCalledTimes(1)
    expect(result.messages).toHaveLength(messageCount)

    release.resolve(runEvent(5, 'run_end', { status: 'completed', message_id: 'assistant-1' }))
    await sending
  })

  it('surfaces an answer submission failure and keeps the question pending', async () => {
    const onError = mock()
    const release = deferred<StreamEvent>()
    options = { agentId: 'agent-1', onError }
    renderHookHarness()
    streamEvents = [
      runEvent(1, 'run_start', { status: 'running', run_id: 'run-1' }),
      runEvent(2, 'message_start', { conversation_id: 'conversation-1', message_id: 'assistant-1' }),
      runEvent(3, 'tool_call', { tool_call_id: 'call-ask', tool_name: 'ask_user', arguments: { questions: [] } }),
      runEvent(4, 'run_status', { status: 'waiting', pending_tool_call_id: 'call-ask', pending_tool_name: 'ask_user', pending_tool_input: { questions: [] } }),
      release.promise,
    ]
    postRunAnswer.mockRejectedValue(new Error('answer rejected'))

    const sending = result.sendMessage('deploy')
    for (let attempt = 0; attempt < 20 && result.pendingAskUserToolCallId !== 'call-ask'; attempt += 1) await flush()

    await expect(result.submitAskUser('call-ask', { answers: {}, skipped: true }))
      .rejects.toThrow('answer rejected')
    await flush()

    expect(postRunAnswer).toHaveBeenCalledWith('agent-1', 'run-1', {
      tool_call_id: 'call-ask',
      answers: {},
      skipped: true,
    })
    expect(onError).toHaveBeenCalledWith({ message: 'answer rejected' })
    expect(result.error).toEqual({ message: 'answer rejected' })
    expect(result.pendingAskUserToolCallId).toBe('call-ask')
    expect(result.runStatus).toBe('waiting')

    release.resolve(runEvent(5, 'run_end', { status: 'completed', message_id: 'assistant-1' }))
    await sending
  })

  it('rebuilds an in-flight assistant message from persisted parts on reconnect', async () => {
    const parts: MessagePart[] = [
      { type: 'user-instruction', content: 'earlier steer' },
      { type: 'text', text: 'existing answer' },
      { type: 'reasoning', text: 'existing reasoning', state: 'done', duration: 12 },
      { type: 'task', taskType: 'rag', state: 'completed', info: 2 },
      { type: 'tool-call', toolCallId: 'tool-1', toolName: 'lookup', input: { q: 'x' }, state: 'done' },
      { type: 'tool-result', toolCallId: 'tool-1', toolName: 'lookup', output: { ok: true }, isError: false },
      { type: 'mcp-tool-call', toolCallId: 'mcp-1', serverName: 'server', toolName: 'fetch', input: {}, state: 'running' },
      { type: 'mcp-tool-result', toolCallId: 'mcp-1', serverName: 'server', toolName: 'fetch', output: 'done' },
      { type: 'source-document', documentId: 'doc-1', documentName: 'Doc', content: 'ctx' },
      { type: 'source-url', url: 'https://example.test/source', title: 'Source' },
      { type: 'media-result', output: { url: 'https://example.test/video.mp4' } },
      { type: 'truncated' },
      { type: 'iteration-cap-reached' },
    ]
    const questions = { questions: [{ id: 'target', question: 'Where?', required: true }] }
    const never = deferred<Response>()
    streamRun.mockReturnValue({ stream: never.promise, abort: mock() })
    storage.set(storageKey, JSON.stringify({ runId: 'run-1', lastSequence: 3 }))
    getRunStatus.mockResolvedValue({
      id: 'run-1',
      status: 'waiting',
      canonical_message_id: 'msg-1',
      pending_tool_call_id: 'ask-ask',
      pending_tool_name: 'ask_user',
      pending_tool_input: questions,
    })
    options = {
      agentId: 'agent-1',
      conversationId: 'conversation-1',
      initialMessages: [{ id: 'msg-1', role: 'assistant', parts, createdAt: new Date(), metadata: { isLoading: true } }],
    }
    renderHookHarness()

    runEffects()
    await waitFor(() => result.pendingAskUserToolCallId === 'ask-ask')

    expect(getRunStatus).toHaveBeenCalledWith('agent-1', 'run-1')
    expect(result.status).toBe('idle')
    expect(result.runStatus).toBe('waiting')
    expect(result.messages).toHaveLength(1)
    const hydrated = result.messages[0]
    expect(hydrated.id).toBe('msg-1')
    expect(hydrated.parts).toContainEqual({ type: 'text', text: 'existing answer', state: 'streaming' })
    expect(hydrated.parts).toContainEqual({ type: 'reasoning', text: 'existing reasoning', state: 'done', duration: 12 })
    expect(hydrated.parts).toContainEqual({ type: 'user-instruction', content: 'earlier steer' })
    expect(hydrated.parts).toContainEqual({
      type: 'tool-call', toolCallId: 'tool-1', toolName: 'lookup', input: { q: 'x' }, state: 'done',
    })
    expect(hydrated.parts).toContainEqual({
      type: 'tool-result', toolCallId: 'tool-1', toolName: 'lookup', output: { ok: true }, isError: false,
    })
    expect(hydrated.parts).toContainEqual(expect.objectContaining({ type: 'mcp-tool-call', toolCallId: 'mcp-1', state: 'done' }))
    expect(hydrated.parts).toContainEqual(expect.objectContaining({ type: 'mcp-tool-result', toolCallId: 'mcp-1', output: 'done' }))
    expect(hydrated.parts).toContainEqual(expect.objectContaining({ type: 'media-result', output: { url: 'https://example.test/video.mp4' } }))
    expect(hydrated.parts).toContainEqual({ type: 'truncated' })
    expect(hydrated.parts).toContainEqual({ type: 'iteration-cap-reached' })
    expect(hydrated.parts).toContainEqual(expect.objectContaining({ type: 'task', taskType: 'rag', state: 'completed' }))
    expect(hydrated.parts).toContainEqual({
      type: 'tool-call',
      toolCallId: 'ask-ask',
      toolName: 'ask_user',
      toolDisplayName: 'ask_user',
      input: questions,
      state: 'pending',
    })
  })
})
