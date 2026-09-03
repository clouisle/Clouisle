import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createEmbedChatAdapter } from '@/lib/chat/embed-chat-adapter'
const startRun = mock(async () => ({ run_id: 'run-1', conversation_id: 'conv-1', user_message_id: 'user-1', status: 'queued', stream_url: '/stream' }))
const streamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const getRunStatus = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'running' }))
const getRunEvents = mock(async () => [])
const postRunInput = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'running' }))
const postRunAnswer = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'queued' }))
const stopRun = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'stopping' }))


mock.module('@/lib/api/embed', () => ({
  embedApi: {
    getAgentInfo: mock(async () => ({
      id: 'agent-1', name: 'Embed Agent', description: '', icon: null, variables: [],
      enable_attachments: false, attachment_config: null,
    })),
    uploadFile: mock(async () => ({ url: '/file.png' })),
    chatStream: mock(() => () => {}),
    startRun,
    streamRun,
    getRunStatus,
    getRunEvents,
    postRunInput,
    postRunAnswer,
    stopRun,
  },
}))


const store = new Map<string, string>()
;(globalThis as unknown as { localStorage: { getItem: (k: string) => string | null; setItem: (k: string, v: string) => void; removeItem: (k: string) => void } }).localStorage = {
  getItem: (key) => store.get(key) ?? null,
  setItem: (key, value) => { store.set(key, value) },
  removeItem: (key) => { store.delete(key) },
}

beforeEach(() => store.clear())

describe('createEmbedChatAdapter', () => {
  const adapter = createEmbedChatAdapter('agent-1', 'key-123')

  test('getAgent maps embed agent info onto PublicAgent', async () => {
    const agent = await adapter.getAgent('agent-1')
    expect(agent.id).toBe('agent-1')
    expect(agent.name).toBe('Embed Agent')
  })

  test('saveConversation persists to localStorage and getConversations reads it back', async () => {
    adapter.saveConversation([{ id: "m1", role: "user", parts: [{ type: "text", text: "hi" }] } as never], undefined)
    const result = await adapter.getConversations('agent-1', { page: 1, pageSize: 10 })
    expect(result.total).toBe(1)
    expect(result.items[0].title).toBe('hi')
    expect(result.items[0].message_count).toBe(1)
  })

  test('getConversation retrieves saved messages', async () => {
    const messages = [{ id: "m1", role: "user", parts: [{ type: "text", text: "hello" }] }] as never[]
    adapter.saveConversation(messages, 'conv-1')
    const conv = await adapter.getConversation('conv-1')
    expect(conv.messages).toHaveLength(1)
  })

  test('getConversation throws when not found', async () => {
    await expect(adapter.getConversation('missing')).rejects.toThrow('Conversation not found')
  })

  test('deleteConversation removes the entry', async () => {
    adapter.saveConversation([{ id: "m1", role: "user", parts: [{ type: "text", text: "a" }] }] as never[], 'conv-1')
    await adapter.deleteConversation('conv-1')
    const result = await adapter.getConversations('agent-1', { page: 1, pageSize: 10 })
    expect(result.total).toBe(0)
  })

  test('updateConversation renames the title', async () => {
    adapter.saveConversation([{ id: "m1", role: "user", parts: [{ type: "text", text: "old" }] }] as never[], 'conv-1')
    await adapter.updateConversation('conv-1', { title: 'new title' } as never)
    const result = await adapter.getConversations('agent-1', { page: 1, pageSize: 10 })
    expect(result.items[0].title).toBe('new title')
  })

  test('editMessageStream and regenerateStream are unsupported', () => {
    expect(() => adapter.editMessageStream('c1', {} as never)).toThrow('Not supported in embed mode')
    expect(() => adapter.regenerateStream('c1', {} as never)).toThrow('Not supported in embed mode')
  })

  test('getMessageVersions and switchMessageVersion are no-ops', async () => {
    expect(await adapter.getMessageVersions('c1', 'm1')).toEqual([])
    await expect(adapter.switchMessageVersion('c1', 'm1', 0)).resolves.toBeUndefined()
  })

  test('getConversations paginates', async () => {
    for (let i = 0; i < 5; i++) {
      adapter.saveConversation([{ id: `m${i}`, role: 'user', parts: [{ type: 'text', text: `msg${i}` }] }] as never, `conv-${i}`)
    }
    const page1 = await adapter.getConversations('agent-1', { page: 1, pageSize: 2 })
    const page2 = await adapter.getConversations('agent-1', { page: 2, pageSize: 2 })
    expect(page1.items).toHaveLength(2)
    expect(page2.items).toHaveLength(2)
    expect(page1.items[0].id).not.toBe(page2.items[0].id)
  })

  test('exposes durable run controls with the embed API key', async () => {
    await expect(adapter.startRun?.('agent-1', { message: 'hello' })).resolves.toMatchObject({ run_id: 'run-1' })
    expect(startRun).toHaveBeenCalledWith('agent-1', { message: 'hello' }, 'key-123')

    adapter.streamRun?.('agent-1', 'run-1', 4)
    expect(streamRun).toHaveBeenCalledWith('agent-1', 'run-1', 'key-123', 4)
    await expect(adapter.getRunStatus?.('agent-1', 'run-1')).resolves.toMatchObject({ status: 'running' })
    await expect(adapter.getRunEvents?.('agent-1', 'run-1', 4)).resolves.toEqual([])
    await expect(adapter.postRunInput?.('agent-1', 'run-1', { delivery: 'steer', content: 'focus' })).resolves.toMatchObject({ status: 'running' })
    const answers = { deploy_to: 'cloud' }
    await expect(adapter.postRunAnswer?.('agent-1', 'run-1', { tool_call_id: 'call-ask', answers })).resolves.toMatchObject({ status: 'queued' })
    expect(postRunAnswer).toHaveBeenCalledWith('agent-1', 'run-1', { tool_call_id: 'call-ask', answers }, 'key-123')
    await expect(adapter.stopRun?.('agent-1', 'run-1')).resolves.toMatchObject({ status: 'stopping' })
  })

  test('normalizes agent variables into variable definitions', async () => {
    mock.module('@/lib/api/embed', () => ({
      embedApi: {
        getAgentInfo: mock(async () => ({
          id: 'agent-1', name: 'Embed Agent', description: '', icon: null,
          variables: [
            { name: 'query', label: 'Query', type: 'string', required: true, default_value: 'hello', description: 'Prompt', hidden: false },
          ],
 enable_attachments: false, attachment_config: null,
        })),
        uploadFile: mock(async () => ({ url: '/file.png' })),
        chatStream: mock(() => () => {}),
      },
    }))
    const agent = await adapter.getAgent('agent-1')
    expect(agent.variables).toHaveLength(1)
    expect(agent.variables[0].name).toBe('query')
  })

  test('uploadFile forwards progress callbacks', () => {
    const onProgress = mock(() => {})
    adapter.uploadFile(new File(['x'], 'x.png'), 'document', onProgress)
    expect(onProgress).toBeDefined()
  })

  test('saveConversation derives title from non-user messages', () => {
    adapter.saveConversation([{ id: 'm1', role: 'assistant', parts: [{ type: 'text', text: 'answer' }] }] as never, 'conv-1')
    adapter.saveConversation([{ id: 'm2', role: 'user', parts: [{ type: 'tool', toolCallId: 't1' }] }] as never, 'conv-2')
  })

  test('saveConversation updates an existing conversation title and messages', () => {
    adapter.saveConversation([{ id: 'm1', role: 'user', parts: [{ type: 'text', text: 'first' }] }] as never, 'conv-1')
    adapter.saveConversation([{ id: 'm2', role: 'user', parts: [{ type: 'text', text: 'second' }] }] as never, 'conv-1')
  })
})
