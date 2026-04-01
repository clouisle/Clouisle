import { api } from './client'
import { PageData } from './agents'

// ============ Workflow Types ============

export type WorkflowStatus = 'draft' | 'published'
export type TriggerType = 'manual' | 'webhook' | 'cron'
export type WorkflowVisibility = 'private' | 'team' | 'public'
export type RunStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled' | 'timeout'
export type NodeStatus = 'pending' | 'queued' | 'running' | 'success' | 'failed' | 'skipped' | 'cancelled'

export interface Workflow {
  id: string
  team_id: string
  name: string
  description?: string | null
  icon?: string | null
  definition: WorkflowDefinition
  variables: VariableDefinition[]
  status: WorkflowStatus
  visibility: WorkflowVisibility
  version: number
  trigger_type: TriggerType
  trigger_config: Record<string, unknown>
  webhook_token?: string | null
  run_count: number
  success_count: number
  fail_count: number
  created_by_id: string
  created_at: string
  updated_at: string
  embed_config?: Record<string, unknown>
}

export interface WorkflowListItem {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  status: WorkflowStatus
  visibility: WorkflowVisibility
  trigger_type: TriggerType
  run_count: number
  success_count: number
  fail_count: number
  created_at: string
  updated_at: string
}

export interface WorkflowRun {
  id: string
  workflow_id: string
  trigger_type: TriggerType
  triggered_by_id?: string | null
  is_debug: boolean
  status: RunStatus
  inputs: Record<string, unknown>
  outputs?: Record<string, unknown> | null
  parent_run_id?: string | null
  root_run_id?: string | null
  depth: number
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  total_nodes: number
  executed_nodes: number
  failed_nodes: number
  skipped_nodes: number
  total_duration_ms?: number | null
  total_token_usage: Record<string, number>
  error_message?: string | null
  error_node_id?: string | null
}

export interface WorkflowRunListItem {
  id: string
  workflow_id: string
  trigger_type: TriggerType
  is_debug: boolean
  status: RunStatus
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  total_duration_ms?: number | null
  executed_nodes: number
  total_nodes: number
  error_message?: string | null
}

export interface WorkflowRunListItemWithWorkflow extends WorkflowRunListItem {
  workflow_name: string
  workflow_icon?: string | null
  triggered_by_name?: string | null
}

export interface WorkflowRunStats {
  total_runs: number
  runs_by_status: Record<string, number>
  runs_by_workflow: Array<{
    workflow_id: string
    workflow_name: string
    workflow_icon?: string | null
    count: number
  }>
  avg_duration_ms: number
}

export interface AllWorkflowRunsQueryParams {
  page?: number
  pageSize?: number
  teamId?: string
  workflowId?: string
  status?: RunStatus
  triggerType?: TriggerType
  userId?: string
  isDebug?: boolean
  search?: string
}

export interface NodeExecution {
  id: string
  run_id: string
  node_id: string
  node_type: string
  node_name: string
  execution_order: number
  status: NodeStatus
  queued_at?: string | null
  started_at?: string | null
  finished_at?: string | null
  queue_duration_ms?: number | null
  execution_duration_ms?: number | null
  inputs?: Record<string, unknown> | null
  outputs?: Record<string, unknown> | null
  config_snapshot?: Record<string, unknown> | null
  model_used?: string | null
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  sub_run_id?: string | null
  error_message?: string | null
  error_type?: string | null
  retry_count: number
}

// ============ Workflow Version Types ============

export interface WorkflowVersion {
  id: string
  workflow_id: string
  version: number
  definition: WorkflowDefinition
  variables: VariableDefinition[]
  trigger_type: TriggerType
  trigger_config: Record<string, unknown> | null
  description?: string | null
  created_by_id?: string | null
  created_at: string
}

export interface WorkflowVersionListItem {
  id: string
  workflow_id: string
  version: number
  description?: string | null
  created_by_id?: string | null
  created_at: string
}

// ============ Workflow Definition Types ============

export interface WorkflowDefinition {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
  viewport: { x: number; y: number; zoom: number }
}

export interface WorkflowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: NodeData
}

export interface NodeData {
  type: string
  label: string
  config: Record<string, unknown>
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
  label?: string | null
}

export interface VariableDefinition {
  name: string
  type: string
  required: boolean
  default?: unknown
  description?: string | null
}

// ============ Input Types ============

export interface WorkflowCreateInput {
  team_id: string
  name: string
  description?: string | null
  icon?: string | null
}

export interface WorkflowUpdateInput {
  name?: string | null
  description?: string | null
  icon?: string | null
  definition?: WorkflowDefinition | null
  variables?: VariableDefinition[] | null
  trigger_type?: TriggerType | null
  trigger_config?: Record<string, unknown> | null
  visibility?: WorkflowVisibility | null
  embed_config?: Record<string, unknown> | null
}

export interface WorkflowQueryParams {
  page?: number
  pageSize?: number
  teamId?: string
  status?: WorkflowStatus
  visibility?: WorkflowVisibility
  triggerType?: TriggerType
  keyword?: string
}

export interface WorkflowRunQueryParams {
  page?: number
  pageSize?: number
  status?: RunStatus
  isDebug?: boolean
}

export interface WorkflowRunInput {
  inputs: Record<string, unknown>
}

export interface WorkflowRunStartResponse {
  run_id: string
  stream_url: string
}

// ============ SSE Event Types ============

export type WorkflowEventType =
  | 'workflow_start'
  | 'workflow_complete'
  | 'workflow_error'
  | 'node_start'
  | 'node_complete'
  | 'node_error'
  | 'node_skip'
  | 'token'
  | 'output'

export interface WorkflowEvent {
  type: WorkflowEventType
  data: Record<string, unknown>
  sequence: number
  timestamp: string
}

// ============ Workflows API ============

export const workflowsApi = {
  /**
   * 获取工作流列表
   */
  getWorkflows: async (params: WorkflowQueryParams = {}): Promise<PageData<WorkflowListItem>> => {
    const { page = 1, pageSize = 20, teamId, status, visibility, triggerType, keyword } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (teamId) queryParams.append('team_id', teamId)
    if (status) queryParams.append('status', status)
    if (visibility) queryParams.append('visibility', visibility)
    if (triggerType) queryParams.append('trigger_type', triggerType)
    if (keyword) queryParams.append('keyword', keyword)
    return api.get<PageData<WorkflowListItem>>(`/workflows?${queryParams.toString()}`)
  },

  /**
   * 获取单个工作流
   */
  getWorkflow: async (id: string): Promise<Workflow> => {
    return api.get<Workflow>(`/workflows/${id}`)
  },

  /**
   * 获取工作流统计数据
   */
  getWorkflowStats: async (id: string): Promise<{
    total_runs: number
    success_count: number
    failed_count: number
    timeout_count: number
    avg_duration_ms: number
    last_run_at: string | null
  }> => {
    return api.get(`/workflows/${id}/stats`)
  },

  /**
   * 获取工作流趋势数据
   */
  getWorkflowTrends: async (id: string, period: '7d' | '30d' = '7d'): Promise<{
    period: string
    data: Array<{
      date: string
      runs: number
      success: number
      failed: number
      avgDuration: number
    }>
  }> => {
    return api.get(`/workflows/${id}/stats/trends?period=${period}`)
  },

  /**
   * 创建工作流
   */
  createWorkflow: async (data: WorkflowCreateInput): Promise<Workflow> => {
    return api.post<Workflow>('/workflows', data)
  },

  /**
   * 更新工作流
   */
  updateWorkflow: async (id: string, data: WorkflowUpdateInput): Promise<Workflow> => {
    return api.put<Workflow>(`/workflows/${id}`, data)
  },

  /**
   * 删除工作流
   */
  deleteWorkflow: async (id: string): Promise<void> => {
    return api.delete<void>(`/workflows/${id}`)
  },

  /**
   * 发布工作流
   */
  publishWorkflow: async (id: string): Promise<Workflow> => {
    return api.post<Workflow>(`/workflows/${id}/publish`)
  },

  /**
   * 取消发布工作流
   */
  unpublishWorkflow: async (id: string): Promise<Workflow> => {
    return api.post<Workflow>(`/workflows/${id}/unpublish`)
  },

  /**
   * 复制工作流
   */
  duplicateWorkflow: async (id: string): Promise<Workflow> => {
    return api.post<Workflow>(`/workflows/${id}/duplicate`)
  },

  /**
   * 重新生成 webhook token
   */
  regenerateWebhookToken: async (id: string): Promise<{ webhook_token: string }> => {
    return api.post<{ webhook_token: string }>(`/workflows/${id}/regenerate-webhook-token`)
  },

  // ============ Workflow Runs API ============

  /**
   * 获取所有工作流运行列表（跨工作流，管理员端点）
   */
  getAllWorkflowRuns: async (
    params: AllWorkflowRunsQueryParams = {}
  ): Promise<PageData<WorkflowRunListItemWithWorkflow>> => {
    const {
      page = 1,
      pageSize = 20,
      teamId,
      workflowId,
      status,
      triggerType,
      userId,
      isDebug,
      search,
    } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (teamId) queryParams.append('team_id', teamId)
    if (workflowId) queryParams.append('workflow_id', workflowId)
    if (status) queryParams.append('status', status)
    if (triggerType) queryParams.append('trigger_type', triggerType)
    if (userId) queryParams.append('user_id', userId)
    if (isDebug !== undefined) queryParams.append('is_debug', String(isDebug))
    if (search) queryParams.append('search', search)
    return api.get<PageData<WorkflowRunListItemWithWorkflow>>(
      `/workflows/runs?${queryParams.toString()}`
    )
  },

  /**
   * 获取工作流运行统计信息
   */
  getWorkflowRunStats: async (teamId?: string): Promise<WorkflowRunStats> => {
    const queryParams = new URLSearchParams()
    if (teamId) queryParams.append('team_id', teamId)
    return api.get<WorkflowRunStats>(`/workflows/runs/stats?${queryParams.toString()}`)
  },

  /**
   * 获取工作流运行列表
   */
  getWorkflowRuns: async (
    workflowId: string,
    params: WorkflowRunQueryParams = {}
  ): Promise<PageData<WorkflowRunListItem>> => {
    const { page = 1, pageSize = 20, status, isDebug } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (status) queryParams.append('status', status)
    if (isDebug !== undefined) queryParams.append('is_debug', String(isDebug))
    return api.get<PageData<WorkflowRunListItem>>(
      `/workflows/${workflowId}/runs?${queryParams.toString()}`
    )
  },

  /**
   * 获取工作流运行详情
   */
  getWorkflowRun: async (runId: string): Promise<WorkflowRun> => {
    return api.get<WorkflowRun>(`/workflows/runs/${runId}`)
  },

  /**
   * 获取运行的节点执行列表
   */
  getRunNodeExecutions: async (runId: string): Promise<NodeExecution[]> => {
    return api.get<NodeExecution[]>(`/workflows/runs/${runId}/nodes`)
  },

  /**
   * 删除工作流运行
   */
  deleteWorkflowRun: async (runId: string): Promise<void> => {
    return api.delete<void>(`/workflows/runs/${runId}`)
  },

  // ============ Workflow Execution API ============

  /**
   * 运行工作流
   */
  runWorkflow: async (
    workflowId: string,
    data: WorkflowRunInput = { inputs: {} }
  ): Promise<WorkflowRunStartResponse> => {
    return api.post<WorkflowRunStartResponse>(`/workflows/${workflowId}/run`, data)
  },

  /**
   * 调试工作流（使用当前草稿而非发布版本）
   */
  debugWorkflow: async (
    workflowId: string,
    data: WorkflowRunInput = { inputs: {} }
  ): Promise<WorkflowRunStartResponse> => {
    return api.post<WorkflowRunStartResponse>(`/workflows/${workflowId}/debug`, data)
  },

  /**
   * 取消工作流运行
   */
  cancelWorkflowRun: async (runId: string): Promise<{ cancelled: boolean }> => {
    return api.post<{ cancelled: boolean }>(`/workflows/runs/${runId}/cancel`)
  },

  /**
   * 创建工作流执行事件的 SSE 连接
   * 
   * @param runId 运行 ID
   * @param fromSequence 从指定序列号开始（用于断线重连）
   * @param onEvent 事件回调
   * @param onError 错误回调
   * @returns 关闭连接的函数
   */
  streamWorkflowRun: (
    runId: string,
    options: {
      fromSequence?: number
      onEvent?: (event: WorkflowEvent) => void
      onError?: (error: Error) => void
      onComplete?: () => void
    } = {}
  ): (() => void) => {
    const { fromSequence = 0, onEvent, onError, onComplete } = options
    
    // 构建 SSE URL
    const baseUrl = api.getBaseUrl()
    const url = `${baseUrl}/workflows/runs/${runId}/stream?from_sequence=${fromSequence}`
    
    // 获取认证 headers
    const authHeaders = api.getAuthHeaders()
    
    // 创建 AbortController 用于取消请求
    const controller = new AbortController()
    
    const connect = async () => {
      try {
        const response = await fetch(url, {
          headers: {
            ...authHeaders,
            'Accept': 'text/event-stream',
          },
          signal: controller.signal,
        })
        
        if (!response.ok) {
          throw new Error(`SSE connection failed: ${response.status}`)
        }
        
        const reader = response.body?.getReader()
        if (!reader) {
          throw new Error('No response body')
        }
        
        const decoder = new TextDecoder()
        let buffer = ''
        
        while (true) {
          const { done, value } = await reader.read()
          
          if (done) {
            onComplete?.()
            break
          }
          
          buffer += decoder.decode(value, { stream: true })
          
          // 解析 SSE 事件
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''
          
          let eventType = ''
          let eventData = ''
          
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              eventData = line.slice(5).trim()
            } else if (line === '' && eventData) {
              // 空行表示事件结束
              try {
                const parsedData = JSON.parse(eventData)
                // 后端 SSE 格式: { event, data, node_id, timestamp, sequence }
                // 将 node_id 合并到 data 中供前端使用
                const eventDataWithNodeId = {
                  ...parsedData.data,
                  node_id: parsedData.node_id,
                }
                const event: WorkflowEvent = {
                  type: (eventType || parsedData.event || 'message') as WorkflowEventType,
                  data: eventDataWithNodeId,
                  sequence: parsedData.sequence || 0,
                  timestamp: parsedData.timestamp || new Date().toISOString(),
                }
                onEvent?.(event)
              } catch {
                // 忽略解析错误
              }
              eventType = ''
              eventData = ''
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name !== 'AbortError') {
          onError?.(error)
        }
      }
    }
    
    connect()
    
    // 返回关闭函数
    return () => {
      controller.abort()
    }
  },

  // ============ Workflow Versions API ============

  /**
   * 获取工作流版本列表
   */
  getWorkflowVersions: async (
    workflowId: string,
    params: { page?: number; pageSize?: number } = {}
  ): Promise<PageData<WorkflowVersionListItem>> => {
    const { page = 1, pageSize = 20 } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    return api.get<PageData<WorkflowVersionListItem>>(
      `/workflows/${workflowId}/versions?${queryParams.toString()}`
    )
  },

  /**
   * 获取工作流指定版本详情
   */
  getWorkflowVersion: async (workflowId: string, version: number): Promise<WorkflowVersion> => {
    return api.get<WorkflowVersion>(`/workflows/${workflowId}/versions/${version}`)
  },

  /**
   * 手动创建版本快照
   */
  createWorkflowVersion: async (
    workflowId: string,
    data: { description?: string } = {}
  ): Promise<WorkflowVersion> => {
    return api.post<WorkflowVersion>(`/workflows/${workflowId}/versions`, data)
  },

  /**
   * 恢复到指定版本
   */
  restoreWorkflowVersion: async (
    workflowId: string,
    version: number,
    data: { description?: string } = {}
  ): Promise<Workflow> => {
    return api.post<Workflow>(`/workflows/${workflowId}/versions/${version}/restore`, data)
  },
}
