import { beforeEach, expect, mock, test } from 'bun:test'

const calls: Array<{ method: string; url: string; body?: unknown }> = []
const record = (method: string) =>
  mock(async (url: string, body?: unknown) => {
    calls.push({ method, url, body })
    return []
  })

mock.module('./client', () => ({
  api: {
    get: record('get'),
    post: record('post'),
    patch: record('patch'),
    delete: record('delete'),
  },
}))

const { toolConnectionsApi } = await import('./tool-connections')

beforeEach(() => {
  calls.length = 0
})

test('tool connection list endpoints build scoped query strings', async () => {
  await toolConnectionsApi.listForTool('tool-1', { teamId: 'team-1' })
  await toolConnectionsApi.list('team-1', { toolId: 'tool-1', includeRevoked: true })
  await toolConnectionsApi.get('conn-1', 'team-1')
  await toolConnectionsApi.getOAuthStatus('conn-1', 'team-1')

  expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual([
    'get /tools/tool-1/connections?team_id=team-1&include_site=true&include_revoked=false',
    'get /tool-connections?team_id=team-1&tool_id=tool-1&include_revoked=true',
    'get /tool-connections/conn-1?team_id=team-1',
    'get /tool-connections/conn-1/oauth?team_id=team-1',
  ])
})

test('tool connection mutation endpoints forward payloads', async () => {
  await toolConnectionsApi.createForTool('tool-1', { scope: 'user', name: 'A' })
  await toolConnectionsApi.create({ scope: 'team', name: 'B' })
  await toolConnectionsApi.update('conn-1', { name: 'C' })
  await toolConnectionsApi.revoke('conn-1', 'cleanup')
  await toolConnectionsApi.startOAuth('conn-1', { redirect_path: '/app' })
  await toolConnectionsApi.disconnectOAuth('conn-1')

  expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual([
    'post /tools/tool-1/connections',
    'post /tool-connections',
    'patch /tool-connections/conn-1',
    'delete /tool-connections/conn-1?reason=cleanup',
    'post /tool-connections/conn-1/oauth/start',
    'post /tool-connections/conn-1/oauth/disconnect',
  ])
  expect(calls[0].body).toEqual({ scope: 'user', name: 'A' })
  expect(calls[4].body).toEqual({ redirect_path: '/app' })
})
