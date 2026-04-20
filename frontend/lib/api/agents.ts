import { api, ApiError, getErrorMessage } from './client'

function getPublicStatusErrorMessage(status: number): string {
  if (status === 404) return getErrorMessage('resourceNotFound')
  if (status >= 500 && status < 600) return getErrorMessage('serverError')
  return getErrorMessage('requestFailed')
}

function resolvePublicApiErrorMessage(status: number, message: unknown): string {
  if (typeof message === 'string') {
    const trimmed = message.trim()
    if (
      trimmed
      && trimmed.length <= 200
      && !/^[a-z0-9]+(?:[._-][a-z0-9]+)+$/i.test(trimmed)
      && !trimmed.includes('\n')
      && !trimmed.includes('Traceback')
      && !trimmed.includes('Exception')
      && !trimmed.includes('HTTP ')
      && !trimmed.includes('Failed to fetch')
    ) {
      return trimmed
    }
  }

  return getPublicStatusErrorMessage(status)
}

// ============ Types ============

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface TeamInfo {
  id: string
  name: string
  avatar_url?: string | null
}

export interface CreatorInfo {
  id: string
  username: string
  avatar_url?: string | null
}

export interface ModelInfo {
  id: string
  name: string
  provider: string
  model_id: string
}

export interface KnowledgeBaseInfo {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  document_count: number
}

// ============ Tool & Variable Types ============

export interface ToolConfig {
  type: 'builtin' | 'custom' | 'mcp'
  name?: string | null
  tool_id?: string | null  // for custom tools
  server_id?: string | null  // for mcp tools
  config?: Record<string, unknown> | null
}

export type VariableType = 'text' | 'paragraph' | 'select' | 'number' | 'checkbox' | 'array' | 'object' | 'file' | 'image' | 'files' | 'images'

export interface VariableDefinition {
  name: string
  type: VariableType
  label?: string | null
  required: boolean
  hidden?: boolean
  default?: string | null
  description?: string | null
  options?: string[] | null
  min?: number | null
  max?: number | null
  maxLength?: number | null
  fileConfig?: FileParameterConfig | null
}

export interface FileParameterConfig {
  maxSize?: number        // 最大文件大小 (MB)
  accept?: string[]       // 允许的文件类型 (MIME types 或扩展名)
  maxFiles?: number       // 最大文件数量 (仅 files 类型)
}

export interface AgentKnowledgeBaseConfig {
  knowledge_base_id: string
  retrieval_top_k: number
  score_threshold: number
  search_mode: 'vector' | 'fulltext' | 'hybrid'
}

/** File parser configuration - which tool to use for parsing files */
export interface FileParserConfig {
  type: 'builtin' | 'custom'
  name?: string       // for builtin, e.g., 'markitdown'
  tool_id?: string    // for custom tools
}

export interface FileUploadConfig {
  parser?: FileParserConfig | null  // null means no parser selected
  max_file_size: number  // bytes
  max_files: number
  max_content_length: number  // characters
  truncate_strategy: 'end' | 'start' | 'middle'
  allowed_extensions: string[]
}

// ============ Agent Types ============

export type AgentStatus = 'draft' | 'published'
export type AgentVisibility = 'private' | 'team'
export type RAGMode = 'off' | 'auto' | 'agentic'

export interface AgentKnowledgeBaseOut {
  id: string
  knowledge_base: KnowledgeBaseInfo
  retrieval_top_k: number
  score_threshold: number
  search_mode: 'vector' | 'fulltext' | 'hybrid'
}

export interface MemoryConfig {
  max_memories_per_retrieval: number
  auto_extract: boolean
  importance_threshold: 'low' | 'medium' | 'high'
}

export interface ContextCompressionConfig {
  enabled: boolean
  micro_compaction_enabled: boolean
  macro_compaction_enabled: boolean
  preflight_guard_enabled: boolean
  reactive_retry_enabled: boolean
  recent_raw_turns: number
  recent_tool_turns: number
  warning_ratio: number
  auto_compact_trigger_ratio: number
  blocking_ratio: number
  compaction_policy: 'staged' | 'hard_budget_only'
  macro_on_trigger: boolean
  retention_strategy: 'recent_raw_and_tool_first'
  keep_recent_tool_results: number
  keep_recent_tool_result_minutes: number
  tool_result_compact_min_tokens: number
  session_memory_enabled: boolean
  session_memory_async_extract: boolean
  session_memory_max_tokens: number
  session_memory_min_turns: number
  session_memory_failure_threshold: number
  session_memory_cooldown_seconds: number
  legacy_compact_enabled: boolean
  legacy_compact_failure_threshold: number
  legacy_compact_cooldown_seconds: number
  output_token_reserve: number
  safety_margin_tokens: number
  summary_max_tokens: number
  drop_historical_reasoning_first: boolean
  emit_sse_events: boolean
}

export interface ImageGenerationConfig {
  default_model_ref?: string | null
  default_width: number
  default_height: number
  max_images: number
  allow_reference_images: boolean
  allowed_providers?: string[]
  require_confirmation?: boolean
}

export interface VideoGenerationConfig {
  default_model_ref?: string | null
  default_duration: number
  max_duration: number
  default_aspect_ratio: string
  poll_interval_ms: number
  poll_timeout_s: number
  allowed_providers?: string[]
  require_confirmation?: boolean
}

export interface Agent {
  id: string
  team: TeamInfo
  name: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
  model_id?: string | null
  model?: ModelInfo | null
  system_prompt?: string | null
  max_iterations: number
  tools_config: ToolConfig[]
  variables: VariableDefinition[]
  opening_message?: string | null
  suggested_questions: string[]
  knowledge_bases: AgentKnowledgeBaseOut[]
  enable_vision: boolean
  enable_file_upload: boolean
  file_upload_config?: FileUploadConfig | null
  enable_user_input_request: boolean
  enable_memory: boolean
  memory_config?: MemoryConfig | null
  context_compression_config?: ContextCompressionConfig | null
  enable_image_generation: boolean
  image_generation_config?: ImageGenerationConfig | null
  enable_video_generation: boolean
  video_generation_config?: VideoGenerationConfig | null
  rag_mode: RAGMode
  embed_config?: Record<string, unknown>
  status: AgentStatus
  visibility: AgentVisibility
  conversation_count: number
  message_count: number
  created_by?: CreatorInfo | null
  created_at: string
  updated_at: string
}

export interface AgentListItem {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
  team: TeamInfo
  model?: ModelInfo | null
  status: AgentStatus
  visibility: AgentVisibility
  conversation_count: number
  message_count: number
  created_by?: CreatorInfo | null
  created_at: string
  updated_at: string
}

export interface AgentCreateInput {
  team_id: string
  name: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
  model_id?: string | null
  system_prompt?: string | null
  max_iterations?: number
  tools_config?: ToolConfig[]
  knowledge_base_configs?: AgentKnowledgeBaseConfig[]
  variables?: VariableDefinition[]
  opening_message?: string | null
  suggested_questions?: string[]
  enable_vision?: boolean
  enable_file_upload?: boolean
  file_upload_config?: FileUploadConfig | null
  enable_user_input_request?: boolean
  enable_memory?: boolean
  memory_config?: MemoryConfig | null
  context_compression_config?: ContextCompressionConfig | null
  enable_image_generation?: boolean
  image_generation_config?: ImageGenerationConfig | null
  enable_video_generation?: boolean
  video_generation_config?: VideoGenerationConfig | null
  rag_mode?: RAGMode
  visibility?: AgentVisibility
}

export interface AgentUpdateInput {
  name?: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
  model_id?: string | null
  system_prompt?: string | null
  max_iterations?: number
  tools_config?: ToolConfig[]
  knowledge_base_configs?: AgentKnowledgeBaseConfig[]
  variables?: VariableDefinition[]
  opening_message?: string | null
  suggested_questions?: string[]
  enable_vision?: boolean
  enable_file_upload?: boolean
  file_upload_config?: FileUploadConfig | null
  enable_user_input_request?: boolean
  enable_memory?: boolean
  memory_config?: MemoryConfig | null
  context_compression_config?: ContextCompressionConfig | null
  enable_image_generation?: boolean
  image_generation_config?: ImageGenerationConfig | null
  enable_video_generation?: boolean
  video_generation_config?: VideoGenerationConfig | null
  rag_mode?: RAGMode
  embed_config?: Record<string, unknown>
  visibility?: AgentVisibility
}

export interface AgentQueryParams {
  page?: number
  pageSize?: number
  search?: string
  status?: AgentStatus
  visibility?: AgentVisibility
  teamId?: string
}

// ============ Conversation Types ============

export interface Conversation {
  id: string
  agent_id: string
  agent_name?: string | null
  agent_icon?: string | null
  title?: string | null
  variables: Record<string, unknown>
  message_count: number
  token_usage: number
  created_at: string
  updated_at: string
}

export interface ConversationListItem {
  id: string
  agent_id: string
  agent_name?: string | null
  agent_icon?: string | null
  title?: string | null
  message_count: number
  created_at: string
  updated_at: string
}

export interface ConversationUpdateInput {
  title?: string
}

// ============ Message Types ============

export type MessageRole = 'system' | 'user' | 'assistant' | 'tool'
export type MessageRoundRole = 'user_input' | 'assistant_final' | 'assistant_step' | 'tool_result'
export type MessageRoundStatus = 'completed' | 'max_iterations_reached' | 'manually_stopped' | 'error'

export interface MessageRoundStep {
  id: string
  role: MessageRole
  content: string
  tool_calls?: Record<string, unknown>[] | null
  tool_call_id?: string | null
  tool_name?: string | null
  reasoning_content?: string | null
  model_used?: string | null
  token_usage?: { prompt: number; completion: number } | null
  duration_ms?: number | null
  is_manually_stopped?: boolean
  rag_context?: Record<string, unknown>[] | null
  created_at: string
  round_id?: string | null
  round_index?: number
  round_role?: MessageRoundRole | null
  is_round_canonical?: boolean
  iteration_index?: number | null
  round_status?: MessageRoundStatus | null
}

export interface Message {
  id: string
  conversation_id: string
  role: MessageRole
  content: string
  // Attachments (for user messages)
  images?: Array<{ type: string; url: string }> | null
  file_urls?: Array<{ filename: string; url: string; size: number; mime_type: string }> | null
  // Tool calls
  tool_calls?: Record<string, unknown>[] | null
  tool_call_id?: string | null
  tool_name?: string | null
  // Reasoning (Chain of Thought)
  reasoning_content?: string | null
  // Metadata
  model_used?: string | null
  token_usage?: { prompt: number; completion: number } | null
  duration_ms?: number | null
  is_manually_stopped?: boolean
  rag_context?: Record<string, unknown>[] | null
  created_at: string
  round_id?: string | null
  round_index?: number
  round_role?: MessageRoundRole | null
  is_round_canonical?: boolean
  iteration_index?: number | null
  round_status?: MessageRoundStatus | null
  steps?: MessageRoundStep[] | null
  // Version fields
  parent_id?: string | null
  is_active?: boolean
  version_number?: number
  version_count?: number
  versions?: MessageVersion[] | null
}

export interface MessageVersion {
  id: string
  version_number: number
  is_active: boolean
  content: string
  created_at: string
}

export interface ConversationWithMessages extends Conversation {
  messages: Message[]
}

// ============ Chat Types ============

export interface ChatImageContent {
  type: 'image_url'
  url: string
}

export interface ChatFileContent {
  filename: string
  content: string
  mime_type: string
  size: number
  truncated: boolean
  original_length?: number | null
}

/** File URL for backend file parsing and injection into {{fileContent}} */
export interface ChatFileUrl {
  filename: string
  url: string
  size: number
  mime_type: string
}

export interface HistoryToolCall {
  id: string
  name: string
  arguments: Record<string, unknown> | string
}

export interface HistoryMessage {
  role: 'user' | 'assistant' | 'tool'
  content: string
  reasoning_content?: string | null
  tool_calls?: HistoryToolCall[] | null
  tool_call_id?: string | null
  tool_name?: string | null
  round_id?: string | null
  round_index?: number
  round_role?: MessageRoundRole | null
  is_round_canonical?: boolean
  iteration_index?: number | null
  round_status?: MessageRoundStatus | null
}

export interface ChatRequest {
  message: string
  images?: ChatImageContent[]
  /** @deprecated Use file_urls instead */
  files?: ChatFileContent[]
  /** File URLs for backend to parse and inject into {{fileContent}} */
  file_urls?: ChatFileUrl[]
  conversation_id?: string | null
  variables?: Record<string, unknown>
  /** Override conversation history for version switching / regeneration */
  history_override?: HistoryMessage[] | null
}

export interface ChatResponse {
  conversation_id: string
  message: Message
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number } | null
}

// SSE Event Types
export type SSEEventType =
  | 'message_start'
  | 'content_delta'
  | 'reasoning_start'
  | 'reasoning_delta'
  | 'reasoning_end'
  | 'tool_call'
  | 'tool_result'
  | 'media_result'
  | 'rag_start'
  | 'rag_context'
  | 'user_input_request'
  | 'compression_start'
  | 'compression_end'
  | 'output_truncated'
  | 'iteration_cap_reached'
  | 'message_end'
  | 'error'

export interface SSEMessageStart {
  conversation_id: string
  message_id: string
}

export interface SSEContentDelta {
  delta: string
}

export interface SSEUserInputRequest {
  question: string
  options: string[]
}

export interface SSECompression {
  stage: 'micro' | 'macro' | 'reactive_retry'
  trigger: 'proactive_threshold' | 'blocking_threshold' | 'context_length_error' | string
  pressure_level?: 'normal' | 'warning' | 'auto_compact' | 'blocking' | 'over_budget'
  before_tokens: number
  after_tokens: number
  input_budget: number
  trigger_ratio?: number
  warning_ratio?: number
  blocking_ratio?: number
  trigger_budget?: number
  hard_budget?: number
  utilization_before?: number
  utilization_after?: number
  policy_used?: string
  actions?: string[]
  retained_recent_turns?: number
  retained_tool_turns?: number
  compacted_blocks?: number
  summary_turns?: number
  reasoning_dropped?: boolean
  tool_results_trimmed?: boolean
  file_content_trimmed?: boolean
  retry_index?: number
  note?: string
}

export interface SSERagContext {
  contexts: Array<{
    kb_id: string
    kb_name: string
    document_id: string
    document_name: string
    content: string
    score: number
  }>
}

export interface SSEMessageEnd {
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  timing?: {
    first_token_ms: number | null
    duration_ms: number
    tokens_per_second: number | null
  }
}

export interface SSEIterationCapReached {
  content?: string
}

export interface SSEError {
  code: number
  msg: string
  quota_type?: string
}

export interface SSEToolCall {
  tool_call_id: string
  tool_name: string
  tool_display_name?: string
  arguments: Record<string, unknown>
}

export interface SSEToolResult {
  tool_call_id: string
  tool_name: string
  tool_display_name?: string
  result: string
  is_error?: boolean
}

export interface SSEMediaResult {
  kind: 'media.image' | 'media.video'
  success: boolean
  prompt: string
  model?: string | null
  model_ref?: string | null
  images?: Array<{
    image: {
      url?: string | null
      base64?: string | null
      file_path?: string | null
      width?: number | null
      height?: number | null
      duration?: number | null
      format?: string
    }
    revised_prompt?: string | null
    seed?: number | null
  }>
  task_id?: string | null
  status?: string
  progress?: number | null
  video?: {
    url?: string | null
    base64?: string | null
    file_path?: string | null
    duration?: number | null
    width?: number | null
    height?: number | null
    format?: string
  } | null
  estimated_time?: number | null
  requires_polling?: boolean
  poll_interval_ms?: number
  poll_timeout_s?: number
  error?: string | null
}

export interface AgentVideoGenerationStatus {
  kind: 'media.video'
  success: boolean
  prompt: string
  model?: string | null
  model_ref?: string | null
  task_id?: string | null
  status: string
  progress?: number | null
  video?: {
    url?: string | null
    base64?: string | null
    file_path?: string | null
    duration?: number | null
    width?: number | null
    height?: number | null
    format?: string
  } | null
  estimated_time?: number | null
  requires_polling?: boolean
  poll_interval_ms?: number
  poll_timeout_s?: number
  error?: string | null
}

// ============ Agent API ============

export const agentsApi = {
  /**
   * 获取 Agent 列表
   */
  getAgents: async (params: AgentQueryParams = {}): Promise<PageData<AgentListItem>> => {
    const { page = 1, pageSize = 20, search, status, visibility, teamId } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('keyword', search)
    if (status) queryParams.append('status', status)
    if (visibility) queryParams.append('visibility', visibility)
    if (teamId) queryParams.append('team_id', teamId)
    return api.get<PageData<AgentListItem>>(`/agents?${queryParams.toString()}`)
  },

  /**
   * 获取单个 Agent
   */
  getAgent: async (id: string): Promise<Agent> => {
    return api.get<Agent>(`/agents/${id}`)
  },

  /**
   * 创建 Agent
   */
  createAgent: async (data: AgentCreateInput): Promise<Agent> => {
    return api.post<Agent>('/agents', data)
  },

  /**
   * 更新 Agent
   */
  updateAgent: async (id: string, data: AgentUpdateInput): Promise<Agent> => {
    return api.put<Agent>(`/agents/${id}`, data)
  },

  /**
   * 删除 Agent
   */
  deleteAgent: async (id: string): Promise<void> => {
    return api.delete<void>(`/agents/${id}`)
  },

  /**
   * 发布 Agent
   */
  publishAgent: async (id: string): Promise<Agent> => {
    return api.post<Agent>(`/agents/${id}/publish`)
  },

  /**
   * 取消发布 Agent
   */
  unpublishAgent: async (id: string): Promise<Agent> => {
    return api.post<Agent>(`/agents/${id}/unpublish`)
  },

  /**
   * 复制 Agent
   */
  duplicateAgent: async (id: string): Promise<Agent> => {
    return api.post<Agent>(`/agents/${id}/duplicate`)
  },

  // ============ Conversation API ============

  /**
   * 获取 Agent 的对话列表
   */
  getAgentConversations: async (
    agentId: string,
    params: { page?: number; pageSize?: number } = {}
  ): Promise<PageData<ConversationListItem>> => {
    const { page = 1, pageSize = 20 } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    return api.get<PageData<ConversationListItem>>(
      `/agents/${agentId}/conversations?${queryParams.toString()}`
    )
  },

  /**
   * 获取对话详情（含消息）
   */
  getConversation: async (conversationId: string): Promise<ConversationWithMessages> => {
    return api.get<ConversationWithMessages>(`/agents/conversations/${conversationId}`)
  },

  /**
   * 更新对话
   */
  updateConversation: async (
    conversationId: string,
    data: ConversationUpdateInput
  ): Promise<Conversation> => {
    return api.patch<Conversation>(`/agents/conversations/${conversationId}`, data)
  },

  /**
   * 删除对话
   */
  deleteConversation: async (conversationId: string): Promise<void> => {
    return api.delete<void>(`/agents/conversations/${conversationId}`)
  },

  /**
   * 删除消息
   */
  deleteMessage: async (agentId: string, conversationId: string, messageId: string): Promise<void> => {
    return api.delete<void>(`/agents/${agentId}/conversations/${conversationId}/messages/${messageId}`)
  },

  // ============ Message Version API ============

  /**
   * 获取消息的所有版本
   */
  getMessageVersions: async (agentId: string, messageId: string): Promise<MessageVersion[]> => {
    return api.get<MessageVersion[]>(`/agents/${agentId}/messages/${messageId}/versions`)
  },

  /**
   * 切换消息版本
   */
  switchMessageVersion: async (agentId: string, messageId: string, versionId: string): Promise<Message> => {
    return api.post<Message>(`/agents/${agentId}/messages/${messageId}/switch-version`, {
      version_id: versionId,
    })
  },

  /**
   * 重新生成消息（流式 SSE）
   */
  regenerateStream: (
    agentId: string,
    messageId: string,
    variables?: Record<string, unknown>
  ): { stream: Promise<Response>; abort: () => void } => {
    const controller = new AbortController()
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    
    const stream = fetch(`${baseUrl}/agents/${agentId}/messages/${messageId}/regenerate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ variables }),
      signal: controller.signal,
    })

    return {
      stream,
      abort: () => controller.abort(),
    }
  },

  // ============ Chat API ============

  /**
   * 发送消息（非流式）
   */
  chat: async (agentId: string, data: ChatRequest): Promise<ChatResponse> => {
    return api.post<ChatResponse>(`/agents/${agentId}/chat`, data)
  },

  /**
   * 发送消息（流式 SSE）
   * 返回一个 ReadableStream，调用方需要自行处理 SSE 事件
   */
  chatStream: (agentId: string, data: ChatRequest): { stream: Promise<Response>; abort: () => void } => {
    const controller = new AbortController()
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    
    const stream = fetch(`${baseUrl}/agents/${agentId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal: controller.signal,
    })

    return {
      stream,
      abort: () => controller.abort(),
    }
  },

  getVideoGenerationStatus: async (
    agentId: string,
    taskId: string
  ): Promise<AgentVideoGenerationStatus> => {
    const queryParams = new URLSearchParams({ task_id: taskId })
    return api.get<AgentVideoGenerationStatus>(
      `/agents/${agentId}/media/video-status?${queryParams.toString()}`
    )
  },
}

// ============ SSE Parser Utility ============

export interface SSEEvent {
  event: SSEEventType
  data: unknown
}

/**
 * 解析 SSE 流
 */
export async function* parseSSEStream(response: Response): AsyncGenerator<SSEEvent> {
  const reader = response.body?.getReader()
  if (!reader) return

  const decoder = new TextDecoder()
  let buffer = ''
  // Track event/data across chunks to handle TCP splitting
  let currentEvent: SSEEventType | null = null
  let currentDataLines: string[] = []

  const flushEvent = (): SSEEvent | null => {
    if (!currentEvent || currentDataLines.length === 0) {
      currentEvent = null
      currentDataLines = []
      return null
    }

    try {
      return {
        event: currentEvent,
        data: JSON.parse(currentDataLines.join('\n')),
      }
    } catch {
      return null
    } finally {
      currentEvent = null
      currentDataLines = []
    }
  }

  const processLine = (rawLine: string): SSEEvent | null => {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine

    if (line.startsWith('event:')) {
      currentEvent = line.slice(6).trim() as SSEEventType
      return null
    }

    if (line.startsWith('data:')) {
      currentDataLines.push(line.slice(5).trimStart())
      return null
    }

    if (line === '') {
      return flushEvent()
    }

    return null
  }

  while (true) {
    const { done, value } = await reader.read()

    if (done) {
      buffer += decoder.decode()
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const event = processLine(line)
      if (event) {
        yield event
      }
    }
  }

  if (buffer) {
    for (const line of buffer.split('\n')) {
      const event = processLine(line)
      if (event) {
        yield event
      }
    }
  }

  const finalEvent = flushEvent()
  if (finalEvent) {
    yield finalEvent
  }
}

// ============ Agent Stats Types ============

export interface AgentStatsOverview {
  total_conversations: number
  total_messages: number
  user_messages: number
  assistant_messages: number
  tool_messages: number
  active_users: number
}

export interface AgentStatsTokens {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface AgentStatsPerformance {
  avg_response_time_ms: number
}

export interface AgentStatsTools {
  tool_call_count: number
}

export interface AgentStats {
  period: string
  overview: AgentStatsOverview
  tokens: AgentStatsTokens
  performance: AgentStatsPerformance
  tools: AgentStatsTools
}

export interface AgentTrendDataPoint {
  timestamp: string
  label: string
  conversations: number
  messages: number
  tokens: number
  avg_response_time_ms: number
}

export interface AgentTrends {
  period: string
  granularity: string
  data: AgentTrendDataPoint[]
}

export interface ToolUsageItem {
  name: string
  count: number
}

export interface AgentToolUsage {
  period: string
  tools: ToolUsageItem[]
  total_calls: number
}

export interface RecentConversationItem {
  id: string
  title?: string | null
  user?: { id: string; username: string } | null
  message_count: number
  token_usage: number
  created_at: string
  updated_at: string
}

// ============ Agent Stats API ============

export const agentStatsApi = {
  /**
   * 获取 Agent 统计概览
   */
  getStats: async (agentId: string, period: string = '7d'): Promise<AgentStats> => {
    return api.get<AgentStats>(`/agents/${agentId}/stats?period=${period}`)
  },

  /**
   * 获取 Agent 趋势数据（用于图表）
   */
  getTrends: async (agentId: string, period: string = '7d'): Promise<AgentTrends> => {
    return api.get<AgentTrends>(`/agents/${agentId}/stats/trends?period=${period}`)
  },

  /**
   * 获取工具使用统计
   */
  getToolUsage: async (agentId: string, period: string = '7d'): Promise<AgentToolUsage> => {
    return api.get<AgentToolUsage>(`/agents/${agentId}/stats/tool-usage?period=${period}`)
  },

  /**
   * 获取最近对话
   */
  getRecentConversations: async (agentId: string, limit: number = 10): Promise<RecentConversationItem[]> => {
    return api.get<RecentConversationItem[]>(`/agents/${agentId}/stats/recent-conversations?limit=${limit}`)
  },
}

// ============ Admin Conversation Types ============

export interface AdminConversationListItem extends ConversationListItem {
  user_id?: string
  user_name?: string | null
}

export interface AdminConversationWithMessages extends ConversationWithMessages {
  user_id?: string
  user_name?: string | null
}

export interface ConversationStats {
  total_conversations: number
  total_messages: number
  active_users: number
  conversations_by_agent: Array<{
    agent_id: string
    agent_name: string
    agent_icon?: string | null
    count: number
  }>
}

export interface ConversationTrends {
  period: string
  data: Array<{
    date: string
    conversations: number
    messages: number
    tokens: number
  }>
}

export interface AdminConversationQueryParams {
  team_id?: string[]
  agent_id?: string[]
  user_id?: string[]
  search?: string
  untitled_only?: boolean
  page?: number
  pageSize?: number
}

// ============ Admin Conversation API ============

export const conversationsApi = {
  /**
   * 获取所有对话列表（管理员）
   */
  listAll: async (
    params: AdminConversationQueryParams = {}
  ): Promise<PageData<AdminConversationListItem>> => {
    const { page = 1, pageSize = 20, team_id, agent_id, user_id, search, untitled_only } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    team_id?.forEach((value) => queryParams.append('team_id', value))
    agent_id?.forEach((value) => queryParams.append('agent_id', value))
    user_id?.forEach((value) => queryParams.append('user_id', value))
    if (search) queryParams.append('search', search)
    if (untitled_only) queryParams.append('untitled_only', 'true')
    return api.get<PageData<AdminConversationListItem>>(
      `/conversations?${queryParams.toString()}`
    )
  },

  /**
   * 获取对话统计数据
   */
  getStats: async (teamId?: string): Promise<ConversationStats> => {
    const queryParams = new URLSearchParams()
    if (teamId) queryParams.append('team_id', teamId)
    const query = queryParams.toString()
    return api.get<ConversationStats>(`/conversations/stats${query ? `?${query}` : ''}`)
  },

  /**
   * 获取对话趋势数据
   */
  getTrends: async (teamId?: string, period: '7d' | '30d' = '7d'): Promise<ConversationTrends> => {
    const queryParams = new URLSearchParams()
    if (teamId) queryParams.append('team_id', teamId)
    queryParams.append('period', period)
    return api.get<ConversationTrends>(`/conversations/stats/trends?${queryParams.toString()}`)
  },

  /**
   * 获取对话详情（管理员）
   */
  getDetail: async (conversationId: string): Promise<AdminConversationWithMessages> => {
    return api.get<AdminConversationWithMessages>(`/conversations/${conversationId}`)
  },

  /**
   * 删除对话（管理员）
   */
  delete: async (conversationId: string): Promise<void> => {
    return api.delete<void>(`/conversations/${conversationId}`)
  },

  /**
   * 批量删除对话（管理员）
   */
  batchDelete: async (ids: string[]): Promise<{ deleted_count: number; ids: string[] }> => {
    const queryParams = new URLSearchParams()
    ids.forEach((id) => queryParams.append('ids', id))
    return api.delete<{ deleted_count: number; ids: string[] }>(
      `/conversations?${queryParams.toString()}`
    )
  },
}

// ============ Public Agent Types ============

export interface PublicAgent {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
  opening_message?: string | null
  suggested_questions: string[]
  variables: VariableDefinition[]
  enable_vision: boolean
  enable_file_upload: boolean
  file_upload_config?: FileUploadConfig | null
  created_by?: CreatorInfo | null
}

// ============ Public Agent API (No Auth Required) ============

import { API_BASE_URL } from '@/lib/constants'

export const publicAgentsApi = {
  /**
   * 获取 Agent 信息（可选认证）
   * - 已登录：返回用户有权限访问的 Agent
   * - 未登录：仅返回公开发布的 Agent
   */
  getPublicAgent: async (id: string): Promise<PublicAgent> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    
    const response = await fetch(`${API_BASE_URL}/agents/${id}/public`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new ApiError(response.status, resolvePublicApiErrorMessage(response.status, error.msg), error.data)
    }
    
    const data = await response.json()
    return data.data
  },

  /**
   * 获取用户与该 Agent 的对话列表
   */
  getConversations: async (agentId: string, params: { page?: number; pageSize?: number } = {}): Promise<PageData<ConversationListItem>> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    const { page = 1, pageSize = 50 } = params
    
    const response = await fetch(`${API_BASE_URL}/agents/${agentId}/conversations?page=${page}&page_size=${pageSize}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new ApiError(response.status, resolvePublicApiErrorMessage(response.status, error.msg), error.data)
    }
    
    const data = await response.json()
    return data.data
  },

  /**
   * 获取对话详情（含消息）
   */
  getConversation: async (conversationId: string): Promise<ConversationWithMessages> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    
    const response = await fetch(`${API_BASE_URL}/agents/conversations/${conversationId}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new ApiError(response.status, resolvePublicApiErrorMessage(response.status, error.msg), error.data)
    }
    
    const data = await response.json()
    return data.data
  },

  /**
   * 删除对话
   */
  deleteConversation: async (conversationId: string): Promise<void> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

    const response = await fetch(`${API_BASE_URL}/agents/conversations/${conversationId}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new ApiError(response.status, resolvePublicApiErrorMessage(response.status, error.msg), error.data)
    }
  },

  /**
   * 更新对话
   */
  updateConversation: async (
    conversationId: string,
    data: ConversationUpdateInput
  ): Promise<Conversation> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

    const response = await fetch(`${API_BASE_URL}/agents/conversations/${conversationId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new ApiError(response.status, resolvePublicApiErrorMessage(response.status, error.msg), error.data)
    }

    const result = await response.json()
    return result.data
  },

  /**
   * 公开聊天流（需要登录）
   */
  chatStream: (agentId: string, data: ChatRequest): { stream: Promise<Response>; abort: () => void } => {
    const controller = new AbortController()
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null

    const stream = fetch(`${API_BASE_URL}/agents/${agentId}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify(data),
      signal: controller.signal,
    })

    return {
      stream,
      abort: () => controller.abort(),
    }
  },
}
