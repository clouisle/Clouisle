import { expect, mock, test } from 'bun:test'

const TeamsClient = {}
const TeamDialog = {}
const TeamDetailDialog = {}
const TeamModelsTab = {}

mock.module('./teams-client', () => ({ TeamsClient }))
mock.module('./team-dialog', () => ({ TeamDialog }))
mock.module('./team-detail-dialog', () => ({ TeamDetailDialog }))
mock.module('./team-models-tab', () => ({ TeamModelsTab }))

const components = await import('./index')

test('re-exports the team management components', () => {
  expect(components).toMatchObject({ TeamsClient, TeamDialog, TeamDetailDialog, TeamModelsTab })
})
