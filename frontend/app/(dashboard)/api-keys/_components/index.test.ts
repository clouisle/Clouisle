import { expect, mock, test } from 'bun:test'

const APIKeysClient = {}
const APIKeyDialog = {}
const DeleteAPIKeyDialog = {}
const ShowKeyDialog = {}

mock.module('./api-keys-client', () => ({ APIKeysClient }))
mock.module('./api-key-dialog', () => ({ APIKeyDialog }))
mock.module('./delete-api-key-dialog', () => ({ DeleteAPIKeyDialog }))
mock.module('./show-key-dialog', () => ({ ShowKeyDialog }))

const components = await import('./index')

test('re-exports the API key management components', () => {
  expect(components).toMatchObject({
    APIKeysClient,
    APIKeyDialog,
    DeleteAPIKeyDialog,
    ShowKeyDialog,
  })
})
