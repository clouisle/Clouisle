import { api } from '../client'

export interface FeishuKnowledgeSpace { space_id: string; name: string }
export interface FeishuKnowledgeTarget { id: string; name: string; team_name: string }
export interface FeishuKnowledgeSource {
  id: string
  knowledge_base_id: string
  knowledge_base_name: string
  space_id: string
  space_name?: string | null
  name: string
  interval_minutes: number
  is_enabled: boolean
  status: 'idle' | 'queued' | 'running' | 'success' | 'error'
  last_synced_at: string | null
  last_error: string | null
  last_result: Record<string, unknown>
  created_at: string
  updated_at: string
}
export interface FeishuKnowledgeSourceCreate {
  knowledge_base_id: string
  space_id: string
  name: string
  interval_minutes: number
  is_enabled: boolean
}
export type FeishuKnowledgeSourceUpdate = Pick<FeishuKnowledgeSourceCreate, 'name' | 'interval_minutes' | 'is_enabled'>
const base = '/admin/integrations/feishu/knowledge'
export const feishuKnowledgeApi = {
  spaces: () => api.get<FeishuKnowledgeSpace[]>(`${base}/spaces`),
  targets: () => api.get<FeishuKnowledgeTarget[]>(`${base}/targets`),
  sources: () => api.get<FeishuKnowledgeSource[]>(`${base}/sources`),
  create: (data: FeishuKnowledgeSourceCreate) => api.post<FeishuKnowledgeSource>(`${base}/sources`, data),
  update: (id: string, data: FeishuKnowledgeSourceUpdate) => api.put<FeishuKnowledgeSource>(`${base}/sources/${id}`, data),
  sync: (id: string) => api.post<FeishuKnowledgeSource>(`${base}/sources/${id}/sync`),
  delete: (id: string) => api.delete<{ id: string }>(`${base}/sources/${id}`),
}
