import { api } from '../client'
import type { PageData } from '../users'
import type {
  CodeExecuteRequest,
  CodeExecuteResponse,
  McpConfig,
  McpToolsListResponse,
  Tool,
  ToolConfig,
  ToolCreateInput,
  ToolDetail,
  ToolExecuteRequest,
  ToolExecuteResponse,
  ToolFilterOptions,
  ToolListQueryParams,
  ToolShare,
  ToolShareInput,
  ToolShareListResponse,
  ToolUpdateInput,
} from '../tools'

export const adminToolsApi = {
  listPage: async (params: ToolListQueryParams = {}): Promise<PageData<Tool>> => {
    const { page = 1, pageSize = 10, search, type, category, status, team_id, creator } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('search', search)
    type?.forEach((value) => queryParams.append('type', value))
    category?.forEach((value) => queryParams.append('category', value))
    status?.forEach((value) => queryParams.append('status', value))
    team_id?.forEach((value) => queryParams.append('team_id', value))
    creator?.forEach((value) => queryParams.append('creator', value))
    return api.get<PageData<Tool>>(`/admin/tools?${queryParams.toString()}`)
  },

  getFilterOptions: async (): Promise<ToolFilterOptions> =>
    api.get<ToolFilterOptions>('/admin/tools/filters'),

  getById: async (id: string): Promise<ToolDetail> =>
    api.get<ToolDetail>(`/admin/tools/id/${id}`),

  create: async (teamId: string, data: ToolCreateInput): Promise<ToolDetail> =>
    api.post<ToolDetail>('/admin/tools', data, { params: { team_id: teamId } }),

  update: async (id: string, data: ToolUpdateInput): Promise<ToolDetail> =>
    api.put<ToolDetail>(`/admin/tools/${id}`, data),

  delete: async (id: string): Promise<void> => {
    await api.delete(`/admin/tools/${id}`)
  },

  toggle: async (id: string): Promise<ToolDetail> =>
    api.post<ToolDetail>(`/admin/tools/${id}/toggle`),

  duplicate: async (id: string): Promise<ToolDetail> =>
    api.post<ToolDetail>(`/admin/tools/${id}/duplicate`),

  test: async (request: ToolExecuteRequest, teamId?: string): Promise<ToolExecuteResponse> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.post<ToolExecuteResponse>('/admin/tools/test', request, {
      params,
      timeout: 120000,
    })
  },

  executeCode: async (request: CodeExecuteRequest): Promise<CodeExecuteResponse> => {
    const { client_timeout_ms, ...payload } = request
    return api.post<CodeExecuteResponse>('/admin/tools/execute-code', payload, {
      timeout: client_timeout_ms ?? 120000,
    })
  },

  listMcpTools: async (mcpConfig: McpConfig): Promise<McpToolsListResponse> =>
    api.post<McpToolsListResponse>('/admin/tools/mcp/list-tools', { mcp_config: mcpConfig }),

  listConfigs: async (teamId?: string): Promise<ToolConfig[]> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.get<ToolConfig[]>('/admin/tools/config', { params })
  },

  getConfig: async (toolName: string, teamId?: string): Promise<ToolConfig> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.get<ToolConfig>(`/admin/tools/config/${toolName}`, { params })
  },

  createConfig: async (
    toolName: string,
    credentials: Record<string, string>,
    teamId?: string
  ): Promise<ToolConfig> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.post<ToolConfig>('/admin/tools/config', { tool_name: toolName, credentials }, { params })
  },

  updateConfig: async (
    toolName: string,
    credentials: Record<string, string>,
    teamId?: string
  ): Promise<ToolConfig> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.put<ToolConfig>(`/admin/tools/config/${toolName}`, { credentials }, { params })
  },

  deleteConfig: async (toolName: string, teamId?: string): Promise<void> => {
    const params = teamId ? { team_id: teamId } : {}
    await api.delete(`/admin/tools/config/${toolName}`, { params })
  },

  shareTool: async (toolId: string, data: ToolShareInput): Promise<ToolShare> =>
    api.post<ToolShare>(`/admin/tools/${toolId}/share`, data),

  listToolShares: async (toolId: string): Promise<ToolShareListResponse> =>
    api.get<ToolShareListResponse>(`/admin/tools/${toolId}/shares`),

  unshareTool: async (toolId: string, teamId: string): Promise<void> => {
    await api.delete(`/admin/tools/${toolId}/share/${teamId}`)
  },
}
