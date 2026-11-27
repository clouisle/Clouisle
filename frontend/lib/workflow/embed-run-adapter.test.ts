import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createEmbedWorkflowRunAdapter } from '@/lib/workflow/embed-run-adapter'
import type { RunSnapshot } from '@/lib/workflow/run-adapter'
import { extractVariables } from '@/lib/utils/extract-variables'

const getWorkflowInfo = mock(async () => ({
  id: 'embed-1', name: 'Embed Flow', description: '', icon: null, variables: [], embed_config: {},
}))
const runWorkflow = mock(async () => ({ run_id: 'run-1' }))
const streamWorkflowRun = mock(() => () => {})

const serverRun = {
  id: 'run-1',
  workflow_id: 'embed-1',
  trigger_type: 'manual',
  is_debug: false,
  status: 'success',
  inputs: { query: 'hello' },
  outputs: { answer: 'ok' },
  created_at: '2026-01-01T00:00:00Z',
  total_nodes: 1,
  executed_nodes: 1,
}
const serverNodes = [
  { id: 'node-1', run_id: 'run-1', node_id: 'start', node_type: 'start', node_name: 'Start', execution_order: 0, status: 'success', outputs: null, retry_count: 0 },
]

const getWorkflowRuns = mock(async () => ({
  items: [serverRun],
  total: 1,
  page: 1,
  page_size: 20,
}))
const getWorkflowRun = mock(async () => serverRun)
const getWorkflowRunNodes = mock(async () => serverNodes)

mock.module('@/lib/api/embed', () => ({
  embedApi: {
    getWorkflowInfo,
    runWorkflow,
    streamWorkflowRun,
    getWorkflowRuns,
    getWorkflowRun,
    getWorkflowRunNodes,
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
  getWorkflowRuns.mockClear()
  getWorkflowRun.mockClear()
  getWorkflowRunNodes.mockClear()
})

const snapshot: RunSnapshot = {
  runId: 'run-1',
  status: 'success',
  outputs: { answer: 'ok' },
  nodes: [{ nodeType: 'start', outputs: null, order: 0, status: 'success' }],
  error: null,
  inputs: { query: 'hello' },
  createdAt: '2026-01-01T00:00:00Z',
}

describe('createEmbedWorkflowRunAdapter', () => {
  const apiKey = 'key-123'

  test('getWorkflow maps embed workflow info', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const workflow = await adapter.getWorkflow('embed-1')
    expect(workflow.id).toBe('embed-1')
    expect(workflow.name).toBe('Embed Flow')
    expect(workflow.status).toBe('published')
  })

  test('projects start-node parameters into the run form inputs', async () => {
    getWorkflowInfo.mockImplementationOnce(async () => ({
      id: 'embed-1',
      name: 'Embed Flow',
      description: '',
      icon: null,
      variables: [],
      embed_config: {},
      input_parameters: [
        { name: 'query', type: 'text', required: true },
        { name: 'limit', type: 'number', required: false, default: 5 },
      ],
    }))

    const workflow = await createEmbedWorkflowRunAdapter(apiKey).getWorkflow('embed-1')
    const inputs = extractVariables(workflow, 'workflow')

    expect(inputs.map((input) => input.name)).toEqual(['query', 'limit'])
    expect(inputs[0].required).toBe(true)
    expect(inputs[1].required).toBe(false)
    expect(inputs[1].default).toBe(5)
  })

  test('leaves the definition empty when the workflow takes no inputs', async () => {
    const workflow = await createEmbedWorkflowRunAdapter(apiKey).getWorkflow('embed-1')
    expect(extractVariables(workflow, 'workflow')).toEqual([])
  })

  test('createRunApi wires embed endpoints', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const api = adapter.createRunApi()
    await api.runWorkflow('embed-1', { inputs: { query: 'hi' } })
    const stop = api.streamWorkflowRun('run-1', { fromSequence: 7, onEvent: () => {}, onError: () => {}, onComplete: () => {} })
    expect(typeof stop).toBe('function')
    await expect(api.cancelWorkflowRun('run-1')).resolves.toBeUndefined()
  })

  test('loadHistory reads the key-scoped server run list', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const history = await adapter.loadHistory('embed-1')

    expect(getWorkflowRuns).toHaveBeenCalledWith('embed-1', apiKey, { pageSize: 20 })
    expect(history).toHaveLength(1)
    expect(history[0].id).toBe('run-1')
    expect(history[0].workflow_id).toBe('embed-1')
    expect(history[0].status).toBe('success')
  })

  test('loadHistoryPage forwards server pagination', async () => {
    getWorkflowRuns.mockImplementationOnce(async () => ({ items: [], total: 42, page: 3, page_size: 10 }))
    const adapter = createEmbedWorkflowRunAdapter(apiKey)

    const page = await adapter.loadHistoryPage?.('embed-1', { page: 3, pageSize: 10 })

    expect(getWorkflowRuns).toHaveBeenLastCalledWith('embed-1', apiKey, { page: 3, pageSize: 10 })
    expect(page).toEqual({ items: [], total: 42 })
  })

  test('loadRunDetail reconstructs run and node executions from the server', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const detail = await adapter.loadRunDetail('embed-1', 'run-1')

    expect(getWorkflowRun).toHaveBeenCalledWith('embed-1', 'run-1', apiKey)
    expect(getWorkflowRunNodes).toHaveBeenCalledWith('embed-1', 'run-1', apiKey)
    expect(detail.run.id).toBe('run-1')
    expect(detail.run.inputs).toEqual({ query: 'hello' })
    expect(detail.nodes).toHaveLength(1)
    expect(detail.nodes[0].node_type).toBe('start')
  })

  test('a second credential cannot read the first key run history', async () => {
    const keyA = createEmbedWorkflowRunAdapter('key-a')
    const keyB = createEmbedWorkflowRunAdapter('key-b')

    expect(await keyA.loadHistory('embed-1')).toHaveLength(1)

    // Stand-in for the server's answer to the second key: nothing belongs to it.
    getWorkflowRuns.mockImplementationOnce(async () => ({ items: [], total: 0, page: 1, page_size: 20 }))
    getWorkflowRun.mockImplementationOnce(async () => {
      throw new Error('workflow run not found')
    })

    expect(await keyB.loadHistory('embed-1')).toEqual([])
    expect(getWorkflowRuns).toHaveBeenLastCalledWith('embed-1', 'key-b', { pageSize: 20 })
    await expect(keyB.loadRunDetail('embed-1', 'run-1')).rejects.toThrow()
  })

  test('saveRun keeps nothing in the browser', () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    adapter.saveRun('embed-1', snapshot)
    expect(storage.length).toBe(0)
  })

  test('purges the legacy run cache instead of serving it', async () => {
    const stale = JSON.stringify([
      { runId: 'legacy-run', status: 'success', outputs: { leaked: true }, nodes: [], createdAt: '2026-01-01T00:00:00Z', title: 'key A run', inputs: { query: 'private' } },
    ])
    storage.setItem('clouisle:embed:runs:workflow:embed-1', stale)
    storage.setItem('clouisle:embed:runs:workflow:other-flow', stale)
    storage.setItem('clouisle:embed:history:agent:other-agent', stale)

    const adapter = createEmbedWorkflowRunAdapter(apiKey)

    expect(storage.getItem('clouisle:embed:runs:workflow:embed-1')).toBeNull()
    expect(storage.getItem('clouisle:embed:runs:workflow:other-flow')).toBeNull()
    expect(storage.getItem('clouisle:embed:history:agent:other-agent')).toBeNull()
    expect((await adapter.loadHistory('embed-1')).map((item) => item.id)).toEqual(['run-1'])
  })
})
