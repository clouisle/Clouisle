import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'

const runWorkflow = mock(() => Promise.resolve({ run_id: 'run-1', stream_url: '/stream' }))
const debugWorkflow = mock(() => Promise.resolve({ run_id: 'debug-1', stream_url: '/stream' }))
const cancelWorkflowRun = mock(() => Promise.resolve({ cancelled: true }))
const closeConnection = mock(() => {})
let streamOptions: {
  onEvent?: (event: WorkflowEvent) => void
  onError?: (error: Error) => void
  onComplete?: () => void
}
const streamWorkflowRun = mock((_runId: string, options: typeof streamOptions) => {
  streamOptions = options
  return closeConnection
})

let states: unknown[] = []
let refs: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0

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
}))

mock.module('@/lib/api/workflows', () => ({
  workflowsApi: { runWorkflow, debugWorkflow, cancelWorkflowRun, streamWorkflowRun },
}))
mock.module('@/lib/api/client', () => ({ getErrorMessage: () => 'Request failed' }))

type WorkflowEvent = {
  type: string
  data: Record<string, unknown>
  sequence: number
  timestamp: string
}
type Hook = typeof import('./use-workflow-run').useWorkflowRun
let useWorkflowRun: Hook

function render(options: Parameters<Hook>[0]) {
  stateIndex = 0
  refIndex = 0
  return useWorkflowRun(options)
}

function emit(type: string, data: Record<string, unknown> = {}) {
  streamOptions.onEvent?.({ type, data, sequence: 1, timestamp: '2026-01-01' } as WorkflowEvent)
}

beforeAll(async () => {
  ({ useWorkflowRun } = await import('./use-workflow-run'))
})

beforeEach(() => {
  states = []
  refs = []
  stateIndex = 0
  refIndex = 0
  streamOptions = {}
})

afterEach(() => {
  runWorkflow.mockClear()
  debugWorkflow.mockClear()
  cancelWorkflowRun.mockClear()
  streamWorkflowRun.mockClear()
  closeConnection.mockClear()
  runWorkflow.mockImplementation(() => Promise.resolve({ run_id: 'run-1', stream_url: '/stream' }))
  debugWorkflow.mockImplementation(() => Promise.resolve({ run_id: 'debug-1', stream_url: '/stream' }))
})

describe('useWorkflowRun', () => {
  test('starts a run and maps node and token events into execution and message state', async () => {
    const options = { workflowId: 'workflow-1' }
    let hook = render(options)

    await hook.start({ query: 'Explain this', extra: 7 })
    hook = render(options)

    expect(runWorkflow).toHaveBeenCalledWith('workflow-1', {
      inputs: { query: 'Explain this', extra: 7 },
    })
    expect(streamWorkflowRun).toHaveBeenCalledWith('run-1', expect.any(Object))
    expect(hook.runId).toBe('run-1')
    expect(hook.isStreaming).toBe(true)
    expect(hook.messages[0]).toMatchObject({ role: 'user', parts: [{ type: 'text', text: 'Explain this' }] })

    emit('workflow_start', { total_nodes: 2 })
    emit('node_start', { node_id: 'llm', node_type: 'llm', node_label: 'Think', inputs: { prompt: 'x' } })
    emit('token', { node_id: 'llm', token: 'hidden' })
    emit('node_complete', { node_id: 'llm', node_type: 'llm', outputs: { result: 'ok' }, duration_ms: 12 })
    emit('node_start', { node_id: 'answer', node_type: 'answer', node_label: 'Answer' })
    emit('token', { node_id: 'answer', token: 'Hello' })
    emit('token', { node_id: 'answer', token: ' world' })
    emit('node_complete', { node_id: 'answer', node_type: 'answer', outputs: {}, duration_ms: 3 })
    emit('workflow_complete')
    hook = render(options)

    expect(hook.executionState.progress).toEqual({ current: 2, total: 2 })
    expect(hook.executionState.nodes.get('llm')).toMatchObject({
      status: 'completed', duration: 12, output: { result: 'ok' }, metadata: { streamingContent: 'hidden' },
    })
    expect(hook.executionState.nodes.get('answer')?.status).toBe('completed')
    expect(hook.messages[1].parts).toEqual([
      expect.objectContaining({ type: 'tool-call', toolCallId: 'llm', state: 'done' }),
      expect.objectContaining({ type: 'tool-result', toolCallId: 'llm', output: { result: 'ok' }, isError: false }),
      { type: 'text', text: 'Hello world', state: 'done' },
    ])
    expect(hook.isStreaming).toBe(false)
  })

  test('uses debug execution and exposes stream failure and completion callbacks', async () => {
    const onError = mock(() => {})
    const onComplete = mock(() => {})
    const options = { workflowId: 'workflow-1', isDebug: true, onError, onComplete }
    let hook = render(options)

    await hook.start({ value: 1 })
    expect(debugWorkflow).toHaveBeenCalledWith('workflow-1', { inputs: { value: 1 } })
    expect(runWorkflow).not.toHaveBeenCalled()

    const streamError = new Error('stream failed')
    streamOptions.onError?.(streamError)
    hook = render(options)
    expect(hook.isStreaming).toBe(false)
    expect(onError).toHaveBeenCalledWith(streamError)

    streamOptions.onComplete?.()
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  test('surfaces safe event errors and replaces technical details with the API fallback', async () => {
    const options = { workflowId: 'workflow-1' }
    let hook = render(options)
    await hook.start({})

    emit('node_start', { node_id: 'tool', node_type: 'http', node_label: 'Fetch' })
    emit('node_error', { node_id: 'tool', error: 'HTTP 500 Exception' })
    emit('workflow_error', { error: 'Could not finish request' })
    hook = render(options)

    expect(hook.executionState.nodes.get('tool')).toMatchObject({ status: 'error', error: 'Request failed' })
    expect(hook.messages[0].parts).toEqual([
      expect.objectContaining({ type: 'tool-call', state: 'error' }),
      expect.objectContaining({ type: 'tool-result', output: 'Request failed', isError: true }),
    ])
    expect(hook.messages[1]).toMatchObject({ parts: [{ type: 'text', text: 'Could not finish request' }] })
    expect(hook.isStreaming).toBe(false)
  })

  test('cleans up active runs on stop and reset, and recovers from start failures', async () => {
    const onError = mock(() => {})
    const options = { workflowId: 'workflow-1', onError }
    let hook = render(options)
    await hook.start({ query: 'hello' })
    hook = render(options)

    hook.stop()
    expect(closeConnection).toHaveBeenCalledTimes(1)
    expect(cancelWorkflowRun).toHaveBeenCalledWith('run-1')

    hook.reset()
    hook = render(options)
    expect(hook.runId).toBeNull()
    expect(hook.messages).toEqual([])
    expect(hook.executionState.progress).toEqual({ current: 0, total: 0 })

    const failure = new Error('start failed')
    runWorkflow.mockRejectedValueOnce(failure)
    await hook.start({})
    hook = render(options)
    expect(hook.isStreaming).toBe(false)
    expect(onError).toHaveBeenCalledWith(failure)
    expect(streamWorkflowRun).toHaveBeenCalledTimes(1)
  })
})
