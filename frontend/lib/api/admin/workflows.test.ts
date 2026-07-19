import { describe, expect, test, spyOn } from 'bun:test'

import { api } from '../client'
import { adminWorkflowsApi } from './workflows'

describe('adminWorkflowsApi', () => {
  test('builds the default and filtered list requests', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({ items: [] } as never)

    try {
      await adminWorkflowsApi.listPage()
      await adminWorkflowsApi.listPage({
        page: 3,
        pageSize: 5,
        search: 'daily sync',
        status: ['draft', 'published'],
        visibility: ['private', 'public'],
        trigger_type: ['manual', 'cron'],
        team_id: ['team-1', 'team-2'],
        creator: ['user-1', 'user-2'],
      })

      expect(get).toHaveBeenNthCalledWith(1, '/admin/workflows?page=1&page_size=20')
      expect(get).toHaveBeenNthCalledWith(
        2,
        '/admin/workflows?page=3&page_size=5&search=daily+sync&status=draft&status=published&visibility=private&visibility=public&trigger_type=manual&trigger_type=cron&team_id=team-1&team_id=team-2&creator=user-1&creator=user-2'
      )
    } finally {
      get.mockRestore()
    }
  })

  test('uses the public routes and forwards mutation payloads', async () => {
    const get = spyOn(api, 'get').mockResolvedValue({} as never)
    const post = spyOn(api, 'post').mockResolvedValue({} as never)
    const put = spyOn(api, 'put').mockResolvedValue({} as never)
    const remove = spyOn(api, 'delete').mockResolvedValue(undefined as never)
    const createPayload = { team_id: 'team-1', name: 'Workflow' }
    const updatePayload = { name: 'Renamed' }

    try {
      await adminWorkflowsApi.getFilterOptions()
      await adminWorkflowsApi.getById('workflow-1')
      await adminWorkflowsApi.create(createPayload)
      await adminWorkflowsApi.update('workflow-1', updatePayload)
      await adminWorkflowsApi.publish('workflow-1')
      await adminWorkflowsApi.unpublish('workflow-1')
      await adminWorkflowsApi.duplicate('workflow-1')
      await adminWorkflowsApi.delete('workflow-1')

      expect(get.mock.calls).toEqual([
        ['/admin/workflows/filters'],
        ['/admin/workflows/workflow-1'],
      ])
      expect(post.mock.calls).toEqual([
        ['/admin/workflows', createPayload],
        ['/admin/workflows/workflow-1/publish'],
        ['/admin/workflows/workflow-1/unpublish'],
        ['/admin/workflows/workflow-1/duplicate'],
      ])
      expect(put).toHaveBeenCalledWith('/admin/workflows/workflow-1', updatePayload)
      expect(remove).toHaveBeenCalledWith('/admin/workflows/workflow-1')
    } finally {
      get.mockRestore()
      post.mockRestore()
      put.mockRestore()
      remove.mockRestore()
    }
  })

  test('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    const get = spyOn(api, 'get').mockRejectedValue(error)

    try {
      await expect(adminWorkflowsApi.getById('workflow-1')).rejects.toBe(error)
    } finally {
      get.mockRestore()
    }
  })
})
