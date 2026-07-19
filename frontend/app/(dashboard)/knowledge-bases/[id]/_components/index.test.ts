import { expect, mock, test } from 'bun:test'

const KnowledgeBaseDetailClient = {}
const DocumentsTable = {}
const UploadDocumentDialog = {}
const ImportUrlDialog = {}
const DocumentChunksDialog = {}
const ChunkEditorDialog = {}

mock.module('./knowledge-base-detail-client', () => ({ KnowledgeBaseDetailClient }))
mock.module('./documents-table', () => ({ DocumentsTable }))
mock.module('./upload-document-dialog', () => ({ UploadDocumentDialog }))
mock.module('./import-url-dialog', () => ({ ImportUrlDialog }))
mock.module('./document-chunks-dialog', () => ({ DocumentChunksDialog }))
mock.module('./chunk-editor-dialog', () => ({ ChunkEditorDialog }))

const components = await import('./index')

test('re-exports the dashboard knowledge base components', () => {
  expect(components).toMatchObject({
    KnowledgeBaseDetailClient,
    DocumentsTable,
    UploadDocumentDialog,
    ImportUrlDialog,
    DocumentChunksDialog,
    ChunkEditorDialog,
  })
})
