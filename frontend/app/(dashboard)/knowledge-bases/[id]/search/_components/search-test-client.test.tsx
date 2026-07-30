import { beforeAll, describe, expect, mock, test } from 'bun:test'
import type { ReactElement } from 'react'

const hasPermission = mock(() => false)
const api = { getKnowledgeBase: mock(), search: mock(), updateKnowledgeBase: mock() }
const push = mock()

mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('@/lib/api/knowledge-bases', () => ({ knowledgeBasesApi: api, adminKnowledgeBasesApi: api }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ hasPermission }) }))
mock.module('@/components/knowledge-bases/retrieval-lab', () => ({ RetrievalLab: 'retrieval-lab' }))

let SearchTestClient: typeof import('./search-test-client').SearchTestClient
beforeAll(async () => { ({ SearchTestClient } = await import('./search-test-client')) })

describe('dashboard SearchTestClient', () => {
  test('keeps admin API, back route, and route-specific update permission', () => {
    const tree = SearchTestClient({ knowledgeBaseId: 'kb-1' }) as ReactElement<Record<string, unknown>>
    expect(tree.type).toBe('retrieval-lab')
    expect(tree.props).toMatchObject({
      knowledgeBaseId: 'kb-1', api, backHref: '/knowledge-bases/kb-1',
      canUpdate: false, canTest: false,
    })
    expect(tree.props.authenticatedMarkdown).toBeUndefined()
    expect(hasPermission.mock.calls.map(call => call[0])).toEqual([
      'admin:knowledge-base:update', 'admin:knowledge-base:test',
    ])
    ;(tree.props.onLoadError as () => void)()
    expect(push).toHaveBeenCalledWith('/knowledge-bases')
  })
})
