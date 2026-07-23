import { expect, mock, test } from 'bun:test'

const ParameterEditDialog = {}
const CodeInputDialog = {}
const TemplateInputDialog = {}
const FileToUrlInputDialog = {}

mock.module('./parameter-edit-dialog', () => ({ ParameterEditDialog }))
mock.module('./code-input-dialog', () => ({ CodeInputDialog }))
mock.module('./template-input-dialog', () => ({ TemplateInputDialog }))
mock.module('./file-to-url-input-dialog', () => ({ FileToUrlInputDialog }))

const dialogs = await import('./index')

test('re-exports workflow node configuration dialogs', () => {
  expect(dialogs).toMatchObject({
    ParameterEditDialog,
    CodeInputDialog,
    TemplateInputDialog,
    FileToUrlInputDialog,
  })
})
