import { api } from './client'
import { PageData } from './agents'

// ============ Workflow Types ============

export type WorkflowStatus = 'draft' | 'published'
export type TriggerType = 'manual' | 'webhook' | 'schedule' | 'chat'
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
}

export interface WorkflowListItem {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  status: WorkflowStatus
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
}

export interface WorkflowQueryParams {
  page?: number
  pageSize?: number
  teamId?: string
  status?: WorkflowStatus
  triggerType?: TriggerType
  keyword?: string
}

export interface WorkflowRunQueryParams {
  page?: number
  pageSize?: number
  status?: RunStatus
  isDebug?: boolean
}

// ============ Workflows API ============

export const workflowsApi = {
  /**
   * 获取工作流列表
   */
  getWorkflows: async (params: WorkflowQueryParams = {}): Promise<PageData<WorkflowListItem>> => {
    const { page = 1, pageSize = 20, teamId, status, triggerType, keyword } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (teamId) queryParams.append('team_id', teamId)
    if (status) queryParams.append('status', status)
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
}
