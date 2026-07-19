import { afterEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from './client'
import { memoriesApi } from './memories'

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

  it('delegates entity mutations to the expected endpoints', async () => {
    const post = spyOn(api, 'post').mockResolvedValue({ id: 'entity-1' })
    const put = spyOn(api, 'put').mockResolvedValue({ id: 'entity-1' })
    const remove = spyOn(api, 'delete').mockResolvedValue(undefined)
    spies.push(post, put, remove)

    const createInput = { name: 'Ada', entity_type: 'person' as const }
    const updateInput = { description: 'Mathematician' }
    await memoriesApi.createEntity(createInput)
    await memoriesApi.updateEntity('entity-1', updateInput)
    await memoriesApi.deleteEntity('entity-1')

    expect(post).toHaveBeenCalledWith('/memories/entities', createInput)
    expect(put).toHaveBeenCalledWith('/memories/entities/entity-1', updateInput)
    expect(remove).toHaveBeenCalledWith('/memories/entities/entity-1')
  })
})
