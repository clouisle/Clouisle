import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const abort = mock(() => {})
const chatStream = mock((): { stream: Promise<Response>; abort: () => void } => ({
  stream: Promise.resolve({ ok: true, status: 200 } as Response),
  abort,
}))
let events: Array<{ event: string; data: Record<string, unknown> }> = []
let waitForMoreEvents: Promise<void> | undefined
const parseSSEStream = mock(async function* () {
  for (const event of events) yield event
  if (waitForMoreEvents) await waitForMoreEvents
})
const cancelAnimationFrame = mock(() => {})

Object.assign(globalThis, {
  window: {
    requestAnimationFrame: mock(() => 7),
    cancelAnimationFrame,
  },
})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('@/lib/api/embed', () => ({ embedApi: { chatStream } }))
mock.module('@/lib/api/agents', () => ({ parseSSEStream }))
mock.module('@/lib/api/client', () => ({ getErrorMessage: (key: string) => key }))
mock.module('@/lib/utils/tool-result', () => ({ parseToolResultOutput: (value: unknown) => value }))
mock.module('@/components/chat', () => ({}))

const { useEmbedChat } = await import('./use-embed-chat')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
type HookValue = ReturnType<typeof useEmbedChat>
type HookOptions = Parameters<typeof useEmbedChat>[0]

let current: HookValue
let renderer: ReactTestRenderer | undefined

function Harness({ options, onRender }: { options: HookOptions; onRender: (value: HookValue) => void }) {
  onRender(useEmbedChat(options))
  return null
}

function renderHook(options: HookOptions) {
  act(() => {
    renderer = create(<Harness options={options} onRender={(value) => { current = value }} />)
  })
}

const initialMessage = {
  id: 'welcome',
  role: 'assistant' as const,
  parts: [{ type: 'text' as const, text: 'Welcome' }],
}

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  events = []
  waitForMoreEvents = undefined
  chatStream.mockReset()
  chatStream.mockImplementation(() => ({
    stream: Promise.resolve({ ok: true, status: 200 } as Response),
    abort,
  }))
  abort.mockClear()
  parseSSEStream.mockClear()
  cancelAnimationFrame.mockClear()
})

test('streams assistant content, tasks, tools, sources, and conversation metadata', async () => {
  const onConversationChange = mock(() => {})
  events = [
    { event: 'message_start', data: { conversation_id: 'conversation-1', message_id: 'assistant-1' } },
    { event: 'rag_start', data: {} },
    { event: 'rag_context', data: { contexts: [{ document_name: 'Guide', content: 'Source text', score: 0.9 }] } },
    { event: 'reasoning_start', data: {} },
    { event: 'reasoning_delta', data: { delta: 'checking' } },
    { event: 'reasoning_end', data: {} },
    { event: 'tool_call', data: { tool_name: 'lookup', tool_call_id: 'call-1', arguments: { q: 'answer' } } },
    { event: 'tool_result', data: { tool_name: 'lookup', tool_call_id: 'call-1', result: { answer: 42 } } },
    { event: 'content_delta', data: { delta: 'Final answer' } },
    { event: 'output_truncated', data: {} },
    { event: 'message_end', data: { usage: { total_tokens: 12 }, timing: { total_ms: 30 } } },
  ]
  renderHook({ agentId: 'agent-1', apiKey: 'embed-key', variables: { locale: 'en' }, onConversationChange })

  const images = [{ type: 'image', url: 'https://example.test/image.png' }]
  const files = [{ filename: 'guide.pdf', url: 'https://example.test/guide.pdf', size: 10, mime_type: 'application/pdf' }]
  await act(async () => current.sendMessage('  explain this  ', images, files))

  expect(chatStream).toHaveBeenCalledWith('agent-1', {
    message: 'explain this',
    images,
    file_urls: files,
    conversation_id: null,
    variables: { locale: 'en' },
  }, 'embed-key')
  expect(current.conversationId).toBe('conversation-1')
  expect(onConversationChange).toHaveBeenCalledWith('conversation-1')
  expect(current.status).toBe('idle')
  expect(current.messages[0].parts).toEqual([
    { type: 'text', text: 'explain this' },
    { type: 'image', url: 'https://example.test/image.png' },
    { type: 'file', filename: 'guide.pdf', size: 10 },
  ])

  const assistant = current.messages[1]
  expect(assistant.id).toBe('assistant-1')
  expect(assistant.parts).toEqual(expect.arrayContaining([
    { type: 'task', taskType: 'rag', state: 'completed', info: 1 },
    { type: 'task', taskType: 'generating', state: 'completed' },
    expect.objectContaining({ type: 'reasoning', text: 'checking', state: 'done' }),
    { type: 'tool-call', toolName: 'lookup', toolCallId: 'call-1', input: { q: 'answer' }, state: 'done' },
    { type: 'tool-result', toolName: 'lookup', toolCallId: 'call-1', output: { answer: 42 } },
    { type: 'text', text: 'Final answer', state: 'done' },
    { type: 'truncated' },
    expect.objectContaining({ type: 'source-document', documentName: 'Guide', content: 'Source text' }),
  ]))
  expect(assistant.metadata).toEqual({ usage: { total_tokens: 12 }, timing: { total_ms: 30 } })
})

test('reports HTTP and startup failures without parsing a stream', async () => {
  const onError = mock(() => {})
  chatStream.mockImplementationOnce(() => ({
    stream: Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: 'hidden' }) } as Response),
    abort,
  }))
  renderHook({ agentId: 'agent-1', apiKey: 'embed-key', onError })

  await act(async () => current.sendMessage('first'))
  expect(current.status).toBe('error')
  expect(onError).toHaveBeenLastCalledWith({ message: 'resourceNotFound' })
  expect(parseSSEStream).not.toHaveBeenCalled()

  chatStream.mockImplementationOnce(() => { throw new Error('stream unavailable') })
  await act(async () => current.sendMessage('second'))
  expect(onError).toHaveBeenLastCalledWith({ message: 'stream unavailable' })
  expect(current.messages.map(message => message.role)).toEqual(['user', 'user'])
})

test('ignores blank and concurrent sends at the request boundary', async () => {
  let resolveResponse!: (response: Response) => void
  chatStream.mockImplementationOnce(() => ({
    stream: new Promise<Response>(resolve => { resolveResponse = resolve }),
    abort,
  }))
  renderHook({ agentId: 'agent-1', apiKey: 'embed-key' })

  await act(async () => current.sendMessage('   '))
  expect(chatStream).not.toHaveBeenCalled()

  let pending!: Promise<void>
  act(() => { pending = current.sendMessage('first') })
  await act(async () => current.sendMessage('second'))
  expect(chatStream).toHaveBeenCalledTimes(1)
  expect(current.messages).toHaveLength(1)

  await act(async () => {
    resolveResponse({ ok: true, status: 200 } as Response)
    await pending
  })
})

test('stop and reset abort work, cancel queued flushes, and restore initial state', async () => {
  let releaseEvents!: () => void
  waitForMoreEvents = new Promise(resolve => { releaseEvents = resolve })
  events = [
    { event: 'message_start', data: { conversation_id: 'conversation-1', message_id: 'assistant-1' } },
    { event: 'content_delta', data: { delta: 'partial' } },
  ]
  renderHook({ agentId: 'agent-1', apiKey: 'embed-key', initialMessages: [initialMessage] })

  let pending!: Promise<void>
  act(() => { pending = current.sendMessage('question') })
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
  expect(current.status).toBe('streaming')

  act(() => current.stop())
  expect(abort).toHaveBeenCalledTimes(1)
  expect(cancelAnimationFrame).toHaveBeenCalledWith(7)
  expect(current.status).toBe('idle')
  expect(current.messages.at(-1)?.parts).toContainEqual({ type: 'text', text: 'partial', state: 'done' })

  act(() => current.reset())
  expect(current.messages).toEqual([initialMessage])
  expect(current.conversationId).toBeNull()

  await act(async () => {
    releaseEvents()
    await pending
  })
  expect(current.messages).toEqual([initialMessage])
})
