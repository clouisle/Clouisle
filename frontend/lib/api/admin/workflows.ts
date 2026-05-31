import { api } from '../client'
import type { PageData } from '../users'
import type { ToolFilterOption } from '../tools'
import type { TriggerType, Workflow, WorkflowListItem, WorkflowStatus, WorkflowUpdateInput, WorkflowVisibility } from '../workflows'

export interface AdminWorkflow extends WorkflowListItem {
  team_id?: string
  team_name?: string | null
  created_by_id?: string | null
  created_by_name?: string | null
  total_tokens?: number
  version?: number
}

export type AdminWorkflowDetail = Workflow

export interface AdminWorkflowFilterOptions {
  statuses: ToolFilterOption[]
  visibilities: ToolFilterOption[]
  trigger_types: ToolFilterOption[]
  teams: ToolFilterOption[]
  creators: ToolFilterOption[]
}

export interface AdminWorkflowListParams {
  page?: number
  pageSize?: number
  search?: string
  status?: WorkflowStatus[]
  visibility?: WorkflowVisibility[]
  trigger_type?: TriggerType[]
  team_id?: string[]
  creator?: string[]
}

export const adminWorkflowsApi = {
  listPage: async (params: AdminWorkflowListParams = {}): Promise<PageData<AdminWorkflow>> => {
    const { page = 1, pageSize = 20, search, status, visibility, trigger_type, team_id, creator } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('search', search)
    status?.forEach((value) => queryParams.append('status', value))
    visibility?.forEach((value) => queryParams.append('visibility', value))
    trigger_type?.forEach((value) => queryParams.append('trigger_type', value))
    team_id?.forEach((value) => queryParams.append('team_id', value))
    creator?.forEach((value) => queryParams.append('creator', value))
    return api.get<PageData<AdminWorkflow>>(`/admin/workflows?${queryParams.toString()}`)
  },

  getFilterOptions: async (): Promise<AdminWorkflowFilterOptions> =>
    api.get<AdminWorkflowFilterOptions>('/admin/workflows/filters'),

  getById: async (id: string): Promise<AdminWorkflowDetail> =>
    api.get<AdminWorkflowDetail>(`/admin/workflows/${id}`),

  update: async (id: string, data: WorkflowUpdateInput): Promise<AdminWorkflowDetail> =>
    api.put<AdminWorkflowDetail>(`/admin/workflows/${id}`, data),

  publish: async (id: string): Promise<AdminWorkflowDetail> =>
    api.post<AdminWorkflowDetail>(`/admin/workflows/${id}/publish`),

  unpublish: async (id: string): Promise<AdminWorkflowDetail> =>
    api.post<AdminWorkflowDetail>(`/admin/workflows/${id}/unpublish`),

  duplicate: async (id: string): Promise<AdminWorkflowDetail> =>
    api.post<AdminWorkflowDetail>(`/admin/workflows/${id}/duplicate`),

  delete: async (id: string): Promise<void> => {
    await api.delete(`/admin/workflows/${id}`)
  },
}
