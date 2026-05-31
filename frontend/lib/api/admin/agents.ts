import { api } from '../client'
import type { PageData } from '../users'
import type { Agent, AgentListItem, AgentStatus, AgentUpdateInput, AgentVisibility } from '../agents'
import type { ToolFilterOption } from '../tools'

export interface AdminAgent extends AgentListItem {
  total_tokens?: number
}

export type AdminAgentDetail = Agent

export interface AdminAgentFilterOptions {
  statuses: ToolFilterOption[]
  visibilities: ToolFilterOption[]
  teams: ToolFilterOption[]
  creators: ToolFilterOption[]
}

export interface AdminAgentListParams {
  page?: number
  pageSize?: number
  search?: string
  status?: AgentStatus[]
  visibility?: AgentVisibility[]
  team_id?: string[]
  creator?: string[]
}

export const adminAgentsApi = {
  listPage: async (params: AdminAgentListParams = {}): Promise<PageData<AdminAgent>> => {
    const { page = 1, pageSize = 20, search, status, visibility, team_id, creator } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('search', search)
    status?.forEach((value) => queryParams.append('status', value))
    visibility?.forEach((value) => queryParams.append('visibility', value))
    team_id?.forEach((value) => queryParams.append('team_id', value))
    creator?.forEach((value) => queryParams.append('creator', value))
    return api.get<PageData<AdminAgent>>(`/admin/agents?${queryParams.toString()}`)
  },

  getFilterOptions: async (): Promise<AdminAgentFilterOptions> =>
    api.get<AdminAgentFilterOptions>('/admin/agents/filters'),

  getById: async (id: string): Promise<AdminAgentDetail> =>
    api.get<AdminAgentDetail>(`/admin/agents/${id}`),

  update: async (id: string, data: AgentUpdateInput): Promise<AdminAgentDetail> =>
    api.put<AdminAgentDetail>(`/admin/agents/${id}`, data),

  publish: async (id: string): Promise<AdminAgentDetail> =>
    api.post<AdminAgentDetail>(`/admin/agents/${id}/publish`),

  unpublish: async (id: string): Promise<AdminAgentDetail> =>
    api.post<AdminAgentDetail>(`/admin/agents/${id}/unpublish`),

  duplicate: async (id: string): Promise<AdminAgentDetail> =>
    api.post<AdminAgentDetail>(`/admin/agents/${id}/duplicate`),

  delete: async (id: string): Promise<void> => {
    await api.delete(`/admin/agents/${id}`)
  },
}
