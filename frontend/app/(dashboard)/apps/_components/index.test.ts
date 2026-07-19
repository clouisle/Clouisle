import { expect, mock, test } from 'bun:test'

const AdminAgentsPanel = {}
const AdminWorkflowsPanel = {}

mock.module('./admin-agents-panel', () => ({ AdminAgentsPanel }))
mock.module('./admin-workflows-panel', () => ({ AdminWorkflowsPanel }))

const components = await import('./index')

test('re-exports the dashboard app panels', () => {
  expect(components).toMatchObject({ AdminAgentsPanel, AdminWorkflowsPanel })
})
