import { expect, mock, test } from 'bun:test'

const KnowledgeBasesClient = {}
const KnowledgeBaseDialog = {}
const DeleteKnowledgeBaseDialog = {}

mock.module('./knowledge-bases-client', () => ({ KnowledgeBasesClient }))
mock.module('./knowledge-base-dialog', () => ({ KnowledgeBaseDialog }))
mock.module('./delete-knowledge-base-dialog', () => ({ DeleteKnowledgeBaseDialog }))

const components = await import('./index')

test('re-exports the knowledge base management components', () => {
  expect(components).toMatchObject({
    KnowledgeBasesClient,
    KnowledgeBaseDialog,
    DeleteKnowledgeBaseDialog,
  })
})
