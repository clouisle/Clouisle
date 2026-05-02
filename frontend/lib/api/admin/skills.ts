import { api } from '../client'
import type { PageData } from '../users'
import type { ToolFilterOption } from '../tools'
import type {
  Skill,
  SkillDetail,
  SkillImportInstallRequest,
  SkillImportInstallResponse,
  SkillImportPreviewGitInput,
  SkillImportPreviewResponse,
  SkillTestRequest,
  SkillTestResponse,
  SkillUpdateInput,
} from '../skills'

export interface AdminSkill extends Skill {
  team_name?: string | null
}

export interface AdminSkillDetail extends SkillDetail {
  team_name?: string | null
}

export interface AdminSkillFilterOptions {
  statuses: ToolFilterOption[]
  sources: ToolFilterOption[]
  teams: ToolFilterOption[]
  creators: ToolFilterOption[]
}

export interface AdminSkillListParams {
  page?: number
  pageSize?: number
  search?: string
  team_id?: string[]
  include_system?: boolean
  enabled?: boolean
  status?: string[]
  source_type?: string[]
  creator?: string[]
}

export const adminSkillsApi = {
  list: async (params: AdminSkillListParams = {}): Promise<PageData<AdminSkill>> => {
    const { page = 1, pageSize = 20, search, team_id, include_system, enabled, status, source_type, creator } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('search', search)
    team_id?.forEach((value) => queryParams.append('team_id', value))
    if (include_system !== undefined) queryParams.append('include_system', String(include_system))
    if (enabled !== undefined) queryParams.append('enabled', String(enabled))
    status?.forEach((value) => queryParams.append('status', value))
    source_type?.forEach((value) => queryParams.append('source_type', value))
    creator?.forEach((value) => queryParams.append('creator', value))
    return api.get<PageData<AdminSkill>>(`/admin/skills?${queryParams.toString()}`)
  },

  getFilterOptions: async (): Promise<AdminSkillFilterOptions> =>
    api.get<AdminSkillFilterOptions>('/admin/skills/filters'),

  get: async (id: string): Promise<AdminSkillDetail> =>
    api.get<AdminSkillDetail>(`/admin/skills/${id}`),

  previewZip: async (teamId: string | null, file: File): Promise<SkillImportPreviewResponse> => {
    const formData = new FormData()
    if (teamId) formData.append('team_id', teamId)
    formData.append('file', file)
    return api.post<SkillImportPreviewResponse>('/admin/skills/import/preview-zip', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  previewGit: async (input: SkillImportPreviewGitInput): Promise<SkillImportPreviewResponse> =>
    api.post<SkillImportPreviewResponse>('/admin/skills/import/preview-git', input, { timeout: 180000 }),

  install: async (sessionId: string, input: SkillImportInstallRequest): Promise<SkillImportInstallResponse> =>
    api.post<SkillImportInstallResponse>(`/admin/skills/import/${sessionId}/install`, input),

  update: async (id: string, input: SkillUpdateInput): Promise<AdminSkillDetail> =>
    api.patch<AdminSkillDetail>(`/admin/skills/${id}`, input),

  delete: async (id: string): Promise<void> => {
    await api.delete(`/admin/skills/${id}`)
  },

  test: async (id: string, input: SkillTestRequest): Promise<SkillTestResponse> =>
    api.post<SkillTestResponse>(`/admin/skills/${id}/test`, input),
}
