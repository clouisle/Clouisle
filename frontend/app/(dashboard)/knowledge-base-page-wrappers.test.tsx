import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('@/components/layout/header', () => ({
  Header: () => <header data-testid="dashboard-header" />,
}))
mock.module('@/app/(dashboard)/knowledge-bases/[id]/_components', () => ({
  KnowledgeBaseDetailClient: (props: { knowledgeBaseId: string }) => <main data-client="detail" {...props} />,
}))
mock.module('@/app/(dashboard)/knowledge-bases/[id]/search/_components/search-test-client', () => ({
  SearchTestClient: (props: { knowledgeBaseId: string }) => <main data-client="search" {...props} />,
}))
mock.module('@/app/(dashboard)/knowledge-bases/[id]/documents/[docId]/_components/document-detail-client', () => ({
  DocumentDetailClient: (props: { knowledgeBaseId: string; documentId: string }) => <main data-client="document" {...props} />,
}))
mock.module('@/app/(dashboard)/knowledge-bases/[id]/documents/preview/_components/documents-preview-client', () => ({
  DocumentsPreviewClient: (props: { knowledgeBaseId: string; documentIds: string[] }) => <main data-client="preview" {...props} />,
}))

let KnowledgeBaseDetailPage: typeof import('./knowledge-bases/[id]/page').default
let SearchTestPage: typeof import('./knowledge-bases/[id]/search/page').default
let DocumentDetailPage: typeof import('./knowledge-bases/[id]/documents/[docId]/page').default
let DocumentsPreviewPage: typeof import('./knowledge-bases/[id]/documents/preview/page').default

beforeAll(async () => {
  ;({ default: KnowledgeBaseDetailPage } = await import('./knowledge-bases/[id]/page'))
  ;({ default: SearchTestPage } = await import('./knowledge-bases/[id]/search/page'))
  ;({ default: DocumentDetailPage } = await import('./knowledge-bases/[id]/documents/[docId]/page'))
  ;({ default: DocumentsPreviewPage } = await import('./knowledge-bases/[id]/documents/preview/page'))
})

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
})

async function renderPage(element: Promise<React.ReactNode>) {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(await element)
  })
  renderers.push(renderer!)
  return renderer!
}

function expectDashboardShell(renderer: ReactTestRenderer) {
  expect(renderer.root.findAllByProps({ 'data-testid': 'dashboard-header' })).toHaveLength(1)
  expect(renderer.root.findAllByType('main')).toHaveLength(1)
}

describe('knowledge base dashboard page wrappers', () => {
  test('renders detail and search landmarks with the route id delegated', async () => {
    const detail = await renderPage(KnowledgeBaseDetailPage({ params: Promise.resolve({ id: 'kb-12' }) }))
    expectDashboardShell(detail)
    expect(detail.root.findByType('main').props).toMatchObject({
      'data-client': 'detail',
      knowledgeBaseId: 'kb-12',
    })

    const search = await renderPage(SearchTestPage({ params: Promise.resolve({ id: 'kb-34' }) }))
    expectDashboardShell(search)
    expect(search.root.findByType('main').props).toMatchObject({
      'data-client': 'search',
      knowledgeBaseId: 'kb-34',
    })
  })

  test('delegates both route ids to document detail', async () => {
    const renderer = await renderPage(DocumentDetailPage({
      params: Promise.resolve({ id: 'kb-56', docId: 'doc-78' }),
    }))

    expectDashboardShell(renderer)
    expect(renderer.root.findByType('main').props).toMatchObject({
      'data-client': 'document',
      knowledgeBaseId: 'kb-56',
      documentId: 'doc-78',
    })
  })

  test('parses preview document ids and preserves the empty boundary', async () => {
    const populated = await renderPage(DocumentsPreviewPage({
      params: Promise.resolve({ id: 'kb-90' }),
      searchParams: Promise.resolve({ docs: 'doc-1,doc-2' }),
    }))
    expectDashboardShell(populated)
    expect(populated.root.findByType('main').props).toMatchObject({
      'data-client': 'preview',
      knowledgeBaseId: 'kb-90',
      documentIds: ['doc-1', 'doc-2'],
    })

    const empty = await renderPage(DocumentsPreviewPage({
      params: Promise.resolve({ id: 'kb-90' }),
      searchParams: Promise.resolve({}),
    }))
    expect(empty.root.findByType('main').props.documentIds).toEqual([])
  })
})
