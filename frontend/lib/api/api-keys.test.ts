import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'

import { apiKeysApi } from './api-keys'
import { api } from './client'

afterEach(() => {
  mock.restore()
})

describe('apiKeysApi', () => {
  test('gets API keys with defaults and representative filters', async () => {
    const response = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 }
    const get = spyOn(api, 'get').mockResolvedValue(response)

    await expect(apiKeysApi.getAPIKeys()).resolves.toBe(response)
    await expect(apiKeysApi.getAPIKeys({
      page: 2,
      pageSize: 50,
      status: ['active', 'expired'],
      userId: ['user-1', 'user-2'],
      search: 'production key',
    })).resolves.toBe(response)

    expect(get).toHaveBeenNthCalledWith(1, '/api-keys?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/api-keys?page=2&page_size=50&status=active&status=expired&user_id=user-1&user_id=user-2&search=production+key'
    )
  })

  test('gets API key stats and details', async () => {
    const response = { id: 'key-1' }
    const get = spyOn(api, 'get').mockResolvedValue(response)

    await expect(apiKeysApi.getStats()).resolves.toBe(response)
    await expect(apiKeysApi.getAPIKey('key-1')).resolves.toBe(response)

    expect(get).toHaveBeenNthCalledWith(1, '/api-keys/stats')
    expect(get).toHaveBeenNthCalledWith(2, '/api-keys/key-1')
  })

  test('creates, updates, deletes, activates, and deactivates API keys', async () => {
    const createInput = {
      name: 'Deployment key',
      scopes: ['agents:read'],
      rate_limit: 60,
      expires_at: '2027-01-01T00:00:00Z',
      agent_ids: ['agent-1'],
      workflow_ids: ['workflow-1'],
    }
    const updateInput = {
      name: 'Rotated deployment key',
      is_active: false,
      workflow_ids: ['workflow-2'],
    }
    const post = spyOn(api, 'post').mockResolvedValue({ id: 'key-1', key: 'secret' })
    const put = spyOn(api, 'put').mockResolvedValue({ id: 'key-1' })
    const remove = spyOn(api, 'delete').mockResolvedValue({ id: 'key-1' })

    await apiKeysApi.createAPIKey(createInput)
    await apiKeysApi.updateAPIKey('key-1', updateInput)
    await apiKeysApi.deleteAPIKey('key-1')
    await apiKeysApi.activateAPIKey('key-1')
    await apiKeysApi.deactivateAPIKey('key-1')

    expect(post).toHaveBeenNthCalledWith(1, '/api-keys', createInput)
    expect(put).toHaveBeenCalledWith('/api-keys/key-1', updateInput)
    expect(remove).toHaveBeenCalledWith('/api-keys/key-1')
    expect(post).toHaveBeenNthCalledWith(2, '/api-keys/key-1/activate')
    expect(post).toHaveBeenNthCalledWith(3, '/api-keys/key-1/deactivate')
  })

  test('propagates API errors', async () => {
    const error = new Error('API unavailable')
    spyOn(api, 'get').mockRejectedValue(error)

    await expect(apiKeysApi.getStats()).rejects.toBe(error)
  })
})
