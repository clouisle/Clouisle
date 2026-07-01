import { api } from './client'
import type { PageData } from './users'

// ============ Types ============

export type ToolType = 'builtin' | 'custom' | 'mcp' | 'skill'

export type CustomToolType = 'http' | 'code'

export const PRESET_TOOL_CATEGORIES = [
  'time',
  'math',
  'search',
  'web',
  'file',
  'code',
  'sandbox',
  'api',
  'data',
  'other',
] as const

export type PresetToolCategory = (typeof PRESET_TOOL_CATEGORIES)[number]
export type ToolCategory = string

export function isPresetToolCategory(category: string): category is PresetToolCategory {
  return (PRESET_TOOL_CATEGORIES as readonly string[]).includes(category)
}

export type ToolSharePermission = 'read_only' | 'read_execute'

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
  // 新增：支持文件上传
  content_type?: 'application/json' | 'multipart/form-data' | 'application/x-www-form-urlencoded'
  form_fields?: FormField[]  // multipart 时的表单字段
}

// 表单字段（用于 multipart/form-data）
export interface FormField {
  name: string       // 字段名
  type: 'text' | 'file'  // 字段类型
  value?: string     // 文本值或变量引用 {{varName}}
}

export interface SandboxArtifactConfig {
  path: string
  optional?: boolean
  description?: string
  file_type?: string
  size?: number
  checksum?: string
  content_type?: string
  storage_path?: string
  url?: string
  filename?: string
}

export interface SandboxLimitsConfig {
  timeout_seconds?: number
  disk_mb?: number
  max_stdout_kb?: number
  max_stderr_kb?: number
}

export interface CodeConfig {
  language: 'javascript' | 'python'
  code: string
  command?: string[]
  python_packages?: string[]
  js_packages?: string[]
  python_package_index_url?: string
  node_package_registry_url?: string
  artifacts?: SandboxArtifactConfig[]
  limits?: SandboxLimitsConfig
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
  created_by_id?: string | null
  created_by_name?: string
  // 工具共享相关字段
  is_owned?: boolean
  owner_team_id?: string
  owner_team_name?: string
  share_permission?: ToolSharePermission
  shared_with_count?: number
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

export interface ToolFilterOption {
  value: string
  label: string
}

export interface ToolFilterOptions {
  types: ToolFilterOption[]
  categories: ToolFilterOption[]
  statuses: ToolFilterOption[]
  teams: ToolFilterOption[]
  creators: ToolFilterOption[]
}

export interface ToolListQueryParams {
  page?: number
  pageSize?: number
  search?: string
  type?: string[]
  category?: string[]
  status?: string[]
  team_id?: string[]
  creator?: string[]
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
  logs?: string
  artifacts?: SandboxArtifactConfig[]
  duration_ms?: number
}

export interface CodeExecuteRequest {
  language: string
  code: string
  params?: Record<string, unknown>
  timeout?: number
  client_timeout_ms?: number
  command?: string[]
  python_packages?: string[]
  js_packages?: string[]
  python_package_index_url?: string
  node_package_registry_url?: string
  artifacts?: SandboxArtifactConfig[]
  limits?: SandboxLimitsConfig
}

export interface CodeExecuteResponse {
  success: boolean
  result?: unknown
  error?: string
  logs?: string
  artifacts?: SandboxArtifactConfig[]
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

export interface ToolConfig {
  id: string
  tool_name: string
  team_id?: string
  credentials: Record<string, string>
  created_at: string
  updated_at: string
}

// ============ Tool Sharing Types ============

export interface ToolShareInput {
  team_id: string
  permission: ToolSharePermission
}

export interface ToolShare {
  id: string
  tool_id: string
  tool_name: string
  tool_display_name: string
  shared_with_team_id: string
  shared_with_team_name: string
  permission: ToolSharePermission
  shared_by_id: string
  shared_by_name: string
  shared_at: string
}

export interface ToolShareListResponse {
  shares: ToolShare[]
  total: number
}

// ============ API Functions ============

export const toolsApi = {
  /**
   * 获取单个团队的工具列表（兼容现有平台页）
   */
  list: async (teamId: string): Promise<ToolListResponse> => {
    return api.get<ToolListResponse>('/tools/legacy', { params: { team_id: teamId } })
  },

  /**
   * 获取工具分页列表（dashboard）
   */
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

    return api.get<PageData<Tool>>(`/tools?${queryParams.toString()}`)
  },

  getFilterOptions: async (): Promise<ToolFilterOptions> =>
    api.get<ToolFilterOptions>('/tools/filters'),

  /**
   * 获取所有内置工具
   */
  listBuiltin: async (): Promise<Tool[]> => {
    return api.get<Tool[]>('/tools/builtin')
  },

  /**
   * 获取可用的文件解析器列表
   */
  listFileParsers: async (teamId: string): Promise<Tool[]> => {
    return api.get<Tool[]>('/tools/file-parsers', { params: { team_id: teamId } })
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
    return api.post<ToolExecuteResponse>('/tools/test', request, {
      params,
      timeout: 120000,
    })
  },

  /**
   * 直接执行代码（不需要保存工具）
   */
  executeCode: async (request: CodeExecuteRequest): Promise<CodeExecuteResponse> => {
    const { client_timeout_ms, ...payload } = request
    return api.post<CodeExecuteResponse>('/tools/execute-code', payload, {
      timeout: client_timeout_ms ?? 120000,
    })
  },

  /**
   * 获取 MCP 服务器的工具列表
   */
  listMcpTools: async (mcpConfig: McpConfig): Promise<McpToolsListResponse> => {
    return api.post<McpToolsListResponse>('/tools/mcp/list-tools', { mcp_config: mcpConfig })
  },

  // ============ Tool Configuration Management ============

  /**
   * 获取工具配置列表
   */
  listConfigs: async (teamId?: string): Promise<ToolConfig[]> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.get<ToolConfig[]>('/tools/config', { params })
  },

  /**
   * 获取指定工具的配置
   */
  getConfig: async (toolName: string, teamId?: string): Promise<ToolConfig> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.get<ToolConfig>(`/tools/config/${toolName}`, { params })
  },

  /**
   * 创建工具配置
   */
  createConfig: async (
    toolName: string,
    credentials: Record<string, string>,
    teamId?: string
  ): Promise<ToolConfig> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.post<ToolConfig>('/tools/config', { tool_name: toolName, credentials }, { params })
  },

  /**
   * 更新工具配置
   */
  updateConfig: async (
    toolName: string,
    credentials: Record<string, string>,
    teamId?: string
  ): Promise<ToolConfig> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.put<ToolConfig>(`/tools/config/${toolName}`, { credentials }, { params })
  },

  /**
   * 删除工具配置
   */
  deleteConfig: async (toolName: string, teamId?: string): Promise<void> => {
    const params = teamId ? { team_id: teamId } : {}
    return api.delete(`/tools/config/${toolName}`, { params })
  },

  // ============ Tool Sharing Management ============

  /**
   * 共享工具给其他团队
   */
  shareTool: async (toolId: string, data: ToolShareInput): Promise<ToolShare> => {
    return api.post<ToolShare>(`/tools/${toolId}/share`, data)
  },

  /**
   * 获取工具的共享列表
   */
  listToolShares: async (toolId: string): Promise<ToolShareListResponse> => {
    return api.get<ToolShareListResponse>(`/tools/${toolId}/shares`)
  },

  /**
   * 取消工具共享
   */
  unshareTool: async (toolId: string, teamId: string): Promise<void> => {
    return api.delete(`/tools/${toolId}/share/${teamId}`)
  },

  /**
   * 获取共享给当前团队的工具
   */
  listSharedTools: async (teamId: string): Promise<ToolListResponse> => {
    return api.get<ToolListResponse>('/tools/shared-with-me', { params: { team_id: teamId } })
  },
}
