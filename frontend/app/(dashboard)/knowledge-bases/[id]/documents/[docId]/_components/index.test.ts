import { expect, mock, test } from 'bun:test'

const DocumentDetailClient = {}

mock.module('./document-detail-client', () => ({ DocumentDetailClient }))

const components = await import('./index')

test('re-exports the dashboard document detail client', () => {
  expect(components).toMatchObject({ DocumentDetailClient })
})
