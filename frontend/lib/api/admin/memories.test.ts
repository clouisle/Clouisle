import { afterEach, beforeEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from '../client'
import { memoriesApi } from './memories'

let getSpy: ReturnType<typeof spyOn<typeof api, 'get'>>
let putSpy: ReturnType<typeof spyOn<typeof api, 'put'>>
let deleteSpy: ReturnType<typeof spyOn<typeof api, 'delete'>>

beforeEach(() => {
  getSpy = spyOn(api, 'get')
  putSpy = spyOn(api, 'put')
  deleteSpy = spyOn(api, 'delete')
})

afterEach(() => {
  getSpy.mockRestore()
  putSpy.mockRestore()
  deleteSpy.mockRestore()
})

describe('admin memories API', () => {
  it('serializes entity query parameters', async () => {
    getSpy.mockResolvedValue({ items: [], total: 0, page: 0, page_size: 0 })

    await memoriesApi.getEntities({
      page: 0,
      page_size: 0,
      user_id: ['user-1', 'user 2'],
      entity_type: ['person', 'project'],
      search: 'Ada Lovelace',
    })

    expect(getSpy).toHaveBeenCalledWith(
      '/admin/memories/entities?page=0&page_size=0&user_id=user-1&user_id=user+2&entity_type=person&entity_type=project&search=Ada+Lovelace'
    )
  })

  it('uses stats and entity CRUD routes with the update payload', async () => {
    getSpy.mockResolvedValue({})
    putSpy.mockResolvedValue({})
    deleteSpy.mockResolvedValue(undefined)
    const update = { description: 'Updated', properties: { confidence: 0.9 } }

    await memoriesApi.getStats()
    await memoriesApi.getEntity('entity-1')
    await memoriesApi.updateEntity('entity-1', update)
    await memoriesApi.deleteEntity('entity-1')

    expect(getSpy).toHaveBeenNthCalledWith(1, '/admin/memories/entities/stats')
    expect(getSpy).toHaveBeenNthCalledWith(2, '/admin/memories/entities/entity-1')
    expect(putSpy).toHaveBeenCalledWith('/admin/memories/entities/entity-1', update)
    expect(deleteSpy).toHaveBeenCalledWith('/admin/memories/entities/entity-1')
  })

  it('passes relation parameters and deletes by relation ID', async () => {
    getSpy.mockResolvedValue({ items: [], total: 0, page: 2, page_size: 25 })
    deleteSpy.mockResolvedValue(undefined)
    const params = { page: 2, page_size: 25, user_id: 'user-1', relation_type: 'knows' }

    await memoriesApi.getRelations(params)
    await memoriesApi.deleteRelation('relation-1')

    expect(getSpy).toHaveBeenCalledWith('/admin/memories/relations', { params })
    expect(deleteSpy).toHaveBeenCalledWith('/admin/memories/relations/relation-1')
  })

  it('propagates request errors', async () => {
    const error = new Error('request failed')
    getSpy.mockRejectedValue(error)

    await expect(memoriesApi.getStats()).rejects.toBe(error)
  })
})
