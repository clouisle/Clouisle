import { expect, mock, test } from 'bun:test'

const CodeEditor = {}

mock.module('./code-editor', () => ({ CodeEditor }))

const components = await import('./index')

test('re-exports the workflow node code editor', () => {
  expect(components).toMatchObject({ CodeEditor })
})
