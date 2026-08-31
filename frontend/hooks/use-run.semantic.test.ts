import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ChatMessage } from '@/components/chat/types'

const sendMessage = mock(async () => {})
const start = mock(async () => {})
const stop = mock(() => {})
const reset = mock(() => {})
const regenerate = mock(async () => {})
const switchVersion = mock(async () => {})
const reconnect = mock(() => {})

let agentMessages: ChatMessage[] = []
let agentOptions: Record<string, unknown>
let workflowOptions: Record<string, unknown>

mock.module('react', () => ({ useMemo: (factory: () => unknown) => factory() }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('./use-chat', () => ({
  useChat: (options: Record<string, unknown>) => {
    agentOptions = options
    return {
      messages: agentMessages,
      isStreaming: true,
      isLoading: true,
      conversationId: 'conversation-1',
      runId: 'run-1',
      runStatus: 'running',
      sendMessage,
      stop,
      reset,
      reconnect,
      regenerate,
      switchVersion,
    }
  },
}))
mock.module('./use-workflow-run', () => ({
  useWorkflowRun: (options: Record<string, unknown>) => {
    workflowOptions = options
    return {
      messages: [],
      executionState: { nodes: new Map(), progress: { current: 0, total: 0 } },
      isStreaming: false,
      runId: 'run-1',
      start,
      stop,
      reset,
    }
  },
}))

const { useRun } = await import('./use-run')

beforeEach(() => {
  agentMessages = []
  agentOptions = {}
  workflowOptions = {}
  sendMessage.mockClear()
  start.mockClear()
})

describe('useRun semantic delegation', () => {
  test('maps agent activity to execution nodes and delegates chat controls', () => {
    agentMessages = [{
      id: 'assistant-1',
      role: 'assistant',
      parts: [
        { type: 'reasoning', text: 'thinking', state: 'done', duration: 12 },
        { type: 'tool-call', toolCallId: 'tool-1', toolName: 'search', input: { q: 'docs' }, state: 'running' },
        { type: 'tool-result', toolCallId: 'tool-1', toolName: 'search', output: 'failed', isError: true },
        { type: 'task', taskType: 'rag', state: 'completed', info: 2 },
      ],
    }]

    const result = useRun({ id: 'agent-1', type: 'agent' })

    expect(agentOptions.agentId).toBe('agent-1')
    expect(workflowOptions.workflowId).toBe('')
    expect(result.sendMessage).toBe(sendMessage)
    expect(result.runId).toBe('run-1')
    expect(result.runStatus).toBe('running')
    expect(result.reconnect).toBe(reconnect)
    expect([...result.executionState!.nodes.values()]).toMatchObject([
      { type: 'reasoning', status: 'completed', output: 'thinking' },
      { id: 'tool-1', status: 'error', output: 'failed', error: 'failed' },
      { type: 'rag', label: 'searchingKnowledge', status: 'completed', metadata: { info: 2 } },
    ])
  })

  test('delegates workflow text as merged query input', async () => {
    const result = useRun({ id: 'workflow-1', type: 'workflow', variables: { locale: 'en' } })

    expect(agentOptions.agentId).toBe('')
    expect(workflowOptions.workflowId).toBe('workflow-1')
    expect(result.isLoading).toBe(false)
    expect(result.runId).toBe('run-1')

    await result.sendMessage('summarize')
    expect(start).toHaveBeenCalledWith({ query: 'summarize', locale: 'en' })
  })
})