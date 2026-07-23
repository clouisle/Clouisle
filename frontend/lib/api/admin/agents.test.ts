import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from '../client'
import { adminAgentsApi } from './agents'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let put: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>
let spies: Array<ReturnType<typeof spyOn>>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  put = spyOn(api, 'put').mockResolvedValue(undefined)
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
  spies = [get, post, put, remove]
})

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
})

describe('adminAgentsApi', () => {
  test('serializes default and filtered list requests', async () => {
    await adminAgentsApi.listPage()
    await adminAgentsApi.listPage({
      page: 2,
      pageSize: 50,
      search: 'chat & code',
      status: ['draft', 'published'],
      visibility: ['private', 'public'],
      team_id: ['team-1', 'team-2'],
      creator: ['user-1', 'user-2'],
    })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/agents?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/admin/agents?page=2&page_size=50&search=chat+%26+code&status=draft&status=published&visibility=private&visibility=public&team_id=team-1&team_id=team-2&creator=user-1&creator=user-2'
    )
  })

  test('constructs read and mutation requests with exact payloads', async () => {
    const createInput = { name: 'Agent', description: 'Creates answers' }
    const updateInput = { name: 'Updated agent' }

    await adminAgentsApi.getFilterOptions()
    await adminAgentsApi.getById('agent-1')
    await adminAgentsApi.create(createInput)
    await adminAgentsApi.update('agent-1', updateInput)
    await adminAgentsApi.publish('agent-1')
    await adminAgentsApi.unpublish('agent-1')
    await adminAgentsApi.duplicate('agent-1')
    await adminAgentsApi.delete('agent-1')

    expect(get).toHaveBeenNthCalledWith(1, '/admin/agents/filters')
    expect(get).toHaveBeenNthCalledWith(2, '/admin/agents/agent-1')
    expect(post).toHaveBeenNthCalledWith(1, '/admin/agents', createInput)
    expect(put).toHaveBeenCalledWith('/admin/agents/agent-1', updateInput)
    expect(post).toHaveBeenNthCalledWith(2, '/admin/agents/agent-1/publish')
    expect(post).toHaveBeenNthCalledWith(3, '/admin/agents/agent-1/unpublish')
    expect(post).toHaveBeenNthCalledWith(4, '/admin/agents/agent-1/duplicate')
    expect(remove).toHaveBeenCalledWith('/admin/agents/agent-1')
  })

  test('propagates request errors', async () => {
    const error = new Error('request failed')
    get.mockRejectedValueOnce(error)

    await expect(adminAgentsApi.getById('agent-1')).rejects.toBe(error)
    expect(get).toHaveBeenCalledWith('/admin/agents/agent-1')
  })
})
