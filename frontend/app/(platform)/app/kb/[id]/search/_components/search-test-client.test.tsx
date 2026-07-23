import { beforeAll, describe, expect, mock, test } from 'bun:test'
import type { ReactElement } from 'react'

const hasPermission = mock(() => true)
const api = { getKnowledgeBase: mock(), search: mock(), updateKnowledgeBase: mock() }
const push = mock()

mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('@/lib/api/knowledge-bases', () => ({ knowledgeBasesApi: api, adminKnowledgeBasesApi: api }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ hasPermission }) }))
mock.module('@/components/knowledge-bases/retrieval-lab', () => ({ RetrievalLab: 'retrieval-lab' }))

let SearchTestClient: typeof import('./search-test-client').SearchTestClient
beforeAll(async () => { ({ SearchTestClient } = await import('./search-test-client')) })

describe('platform SearchTestClient', () => {
  test('keeps platform API, back route, permission, and authenticated markdown', () => {
    const tree = SearchTestClient({ knowledgeBaseId: 'kb-1' }) as ReactElement<Record<string, unknown>>
    expect(tree.type).toBe('retrieval-lab')
    expect(tree.props).toMatchObject({
      knowledgeBaseId: 'kb-1', api, backHref: '/app/kb/kb-1', canUpdate: true, authenticatedMarkdown: true,
    })
    expect(hasPermission).toHaveBeenCalledWith('kb:update')
    ;(tree.props.onLoadError as () => void)()
    expect(push).toHaveBeenCalledWith('/app/kb')
  })
})
