import { expect, mock, test } from 'bun:test'

const MemoriesClient = {}

mock.module('./memories-client', () => ({ MemoriesClient }))

const components = await import('./index')

test('re-exports the memories client', () => {
  expect(components).toMatchObject({ MemoriesClient })
})
