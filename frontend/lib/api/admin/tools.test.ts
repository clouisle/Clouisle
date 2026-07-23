import { afterAll, beforeEach, describe, expect, it, spyOn } from 'bun:test'
import { api } from '../client'
import { adminToolsApi } from './tools'

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

describe('adminToolsApi', () => {
  it('serializes defaults and repeated list filters', async () => {
    await adminToolsApi.listPage()
    expect(get).toHaveBeenLastCalledWith('/admin/tools?page=1&page_size=10')

    await adminToolsApi.listPage({
      page: 2,
      pageSize: 50,
      search: 'shared tool',
      type: ['builtin', 'custom'],
      category: ['search'],
      status: ['enabled'],
      team_id: ['team-1', 'team-2'],
      creator: ['alice'],
    })

    const url = get.mock.calls.at(-1)?.[0] as string
    const query = new URL(url, 'https://example.test').searchParams
    expect(query.get('page')).toBe('2')
    expect(query.get('page_size')).toBe('50')
    expect(query.get('search')).toBe('shared tool')
    expect(query.getAll('type')).toEqual(['builtin', 'custom'])
    expect(query.getAll('category')).toEqual(['search'])
    expect(query.getAll('status')).toEqual(['enabled'])
    expect(query.getAll('team_id')).toEqual(['team-1', 'team-2'])
    expect(query.getAll('creator')).toEqual(['alice'])
  })

  it('maps admin reads and CRUD actions to their routes', async () => {
    const createInput = { name: 'lookup', display_name: 'Lookup', description: 'Find data' }
    const updateInput = { is_enabled: false }

    await adminToolsApi.getFilterOptions()
    await adminToolsApi.getById('tool-1')
    await adminToolsApi.create('team-1', createInput)
    await adminToolsApi.update('tool-1', updateInput)
    await adminToolsApi.delete('tool-1')
    await adminToolsApi.toggle('tool-1')
    await adminToolsApi.duplicate('tool-1')

    expect(get.mock.calls).toEqual([
      ['/admin/tools/filters'],
      ['/admin/tools/id/tool-1'],
    ])
    expect(post.mock.calls).toEqual([
      ['/admin/tools', createInput, { params: { team_id: 'team-1' } }],
      ['/admin/tools/tool-1/toggle'],
      ['/admin/tools/tool-1/duplicate'],
    ])
    expect(put).toHaveBeenCalledWith('/admin/tools/tool-1', updateInput)
    expect(del).toHaveBeenCalledWith('/admin/tools/tool-1')
  })

  it('applies execution timeouts and removes client-only timeout from code payloads', async () => {
    const request = { name: 'lookup', parameters: {} }
    await adminToolsApi.test(request, 'team-1')
    await adminToolsApi.test(request)
    await adminToolsApi.executeCode({ language: 'python', code: 'print(1)', client_timeout_ms: 9000 })
    await adminToolsApi.executeCode({ language: 'javascript', code: 'return 1' })

    expect(post.mock.calls).toEqual([
      ['/admin/tools/test', request, { params: { team_id: 'team-1' }, timeout: 120000 }],
      ['/admin/tools/test', request, { params: {}, timeout: 120000 }],
      ['/admin/tools/execute-code', { language: 'python', code: 'print(1)' }, { timeout: 9000 }],
      ['/admin/tools/execute-code', { language: 'javascript', code: 'return 1' }, { timeout: 120000 }],
    ])
  })

  it('shapes MCP and configuration requests with optional team params', async () => {
    const mcpConfig = { transport: 'sse' as const, url: 'https://mcp.test' }
    const credentials = { api_key: 'secret' }

    await adminToolsApi.listMcpTools(mcpConfig)
    await adminToolsApi.listConfigs()
    await adminToolsApi.getConfig('lookup', 'team-1')
    await adminToolsApi.createConfig('lookup', credentials)
    await adminToolsApi.updateConfig('lookup', credentials, 'team-1')
    await adminToolsApi.deleteConfig('lookup')

    expect(post.mock.calls).toEqual([
      ['/admin/tools/mcp/list-tools', { mcp_config: mcpConfig }],
      ['/admin/tools/config', { tool_name: 'lookup', credentials }, { params: {} }],
    ])
    expect(get.mock.calls).toEqual([
      ['/admin/tools/config', { params: {} }],
      ['/admin/tools/config/lookup', { params: { team_id: 'team-1' } }],
    ])
    expect(put).toHaveBeenCalledWith(
      '/admin/tools/config/lookup',
      { credentials },
      { params: { team_id: 'team-1' } }
    )
    expect(del).toHaveBeenCalledWith('/admin/tools/config/lookup', { params: {} })
  })

  it('maps admin share operations and propagates errors', async () => {
    const share = { team_id: 'team-2', permission: 'manage' as const }
    await adminToolsApi.shareTool('tool-1', share)
    await adminToolsApi.listToolShares('tool-1')
    await adminToolsApi.unshareTool('tool-1', 'team-2')

    expect(post).toHaveBeenCalledWith('/admin/tools/tool-1/share', share)
    expect(get).toHaveBeenCalledWith('/admin/tools/tool-1/shares')
    expect(del).toHaveBeenCalledWith('/admin/tools/tool-1/share/team-2')

    const error = new Error('forbidden')
    del.mockRejectedValueOnce(error)
    await expect(adminToolsApi.delete('tool-1')).rejects.toBe(error)
  })
})
