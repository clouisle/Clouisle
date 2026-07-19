import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'

import { api } from './client'
import { modelsApi, teamModelsApi } from './models'

afterEach(() => {
  mock.restore()
})

describe('modelsApi requests', () => {
  it('requests public model metadata and defaults', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])

    await modelsApi.getProviders()
    await modelsApi.getModelTypes()
    await modelsApi.getDefaultModel('chat')

    expect(get).toHaveBeenNthCalledWith(1, '/models/providers')
    expect(get).toHaveBeenNthCalledWith(2, '/models/types')
    expect(get).toHaveBeenNthCalledWith(3, '/models/default/chat')
  })

  it('omits the available-model filter by default and encodes it when supplied', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])

    await modelsApi.getAvailableModels()
    await modelsApi.getAvailableModels('text to image')

    expect(get).toHaveBeenNthCalledWith(1, '/models/available')
    expect(get).toHaveBeenNthCalledWith(2, '/models/available?model_type=text+to+image')
  })

  it('propagates request errors unchanged', async () => {
    const error = new Error('request failed')
    spyOn(api, 'get').mockRejectedValue(error)

    expect(modelsApi.getProviders()).rejects.toBe(error)
  })
})

describe('teamModelsApi requests', () => {
  it('builds team list routes with default and filtered queries', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])

    await teamModelsApi.getTeamModels('team-1')
    await teamModelsApi.getTeamModels('team-1', 'chat')
    await teamModelsApi.getAvailableModels('team-1')
    await teamModelsApi.getAvailableModels('team-1', 'embedding')

    expect(get).toHaveBeenNthCalledWith(1, '/teams/team-1/models')
    expect(get).toHaveBeenNthCalledWith(2, '/teams/team-1/models?model_type=chat')
    expect(get).toHaveBeenNthCalledWith(3, '/teams/team-1/available-models')
    expect(get).toHaveBeenNthCalledWith(4, '/teams/team-1/available-models?model_type=embedding')
  })

  it('sends team model create, update, and delete requests', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({})
    const put = spyOn(api, 'put').mockResolvedValue({})
    const remove = spyOn(api, 'delete').mockResolvedValue({})
    const createInput = { model_id: 'model-1', priority: 2 }
    const updateInput = { is_enabled: false }

    await teamModelsApi.addTeamModel('team-1', createInput)
    await teamModelsApi.updateTeamModel('team-1', 'model-1', updateInput)
    await teamModelsApi.removeTeamModel('team-1', 'model-1')

    expect(post).toHaveBeenCalledWith('/teams/team-1/models', createInput)
    expect(put).toHaveBeenCalledWith('/teams/team-1/models/model-1', updateInput)
    expect(remove).toHaveBeenCalledWith('/teams/team-1/models/model-1')
  })

  it('sends batch authorization requests and requests quota metadata', async () => {
    const post = spyOn(api, 'post').mockResolvedValue([])
    const remove = spyOn(api, 'delete').mockResolvedValue({ deleted_count: 2 })
    const get = spyOn(api, 'get').mockResolvedValue([])
    const batchInput = { model_ids: ['model-1', 'model-2'], daily_token_limit: 1000 }

    await teamModelsApi.batchAddTeamModels('team-1', batchInput)
    await teamModelsApi.batchRemoveTeamModels('team-1', batchInput.model_ids)
    await teamModelsApi.getTeamModelsQuota('team-1')

    expect(post).toHaveBeenCalledWith('/teams/team-1/models/batch', batchInput)
    expect(remove).toHaveBeenCalledWith('/teams/team-1/models/batch', { model_ids: batchInput.model_ids })
    expect(get).toHaveBeenCalledWith('/teams/team-1/models/quota')
  })
})
