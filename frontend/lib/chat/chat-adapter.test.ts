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
const startRun = mock(async () => ({ run_id: 'run-1', conversation_id: 'conv-1', user_message_id: 'user-1', status: 'queued', stream_url: '/stream' }))
const streamRun = mock(() => ({ stream: Promise.resolve(new Response()), abort: mock() }))
const postRunAnswer = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'queued' }))
const getRunStatus = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'waiting' as const, pending_tool_call_id: 'call-ask' }))
const getRunEvents = mock(async () => [])
const postRunInput = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'running' as const }))
const stopRun = mock(async () => ({ id: 'run-1', agent_id: 'agent-1', conversation_id: 'conv-1', mode: 'send', status: 'stopping' as const }))

mock.module('@/lib/api', () => ({
  publicAgentsApi: { getPublicAgent, getConversations, getConversation, deleteConversation, updateConversation, chatStream, getRunStatus, getRunEvents, postRunInput, stopRun },
  agentsApi: { editMessageStream, regenerateStream, getMessageVersions, switchMessageVersion, startRun, streamRun, getRunStatus, getRunEvents, postRunInput, postRunAnswer, stopRun },
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

  test('delegates durable run controls including structured answers', async () => {
    await defaultChatAdapter.startRun?.('agent-1', { message: 'hi' })
    expect(startRun).toHaveBeenCalledWith('agent-1', { message: 'hi' })
    defaultChatAdapter.streamRun?.('agent-1', 'run-1', 3)
    expect(streamRun).toHaveBeenCalledWith('agent-1', 'run-1', 3)
    await defaultChatAdapter.getRunStatus?.('agent-1', 'run-1')
    expect(getRunStatus).toHaveBeenCalledWith('agent-1', 'run-1')
    await defaultChatAdapter.getRunEvents?.('agent-1', 'run-1', 3)
    expect(getRunEvents).toHaveBeenCalledWith('agent-1', 'run-1', 3)
    await defaultChatAdapter.postRunInput?.('agent-1', 'run-1', { delivery: 'follow_up', content: 'continue' })
    expect(postRunInput).toHaveBeenCalledWith('agent-1', 'run-1', { delivery: 'follow_up', content: 'continue' })
    const answers = { deploy_to: 'cloud' }
    await defaultChatAdapter.postRunAnswer?.('agent-1', 'run-1', { tool_call_id: 'call-ask', answers })
    expect(postRunAnswer).toHaveBeenCalledWith('agent-1', 'run-1', { tool_call_id: 'call-ask', answers })
    await defaultChatAdapter.stopRun?.('agent-1', 'run-1')
    expect(stopRun).toHaveBeenCalledWith('agent-1', 'run-1')
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
