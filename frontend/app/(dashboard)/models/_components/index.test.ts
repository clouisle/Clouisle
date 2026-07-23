import { expect, mock, test } from 'bun:test'

const ModelsClient = {}
const ModelDialog = {}
const DeleteModelDialog = {}

mock.module('./models-client', () => ({ ModelsClient }))
mock.module('./model-dialog', () => ({ ModelDialog }))
mock.module('./delete-model-dialog', () => ({ DeleteModelDialog }))

const components = await import('./index')

test('re-exports the model management components', () => {
  expect(components).toMatchObject({ ModelsClient, ModelDialog, DeleteModelDialog })
})
