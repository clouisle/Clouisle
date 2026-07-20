import { beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'

type StateSetter<T> = (value: T | ((previous: T) => T)) => void

type HookOptions = {
  agentId: string
  conversationId?: string
  onConversationChange?: (id: string) => void
  onError?: (error: { code?: number; message: string }) => void
  onStreamStart?: () => void
  onStreamEnd?: () => void
}

type HookResult = ReturnType<typeof import('./use-chat').useChat>

let stateSlots: unknown[] = []
let refSlots: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
let options: HookOptions
let result: HookResult
let useChat: typeof import('./use-chat').useChat
let agentsApi: typeof import('../lib/api').agentsApi
let renderScheduled = false

const chatStream = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))

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
  })
}

const reactHelpers = {
  createElement: () => null,
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
  ;({ agentsApi } = await import('../lib/api'))
  agentsApi.chatStream = chatStream as typeof agentsApi.chatStream
})

beforeEach(() => {
  stateSlots = []
  refSlots = []
  renderScheduled = false
  chatStream.mockReset()
  options = { agentId: 'agent-1' }
  renderHookHarness()
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

describe('useChat', () => {
  it('moves through loading and streaming before finalizing the conversation', async () => {
    const response = deferred<Response>()
    const releaseStream = deferred<void>()
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

    const encoder = new TextEncoder()
    response.resolve(new Response(new ReadableStream({
      async start(controller) {
        await releaseStream.promise
        for (const event of [
          { event: 'message_start', data: { conversation_id: 'conversation-1', message_id: 'message-1' } },
          { event: 'content_delta', data: { delta: 'Hi there' } },
          { event: 'message_end', data: { version_number: 2, version_count: 3 } },
        ]) {
          controller.enqueue(encoder.encode(`event: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`))
        }
        controller.close()
      },
    })))
    await flush()

    expect(result.status).toBe('streaming')
    expect(result.isStreaming).toBe(true)
    expect(onStreamStart).toHaveBeenCalledTimes(1)

    releaseStream.resolve()
    await sending

    expect(result.status).toBe('idle')
    expect(result.conversationId).toBe('conversation-1')
    expect(onConversationChange).toHaveBeenCalledWith('conversation-1')
    expect(onStreamEnd).toHaveBeenCalledTimes(1)
    expect(result.messages[1]).toMatchObject({
      id: 'message-1',
      versionNumber: 2,
      versionCount: 3,
      metadata: { isLoading: false, isError: false },
    })
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'Hi there', state: 'done' })
  })

  it('stops an active stream, aborts it, and preserves partial output as stopped', async () => {
    const blocked = deferred<void>()
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const abort = mock(() => blocked.reject(abortError))
    const onStreamEnd = mock()
    options = { agentId: 'agent-1', onStreamEnd }
    renderHookHarness()
    chatStream.mockReturnValue({
      stream: Promise.resolve(new Response(new ReadableStream({
        async start(controller) {
          const event = { event: 'content_delta', data: { delta: 'partial' } }
          controller.enqueue(new TextEncoder().encode(`event: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`))
          await blocked.promise
          controller.close()
        },
      }))),
      abort,
    })

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
    chatStream.mockReturnValue({
      stream: Promise.resolve(new Response(new ReadableStream({
        async start(controller) {
          await blocked.promise
          controller.close()
        },
      }))),
      abort,
    })

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
})
