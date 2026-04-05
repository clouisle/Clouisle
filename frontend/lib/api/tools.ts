import { api } from './client'
import type { PageData } from './users'

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

type BuiltinToolI18n = {
  zh: {
    display_name: string
    description: string
    parameters?: Record<string, string>
  }
  en: {
    display_name: string
    description: string
    parameters?: Record<string, string>
  }
}

const BUILTIN_TOOL_I18N: Record<string, BuiltinToolI18n> = {
  get_current_time: {
    zh: {
      display_name: '获取当前时间',
      description: '获取当前时间。返回指定时区的当前日期、时间、星期和时间戳。',
      parameters: {
        timezone_name: "时区名称，如 'UTC', 'Asia/Shanghai', 'America/New_York', 'Europe/London'。默认为 UTC。",
      },
    },
    en: {
      display_name: 'Get Current Time',
      description:
        'Get the current time. Returns the date, time, weekday, and timestamp for a specified timezone.',
      parameters: {
        timezone_name:
          "Timezone name, e.g., 'UTC', 'Asia/Shanghai', 'America/New_York', 'Europe/London'. Default is UTC.",
      },
    },
  },
  format_datetime: {
    zh: {
      display_name: '格式化日期时间',
      description: '格式化日期时间。将时间戳转换为指定格式的字符串。',
      parameters: {
        timestamp: 'Unix 时间戳（秒），不提供则使用当前时间',
        format_string: "Python strftime 格式字符串，如 '%Y-%m-%d %H:%M:%S'",
        timezone_name: '时区名称，默认为 UTC',
      },
    },
    en: {
      display_name: 'Format DateTime',
      description: 'Format a datetime. Convert a timestamp to a formatted string.',
      parameters: {
        timestamp: 'Unix timestamp (seconds). If omitted, uses current time.',
        format_string: "Python strftime format string, e.g. '%Y-%m-%d %H:%M:%S'",
        timezone_name: 'Timezone name. Default is UTC.',
      },
    },
  },
  calculate: {
    zh: {
      display_name: '计算器',
      description:
        '计算数学表达式。支持基本运算（+, -, *, /, //, %, **）和数学函数（sqrt, sin, cos, tan, log, exp, abs, round, min, max, floor, ceil）以及常量（pi, e）。',
      parameters: {
        expression: "数学表达式，如 '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)'",
      },
    },
    en: {
      display_name: 'Calculator',
      description:
        'Evaluate math expressions. Supports basic operators (+, -, *, /, //, %, **), math functions (sqrt, sin, cos, tan, log, exp, abs, round, min, max, floor, ceil), and constants (pi, e).',
      parameters: {
        expression: "Math expression, e.g. '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)'",
      },
    },
  },
  unit_convert: {
    zh: {
      display_name: '单位转换',
      description:
        '单位转换。支持长度（m, km, cm, mm, mi, yd, ft, in）、重量（kg, g, mg, lb, oz, t）、温度（c, f, k）、面积（m2, km2, ha, acre）、体积（l, ml, m3, gal）、时间（s, ms, min, h, d, wk）、数据（b, kb, mb, gb, tb）。',
      parameters: {
        value: '要转换的数值',
        from_unit: '源单位',
        to_unit: '目标单位',
      },
    },
    en: {
      display_name: 'Unit Converter',
      description:
        'Convert units. Supports length (m, km, cm, mm, mi, yd, ft, in), weight (kg, g, mg, lb, oz, t), temperature (c, f, k), area (m2, km2, ha, acre), volume (l, ml, m3, gal), time (s, ms, min, h, d, wk), and data (b, kb, mb, gb, tb).',
      parameters: {
        value: 'Value to convert',
        from_unit: 'Source unit',
        to_unit: 'Target unit',
      },
    },
  },
  web_search: {
    zh: {
      display_name: '网页搜索',
      description: '搜索网页。使用搜索引擎查找相关信息。当需要获取最新信息、查找事实或研究某个话题时使用此工具。',
      parameters: {
        query: '搜索关键词或问题',
        num_results: '返回结果数量，默认 5，最大 10',
      },
    },
    en: {
      display_name: 'Web Search',
      description:
        'Search the web. Use a search engine to find relevant information when you need up-to-date facts or research a topic.',
      parameters: {
        query: 'Search keywords or question',
        num_results: 'Number of results. Default 5, max 10.',
      },
    },
  },
  fetch_webpage: {
    zh: {
      display_name: '获取网页内容',
      description: '获取网页内容。读取指定 URL 的网页文本内容。用于深入阅读搜索结果中感兴趣的页面。',
      parameters: {
        url: '要获取的网页 URL',
        max_length: '返回内容的最大字符数，默认 5000',
      },
    },
    en: {
      display_name: 'Fetch Webpage',
      description:
        'Fetch webpage content. Read the text content of a URL for deeper inspection of search results.',
      parameters: {
        url: 'Webpage URL to fetch',
        max_length: 'Max characters to return. Default 5000.',
      },
    },
  },
  markitdown: {
    zh: {
      display_name: 'MarkItDown 文件解析',
      description:
        '解析文件内容。将 PDF、Word、Excel、PPT 等文档转换为文本。当用户上传文件并希望你分析其内容时使用此工具。支持的格式：PDF、Word (.docx/.doc)、Excel (.xlsx/.xls)、PowerPoint (.pptx/.ppt)、文本文件 (.txt/.md/.csv/.json/.html/.xml)。',
      parameters: {
        files_url: '文件 URL 列表。每个 URL 指向一个需要解析的文件。',
      },
    },
    en: {
      display_name: 'MarkItDown File Parser',
      description:
        'Parse file content. Convert PDF, Word, Excel, and PowerPoint documents to text. Use this tool when a user uploads a file and wants you to analyze its content. Supported formats: PDF, Word (.docx/.doc), Excel (.xlsx/.xls), PowerPoint (.pptx/.ppt), text files (.txt/.md/.csv/.json/.html/.xml).',
      parameters: {
        files_url: 'List of file URLs. Each URL points to a file to parse.',
      },
    },
  },
  generate_image: {
    zh: {
      display_name: '生成图片',
      description:
        '生成图片。根据提示词调用生图模型，可选设置尺寸、数量和参考图。',
      parameters: {
        prompt: '图片生成提示词',
        width: '输出图片宽度',
        height: '输出图片高度',
        num_images: '生成图片数量',
        style: '可选风格提示',
        quality: '可选质量档位',
        negative_prompt: '可选负面提示词',
        seed: '可选随机种子',
        images: '可选参考图数组',
        extra_params: '可选供应商特定参数',
      },
    },
    en: {
      display_name: 'Generate Image',
      description:
        'Generate images from a prompt. Supports optional size, count, and reference images.',
      parameters: {
        prompt: 'Image generation prompt',
        width: 'Output image width',
        height: 'Output image height',
        num_images: 'Number of images to generate',
        style: 'Optional style hint',
        quality: 'Optional quality tier',
        negative_prompt: 'Optional negative prompt',
        seed: 'Optional random seed',
        images: 'Optional reference image array',
        extra_params: 'Optional provider-specific parameters',
      },
    },
  },
  generate_video: {
    zh: {
      display_name: '生成视频',
      description:
        '生成视频。根据提示词调用文生视频模型，可选设置时长、宽高比和风格。',
      parameters: {
        prompt: '视频生成提示词',
        duration: '生成视频时长（秒）',
        aspect_ratio: '输出宽高比',
        motion_intensity: '运动强度（0-1）',
        camera_motion: '镜头运动描述',
        style: '可选风格提示',
        seed: '可选随机种子',
        extra_params: '可选供应商特定参数',
      },
    },
    en: {
      display_name: 'Generate Video',
      description:
        'Generate a video clip from a prompt. Supports optional duration, aspect ratio, and style.',
      parameters: {
        prompt: 'Video generation prompt',
        duration: 'Video duration in seconds',
        aspect_ratio: 'Output aspect ratio',
        motion_intensity: 'Motion intensity from 0 to 1',
        camera_motion: 'Camera motion description',
        style: 'Optional style hint',
        seed: 'Optional random seed',
        extra_params: 'Optional provider-specific parameters',
      },
    },
  },
}

const getLocale = (): string => {
  if (typeof document === 'undefined') return 'en'
  const locale = document.cookie
    .split('; ')
    .find((row) => row.startsWith('locale='))
    ?.split('=')[1]
  return locale || 'en'
}

const applyToolDescriptionOverride = <T extends Tool>(tool: T): T => {
  if (tool.type === 'builtin') {
    const override = BUILTIN_TOOL_I18N[tool.name]
    if (override) {
      const locale = getLocale()
      const localized = override[locale as keyof BuiltinToolI18n] || override.en
      const parameters =
        localized.parameters && tool.parameters?.length
          ? tool.parameters.map((param) => ({
              ...param,
              description: localized.parameters?.[param.name] || param.description,
            }))
          : tool.parameters
      return {
        ...tool,
        display_name: localized.display_name,
        description: localized.description,
        parameters,
      }
    }
  }
  return tool
}

const applyToolListOverrides = (tools: Tool[]): Tool[] =>
  tools.map((tool) => applyToolDescriptionOverride(tool))

// ============ API Functions ============

export const toolsApi = {
  /**
   * 获取单个团队的工具列表（兼容现有平台页）
   */
  list: async (teamId: string): Promise<ToolListResponse> => {
    const response = await api.get<ToolListResponse>('/tools/legacy', { params: { team_id: teamId } })
    return {
      ...response,
      builtin: applyToolListOverrides(response.builtin),
      custom: applyToolListOverrides(response.custom),
      mcp: applyToolListOverrides(response.mcp),
    }
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

    const response = await api.get<PageData<Tool>>(`/tools?${queryParams.toString()}`)
    return {
      ...response,
      items: applyToolListOverrides(response.items),
    }
  },

  getFilterOptions: async (): Promise<ToolFilterOptions> =>
    api.get<ToolFilterOptions>('/tools/filters'),

  /**
   * 获取所有内置工具
   */
  listBuiltin: async (): Promise<Tool[]> => {
    const tools = await api.get<Tool[]>('/tools/builtin')
    return applyToolListOverrides(tools)
  },

  /**
   * 获取可用的文件解析器列表
   */
  listFileParsers: async (teamId: string): Promise<Tool[]> => {
    const tools = await api.get<Tool[]>('/tools/file-parsers', { params: { team_id: teamId } })
    return applyToolListOverrides(tools)
  },

  /**
   * 根据名称获取工具
   */
  getByName: async (name: string, teamId?: string): Promise<Tool> => {
    const params = teamId ? { team_id: teamId } : {}
    const tool = await api.get<Tool>(`/tools/name/${name}`, { params })
    return applyToolDescriptionOverride(tool)
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
