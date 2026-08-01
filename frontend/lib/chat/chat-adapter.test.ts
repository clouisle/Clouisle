import { describe, expect, mock, test } from 'bun:test'
import { defaultChatAdapter } from '@/lib/chat/chat-adapter'

const getPublicAgent = mock(async (id: string) => ({ id, name: 'Agent' }))
const getConversations = mock(async () => ({ items: [], total: 0 }))
const getConversation = mock(async () => ({ messages: [] }))
const deleteConversation = mock(async () => {})
const updateConversation = mock(async () => {})
const uploadFileWithProgress = mock(async () => ({ url: '/file.png' }))
const chatStream = mock(() => () => {})
const editMessageStream = mock(() => () => {})
const regenerateStream = mock(() => () => {})
const getMessageVersions = mock(async () => [])
const switchMessageVersion = mock(async () => {})

mock.module('@/lib/api', () => ({
  publicAgentsApi: { getPublicAgent, getConversations, getConversation, deleteConversation, updateConversation, chatStream },
  agentsApi: { editMessageStream, regenerateStream, getMessageVersions, switchMessageVersion },
  uploadApi: { uploadFileWithProgress },
}))
mock.module('@/lib/api/upload', () => ({ uploadApi: { uploadFileWithProgress } }))

describe('defaultChatAdapter', () => {
  test('delegates agent and conversation methods to the API', async () => {
    const agent = await defaultChatAdapter.getAgent('agent-1')
    expect(getPublicAgent).toHaveBeenCalledWith('agent-1')
    expect(agent.name).toBe('Agent')

    await defaultChatAdapter.getConversations('agent-1', { page: 1, pageSize: 10 })
    expect(getConversations).toHaveBeenCalledWith('agent-1', { page: 1, pageSize: 10 })

    const conv = await defaultChatAdapter.getConversation('conv-1')
    expect(getConversation).toHaveBeenCalledWith('conv-1')
    expect(conv).toEqual({ messages: [] })
  })

  test('delegates mutation methods', async () => {
    await defaultChatAdapter.deleteConversation('conv-1')
    expect(deleteConversation).toHaveBeenCalledWith('conv-1')

    await defaultChatAdapter.updateConversation('conv-1', { title: 'New' })
    expect(updateConversation).toHaveBeenCalledWith('conv-1', { title: 'New' })

    const onProgress = mock(() => {})
    await defaultChatAdapter.uploadFile(new File(['x'], 'x.png'), 'document', onProgress)
    expect(uploadFileWithProgress).toHaveBeenCalled()

    const stop = defaultChatAdapter.chatStream('agent-1', { messages: [] })
    expect(typeof stop).toBe('function')

    const editStop = defaultChatAdapter.editMessageStream('agent-1', 'm1', 'text')
    expect(typeof editStop).toBe('function')

    const regenStop = defaultChatAdapter.regenerateStream('agent-1', 'm1', {})
    expect(typeof regenStop).toBe('function')

    expect(await defaultChatAdapter.getMessageVersions('agent-1', 'm1')).toEqual([])
    await defaultChatAdapter.switchMessageVersion('agent-1', 'm1', 'v1')
    expect(switchMessageVersion).toHaveBeenCalledWith('agent-1', 'm1', 'v1')
  })
})
