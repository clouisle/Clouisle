import { expect, mock, test } from 'bun:test'

const ToolCard = {}
const ToolList = {}
const ToolTestPanel = {}
const SkillsPanel = {}

mock.module('./tool-card', () => ({ ToolCard }))
mock.module('./tool-list', () => ({ ToolList }))
mock.module('./tool-test-panel', () => ({ ToolTestPanel }))
mock.module('./skills-panel', () => ({ SkillsPanel }))

const components = await import('./index')

test('re-exports the platform capability components', () => {
  expect(components).toMatchObject({ ToolCard, ToolList, ToolTestPanel, SkillsPanel })
})
