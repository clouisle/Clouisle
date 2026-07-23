import { afterEach, beforeEach, describe, expect, spyOn, test } from 'bun:test'

import { api } from '../client'
import { modelsApi } from './models'

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

describe('modelsApi', () => {
  test('serializes default and filtered list requests', async () => {
    await modelsApi.getModels()
    await modelsApi.getModels({
      page: 2,
      pageSize: 50,
      provider: ['openai', 'anthropic'],
      model_type: ['llm', 'embedding'],
      is_enabled: false,
      search: 'chat & code',
    })

    expect(get).toHaveBeenNthCalledWith(1, '/admin/models?page=1&page_size=20')
    expect(get).toHaveBeenNthCalledWith(
      2,
      '/admin/models?page=2&page_size=50&provider=openai&provider=anthropic&model_type=llm&model_type=embedding&is_enabled=false&search=chat+%26+code'
    )
  })

  test('constructs CRUD requests', async () => {
    const createInput = {
      name: 'Claude',
      provider: 'anthropic',
      model_id: 'claude-sonnet',
      model_type: 'llm',
    }
    const updateInput = { name: 'Claude Sonnet', is_enabled: false }

    await modelsApi.getModel('model-1')
    await modelsApi.createModel(createInput)
    await modelsApi.updateModel('model-1', updateInput)
    await modelsApi.deleteModel('model-1')

    expect(get).toHaveBeenCalledWith('/admin/models/model-1')
    expect(post).toHaveBeenCalledWith('/admin/models', createInput)
    expect(put).toHaveBeenCalledWith('/admin/models/model-1', updateInput)
    expect(remove).toHaveBeenCalledWith('/admin/models/model-1')
  })

  test('constructs connection, config, and default requests', async () => {
    const config = {
      provider: 'anthropic',
      model_id: 'claude-sonnet',
      model_type: 'llm',
      api_key: 'secret',
    }

    await modelsApi.testConnection('model-1')
    await modelsApi.testModelConfig(config)
    await modelsApi.setDefault('model-1')

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/admin/models/model-1/test',
      undefined,
      { timeout: 300000 }
    )
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/admin/models/test',
      config,
      { timeout: 300000 }
    )
    expect(post).toHaveBeenNthCalledWith(3, '/admin/models/model-1/set-default')
  })

  test('propagates request errors', async () => {
    const error = new Error('request failed')
    get.mockRejectedValueOnce(error)

    await expect(modelsApi.getModel('model-1')).rejects.toBe(error)
    expect(get).toHaveBeenCalledWith('/admin/models/model-1')
  })
})
