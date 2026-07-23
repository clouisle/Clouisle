/* eslint-disable react-hooks/rules-of-hooks */
import { beforeEach, describe, expect, mock, test } from 'bun:test'

let stateIndex = 0
let states: unknown[] = []
let refs: unknown[] = []
let refIndex = 0

mock.module('react', () => ({
  useCallback: (fn: unknown) => fn,
  useRef: (initialValue: unknown) => refs[refIndex++] ??= { current: initialValue },
  useState: (initialValue: unknown) => {
    const index = stateIndex++
    if (states[index] === undefined) states[index] = initialValue
    const setState = (value: unknown) => {
      states[index] = typeof value === 'function' ? (value as (current: unknown) => unknown)(states[index]) : value
    }
    return [states[index], setState]
  },
}))

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('@/lib/api', () => ({
  agentsApi: {
    chatStream: mock(),
  },
  parseSSEStream: mock(),
}))

mock.module('@/lib/api/client', () => ({
  getErrorMessage: (error: unknown) => error instanceof Error ? error.message : 'api-error',
}))

mock.module('@/lib/utils/tool-result', () => ({
  parseToolResultOutput: (output: unknown) => output,
  shouldDisplayMediaResultInBody: () => true,
}))

const { agentsApi, parseSSEStream } = await import('@/lib/api')
const { useChat } = await import('./use-chat')

const chatStream = agentsApi.chatStream as ReturnType<typeof mock>
const parseStream = parseSSEStream as ReturnType<typeof mock>

function useRenderedChat(options: Parameters<typeof useChat>[0]) {
  stateIndex = 0
  refIndex = 0
  return useChat(options)
}

function rerender(options: Parameters<typeof useChat>[0]) {
  return useRenderedChat(options)
}

function resetHookStorage() {
  stateIndex = 0
  refIndex = 0
  states = []
  refs = []
}

function okResponse() {
  return { ok: true, json: async () => ({}) } as Response
}

async function* events(items: Array<{ event: string; data: unknown }>) {
  for (const item of items) yield item
}

describe('useChat', () => {
  beforeEach(() => {
    resetHookStorage()
    chatStream.mockReset()
    parseStream.mockReset()
  })

  test('sends trimmed text with attachments and stores streamed reply', async () => {
    const abort = mock()
    const onConversationChange = mock()
    const onStreamStart = mock()
    const onStreamEnd = mock()
    chatStream.mockReturnValue({ stream: Promise.resolve(okResponse()), abort })
    parseStream.mockReturnValue(events([
      { event: 'message_start', data: { conversation_id: 'conversation-2', message_id: 'assistant-db' } },
      { event: 'content_delta', data: { delta: 'Hello' } },
      { event: 'message_end', data: { version_number: 2, version_count: 3 } },
    ]))

    const options = {
      agentId: 'agent-1',
      conversationId: 'conversation-1',
      variables: { locale: 'en' },
      onConversationChange,
      onStreamStart,
      onStreamEnd,
    }
    await useRenderedChat(options).sendMessage(
      '  Hi  ',
      [{ type: 'image_url', url: 'https://example.test/image.png' }],
      [{ id: 'file-1', filename: 'notes.txt', size: 12 }]
    )
    const hook = rerender(options)

    expect(chatStream).toHaveBeenCalledWith('agent-1', {
      message: 'Hi',
      images: [{ type: 'image_url', url: 'https://example.test/image.png' }],
      file_urls: [{ id: 'file-1', filename: 'notes.txt', size: 12 }],
      conversation_id: 'conversation-1',
      variables: { locale: 'en' },
    })
    expect(onConversationChange).toHaveBeenCalledWith('conversation-2')
    expect(onStreamStart).toHaveBeenCalled()
    expect(onStreamEnd).toHaveBeenCalled()
    expect(hook.conversationId).toBe('conversation-2')
    expect(hook.status).toBe('idle')
    expect(hook.messages).toHaveLength(2)
    expect(hook.messages[0].parts).toMatchObject([
      { type: 'text', text: 'Hi' },
      { type: 'image', url: 'https://example.test/image.png' },
      { type: 'file', filename: 'notes.txt', size: 12 },
    ])
    expect(hook.messages[1]).toMatchObject({
      id: 'assistant-db',
      role: 'assistant',
      versionNumber: 2,
      versionCount: 3,
      metadata: { isLoading: false, isError: false },
    })
    expect(hook.messages[1].parts).toContainEqual({ type: 'text', text: 'Hello', state: 'done' })
  })

  test('ignores blank messages', async () => {
    await useRenderedChat({ agentId: 'agent-1' }).sendMessage('   ')

    expect(chatStream).not.toHaveBeenCalled()
    expect(rerender({ agentId: 'agent-1' }).messages).toEqual([])
  })

  test('marks streaming message as manually stopped', async () => {
    let rejectStream!: (error: Error) => void
    const abortError = new Error('aborted')
    abortError.name = 'AbortError'
    const abort = mock(() => rejectStream(abortError))
    chatStream.mockReturnValue({
      stream: new Promise<Response>((_, reject) => { rejectStream = reject }),
      abort,
    })
    parseStream.mockReturnValue(events([]))

    const options = { agentId: 'agent-1' }
    const sendPromise = useRenderedChat(options).sendMessage('stop me')
    const loadingHook = rerender(options)
    expect(loadingHook.status).toBe('loading')

    loadingHook.stop()
    await sendPromise
    const hook = rerender(options)

    expect(abort).toHaveBeenCalled()
    expect(hook.status).toBe('idle')
    expect(hook.messages[1].metadata).toMatchObject({
      isLoading: false,
      isManuallyStopped: true,
    })
    expect(hook.messages[1].parts.at(-1)).toMatchObject({ type: 'stopped' })
  })

  test('reset clears messages, conversation, and previous errors', async () => {
    chatStream.mockReturnValue({ stream: Promise.resolve({ ok: false, status: 429, json: async () => ({}) } as Response), abort: mock() })
    parseStream.mockReturnValue(events([]))
    const onError = mock()
    const options = { agentId: 'agent-1', conversationId: 'conversation-1', onError }

    await useRenderedChat(options).sendMessage('fail')
    expect(onError).toHaveBeenCalled()
    expect(rerender(options).messages[1].metadata?.isError).toBe(true)

    useRenderedChat(options).reset()
    const hook = rerender(options)

    expect(hook.messages).toEqual([])
    expect(hook.conversationId).toBeNull()
    expect(hook.error).toBeNull()
    expect(hook.status).toBe('idle')
  })
})
