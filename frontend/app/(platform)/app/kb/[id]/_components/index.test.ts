import { expect, mock, test } from 'bun:test'

const DocumentsTable = {}
const UploadDocumentDialog = {}
const ImportUrlDialog = {}

mock.module('./documents-table', () => ({ DocumentsTable }))
mock.module('./upload-document-dialog', () => ({ UploadDocumentDialog }))
mock.module('./import-url-dialog', () => ({ ImportUrlDialog }))

const components = await import('./index')

test('re-exports the knowledge base document components', () => {
  expect(components).toMatchObject({ DocumentsTable, UploadDocumentDialog, ImportUrlDialog })
})
