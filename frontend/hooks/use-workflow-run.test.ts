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
  useMemo: (factory: () => unknown) => factory(),
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

function Render(options: Parameters<Hook>[0]) {
  return useWorkflowRun(options)
}

function render(options: Parameters<Hook>[0]) {
  stateIndex = 0
  refIndex = 0
  return Render(options)
}

function emit(type: string, data: Record<string, unknown> = {}, sequence = 1) {
  streamOptions.onEvent?.({ type, data, sequence, timestamp: '2026-01-01' } as WorkflowEvent)
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

  test('enters waiting state and reconnects after pause submission', async () => {
    const options = { workflowId: 'workflow-1' }
    let hook = render(options)

    await hook.start({ value: 1 })
    emit('node_start', { node_id: 'pause-1', node_type: 'pause', node_label: 'Approval' }, 1)
    emit('workflow_waiting', { node_id: 'pause-1' }, 2)
    hook = render(options)

    expect(hook.status).toBe('waiting')
    expect(hook.isStreaming).toBe(false)

    hook.resume()
    hook = render(options)

    expect(closeConnection).toHaveBeenCalledOnce()
    expect(streamWorkflowRun).toHaveBeenCalledTimes(2)
    expect(hook.status).toBe('pending')
    expect(hook.isStreaming).toBe(true)
    expect(streamWorkflowRun.mock.calls[1]?.[1]).toMatchObject({ fromSequence: 2 })

    emit('node_start', { node_id: 'pause-1', node_type: 'pause', node_label: 'Approval' }, 3)
    emit('node_complete', { node_id: 'pause-1', node_type: 'pause', outputs: { approved: true } }, 4)
    emit('workflow_complete', { outputs: { approved: true } }, 5)
    hook = render(options)

    const pauseCalls = hook.messages[0]?.parts.filter(
      (part) => part.type === 'tool-call' && part.toolCallId === 'pause-1',
    ) ?? []
    expect(pauseCalls).toHaveLength(1)
    hook = render(options)

    expect(hook.executionState.nodes.get('pause-1')).toMatchObject({
      status: 'completed',
      output: { approved: true },
    })
    expect(hook.status).toBe('success')
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

  test('falls back for empty, key-like, multiline, and non-string workflow errors', async () => {
    const options = { workflowId: 'workflow-1' }
    let hook = render(options)
    await hook.start({})

    for (const error of ['', 'errors.request_failed', 'line one\nline two', { detail: 'bad' }]) {
      emit('workflow_error', { error })
    }
    hook = render(options)

    expect(hook.messages.map((message) => message.parts[0])).toEqual([
      { type: 'text', text: 'Request failed' },
      { type: 'text', text: 'Request failed' },
      { type: 'text', text: 'Request failed' },
      { type: 'text', text: 'Request failed' },
    ])
  })

  test('handles skipped nodes, ignored output events, and answer tokens appended after a tool call', async () => {
    const options = { workflowId: 'workflow-1' }
    let hook = render(options)
    await hook.start({})

    emit('node_start', { node_id: 'tool', node_type: 'search', inputs: { query: 'x' } })
    emit('node_complete', { node_id: 'tool', node_type: 'search', outputs: 'ok', duration_ms: 1 })
    emit('node_start', { node_id: 'skip-me', node_type: 'filter' })
    emit('node_skip', { node_id: 'skip-me' })
    emit('node_start', { node_id: 'answer', node_type: 'answer' })
    emit('output', { text: 'ignored' })
    emit('token', { node_id: 'answer', token: 'visible' })
    hook = render(options)

    expect(hook.executionState.nodes.get('skip-me')?.status).toBe('skipped')
    expect(hook.messages[0].parts).toEqual([
      expect.objectContaining({ type: 'tool-call', toolCallId: 'tool', state: 'done' }),
      expect.objectContaining({ type: 'tool-result', output: 'ok' }),
      expect.objectContaining({ type: 'tool-call', toolCallId: 'skip-me', state: 'running' }),
      { type: 'text', text: 'visible', state: 'streaming' },
    ])
  })

  test('starts without a query message and stop without a run is a no-op', async () => {
    const options = { workflowId: 'workflow-1' }
    let hook = render(options)
    hook.stop()
    expect(closeConnection).not.toHaveBeenCalled()
    expect(cancelWorkflowRun).not.toHaveBeenCalled()

    await hook.start({ query: '', other: true })
    hook = render(options)

    expect(hook.messages).toEqual([])
    expect(runWorkflow).toHaveBeenCalledWith('workflow-1', { inputs: { query: '', other: true } })
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
