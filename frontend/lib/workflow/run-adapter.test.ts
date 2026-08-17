import { describe, expect, mock, test } from 'bun:test'

const getMyWorkflowRuns = mock(async () => ({
  items: [{ id: 'run-1' }],
  total: 5,
  page: 1,
  page_size: 20,
}))
const getWorkflow = mock(async () => ({ id: 'wf-1' }))
const getMyWorkflowRun = mock(async () => ({ id: 'run-1', status: 'success' }))
const getMyRunNodeExecutions = mock(async () => [{ id: 'node-1' }])
const getPendingPauseRequest = mock(async () => ({ id: 'pr-1' }))
const submitPauseRequest = mock(async () => ({ pause_request_id: 'pr-1', status: 'submitted' }))
const runWorkflow = mock(async () => ({ run_id: 'run-1' }))
const streamWorkflowRun = mock(() => () => {})
const cancelWorkflowRun = mock(async () => ({ cancelled: true }))

mock.module('@/lib/api/workflows', () => ({
  workflowsApi: {
    getMyWorkflowRuns,
    getWorkflow,
    getMyWorkflowRun,
    getMyRunNodeExecutions,
    getPendingPauseRequest,
    submitPauseRequest,
    runWorkflow,
    streamWorkflowRun,
    cancelWorkflowRun,
  },
}))

const { jwtWorkflowRunAdapter } = await import('./run-adapter')

describe('jwtWorkflowRunAdapter', () => {
  test('loadHistoryPage forwards page/pageSize and maps the page data', async () => {
    const page = await jwtWorkflowRunAdapter.loadHistoryPage('wf-1', { page: 2, pageSize: 20 })

    expect(getMyWorkflowRuns).toHaveBeenCalledWith('wf-1', { page: 2, pageSize: 20 })
    expect(page).toEqual({ items: [{ id: 'run-1' }], total: 5 })
  })

  test('loadHistory requests the first page for the plain history call', async () => {
    await jwtWorkflowRunAdapter.loadHistory('wf-1')

    expect(getMyWorkflowRuns).toHaveBeenCalledWith('wf-1', { pageSize: 20 })
  })

  test('getWorkflow and loadRunDetail delegate to the workflows API', async () => {
    const workflow = await jwtWorkflowRunAdapter.getWorkflow('wf-1')
    expect(getWorkflow).toHaveBeenCalledWith('wf-1')
    expect(workflow).toEqual({ id: 'wf-1' })

    const detail = await jwtWorkflowRunAdapter.loadRunDetail('wf-1', 'run-1')
    expect(getMyWorkflowRun).toHaveBeenCalledWith('wf-1', 'run-1')
    expect(getMyRunNodeExecutions).toHaveBeenCalledWith('wf-1', 'run-1')
    expect(detail).toEqual({ run: { id: 'run-1', status: 'success' }, nodes: [{ id: 'node-1' }] })
  })

  test('pause request getter and submit delegate with comment passthrough', async () => {
    const request = await jwtWorkflowRunAdapter.getPendingPauseRequest!('wf-1', 'run-1')
    expect(getPendingPauseRequest).toHaveBeenCalledWith('wf-1', 'run-1')
    expect(request).toEqual({ id: 'pr-1' })

    const result = await jwtWorkflowRunAdapter.submitPauseRequest!('wf-1', 'run-1', 'pr-1', { price: 1 }, 'ok')
    expect(submitPauseRequest).toHaveBeenCalledWith('wf-1', 'run-1', 'pr-1', { price: 1 }, 'ok')
    expect(result.status).toBe('submitted')
  })

  test('createRunApi wires run/stream/cancel and saveRun is a no-op', async () => {
    const api = jwtWorkflowRunAdapter.createRunApi()
    await api.runWorkflow('wf-1', { inputs: { query: 'hi' } })
    expect(runWorkflow).toHaveBeenCalledWith('wf-1', { inputs: { query: 'hi' } })

    const stop = api.streamWorkflowRun('run-1', { onEvent: () => {}, onError: () => {}, onComplete: () => {} })
    expect(typeof stop).toBe('function')

    await api.cancelWorkflowRun('run-1')
    expect(cancelWorkflowRun).toHaveBeenCalledWith('run-1')

    expect(() => jwtWorkflowRunAdapter.saveRun('wf-1', {} as never)).not.toThrow()
  })
})
