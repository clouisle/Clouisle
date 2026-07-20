import { beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'

let states: unknown[] = []
let refs: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
let effects: Array<() => void | (() => void)> = []

const abortEmbed = mock(() => {})
const chatStream = mock(() => ({ stream: Promise.resolve(okResponse), abort: abortEmbed }))
let sseEvents: Array<{ event: string; data: Record<string, unknown> }> = []
const parseSSEStream = mock(async function* () {
  for (const event of sseEvents) yield event
})

const okResponse = { ok: true, status: 200, json: async () => ({}) }

mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (states.length <= index) states[index] = initial
    return [states[index], (value: unknown) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: unknown) => unknown)(states[index])
        : value
    }]
  },
  useRef: (initial: unknown) => {
    const index = refIndex++
    if (!refs[index]) refs[index] = { current: initial }
    return refs[index]
  },
  useCallback: (callback: unknown) => callback,
  useEffect: (callback: () => void | (() => void)) => {
    effects.push(callback)
  },
}))

mock.module('next-intl', () => ({ useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}` }))
mock.module('@/lib/api/embed', () => ({ embedApi: { chatStream } }))
mock.module('@/lib/api/agents', () => ({ parseSSEStream }))
mock.module('@/lib/api/client', () => ({ getErrorMessage: (key: string) => `api.${key}` }))
mock.module('@/lib/utils/tool-result', () => ({ parseToolResultOutput: (value: unknown) => value }))

type Hook = typeof import('./use-embed-chat').useEmbedChat
let useEmbedChat: Hook

function Render(options: Parameters<Hook>[0]) {
  const hook = useEmbedChat(options)
  for (const effect of effects) effect()
  return hook
}

function render(options: Parameters<Hook>[0]) {
  stateIndex = 0
  refIndex = 0
  effects = []
  return Render(options)
}

beforeAll(async () => {
  ({ useEmbedChat } = await import('./use-embed-chat'))
})

beforeEach(() => {
  states = []
  refs = []
  stateIndex = 0
  refIndex = 0
  effects = []
  sseEvents = []
  abortEmbed.mockClear()
  chatStream.mockClear()
  parseSSEStream.mockClear()
  chatStream.mockImplementation(() => ({ stream: Promise.resolve(okResponse), abort: abortEmbed }))
})

describe('useEmbedChat runtime streaming', () => {
  test('streams embed messages without leaking the API key into message state', async () => {
    const onConversationChange = mock(() => {})
    sseEvents = [
      { event: 'message_start', data: { conversation_id: 'conv-embed', message_id: 'embed-msg' } },
      { event: 'content_delta', data: { delta: 'Before <user_input_request><question>Pick one?</question><options><option>A</option><option>B</option></options></user_input_request> after' } },
      { event: 'tool_call', data: { tool_call_id: 'tool-1', tool_name: 'lookup', arguments: { q: 'x' } } },
      { event: 'tool_result', data: { tool_call_id: 'tool-1', tool_name: 'lookup', result: { found: true } } },
      { event: 'output_truncated', data: {} },
      { event: 'iteration_cap_reached', data: { content: ' capped' } },
      { event: 'message_end', data: { usage: { total_tokens: 9 } } },
    ]

    let hook = render({ agentId: 'agent-1', apiKey: 'embed-secret', variables: { public: true }, onConversationChange })
    await hook.sendMessage(' Hello ', [{ type: 'image_url', url: 'https://example.test/image.png' }], [{ filename: 'a.txt', url: 'https://example.test/a.txt', size: 10, mime_type: 'text/plain' }])
    hook = render({ agentId: 'agent-1', apiKey: 'embed-secret', variables: { public: true }, onConversationChange })

    expect(chatStream).toHaveBeenCalledWith('agent-1', {
      message: 'Hello',
      images: [{ type: 'image_url', url: 'https://example.test/image.png' }],
      file_urls: [{ filename: 'a.txt', url: 'https://example.test/a.txt', size: 10, mime_type: 'text/plain' }],
      conversation_id: null,
      variables: { public: true },
    }, 'embed-secret')
    expect(onConversationChange).toHaveBeenCalledWith('conv-embed')
    expect(hook.conversationId).toBe('conv-embed')
    expect(JSON.stringify(hook.messages)).not.toContain('embed-secret')
    expect(hook.messages[0].parts).toEqual([
      { type: 'text', text: 'Hello' },
      { type: 'image', url: 'https://example.test/image.png' },
      { type: 'file', filename: 'a.txt', size: 10 },
    ])
    expect(hook.messages[1].parts).toEqual([
      expect.objectContaining({ type: 'task', taskType: 'generating', state: 'completed' }),
      { type: 'text', text: 'Before  after', state: 'done' },
      expect.objectContaining({ type: 'user-input-request', question: 'Pick one?', options: ['A', 'B'] }),
      expect.objectContaining({ type: 'tool-call', toolCallId: 'tool-1', state: 'done' }),
      expect.objectContaining({ type: 'tool-result', toolCallId: 'tool-1', output: { found: true } }),
      { type: 'truncated' },
      { type: 'iteration-cap-reached' },
      { type: 'text', text: ' capped', state: 'done' },
    ])
  })

  test('handles http failures, abort stop, and reset to initial messages', async () => {
    const initialMessages = [{ id: 'initial', role: 'assistant' as const, parts: [{ type: 'text' as const, text: 'Welcome' }] }]
    const onError = mock(() => {})
    chatStream.mockImplementation(() => ({
      stream: Promise.resolve({ ok: false, status: 500, json: async () => ({}) }),
      abort: abortEmbed,
    }))

    let hook = render({ agentId: 'agent-1', apiKey: 'embed-secret', initialMessages, onError })
    await hook.sendMessage('fail')
    hook = render({ agentId: 'agent-1', apiKey: 'embed-secret', initialMessages, onError })

    expect(onError).toHaveBeenCalledWith({ message: 'errors.serverErrorDescription' })
    expect(hook.status).toBe('error')

    expect(abortEmbed).not.toHaveBeenCalled()
    hook.reset()
    hook = render({ agentId: 'agent-1', apiKey: 'embed-secret', initialMessages, onError })
    expect(hook.status).toBe('idle')
    expect(hook.messages).toEqual(initialMessages)
  })
})
