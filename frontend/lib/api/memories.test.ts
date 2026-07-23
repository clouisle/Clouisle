import { afterEach, describe, expect, it, mock, spyOn } from 'bun:test'
import { api } from './client'
import { memoriesApi } from './memories'

mock.module('server-only', () => ({}))

const serverUrl = await import('./server-url')
const spies: Array<{ mockRestore(): void }> = []

afterEach(() => {
  spies.splice(0).forEach(spy => spy.mockRestore())
})

describe('memoriesApi', () => {
  it('serializes entity filters and returns the client result', async () => {
    const entities = [{ id: 'entity-1' }]
    const get = spyOn(api, 'get').mockResolvedValue(entities)
    spies.push(get)

    await expect(memoriesApi.getEntities({
      entity_type: 'person',
      search: 'Ada Lovelace',
      limit: 20,
      offset: 10,
    })).resolves.toBe(entities)
    expect(get).toHaveBeenCalledWith('/memories/entities?entity_type=person&search=Ada+Lovelace&limit=20&offset=10')
  })

  it('serializes relation filters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])
    spies.push(get)

    await memoriesApi.getRelations({
      source_entity_id: 'source',
      target_entity_id: 'target',
      relation_type: 'knows',
      limit: 5,
      offset: 2,
    })

    expect(get).toHaveBeenCalledWith('/memories/relations?source_entity_id=source&target_entity_id=target&relation_type=knows&limit=5&offset=2')
  })

  it('omits empty entity and relation filters', async () => {
    const get = spyOn(api, 'get').mockResolvedValue([])
    spies.push(get)

    await memoriesApi.getEntities()
    await memoriesApi.getEntities({ entity_type: undefined, search: '', limit: 0, offset: 0 })
    await memoriesApi.getRelations()
    await memoriesApi.getRelations({
      source_entity_id: '',
      target_entity_id: '',
      relation_type: undefined,
      limit: 0,
      offset: 0,
    })

    expect(get).toHaveBeenNthCalledWith(1, '/memories/entities')
    expect(get).toHaveBeenNthCalledWith(2, '/memories/entities')
    expect(get).toHaveBeenNthCalledWith(3, '/memories/relations')
    expect(get).toHaveBeenNthCalledWith(4, '/memories/relations')
  })

  it('delegates entity and relation operations to the expected endpoints', async () => {
    const entity = { id: 'entity-1' }
    const relation = { id: 'relation-1' }
    const graph = { entities: [entity], relations: [relation] }
    const get = spyOn(api, 'get')
      .mockResolvedValueOnce(entity)
      .mockResolvedValueOnce(graph)
    const post = spyOn(api, 'post')
      .mockResolvedValueOnce(entity)
      .mockResolvedValueOnce(relation)
    const put = spyOn(api, 'put').mockResolvedValue(entity)
    const remove = spyOn(api, 'delete').mockResolvedValue(undefined)
    spies.push(get, post, put, remove)

    const createEntityInput = { name: 'Ada', entity_type: 'person' as const }
    const updateEntityInput = { description: 'Mathematician' }
    const createRelationInput = {
      source_entity_id: 'entity-1',
      target_entity_id: 'entity-2',
      relation_type: 'knows' as const,
    }

    await expect(memoriesApi.getEntity('entity-1')).resolves.toBe(entity)
    await expect(memoriesApi.createEntity(createEntityInput)).resolves.toBe(entity)
    await expect(memoriesApi.updateEntity('entity-1', updateEntityInput)).resolves.toBe(entity)
    await memoriesApi.deleteEntity('entity-1')
    await expect(memoriesApi.createRelation(createRelationInput)).resolves.toBe(relation)
    await memoriesApi.deleteRelation('relation-1')
    await expect(memoriesApi.getGraph()).resolves.toBe(graph)

    expect(get).toHaveBeenNthCalledWith(1, '/memories/entities/entity-1')
    expect(get).toHaveBeenNthCalledWith(2, '/memories/graph')
    expect(post).toHaveBeenNthCalledWith(1, '/memories/entities', createEntityInput)
    expect(post).toHaveBeenNthCalledWith(2, '/memories/relations', createRelationInput)
    expect(put).toHaveBeenCalledWith('/memories/entities/entity-1', updateEntityInput)
    expect(remove).toHaveBeenNthCalledWith(1, '/memories/entities/entity-1')
    expect(remove).toHaveBeenNthCalledWith(2, '/memories/relations/relation-1')
  })
})

describe('server URL helpers', () => {
  const originalBackendInternalUrl = process.env.BACKEND_INTERNAL_URL

  afterEach(() => {
    if (originalBackendInternalUrl === undefined) delete process.env.BACKEND_INTERNAL_URL
    else process.env.BACKEND_INTERNAL_URL = originalBackendInternalUrl
  })

  it('keeps an absolute API URL and derives its backend origin', () => {
    expect(serverUrl.getServerApiBaseUrl()).toBe('http://localhost:8000/api/v1')
    expect(serverUrl.getServerBackendOrigin()).toBe('http://localhost:8000')
  })

  it('evaluates the HTTPS condition', () => {
    const startsWith = spyOn(String.prototype, 'startsWith')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true)
    spies.push(startsWith)

    expect(serverUrl.getServerApiBaseUrl()).toBe('http://localhost:8000/api/v1')
    expect(startsWith).toHaveBeenNthCalledWith(1, 'http://')
    expect(startsWith).toHaveBeenNthCalledWith(2, 'https://')
  })

  it('uses configured and default backend origins for a relative API path', () => {
    const startsWith = spyOn(String.prototype, 'startsWith').mockReturnValue(false)
    spies.push(startsWith)

    process.env.BACKEND_INTERNAL_URL = 'http://backend:8000'
    expect(serverUrl.getServerApiBaseUrl()).toBe('http://backend:8000http://localhost:8000/api/v1')

    delete process.env.BACKEND_INTERNAL_URL
    expect(serverUrl.getServerApiBaseUrl()).toBe('http://localhost:8000http://localhost:8000/api/v1')
  })
})
