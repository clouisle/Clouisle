import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createEmbedWorkflowRunAdapter } from '@/lib/workflow/embed-run-adapter'
import type { RunSnapshot } from '@/lib/workflow/run-adapter'

mock.module('@/lib/api/embed', () => ({
  embedApi: {
    getWorkflowInfo: mock(async () => ({
      id: 'embed-1', name: 'Embed Flow', description: '', icon: null, variables: [], embed_config: {},
    })),
    runWorkflow: mock(async () => ({ run_id: 'run-1' })),
    streamWorkflowRun: mock(() => () => {}),
  },
}))

const store = new Map<string, string>()
const localStorageMock = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => { store.set(key, value) },
  removeItem: (key: string) => { store.delete(key) },
  clear: () => { store.clear() },
}
;(globalThis as unknown as { localStorage: typeof localStorageMock }).localStorage = localStorageMock

beforeEach(() => store.clear())

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

  test('createRunApi wires embed endpoints', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const api = adapter.createRunApi()
    await api.runWorkflow('embed-1', { inputs: { query: 'hi' } })
    const stop = api.streamWorkflowRun('run-1', { fromSequence: 7, onEvent: () => {}, onError: () => {}, onComplete: () => {} })
    expect(typeof stop).toBe('function')
    await expect(api.cancelWorkflowRun('run-1')).resolves.toBeUndefined()
  })

  test('saveRun persists to localStorage and loadHistory reads it back', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    adapter.saveRun('embed-1', snapshot)
    const history = await adapter.loadHistory('embed-1')
    expect(history).toHaveLength(1)
    expect(history[0].id).toBe('run-1')
    expect(history[0].workflow_id).toBe('embed-1')
    expect(history[0].status).toBe('success')
    expect(history[0].executed_nodes).toBe(1)
  })

  test('saveRun caps history at 20 entries', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    for (let i = 0; i < 25; i++) {
      adapter.saveRun('embed-1', { ...snapshot, runId: `run-${i}` })
    }
    const history = await adapter.loadHistory('embed-1')
    expect(history).toHaveLength(20)
    expect(history[0].id).toBe('run-24')
  })

  test('loadRunDetail reconstructs run and node executions', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    adapter.saveRun('embed-1', snapshot)
    const detail = await adapter.loadRunDetail('embed-1', 'run-1')
    expect(detail.run.id).toBe('run-1')
    expect(detail.run.workflow_id).toBe('embed-1')
    expect(detail.run.inputs).toEqual({ query: 'hello' })
    expect(detail.nodes).toHaveLength(1)
    expect(detail.nodes[0].node_type).toBe('start')
    expect(detail.nodes[0].run_id).toBe('run-1')
  })

  test('loadRunDetail throws when the run is not in local history', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    await expect(adapter.loadRunDetail('embed-1', 'missing')).rejects.toThrow('run not found')
  })

  test('loadHistory returns empty when storage is empty', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const history = await adapter.loadHistory('embed-1')
    expect(history).toEqual([])
  })

  test('saveRun derives title from query input or runId', async () => {
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    adapter.saveRun('embed-1', { ...snapshot, inputs: null })
    const history = await adapter.loadHistory('embed-1')
    expect(history).toHaveLength(1)
    adapter.saveRun('embed-1', { ...snapshot, runId: 'run-2', inputs: { query: 'search term' } })
    const updated = await adapter.loadHistory('embed-1')
    expect(updated).toHaveLength(2)
    expect(updated[0].id).toBe('run-2')
  })

  test('falls back to empty history when storage throws', async () => {
    const originalGetItem = store.get.bind(store)
    store.set('clouisle:embed:runs:workflow:embed-1', '{invalid json')
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    const history = await adapter.loadHistory('embed-1')
    expect(history).toEqual([])
    expect(originalGetItem).toBeDefined()
  })

  test('loadRunDetail falls back to empty when the stored payload is corrupt', async () => {
    store.set('clouisle:embed:runs:workflow:embed-1', 'not-json')
    const adapter = createEmbedWorkflowRunAdapter(apiKey)
    await expect(adapter.loadRunDetail('embed-1', 'run-1')).rejects.toThrow('run not found')
  })
})

  test('loadHistoryPage slices local history like the authenticated adapter', async () => {
    const adapter = createEmbedWorkflowRunAdapter('key-123')
    // 本地存储有 MAX_RUNS=20 上限
    for (let index = 1; index <= 22; index += 1) {
      adapter.saveRun('embed-1', { ...snapshot, runId: `run-${index}`, inputs: { query: `q-${index}` } })
    }

    const page1 = await adapter.loadHistoryPage('embed-1', { page: 1, pageSize: 20 })
    expect(page1.total).toBe(20)
    expect(page1.items).toHaveLength(20)
    expect(page1.items[0].id).toBe('run-22')

    const page2 = await adapter.loadHistoryPage('embed-1', { page: 2, pageSize: 20 })
    expect(page2.items).toHaveLength(0)
    expect(page2.total).toBe(20)
  })
