import { expect, mock, test } from 'bun:test'

const ApiAccessContent = {}

mock.module('./api-access-content', () => ({ ApiAccessContent }))

const components = await import('./index')

test('re-exports the application API access content', () => {
  expect(components).toMatchObject({ ApiAccessContent })
})
