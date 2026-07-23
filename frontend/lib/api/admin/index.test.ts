import { expect, mock, test } from 'bun:test'

const dashboardApi = {}
const usersApi = {}
const rolesApi = {}
const permissionsApi = {}
const auditLogsApi = {}
const notificationsApi = {}
const teamsApi = {}
const modelsApi = {}
const siteSettingsApi = {}
const ssoApi = {}
const conversationsApi = {}
const adminToolsApi = {}
const adminSkillsApi = {}
const adminAgentsApi = {}
const adminWorkflowsApi = {}
const observabilityApi = {}

mock.module('./dashboard', () => ({ dashboardApi }))
mock.module('./users', () => ({ usersApi }))
mock.module('./roles', () => ({ rolesApi, permissionsApi }))
mock.module('./audit-logs', () => ({ auditLogsApi }))
mock.module('./notifications', () => ({ notificationsApi }))
mock.module('../teams', () => ({ teamsApi }))
mock.module('./models', () => ({ modelsApi }))
mock.module('./site-settings', () => ({ siteSettingsApi }))
mock.module('./sso', () => ({ ssoApi }))
mock.module('./conversations', () => ({ conversationsApi }))
mock.module('./tools', () => ({ adminToolsApi }))
mock.module('./skills', () => ({ adminSkillsApi }))
mock.module('./agents', () => ({ adminAgentsApi }))
mock.module('./workflows', () => ({ adminWorkflowsApi }))
mock.module('./observability', () => ({ observabilityApi }))

const api = await import('./index')

test('exports the admin API clients without changing their identities', () => {
  expect(api).toMatchObject({
    dashboardApi,
    usersApi,
    rolesApi,
    permissionsApi,
    auditLogsApi,
    notificationsApi,
    teamsApi,
    modelsApi,
    siteSettingsApi,
    ssoApi,
    conversationsApi,
    adminToolsApi,
    adminSkillsApi,
    adminAgentsApi,
    adminWorkflowsApi,
    observabilityApi,
  })
})
