import { beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'

let memoValues: unknown[] = []
let memoIndex = 0

const sendAgentMessage = mock(async () => {})
const stopAgent = mock(() => {})
const resetAgent = mock(() => {})
const regenerate = mock(async () => {})
const switchVersion = mock(async () => {})
const startWorkflow = mock(async () => {})
const stopWorkflow = mock(() => {})
const resetWorkflow = mock(() => {})

let agentMessages: Array<{ id: string; role: 'assistant'; parts: Array<Record<string, unknown>> }> = []
const workflowState = { nodes: new Map([['workflow-node', { id: 'workflow-node', status: 'running' }]]), progress: { current: 0, total: 1 } }

mock.module('react', () => ({
  useMemo: (callback: () => unknown) => {
    const index = memoIndex++
    memoValues[index] = callback()
    return memoValues[index]
  },
}))

mock.module('next-intl', () => ({ useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}` }))
mock.module('./use-chat', () => ({
  useChat: mock((options: Record<string, unknown>) => ({
    messages: agentMessages,
    isStreaming: true,
    isLoading: true,
    conversationId: options.conversationId || 'conv-1',
    sendMessage: sendAgentMessage,
    stop: stopAgent,
    reset: resetAgent,
    regenerate,
    switchVersion,
  })),
}))
mock.module('./use-workflow-run', () => ({
  useWorkflowRun: mock(() => ({
    messages: [{ id: 'workflow-msg', role: 'assistant', parts: [] }],
    executionState: workflowState,
    isStreaming: true,
    runId: 'run-1',
    start: startWorkflow,
    stop: stopWorkflow,
    reset: resetWorkflow,
  })),
}))

type Hook = typeof import('./use-run').useRun
let useRun: Hook

function Render(options: Parameters<Hook>[0]) {
  return useRun(options)
}

function render(options: Parameters<Hook>[0]) {
  memoIndex = 0
  return Render(options)
}

beforeAll(async () => {
  ({ useRun } = await import('./use-run'))
})

beforeEach(() => {
  memoValues = []
  memoIndex = 0
  agentMessages = []
  sendAgentMessage.mockClear()
  stopAgent.mockClear()
  resetAgent.mockClear()
  regenerate.mockClear()
  switchVersion.mockClear()
  startWorkflow.mockClear()
  stopWorkflow.mockClear()
  resetWorkflow.mockClear()
})

describe('useRun', () => {
  test('maps agent chat parts into execution nodes and exposes chat actions', async () => {
    agentMessages = [{
      id: 'assistant-1',
      role: 'assistant',
      parts: [
        { type: 'task', taskType: 'rag', state: 'running', info: 2 },
        { type: 'reasoning', text: 'think', state: 'done', duration: 5 },
        { type: 'tool-call', toolCallId: 'tool-1', toolName: 'search', toolDisplayName: 'Search', input: { q: 'x' }, state: 'running' },
        { type: 'tool-result', toolCallId: 'tool-1', output: 'boom', isError: true },
      ],
    }]

    const hook = render({ id: 'agent-1', type: 'agent', conversationId: 'conv-existing' })

    expect(hook.conversationId).toBe('conv-existing')
    expect(hook.isLoading).toBe(true)
    expect(hook.executionState?.progress).toEqual({ current: 3, total: 3 })
    expect(Array.from(hook.executionState?.nodes.values() || [])).toEqual([
      expect.objectContaining({ type: 'rag', label: 'chat.task.searchingKnowledge', status: 'running', metadata: { info: 2 } }),
      expect.objectContaining({ type: 'reasoning', label: 'agents.chat.messages.reasoning', status: 'completed', output: 'think', duration: 5 }),
      expect.objectContaining({ id: 'tool-1', label: 'Search', status: 'error', input: { q: 'x' }, output: 'boom', error: 'boom' }),
    ])

    await hook.sendMessage('hello')
    hook.stop()
    hook.reset()
    await hook.regenerate?.('assistant-1')
    await hook.switchVersion?.('assistant-1', 1)

    expect(sendAgentMessage).toHaveBeenCalledWith('hello')
    expect(stopAgent).toHaveBeenCalledTimes(1)
    expect(resetAgent).toHaveBeenCalledTimes(1)
    expect(regenerate).toHaveBeenCalledWith('assistant-1')
    expect(switchVersion).toHaveBeenCalledWith('assistant-1', 1)
  })

  test('delegates workflow runs and merges text with variables as query input', async () => {
    const hook = render({ id: 'workflow-1', type: 'workflow', variables: { locale: 'en' }, isDebug: true })

    await hook.sendMessage('run this')
    hook.stop()
    hook.reset()

    expect(hook.messages).toEqual([{ id: 'workflow-msg', role: 'assistant', parts: [] }])
    expect(hook.executionState).toBe(workflowState)
    expect(hook.runId).toBe('run-1')
    expect(hook.isLoading).toBe(false)
    expect(startWorkflow).toHaveBeenCalledWith({ query: 'run this', locale: 'en' })
    expect(stopWorkflow).toHaveBeenCalledTimes(1)
    expect(resetWorkflow).toHaveBeenCalledTimes(1)
  })
})
