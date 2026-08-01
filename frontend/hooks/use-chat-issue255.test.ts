/* eslint-disable react-hooks/rules-of-hooks */
import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Chat = ReturnType<typeof import('./use-chat').useChat>
type Message = Chat['messages'][number]
type Event = { event: string; data: unknown }

let states: unknown[] = []
let refs: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
let streamEvents: Event[] = []

const chatStream = mock()
const regenerateStream = mock()
const editMessageStream = mock()
const getConversation = mock()
const agentsApi = {
  chatStream,
  regenerateStream,
  editMessageStream,
  getConversation,
  getMessageVersions: mock(),
  switchMessageVersion: mock(),
}

mock.module('react', () => ({
  useCallback: <T>(callback: T) => callback,
  useMemo: <T>(factory: () => T) => factory(),
  useRef: <T>(initial: T) => refs[refIndex++] ??= { current: initial },
  useState: <T>(initial: T) => {
    const index = stateIndex++
    if (states[index] === undefined) states[index] = initial
    const setter = (value: T | ((previous: T) => T)) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(states[index] as T)
        : value
    }
    return [states[index] as T, setter] as const
  },
}))

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))

mock.module('@/lib/api', () => ({
  agentsApi,
  async *parseSSEStream() {
    for (const event of streamEvents) yield event
  },
}))

mock.module('@/lib/api/client', () => ({ getErrorMessage: (key: string) => `api.${key}` }))
mock.module('@/lib/utils/message-converter', () => ({ convertBackendMessages: (messages: Message[]) => messages }))
mock.module('@/lib/utils/tool-result', () => ({
  parseToolResultOutput: (output: unknown) => output,
  shouldDisplayMediaResultInBody: (output: { hidden?: boolean }) => !output.hidden,
}))

const { getErrorMsgKey, useChat } = await import('./use-chat')

function render(options: Parameters<typeof useChat>[0] = { agentId: 'agent-1' }) {
  stateIndex = 0
  refIndex = 0
  return useChat(options)
}

function ok() {
  return Promise.resolve(new Response())
}

function response(status: number) {
  return Promise.resolve(new Response('{}', { status }))
}

function setMessages(messages: Message[], options: Parameters<typeof useChat>[0] = { agentId: 'agent-1' }) {
  render(options).setMessages(messages)
  return render(options)
}

beforeEach(() => {
  states = []
  refs = []
  stateIndex = 0
  refIndex = 0
  streamEvents = []
  for (const fn of Object.values(agentsApi)) fn.mockReset()
  getConversation.mockResolvedValue({ messages: [] })
})

describe('useChat issue 255 branches', () => {
  test('finalizes batched send progress and ignores hidden media', async () => {
    const frames: FrameRequestCallback[] = []
    const originalWindow = globalThis.window
    const cancelAnimationFrame = mock()
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: {
        requestAnimationFrame: (callback: FrameRequestCallback) => {
          frames.push(callback)
          return frames.length
        },
        cancelAnimationFrame,
      },
    })
    streamEvents = [
      { event: 'rag_start', data: {} },
      { event: 'reasoning_start', data: {} },
      { event: 'reasoning_delta', data: { delta: 'thinking' } },
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'search', arguments: {} } },
      { event: 'media_result', data: { hidden: true } },
      { event: 'content_delta', data: { delta: 'answer' } },
      { event: 'message_end', data: {} },
    ]
    chatStream.mockReturnValue({ stream: ok(), abort: mock() })

    await render().sendMessage('question')
    const result = render()

    expect(cancelAnimationFrame).toHaveBeenCalled()
    expect(result.messages[1].parts).toContainEqual(expect.objectContaining({ type: 'reasoning', text: 'thinking' }))
    expect(result.messages[1].parts).toContainEqual(expect.objectContaining({ type: 'tool-call', state: 'done' }))
    expect(result.messages[1].parts).toContainEqual({ type: 'text', text: 'answer', state: 'done' })
    expect(result.messages[1].parts.some((part) => part.type === 'media-result')).toBe(false)

    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow })
  })

  test('maps send HTTP and transport failures to safe user-facing errors', async () => {
    const cases = [
      [401, 'auth.sessionExpired'],
      [404, 'errors.resourceNotFound'],
      [503, 'errors.serverErrorDescription'],
      [418, 'api.requestFailed'],
    ] as const

    for (const [status, errorMessage] of cases) {
      states = []
      refs = []
      const onError = mock()
      chatStream.mockReturnValue({ stream: response(status), abort: mock() })
      await render({ agentId: 'agent-1', onError }).sendMessage('question')
      expect(onError).toHaveBeenCalledWith({ message: errorMessage })
    }

    states = []
    refs = []
    const onError = mock()
    chatStream.mockReturnValue({ stream: Promise.reject(new Error('Failed to fetch')), abort: mock() })
    await render({ agentId: 'agent-1', onError }).sendMessage('question')
    expect(render({ agentId: 'agent-1', onError }).messages[1].metadata?.errorMessage).toBe('errors.networkError')
  })

  test('maps streamed error families and preserves recovery progress', async () => {
    const cases = [
      [{ message: 'Timeout waiting' }, 'errors.timeout'],
      [{ code: 6100, message: 'missing' }, 'errors.modelNotFound'],
      [{ code: 6104, message: 'forbidden' }, 'errors.modelNotAuthorized'],
      [{ code: 2001, message: 'session' }, 'auth.sessionExpired'],
      [{ code: 404, message: 'missing' }, 'errors.resourceNotFound'],
      [{ code: 500, message: 'broken' }, 'errors.serverErrorDescription'],
      [{ message: 'model is not configured' }, 'errors.modelNotConfigured'],
      [{ message: 'A useful backend explanation' }, 'A useful backend explanation'],
      [{ message: 'internal.error_key' }, 'errors.unknown'],
    ]

    for (const [error, expected] of cases) {
      states = []
      refs = []
      streamEvents = [
        { event: 'content_delta', data: { delta: 'partial' } },
        { event: 'error', data: { code: error.code, msg: error.message } },
      ]
      chatStream.mockReturnValue({ stream: ok(), abort: mock() })
      await render().sendMessage('question')
      expect(render().messages[1].metadata?.errorMessage).toBe(expected)
      expect(render().messages[1].metadata?.preservedPartialProgress).toBe(true)
    }
  })

  test('stops after backend ID recovery and calls stream end once', async () => {
    let reject!: (error: Error) => void
    const blocked = new Promise<Event>((_, rejectPromise) => { reject = rejectPromise })
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const abort = mock(() => reject(abortError))
    const onStreamEnd = mock()
    streamEvents = [
      { event: 'message_start', data: { message_id: 'backend-message' } },
      { event: 'content_delta', data: { delta: 'recoverable' } },
    ]
    chatStream.mockReturnValue({ stream: ok(), abort })

    await render({ agentId: 'agent-1', onStreamEnd }).sendMessage('question')
    const result = render({ agentId: 'agent-1', onStreamEnd })
    result.stop()

    expect(result.messages[1].id).toBe('backend-message')
    expect(render({ agentId: 'agent-1', onStreamEnd }).status).toBe('idle')
    expect(onStreamEnd).toHaveBeenCalled()
    void blocked.catch(() => undefined)
  })

  test('covers regeneration reasoning, RAG, compression, markers, and recovery', async () => {
    const id = '22222222-2222-2222-2222-222222222222'
    const options = { agentId: 'agent-1', onError: mock(), onStreamEnd: mock() }
    setMessages([{ id, role: 'assistant', parts: [{ type: 'text', text: 'old' }] }] as Message[], options)
    streamEvents = [
      { event: 'message_start', data: { message_id: 'version-2', version_number: 2, version_count: 2 } },
      { event: 'rag_start', data: {} },
      { event: 'reasoning_start', data: {} },
      { event: 'reasoning_delta', data: { delta: 'reason' } },
      { event: 'reasoning_end', data: {} },
      { event: 'rag_context', data: { contexts: [{ document_id: 'doc', document_name: 'Doc', content: 'chunk', kb_id: 'kb', kb_name: 'KB', score: 1 }] } },
      { event: 'compression_start', data: {} },
      { event: 'compression_end', data: { before_tokens: 9, after_tokens: 4 } },
      { event: 'content_delta', data: { delta: '<user_input_request><question>Continue?</question><options><option>Yes</option><option>No</option></options></user_input_request>' } },
      { event: 'tool_call', data: { tool_call_id: 'a', tool_name: 'one', arguments: {} } },
      { event: 'tool_call', data: { tool_call_id: 'b', tool_name: 'two', arguments: {} } },
      { event: 'tool_result', data: { tool_call_id: 'a', tool_name: 'one', result: 'ok', is_error: false } },
      { event: 'tool_result', data: { tool_call_id: 'b', tool_name: 'two', result: 'bad', is_error: true } },
      { event: 'output_truncated', data: {} },
      { event: 'iteration_cap_reached', data: { content: 'limit' } },
      { event: 'message_end', data: {} },
    ]
    regenerateStream.mockReturnValue({ stream: ok(), abort: mock() })

    await render(options).regenerate(id)
    const parts = render(options).messages[0].parts

    expect(parts).toContainEqual(expect.objectContaining({ type: 'reasoning', text: 'reason', state: 'done' }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'source-document', documentId: 'doc' }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'user-input-request', question: 'Continue?' }))
    expect(parts).toContainEqual(expect.objectContaining({ type: 'tool-call', toolCallId: 'b', state: 'error' }))
    expect(parts).toContainEqual({ type: 'truncated' })
    expect(parts).toContainEqual({ type: 'iteration-cap-reached' })
  })

  test('recovers conversation after edit HTTP and transport errors', async () => {
    const id = '11111111-1111-1111-1111-111111111111'
    const recovered = [{ id, role: 'user', parts: [{ type: 'text', text: 'original' }] }] as Message[]
    const options = { agentId: 'agent-1', conversationId: 'conversation-1', onError: mock() }

    for (const failure of [response(503), Promise.reject(new Error('network unavailable'))]) {
      states = []
      refs = []
      render(options).setConversationId('conversation-1')
      setMessages(recovered, options)
      editMessageStream.mockReturnValue({ stream: failure, abort: mock() })
      getConversation.mockResolvedValue({ messages: recovered })
      await render(options).editMessage(id, 'edited')
      expect(getConversation).toHaveBeenCalledWith('conversation-1')
      expect(render(options).status).toBe('idle')
    }
  })

  test('recovers a saved regeneration after HTTP and transport failures', async () => {
    const id = '22222222-2222-2222-2222-222222222222'
    const options = { agentId: 'agent-1', onError: mock() }

    for (const failure of [response(503), Promise.reject(new Error('network unavailable'))]) {
      states = []
      refs = []
      setMessages([{ id, role: 'assistant', parts: [{ type: 'text', text: 'old' }] }] as Message[], options)
      regenerateStream.mockReturnValue({ stream: failure, abort: mock() })
      await render(options).regenerate(id)
      expect(render(options).status).toBe('idle')
      expect(render(options).messages[0].metadata).toMatchObject({ isLoading: false, isError: true })
    }
  })

  test('exposes stable public error keys', () => {
    expect(getErrorMsgKey({ message: 'ignored', msgKey: 'custom.key' })).toBe('custom.key')
    expect(getErrorMsgKey({ message: 'model_vision_not_supported' })).toBe('modelVisionNotSupported')
    expect(getErrorMsgKey({ code: 6100, message: '' })).toBe('modelNotFound')
    expect(getErrorMsgKey({ code: 6104, message: '' })).toBe('modelNotAuthorized')
    expect(getErrorMsgKey({ code: 6103, message: '' })).toBe('quotaExceeded')
    expect(getErrorMsgKey({ message: 'other' })).toBeUndefined()
  })
})
