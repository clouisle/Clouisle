import { beforeEach, expect, mock, test } from 'bun:test'

const calls: Array<{ method: string; url: string; body?: unknown }> = []
const record = (method: string) =>
  mock(async (url: string, body?: unknown) => {
    calls.push({ method, url, body })
    return { ok: true }
  })

mock.module('./client', () => ({
  api: { get: record('get'), post: record('post') },
}))

const { toolMcpApi } = await import('./tool-mcp')

beforeEach(() => {
  calls.length = 0
})

test('mcp enumeration endpoints forward scoped query parameters', async () => {
  const params = {
    teamId: 'team-1',
    connection_mode: 'team' as const,
    connection_id: 'conn-1',
    maxItems: 10,
    cursor: 'next',
    execution_id: 'exec-1',
  }
  await toolMcpApi.getCapabilities('tool-1', params)
  await toolMcpApi.listTools('tool-1', params)
  await toolMcpApi.listResources('tool-1', params)
  await toolMcpApi.listResourceTemplates('tool-1', params)
  await toolMcpApi.listPrompts('tool-1', params)

  expect(calls.map((c) => c.url)).toEqual([
    '/tools/tool-1/mcp/capabilities?team_id=team-1&connection_mode=team&connection_id=conn-1&execution_id=exec-1',
    '/tools/tool-1/mcp/tools?team_id=team-1&connection_mode=team&connection_id=conn-1&max_items=10&cursor=next&execution_id=exec-1',
    '/tools/tool-1/mcp/resources?team_id=team-1&connection_mode=team&connection_id=conn-1&max_items=10&cursor=next&execution_id=exec-1',
    '/tools/tool-1/mcp/resource-templates?team_id=team-1&connection_mode=team&connection_id=conn-1&max_items=10&cursor=next&execution_id=exec-1',
    '/tools/tool-1/mcp/prompts?team_id=team-1&connection_mode=team&connection_id=conn-1&max_items=10&cursor=next&execution_id=exec-1',
  ])
})

test('mcp resource and prompt reads post their identity', async () => {
  await toolMcpApi.readResource('tool-1', 'team-1', 'file://a', { connection_id: 'conn-1' })
  await toolMcpApi.getPrompt('tool-1', 'team-1', 'summarize', { text: 'a' })

  expect(calls).toEqual([
    {
      method: 'post',
      url: '/tools/tool-1/mcp/resources/read?team_id=team-1',
      body: { uri: 'file://a', connection_id: 'conn-1' },
    },
    {
      method: 'post',
      url: '/tools/tool-1/mcp/prompts/get?team_id=team-1',
      body: { name: 'summarize', arguments: { text: 'a' } },
    },
  ])
})
