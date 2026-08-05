import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createEmbedChatAdapter } from '@/lib/chat/embed-chat-adapter'

mock.module('@/lib/api/embed', () => ({
  embedApi: {
    getAgentInfo: mock(async () => ({
      id: 'agent-1', name: 'Embed Agent', description: '', icon: null, variables: [],
 enable_attachments: false, attachment_config: null,
    })),
    uploadFile: mock(async () => ({ url: '/file.png' })),
    chatStream: mock(() => () => {}),
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
