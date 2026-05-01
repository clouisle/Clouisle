import { api } from './client'
import type { SandboxArtifactConfig, ToolCategory } from './tools'

export type SkillSourceType = 'zip' | 'git' | 'manual_text' | 'legacy'
export type SkillInstallAction = 'install' | 'update' | 'skip'

export interface Skill {
  id: string
  team_id?: string | null
  name: string
  display_name: string
  description: string
  icon?: string | null
  category: ToolCategory
  version: string
  source_type: SkillSourceType
  source_uri?: string | null
  source_ref?: string | null
  source_subdir?: string | null
  package_path?: string | null
  package_hash?: string | null
  input_schema: Record<string, unknown>
  default_config: Record<string, unknown>
  is_enabled: boolean
  is_system: boolean
  import_warnings: string[]
  created_by_id?: string | null
  created_by_name?: string | null
  created_at: string
  updated_at: string
}

export interface SkillDetail extends Skill {
  skill_md: string
  instructions: string
  frontmatter: Record<string, unknown>
  package_manifest: Record<string, unknown>
  execution_config: Record<string, unknown>
  config_schema: Record<string, unknown>
}

export interface SkillListResponse {
  system: Skill[]
  team: Skill[]
}

export interface SkillConflict {
  type: string
  skill_id?: string | null
  message?: string | null
}

export interface SkillPreviewItem {
  package_path: string
  name?: string | null
  display_name?: string | null
  description: string
  version: string
  category: ToolCategory
  icon?: string | null
  valid: boolean
  errors: string[]
  warnings: string[]
  conflict?: SkillConflict | null
  file_count: number
  package_hash?: string | null
}

export interface SkillImportPreviewResponse {
  session_id: string
  source_type: SkillSourceType
  source_uri?: string | null
  source_ref?: string | null
  source_subdir?: string | null
  skills: SkillPreviewItem[]
  invalid: SkillPreviewItem[]
  warnings: string[]
}

export interface SkillImportPreviewGitInput {
  team_id?: string | null
  repo_url: string
  ref?: string | null
}

export interface SkillImportInstallItem {
  package_path: string
  action: SkillInstallAction
  skill_id?: string | null
}

export interface SkillImportInstallRequest {
  items: SkillImportInstallItem[]
  is_enabled?: boolean
}

export interface SkillImportInstallResponse {
  installed: string[]
  updated: string[]
  skipped: string[]
  errors: string[]
}

export type SkillUpdateInput = Partial<Pick<Skill, 'display_name' | 'description' | 'icon' | 'category' | 'is_enabled' | 'default_config'>>

export interface SkillTestRequest {
  arguments: Record<string, unknown>
  config?: Record<string, unknown>
}

export interface SkillTestResponse {
  success: boolean
  result?: unknown
  error?: string | null
  stdout: string
  stderr: string
  artifacts: SandboxArtifactConfig[]
  duration_ms?: number | null
}

export interface SkillListParams {
  team_id: string
  include_system?: boolean
  enabled?: boolean
  search?: string
  category?: string
}

export const skillsApi = {
  list(params: SkillListParams): Promise<SkillListResponse> {
    return api.get<SkillListResponse>('/skills', { params })
  },

  get(id: string, teamId?: string): Promise<SkillDetail> {
    return api.get<SkillDetail>(`/skills/${id}`, {
      params: teamId ? { team_id: teamId } : undefined,
    })
  },

  previewZip(teamId: string, file: File): Promise<SkillImportPreviewResponse> {
    const formData = new FormData()
    formData.append('team_id', teamId)
    formData.append('file', file)
    return api.post<SkillImportPreviewResponse>('/skills/import/preview-zip', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  previewGit(input: SkillImportPreviewGitInput): Promise<SkillImportPreviewResponse> {
    return api.post<SkillImportPreviewResponse>('/skills/import/preview-git', input, { timeout: 180000 })
  },

  install(sessionId: string, input: SkillImportInstallRequest): Promise<SkillImportInstallResponse> {
    return api.post<SkillImportInstallResponse>(`/skills/import/${sessionId}/install`, input)
  },

  update(id: string, input: SkillUpdateInput): Promise<SkillDetail> {
    return api.patch<SkillDetail>(`/skills/${id}`, input)
  },

  async delete(id: string): Promise<void> {
    await api.delete(`/skills/${id}`)
  },

  test(id: string, input: SkillTestRequest): Promise<SkillTestResponse> {
    return api.post<SkillTestResponse>(`/skills/${id}/test`, input)
  },
}
