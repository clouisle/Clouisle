import { expect, mock, test } from 'bun:test'

const DocumentsPreviewClient = {}

mock.module('./documents-preview-client', () => ({ DocumentsPreviewClient }))

const components = await import('./index')

test('re-exports the document preview client', () => {
  expect(components).toMatchObject({ DocumentsPreviewClient })
})
