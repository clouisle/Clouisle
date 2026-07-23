import { afterAll, beforeEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from './client'
import { toolsApi } from './tools'

const get = spyOn(api, 'get').mockResolvedValue(undefined as never)
const post = spyOn(api, 'post').mockResolvedValue(undefined as never)
const put = spyOn(api, 'put').mockResolvedValue(undefined as never)
const del = spyOn(api, 'delete').mockResolvedValue(undefined as never)

beforeEach(() => {
  get.mockClear()
  post.mockClear()
  put.mockClear()
  del.mockClear()
})

afterAll(() => {
  get.mockRestore()
  post.mockRestore()
  put.mockRestore()
  del.mockRestore()
})

describe('toolsApi', () => {
  it('serializes defaults and repeated list filters', async () => {
    await toolsApi.listPage()
    expect(get).toHaveBeenLastCalledWith('/tools?page=1&page_size=10')

    await toolsApi.listPage({
      page: 3,
      pageSize: 25,
      search: 'data source',
      type: ['builtin', 'custom'],
      category: ['search'],
      status: ['enabled', 'disabled'],
      team_id: ['team-1'],
      creator: ['alice', 'bob'],
    })

    const url = get.mock.calls.at(-1)?.[0] as string
    const query = new URL(url, 'https://example.test').searchParams
    expect(Object.fromEntries(query.entries())).toEqual({
      page: '3',
      page_size: '25',
      search: 'data source',
      type: 'custom',
      category: 'search',
      status: 'disabled',
      team_id: 'team-1',
      creator: 'bob',
    })
    expect(query.getAll('type')).toEqual(['builtin', 'custom'])
    expect(query.getAll('status')).toEqual(['enabled', 'disabled'])
    expect(query.getAll('creator')).toEqual(['alice', 'bob'])
  })

  it('uses team params for team-scoped reads and supports absent optional params', async () => {
    await toolsApi.list('team-1')
    await toolsApi.listFileParsers('team-1')
    await toolsApi.getByName('lookup', 'team-1')
    await toolsApi.getByName('lookup')
    await toolsApi.listSharedTools('team-1')

    expect(get.mock.calls).toEqual([
      ['/tools/legacy', { params: { team_id: 'team-1' } }],
      ['/tools/file-parsers', { params: { team_id: 'team-1' } }],
      ['/tools/name/lookup', { params: { team_id: 'team-1' } }],
      ['/tools/name/lookup', { params: {} }],
      ['/tools/shared-with-me', { params: { team_id: 'team-1' } }],
    ])
  })

  it('maps representative reads and CRUD actions to their routes', async () => {
    const createInput = { name: 'lookup', display_name: 'Lookup', description: 'Find data' }
    const updateInput = { display_name: 'New lookup' }

    await toolsApi.getFilterOptions()
    await toolsApi.listBuiltin()
    await toolsApi.getById('tool-1')
    await toolsApi.create('team-1', createInput)
    await toolsApi.update('tool-1', updateInput)
    await toolsApi.delete('tool-1')
    await toolsApi.toggle('tool-1')
    await toolsApi.duplicate('tool-1')

    expect(get.mock.calls).toEqual([
      ['/tools/filters'],
      ['/tools/builtin'],
      ['/tools/id/tool-1'],
    ])
    expect(post.mock.calls).toEqual([
      ['/tools', createInput, { params: { team_id: 'team-1' } }],
      ['/tools/tool-1/toggle'],
      ['/tools/tool-1/duplicate'],
    ])
    expect(put).toHaveBeenCalledWith('/tools/tool-1', updateInput)
    expect(del).toHaveBeenCalledWith('/tools/tool-1')
  })

  it('applies execution timeouts and removes client-only timeout from code payloads', async () => {
    const toolRequest = { name: 'lookup', parameters: { query: 'hello' } }
    await toolsApi.test(toolRequest, 'team-1')
    await toolsApi.test(toolRequest)
    await toolsApi.executeCode({ language: 'python', code: 'print(1)', client_timeout_ms: 4500 })
    await toolsApi.executeCode({ language: 'javascript', code: 'return 1' })

    expect(post.mock.calls).toEqual([
      ['/tools/test', toolRequest, { params: { team_id: 'team-1' }, timeout: 120000 }],
      ['/tools/test', toolRequest, { params: {}, timeout: 120000 }],
      ['/tools/execute-code', { language: 'python', code: 'print(1)' }, { timeout: 4500 }],
      ['/tools/execute-code', { language: 'javascript', code: 'return 1' }, { timeout: 120000 }],
    ])
  })

  it('shapes MCP and configuration payloads with optional team params', async () => {
    const mcpConfig = { transport: 'http' as const, url: 'https://mcp.test' }
    const credentials = { token: 'secret' }

    await toolsApi.listMcpTools(mcpConfig)
    await toolsApi.listConfigs('team-1')
    await toolsApi.getConfig('lookup')
    await toolsApi.createConfig('lookup', credentials, 'team-1')
    await toolsApi.updateConfig('lookup', credentials)
    await toolsApi.deleteConfig('lookup', 'team-1')

    expect(post.mock.calls).toEqual([
      ['/tools/mcp/list-tools', { mcp_config: mcpConfig }],
      ['/tools/config', { tool_name: 'lookup', credentials }, { params: { team_id: 'team-1' } }],
    ])
    expect(get.mock.calls).toEqual([
      ['/tools/config', { params: { team_id: 'team-1' } }],
      ['/tools/config/lookup', { params: {} }],
    ])
    expect(put).toHaveBeenCalledWith('/tools/config/lookup', { credentials }, { params: {} })
    expect(del).toHaveBeenCalledWith('/tools/config/lookup', { params: { team_id: 'team-1' } })
  })

  it('maps share, list, and unshare operations', async () => {
    const share = { team_id: 'team-2', permission: 'execute' as const }
    await toolsApi.shareTool('tool-1', share)
    await toolsApi.listToolShares('tool-1')
    await toolsApi.unshareTool('tool-1', 'team-2')

    expect(post).toHaveBeenCalledWith('/tools/tool-1/share', share)
    expect(get).toHaveBeenCalledWith('/tools/tool-1/shares')
    expect(del).toHaveBeenCalledWith('/tools/tool-1/share/team-2')
  })

  it('returns API results and propagates client errors unchanged', async () => {
    const result = { id: 'tool-1' }
    get.mockResolvedValueOnce(result)
    expect(await toolsApi.getById('tool-1')).toBe(result)

    const error = new Error('request failed')
    post.mockRejectedValueOnce(error)
    await expect(toolsApi.duplicate('tool-1')).rejects.toBe(error)
  })
})
