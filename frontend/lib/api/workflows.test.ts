import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from './client'
import { workflowsApi } from './workflows'

let getSpy: ReturnType<typeof spyOn<typeof api, 'get'>> | undefined
let postSpy: ReturnType<typeof spyOn<typeof api, 'post'>> | undefined
let putSpy: ReturnType<typeof spyOn<typeof api, 'put'>> | undefined
let deleteSpy: ReturnType<typeof spyOn<typeof api, 'delete'>> | undefined
let baseUrlSpy: ReturnType<typeof spyOn<typeof api, 'getBaseUrl'>> | undefined
let authHeadersSpy: ReturnType<typeof spyOn<typeof api, 'getAuthHeaders'>> | undefined
let fetchSpy: ReturnType<typeof spyOn<typeof globalThis, 'fetch'>> | undefined

afterEach(() => {
  getSpy?.mockRestore()
  postSpy?.mockRestore()
  putSpy?.mockRestore()
  deleteSpy?.mockRestore()
  baseUrlSpy?.mockRestore()
  authHeadersSpy?.mockRestore()
  fetchSpy?.mockRestore()
  getSpy = postSpy = putSpy = deleteSpy = undefined
  baseUrlSpy = authHeadersSpy = fetchSpy = undefined
})

describe('workflowsApi request construction', () => {
  it('uses workflow list defaults and omits unset filters', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)

    await workflowsApi.getWorkflows()

    expect(getSpy).toHaveBeenCalledWith('/workflows?page=1&page_size=20')
  })

  it('serializes workflow and all-run optional filters', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)

    await workflowsApi.getWorkflows({
      page: 2,
      pageSize: 5,
      teamId: 'team-1',
      status: 'published',
      visibility: 'team',
      triggerType: 'webhook',
      keyword: 'daily report',
      ownOnly: true,
    })
    await workflowsApi.getAllWorkflowRuns({
      teamId: ['team-1', 'team-2'],
      workflowId: ['workflow-1'],
      status: ['failed'],
      triggerType: ['cron'],
      userId: ['user-1'],
      isDebug: false,
      search: 'timeout',
    })

    expect(getSpy).toHaveBeenNthCalledWith(
      1,
      '/workflows?page=2&page_size=5&team_id=team-1&status=published&visibility=team&trigger_type=webhook&keyword=daily+report&own_only=true'
    )
    expect(getSpy).toHaveBeenNthCalledWith(
      2,
      '/workflows/runs?page=1&page_size=20&team_id=team-1&team_id=team-2&workflow_id=workflow-1&status=failed&trigger_type=cron&user_id=user-1&is_debug=false&search=timeout'
    )
  })

  it('sends CRUD methods to the workflow routes with their payloads', async () => {
    postSpy = spyOn(api, 'post').mockResolvedValue(undefined as never)
    putSpy = spyOn(api, 'put').mockResolvedValue(undefined as never)
    deleteSpy = spyOn(api, 'delete').mockResolvedValue(undefined as never)
    const create = { team_id: 'team-1', name: 'New workflow', description: 'draft' }
    const update = { name: 'Renamed workflow', visibility: 'public' as const }

    await workflowsApi.createWorkflow(create)
    await workflowsApi.updateWorkflow('workflow-1', update)
    await workflowsApi.deleteWorkflow('workflow-1')

    expect(postSpy).toHaveBeenCalledWith('/workflows', create)
    expect(putSpy).toHaveBeenCalledWith('/workflows/workflow-1', update)
    expect(deleteSpy).toHaveBeenCalledWith('/workflows/workflow-1')
  })

  it('uses default and supplied inputs for run and debug routes', async () => {
    postSpy = spyOn(api, 'post').mockResolvedValue(undefined as never)
    const input = { inputs: { question: 'What changed?' } }

    await workflowsApi.runWorkflow('workflow-1')
    await workflowsApi.debugWorkflow('workflow-1', input)
    await workflowsApi.cancelWorkflowRun('run-1')

    expect(postSpy).toHaveBeenNthCalledWith(1, '/workflows/workflow-1/run', { inputs: {} })
    expect(postSpy).toHaveBeenNthCalledWith(2, '/workflows/workflow-1/debug', input)
    expect(postSpy).toHaveBeenNthCalledWith(3, '/workflows/runs/run-1/cancel')
  })

  it('uses exact workflow read and action routes', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)
    postSpy = spyOn(api, 'post').mockResolvedValue(undefined as never)

    await workflowsApi.getWorkflow('workflow-1')
    await workflowsApi.getWorkflowStats('workflow-1')
    await workflowsApi.getWorkflowTrends('workflow-1')
    await workflowsApi.getWorkflowTrends('workflow-1', '30d')
    await workflowsApi.publishWorkflow('workflow-1')
    await workflowsApi.unpublishWorkflow('workflow-1')
    await workflowsApi.duplicateWorkflow('workflow-1')
    await workflowsApi.regenerateWebhookToken('workflow-1')

    expect(getSpy).toHaveBeenNthCalledWith(1, '/workflows/workflow-1')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/workflows/workflow-1/stats')
    expect(getSpy).toHaveBeenNthCalledWith(3, '/workflows/workflow-1/stats/trends?period=7d')
    expect(getSpy).toHaveBeenNthCalledWith(4, '/workflows/workflow-1/stats/trends?period=30d')
    expect(postSpy).toHaveBeenNthCalledWith(1, '/workflows/workflow-1/publish')
    expect(postSpy).toHaveBeenNthCalledWith(2, '/workflows/workflow-1/unpublish')
    expect(postSpy).toHaveBeenNthCalledWith(3, '/workflows/workflow-1/duplicate')
    expect(postSpy).toHaveBeenNthCalledWith(4, '/workflows/workflow-1/regenerate-webhook-token')
  })

  it('uses defaults and optional filters for run lists and stats', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)

    await workflowsApi.getAllWorkflowRuns()
    await workflowsApi.getWorkflowRunStats()
    await workflowsApi.getWorkflowRunStats('team-1')
    await workflowsApi.getWorkflowRuns('workflow-1')
    await workflowsApi.getWorkflowRuns('workflow-1', {
      page: 2,
      pageSize: 5,
      status: 'failed',
      isDebug: false,
      search: 'timeout',
      createdAfter: '2026-01-01',
      createdBefore: '2026-02-01',
    })

    expect(getSpy).toHaveBeenNthCalledWith(1, '/workflows/runs?page=1&page_size=20')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/workflows/runs/stats?')
    expect(getSpy).toHaveBeenNthCalledWith(3, '/workflows/runs/stats?team_id=team-1')
    expect(getSpy).toHaveBeenNthCalledWith(4, '/workflows/workflow-1/runs?page=1&page_size=20')
    expect(getSpy).toHaveBeenNthCalledWith(
      5,
      '/workflows/workflow-1/runs?page=2&page_size=5&status=failed&is_debug=false&search=timeout&created_after=2026-01-01&created_before=2026-02-01'
    )
  })

  it('uses exact run detail, node, and delete routes', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)
    deleteSpy = spyOn(api, 'delete').mockResolvedValue(undefined as never)

    await workflowsApi.getWorkflowRun('run-1')
    await workflowsApi.getRunNodeExecutions('run-1')
    await workflowsApi.deleteWorkflowRun('run-1')

    expect(getSpy).toHaveBeenNthCalledWith(1, '/workflows/runs/run-1')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/workflows/runs/run-1/nodes')
    expect(deleteSpy).toHaveBeenCalledWith('/workflows/runs/run-1')
  })

  it('constructs version routes with default and supplied payloads', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)
    postSpy = spyOn(api, 'post').mockResolvedValue(undefined as never)
    const snapshot = { description: 'Before release' }
    const restore = { description: 'Rollback release' }

    await workflowsApi.getWorkflowVersions('workflow-1')
    await workflowsApi.getWorkflowVersions('workflow-1', { page: 3, pageSize: 10 })
    await workflowsApi.getWorkflowVersion('workflow-1', 7)
    await workflowsApi.createWorkflowVersion('workflow-1')
    await workflowsApi.createWorkflowVersion('workflow-1', snapshot)
    await workflowsApi.restoreWorkflowVersion('workflow-1', 7)
    await workflowsApi.restoreWorkflowVersion('workflow-1', 7, restore)

    expect(getSpy).toHaveBeenNthCalledWith(1, '/workflows/workflow-1/versions?page=1&page_size=20')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/workflows/workflow-1/versions?page=3&page_size=10')
    expect(getSpy).toHaveBeenNthCalledWith(3, '/workflows/workflow-1/versions/7')
    expect(postSpy).toHaveBeenNthCalledWith(1, '/workflows/workflow-1/versions', {})
    expect(postSpy).toHaveBeenNthCalledWith(2, '/workflows/workflow-1/versions', snapshot)
    expect(postSpy).toHaveBeenNthCalledWith(3, '/workflows/workflow-1/versions/7/restore', {})
    expect(postSpy).toHaveBeenNthCalledWith(4, '/workflows/workflow-1/versions/7/restore', restore)
  })

  it('returns rejected API errors unchanged', async () => {
    const error = new Error('request failed')
    getSpy = spyOn(api, 'get').mockRejectedValue(error)

    await expect(workflowsApi.getWorkflow('workflow-1')).rejects.toBe(error)
  })
})

describe('workflowsApi streamWorkflowRun', () => {
  const prepareStream = (response: Response) => {
    baseUrlSpy = spyOn(api, 'getBaseUrl').mockReturnValue('https://api.example.test')
    authHeadersSpy = spyOn(api, 'getAuthHeaders').mockReturnValue({ Authorization: 'Bearer token' })
    fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue(response)
  }

  it('streams parsed events, skips malformed data, and completes', async () => {
    const payload = [
      'event: node_completed',
      'data: {"data":{"output":"done"},"node_id":"node-1","sequence":4,"timestamp":"2026-01-01T00:00:00Z"}',
      '',
      'data: not-json',
      '',
      'data: {"event":"run_completed","data":{},"node_id":null}',
      '',
      '',
    ].join('\n')
    prepareStream(new Response(payload))
    const events: unknown[] = []
    let completed = false

    workflowsApi.streamWorkflowRun('run-1', {
      fromSequence: 3,
      onEvent: (event) => events.push(event),
      onComplete: () => { completed = true },
    })
    await fetchSpy!.mock.results[0].value
    await Bun.sleep(10)

    expect(fetchSpy).toHaveBeenCalledWith('https://api.example.test/workflows/runs/run-1/stream?from_sequence=3', {
      headers: { Authorization: 'Bearer token', Accept: 'text/event-stream' },
      signal: expect.any(AbortSignal),
    })
    expect(events).toEqual([
      {
        type: 'node_completed',
        data: { output: 'done', node_id: 'node-1' },
        sequence: 4,
        timestamp: '2026-01-01T00:00:00Z',
      },
      {
        type: 'run_completed',
        data: { node_id: null },
        sequence: 0,
        timestamp: expect.any(String),
      },
    ])
    expect(completed).toBe(true)
  })

  it('reports HTTP and missing-body errors', async () => {
    const errors: Error[] = []
    prepareStream(new Response(null, { status: 503 }))

    workflowsApi.streamWorkflowRun('run-1', { onError: (error) => errors.push(error) })
    await Bun.sleep(10)
    expect(errors[0]?.message).toContain('503')

    fetchSpy?.mockRestore()
    fetchSpy = spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, body: null } as Response)
    workflowsApi.streamWorkflowRun('run-2', { onError: (error) => errors.push(error) })
    await Bun.sleep(10)
    expect(errors[1]).toBeInstanceOf(Error)
  })

  it('aborts without reporting an error', async () => {
    prepareStream(new Response(''))
    let reported = false

    const close = workflowsApi.streamWorkflowRun('run-1', { onError: () => { reported = true } })
    close()
    await Bun.sleep(10)

    const signal = fetchSpy!.mock.calls[0][1]?.signal
    expect(signal?.aborted).toBe(true)
    expect(reported).toBe(false)
  })
})
