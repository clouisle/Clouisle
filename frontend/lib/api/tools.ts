import { api } from './client'

// ============ Types ============

export type ToolType = 'builtin' | 'custom' | 'mcp'

export type CustomToolType = 'http' | 'code'

export type ToolCategory =
  | 'time'
  | 'math'
  | 'search'
  | 'web'
  | 'file'
  | 'code'
  | 'api'
  | 'data'
  | 'other'

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface ToolParameter {
  name: string
  type: string
  description?: string
  required: boolean
  enum?: string[]
  default?: unknown
}

export interface HttpConfig {
  method: HttpMethod
  url: string
  headers?: Record<string, string>
  query_params?: Record<string, string>
  body_template?: string
  timeout?: number
  response_path?: string
}

export interface CodeConfig {
  language: 'javascript' | 'python'
  code: string
  dependencies?: string[]
}

export type McpTransportType = 'stdio' | 'sse' | 'http'

export interface McpConfig {
  transport: McpTransportType
  // stdio 配置
  command?: string
  args?: string[]
  env?: Record<string, string>
  // SSE/HTTP 配置
  url?: string
  headers?: Record<string, string>
}

export interface Tool {
  id?: string
  name: string
  display_name: string
  description: string
  type: ToolType
  category: ToolCategory
  icon?: string
  parameters: ToolParameter[]
  is_enabled: boolean
  requires_config: boolean
  config_fields: string[]
  custom_type?: CustomToolType
  http_config?: HttpConfig
  code_config?: CodeConfig
  mcp_config?: McpConfig
  team_id?: string
  created_by_name?: string
}

export interface ToolDetail extends Tool {
  created_at?: string
  updated_at?: string
}

export interface ToolListResponse {
  builtin: Tool[]
  custom: Tool[]
  mcp: Tool[]
}

export interface ToolCreateInput {
  name: string
  display_name: string
  description: string
  icon?: string
  category?: ToolCategory
  type?: ToolType
  custom_type?: CustomToolType
  parameters?: ToolParameter[]
  http_config?: HttpConfig
  code_config?: CodeConfig
  mcp_config?: McpConfig
  credentials?: Record<string, string>
  is_enabled?: boolean
}

export interface ToolUpdateInput {
  name?: string
  display_name?: string
  description?: string
  icon?: string
  category?: ToolCategory
  type?: ToolType
  custom_type?: CustomToolType
  parameters?: ToolParameter[]
  http_config?: HttpConfig
  code_config?: CodeConfig
  mcp_config?: McpConfig
  credentials?: Record<string, string>
  is_enabled?: boolean
}

export interface ToolExecuteRequest {
  name: string
  arguments: Record<string, unknown>
}

export interface ToolExecuteResponse {
  name: string
  success: boolean
  result?: unknown
  error?: string
  duration_ms?: number
}

export interface CodeExecuteRequest {
  language: string
  code: string
  params?: Record<string, unknown>
  timeout?: number
}

export interface CodeExecuteResponse {
  success: boolean
  result?: unknown
  error?: string
  logs?: string
  duration_ms?: number
}

// ============ MCP Types ============

export interface McpToolInfo {
  name: string
  description?: string
  parameters: Record<string, unknown>
}

export interface McpToolsListResponse {
  tools: McpToolInfo[]
  server_name?: string
  server_version?: string
}

// ============ API Functions ============

export const toolsApi = {
  /**
   * 获取所有工具（内置 + 自定义 + MCP）
   */
  list: async (teamId: string): Promise<ToolListResponse> => {
    return api.get<ToolListResponse>('/tools', { params: { team_id: teamId } })
  },

  /**
   * 获取所有内置工具
   */
  listBuiltin: async (): Promise<Tool[]> => {
    return api.get<Tool[]>('/tools/builtin')
  },

  /**
   * 根据名称获取工具
   */
  getByName: async (name: string, teamId?: string): Promise<Tool> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.get<Tool>(`/tools/name/${name}`, { params })
  },

  /**
   * 根据 ID 获取工具详情
   */
  getById: async (id: string): Promise<ToolDetail> => {
    return api.get<ToolDetail>(`/tools/id/${id}`)
  },

  /**
   * 创建自定义工具
   */
  create: async (teamId: string, data: ToolCreateInput): Promise<ToolDetail> => {
    return api.post<ToolDetail>('/tools', data, { params: { team_id: teamId } })
  },

  /**
   * 更新工具
   */
  update: async (id: string, data: ToolUpdateInput): Promise<ToolDetail> => {
    return api.put<ToolDetail>(`/tools/${id}`, data)
  },

  /**
   * 删除工具
   */
  delete: async (id: string): Promise<void> => {
    return api.delete(`/tools/${id}`)
  },

  /**
   * 切换工具启用状态
   */
  toggle: async (id: string): Promise<ToolDetail> => {
    return api.post<ToolDetail>(`/tools/${id}/toggle`)
  },

  /**
   * 复制工具
   */
  duplicate: async (id: string): Promise<ToolDetail> => {
    return api.post<ToolDetail>(`/tools/${id}/duplicate`)
  },

  /**
   * 测试执行工具
   */
  test: async (request: ToolExecuteRequest, teamId?: string): Promise<ToolExecuteResponse> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.post<ToolExecuteResponse>('/tools/test', request, { params })
  },

  /**
   * 直接执行代码（不需要保存工具）
   */
  executeCode: async (request: CodeExecuteRequest): Promise<CodeExecuteResponse> => {
    return api.post<CodeExecuteResponse>('/tools/execute-code', request)
  },

  /**
   * 获取 MCP 服务器的工具列表
   */
  listMcpTools: async (mcpConfig: McpConfig): Promise<McpToolsListResponse> => {
    return api.post<McpToolsListResponse>('/tools/mcp/list-tools', { mcp_config: mcpConfig })
  },
}
