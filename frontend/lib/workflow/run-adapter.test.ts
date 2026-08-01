import { describe, expect, mock, test } from 'bun:test'
import { mapEmbedWorkflow, jwtWorkflowRunAdapter } from '@/lib/workflow/run-adapter'
import { workflowsApi } from '@/lib/api/workflows'
import type { EmbedWorkflowInfo } from '@/lib/api/embed'

mock.module('@/lib/api/workflows', () => ({
  workflowsApi: {
    getWorkflow: mock(async (id: string) => ({ id, name: 'wf' })),
    runWorkflow: mock(async () => ({ run_id: 'run-1' })),
    streamWorkflowRun: mock(() => () => {}),
    cancelWorkflowRun: mock(async () => {}),
    getMyWorkflowRuns: mock(async () => ({ items: [{ id: 'run-1' }], total: 1 })),
    getMyWorkflowRun: mock(async () => ({ id: 'run-1', status: 'success' })),
    getMyRunNodeExecutions: mock(async () => [{ id: 'n1' }]),
  },
}))

describe('mapEmbedWorkflow', () => {
  test('maps embed info onto the full Workflow shape', () => {
    const info: EmbedWorkflowInfo = {
      id: 'embed-1',
      name: 'Embed Flow',
      description: 'desc',
      icon: 'spark',
      variables: [{ name: 'q', type: 'string', required: false, hidden: false }],
      embed_config: { allow_new: true },
    } as unknown as EmbedWorkflowInfo

    const workflow = mapEmbedWorkflow(info)

    expect(workflow.id).toBe('embed-1')
    expect(workflow.name).toBe('Embed Flow')
    expect(workflow.status).toBe('published')
    expect(workflow.visibility).toBe('public')
    expect(workflow.definition).toEqual({ nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } })
    expect(workflow.run_page_config).toEqual({ presentation_mode: 'simple' })
    expect(workflow.variables).toEqual(info.variables)
  })
})

describe('jwtWorkflowRunAdapter', () => {
  test('getWorkflow delegates to workflowsApi', async () => {
    const workflow = await jwtWorkflowRunAdapter.getWorkflow('wf-1')
    expect(workflowsApi.getWorkflow).toHaveBeenCalledWith('wf-1')
    expect(workflow).toEqual({ id: 'wf-1', name: 'wf' })
  })

  test('createRunApi wires the authenticated API methods', async () => {
    const api = jwtWorkflowRunAdapter.createRunApi()
    await api.runWorkflow('wf-1', { inputs: {} })
    expect(workflowsApi.runWorkflow).toHaveBeenCalledWith('wf-1', { inputs: {} })

    const stop = api.streamWorkflowRun('run-1', { onEvent: () => {}, onError: () => {}, onComplete: () => {} })
    expect(workflowsApi.streamWorkflowRun).toHaveBeenCalledWith('run-1', expect.anything())
    expect(typeof stop).toBe('function')

    await api.cancelWorkflowRun('run-1')
    expect(workflowsApi.cancelWorkflowRun).toHaveBeenCalledWith('run-1')
  })

  test('loadHistory returns the workflow runs items', async () => {
    const items = await jwtWorkflowRunAdapter.loadHistory('wf-1')
    expect(workflowsApi.getMyWorkflowRuns).toHaveBeenCalledWith('wf-1', { pageSize: 10 })
    expect(items).toEqual([{ id: 'run-1' }])
  })

  test('loadRunDetail fetches run and node executions in parallel', async () => {
    const detail = await jwtWorkflowRunAdapter.loadRunDetail('wf-1', 'run-1')
    expect(workflowsApi.getMyWorkflowRun).toHaveBeenCalledWith('wf-1', 'run-1')
    expect(workflowsApi.getMyRunNodeExecutions).toHaveBeenCalledWith('wf-1', 'run-1')
    expect(detail).toEqual({ run: { id: 'run-1', status: 'success' }, nodes: [{ id: 'n1' }] })
  })

  test('saveRun is a no-op for authenticated runs', () => {
    expect(() => jwtWorkflowRunAdapter.saveRun('wf-1', {
      runId: 'run-1', status: 'success', outputs: null, nodes: [], createdAt: '',
    })).not.toThrow()
  })
})
