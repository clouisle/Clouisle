import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from './client'
import { workflowsApi } from './workflows'

let getSpy: ReturnType<typeof spyOn<typeof api, 'get'>> | undefined
let postSpy: ReturnType<typeof spyOn<typeof api, 'post'>> | undefined
let putSpy: ReturnType<typeof spyOn<typeof api, 'put'>> | undefined
let deleteSpy: ReturnType<typeof spyOn<typeof api, 'delete'>> | undefined

afterEach(() => {
  getSpy?.mockRestore()
  postSpy?.mockRestore()
  putSpy?.mockRestore()
  deleteSpy?.mockRestore()
  getSpy = postSpy = putSpy = deleteSpy = undefined
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

  it('constructs version list, snapshot, and restore requests', async () => {
    getSpy = spyOn(api, 'get').mockResolvedValue(undefined as never)
    postSpy = spyOn(api, 'post').mockResolvedValue(undefined as never)
    const snapshot = { description: 'Before release' }
    const restore = { description: 'Rollback release' }

    await workflowsApi.getWorkflowVersions('workflow-1', { page: 3, pageSize: 10 })
    await workflowsApi.createWorkflowVersion('workflow-1', snapshot)
    await workflowsApi.restoreWorkflowVersion('workflow-1', 7, restore)

    expect(getSpy).toHaveBeenCalledWith('/workflows/workflow-1/versions?page=3&page_size=10')
    expect(postSpy).toHaveBeenNthCalledWith(1, '/workflows/workflow-1/versions', snapshot)
    expect(postSpy).toHaveBeenNthCalledWith(2, '/workflows/workflow-1/versions/7/restore', restore)
  })
})
