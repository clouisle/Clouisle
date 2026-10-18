import { beforeEach, describe, expect, mock, test } from 'bun:test'

const get = mock(() => Promise.resolve([]))
const post = mock(() => Promise.resolve({}))
const put = mock(() => Promise.resolve({}))
const del = mock(() => Promise.resolve({ id: 'source-1' }))

mock.module('../client', () => ({
  api: { get, post, put, delete: del },
}))

const { feishuKnowledgeApi } = await import('./feishu-knowledge')

const source = {
  knowledge_base_id: 'kb-1',
  space_id: 'space-1',
  name: 'Docs',
  interval_minutes: 30,
  is_enabled: true,
}

beforeEach(() => {
  for (const spy of [get, post, put, del]) spy.mockClear()
})

describe('feishuKnowledgeApi', () => {
  test('reads the configured spaces, targets and sources', async () => {
    await feishuKnowledgeApi.spaces()
    await feishuKnowledgeApi.targets()
    await feishuKnowledgeApi.sources()
    expect(get.mock.calls).toEqual([
      ['/admin/integrations/feishu/knowledge/spaces'],
      ['/admin/integrations/feishu/knowledge/targets'],
      ['/admin/integrations/feishu/knowledge/sources'],
    ])
  })

  test('creates and updates one sync source by id', async () => {
    await feishuKnowledgeApi.create(source)
    await feishuKnowledgeApi.update('source-1', { name: 'Renamed', interval_minutes: 60, is_enabled: false })
    expect(post.mock.calls[0]).toEqual(['/admin/integrations/feishu/knowledge/sources', source])
    expect(put.mock.calls[0]).toEqual([
      '/admin/integrations/feishu/knowledge/sources/source-1',
      { name: 'Renamed', interval_minutes: 60, is_enabled: false },
    ])
  })

  test('triggers an immediate sync and deletes by id', async () => {
    await feishuKnowledgeApi.sync('source-1')
    await feishuKnowledgeApi.delete('source-1')
    expect(post.mock.calls[0]).toEqual(['/admin/integrations/feishu/knowledge/sources/source-1/sync'])
    expect(del.mock.calls[0]).toEqual(['/admin/integrations/feishu/knowledge/sources/source-1'])
  })
})
