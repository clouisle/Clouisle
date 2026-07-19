import { expect, mock, test } from 'bun:test'

const ToolsClient = {}
const AdminSkillsPanel = {}
const HttpToolDialog = {}
const McpToolDialog = {}
const DeleteToolDialog = {}

mock.module('./tools-client', () => ({ ToolsClient }))
mock.module('./admin-skills-panel', () => ({ AdminSkillsPanel }))
mock.module('./http-tool-dialog', () => ({ HttpToolDialog }))
mock.module('./mcp-tool-dialog', () => ({ McpToolDialog }))
mock.module('./delete-tool-dialog', () => ({ DeleteToolDialog }))

const components = await import('./index')

test('re-exports the dashboard capability components', () => {
  expect(components).toMatchObject({
    ToolsClient,
    AdminSkillsPanel,
    HttpToolDialog,
    McpToolDialog,
    DeleteToolDialog,
  })
})
