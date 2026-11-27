import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createEmbedChatAdapter } from '@/lib/chat/embed-chat-adapter'

const startRun = mock(async () => ({ run_id: 'run-1', conversation_id: 'conv-1', user_message_id: 'user-1', status: 'queued', stream_url: '/stream' }))
const streamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const getRunStatus = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'running' }))
const getRunEvents = mock(async () => [])
const postRunInput = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'running' }))
const postRunAnswer = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'queued' }))
const stopRun = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'stopping' }))

const agentInfo = {
  id: 'agent-1', name: 'Embed Agent', description: '', icon: null, variables: [],
  enable_attachments: false, attachment_config: null,
  enable_citations: false, hide_artifact_list: true,
}
const getAgentInfo = mock(async () => agentInfo)
const uploadFile = mock(async () => ({ url: '/file.png' }))
const chatStream = mock(() => () => {})

const serverConversation = {
  id: '11111111-1111-4111-8111-111111111111',
  title: 'Server chat',
  messages: [
    { id: 'm1', conversation_id: 'c1', role: 'user', content: 'hello from the server', created_at: '2026-01-01T00:00:00Z' },
    { id: 'm2', conversation_id: 'c1', role: 'assistant', content: 'server answer', created_at: '2026-01-01T00:00:01Z' },
  ],
  active_run_id: 'run-9',
}

const getConversations = mock(async () => ({
  items: [{
    id: serverConversation.id,
    agent_id: 'agent-1',
    title: serverConversation.title,
    message_count: 2,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:01Z',
  }],
  total: 1,
  page: 1,
  page_size: 20,
}))
const getConversation = mock(async () => serverConversation)
const renameConversation = mock(async () => ({ id: serverConversation.id, title: 'Renamed' }))
const deleteConversation = mock(async () => undefined)

mock.module('@/lib/api/embed', () => ({
  embedApi: {
    getAgentInfo,
    uploadFile,
    chatStream,
    startRun,
    streamRun,
    getRunStatus,
    getRunEvents,
    postRunInput,
    postRunAnswer,
    stopRun,
    getConversations,
    getConversation,
    renameConversation,
    deleteConversation,
  },
}))

/** Storage twin that also supports the key enumeration the purge needs. */
class MemoryStorage {
  private data = new Map<string, string>()

  get length() { return this.data.size }
  key(index: number) { return Array.from(this.data.keys())[index] ?? null }
  getItem(key: string) { return this.data.get(key) ?? null }
  setItem(key: string, value: string) { this.data.set(key, value) }
  removeItem(key: string) { this.data.delete(key) }
  clear() { this.data.clear() }
}

const storage = new MemoryStorage()
;(globalThis as unknown as { localStorage: MemoryStorage }).localStorage = storage

beforeEach(() => {
  storage.clear()
  getConversations.mockClear()
  getConversation.mockClear()
  renameConversation.mockClear()
  deleteConversation.mockClear()
})

describe('createEmbedChatAdapter', () => {
  const adapter = createEmbedChatAdapter('agent-1', 'key-123')

  test('getAgent maps embed agent info onto PublicAgent', async () => {
    const agent = await adapter.getAgent('agent-1')
    expect(agent.id).toBe('agent-1')
    expect(agent.name).toBe('Embed Agent')
    expect(agent.hide_artifact_list).toBe(true)
    expect(agent.enable_citations).toBe(false)
  })

  test('getConversations reads the key-scoped server list with pagination', async () => {
    const result = await adapter.getConversations('agent-1', { page: 2, pageSize: 5 })

    expect(getConversations).toHaveBeenCalledWith('agent-1', 'key-123', { page: 2, pageSize: 5 })
    expect(result.total).toBe(1)
    expect(result.items[0].title).toBe('Server chat')
  })

  test('getConversation converts server messages and reports the active run', async () => {
    const conversation = await adapter.getConversation(serverConversation.id)

    expect(getConversation).toHaveBeenCalledWith(serverConversation.id, 'key-123')
    expect(conversation.messages).toHaveLength(2)
    expect(conversation.messages[0].parts).toEqual([{ type: 'text', text: 'hello from the server', state: 'done' }])
    expect(conversation.activeRunId).toBe('run-9')
  })

  test('getConversation omits the active run when the server reports none', async () => {
    getConversation.mockImplementationOnce(async () => ({ ...serverConversation, active_run_id: null }))

    const conversation = await adapter.getConversation(serverConversation.id)
    expect(conversation.activeRunId).toBeNull()
  })

  test('deleteConversation removes the server conversation with the API key', async () => {
    await adapter.deleteConversation(serverConversation.id)
    expect(deleteConversation).toHaveBeenCalledWith('agent-1', serverConversation.id, 'key-123')
  })

  test('updateConversation renames on the server with the API key', async () => {
    await adapter.updateConversation(serverConversation.id, { title: 'Renamed' })
    expect(renameConversation).toHaveBeenCalledWith('agent-1', serverConversation.id, 'Renamed', 'key-123')
  })

  test('a second credential cannot list or open the first key history', async () => {
    const keyA = createEmbedChatAdapter('agent-1', 'key-a')
    const keyB = createEmbedChatAdapter('agent-1', 'key-b')

    // The first key still reads its own history from the server.
    expect((await keyA.getConversations('agent-1', { page: 1, pageSize: 20 })).total).toBe(1)
    expect((await keyA.getConversation(serverConversation.id)).messages).toHaveLength(2)

    // Stand-in for the server's answer to the second key: nothing belongs to it.
    getConversations.mockImplementationOnce(async () => ({ items: [], total: 0, page: 1, page_size: 20 }))
    getConversation.mockImplementationOnce(async () => {
      throw new Error('The requested resource could not be found')
    })

    expect((await keyB.getConversations('agent-1', { page: 1, pageSize: 20 })).items).toEqual([])
    expect(getConversations).toHaveBeenLastCalledWith('agent-1', 'key-b', { page: 1, pageSize: 20 })
    await expect(keyB.getConversation(serverConversation.id)).rejects.toThrow()
    expect(getConversation).toHaveBeenLastCalledWith(serverConversation.id, 'key-b')
  })

  test('purges the legacy browser cache instead of serving its content', async () => {
    const stale = JSON.stringify([
      { id: 'legacy-conv', title: 'key A private chat', createdAt: 1, messages: [{ id: 'old', role: 'user', parts: [{ type: 'text', text: 'leaked' }] }] },
    ])
    storage.setItem('clouisle:embed:history:agent:agent-1', stale)
    storage.setItem('clouisle:embed:history:agent:other-agent', stale)
    storage.setItem('clouisle:embed:runs:workflow:other-flow', stale)

    const fresh = createEmbedChatAdapter('agent-1', 'key-123')

    expect(storage.getItem('clouisle:embed:history:agent:agent-1')).toBeNull()
    expect(storage.getItem('clouisle:embed:history:agent:other-agent')).toBeNull()
    expect(storage.getItem('clouisle:embed:runs:workflow:other-flow')).toBeNull()
    expect(JSON.stringify(await fresh.getConversations('agent-1', { page: 1, pageSize: 20 }))).not.toContain('leaked')
  })

  test('never writes conversation content to browser storage', async () => {
    await adapter.getConversation(serverConversation.id)
    await adapter.getConversations('agent-1', { page: 1, pageSize: 20 })
    expect(storage.length).toBe(0)
  })

  test('saveConversation is not exposed: the server owns persistence', () => {
    expect(adapter.saveConversation).toBeUndefined()
  })

  test('editMessageStream and regenerateStream are unsupported', () => {
    expect(() => adapter.editMessageStream('c1', {} as never)).toThrow('Not supported in embed mode')
    expect(() => adapter.regenerateStream('c1', {} as never)).toThrow('Not supported in embed mode')
  })

  test('getMessageVersions and switchMessageVersion are no-ops', async () => {
    expect(await adapter.getMessageVersions('c1', 'm1')).toEqual([])
    await expect(adapter.switchMessageVersion('c1', 'm1', 0)).resolves.toBeUndefined()
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
    getAgentInfo.mockImplementationOnce(async () => ({
      ...agentInfo,
      variables: [
        { name: 'query', label: 'Query', type: 'string', required: true, default_value: 'hello', description: 'Prompt', hidden: false },
      ],
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
})
