import { api } from './client'
import { publicAgentsApi } from './agents'
import { API_BASE_URL } from '@/lib/constants'

export type WeChatPurpose = 'none' | 'knowledge_collection' | 'agent'

export interface WeChatTarget { id: string; name: string; team_name: string }
export interface WeChatCollection {
  knowledge_base_id: string | null
  knowledge_base_name: string | null
  vision_model_id: string | null
  stt_model_id: string | null
}
export interface WeChatAgentConfigSummary {
  agent_id: string | null
  agent_name: string | null
  variables: Record<string, unknown>
  stt_model_id: string | null
  conversation_id: string | null
  run_id: string | null
  run_status: string | null
}
export interface WeChatBinding {
  id: string
  status: 'connected' | 'disconnected' | 'error'
  last_error: string | null
  last_received_at: string | null
  created_at: string
  bot_id: string
  purpose: WeChatPurpose
  collection: WeChatCollection | null
  agent_config: WeChatAgentConfigSummary | null
}
export interface WeChatPurposeInput {
  purpose: WeChatPurpose
  knowledge_base_id?: string | null
  vision_model_id?: string | null
  stt_model_id?: string | null
  agent_id?: string | null
  variables?: Record<string, unknown>
}
export interface WeChatAgentOption {
  id: string
  name: string
  team_name: string
  variables: WeChatAgentVariable[]
  enable_attachments: boolean
  attachment_config: Record<string, unknown> | null
}
export interface WeChatAgentVariable {
  name: string
  type: 'text' | 'paragraph' | 'select' | 'number' | 'checkbox'
  label?: string | null
  required: boolean
  hidden?: boolean
  default?: string | null
  description?: string | null
  options?: string[] | null
  min?: number | null
  max?: number | null
  maxLength?: number | null
}
export interface WeChatAgentReceipt {
  id: string
  binding_id: string
  status: string
  agent_name: string | null
  agent_id: string | null
  conversation_id: string | null
  run_id: string | null
  run_status: string | null
  error: string | null
  delivery_status: string[]
  created_at: string
}
export interface WeChatLogin {
  id: string
  status: 'wait' | 'scaned' | 'confirmed' | 'expired' | 'need_verifycode' | 'verify_code_blocked'
  qrcode_content: string
  expires_at: string
  binding?: WeChatBinding
}
export interface WeChatReceipt {
  id: string
  binding_id: string
  knowledge_base_id: string | null
  status: string
  last_error: string | null
  reply_status: string
  results: { index: number; name: string; status: string; document_id: string | null; item_id: string; has_original: boolean; error: string | null }[]
  created_at: string
}
export interface WeChatModel { id: string; name: string }
export interface WeChatModels { vision: WeChatModel[]; stt: WeChatModel[] }

/** Receipt/run statuses that need polling for progress. */
export const WECHAT_ACTIVE_RECEIPT_STATUSES = ['pending', 'submitted'] as const
export const WECHAT_ACTIVE_RUN_STATUSES = ['queued', 'running', 'stopping', 'completing', 'waiting'] as const

const base = '/wechat-knowledge'
export const wechatKnowledgeApi = {
  bindings: () => api.get<WeChatBinding[]>(`${base}/bindings`),
  targets: () => api.get<WeChatTarget[]>(`${base}/targets`),
  models: (id: string) => api.get<WeChatModels>(`${base}/models`, { params: { knowledge_base_id: id } }),
  agents: () => api.get<WeChatAgentOption[]>(`${base}/agents`),
  agentModels: (agentId: string) => api.get<{ stt: WeChatModel[] }>(`${base}/agent-models`, { params: { agent_id: agentId } }),
  purpose: (id: string, data: WeChatPurposeInput) => api.put<WeChatBinding>(`${base}/bindings/${id}/purpose`, data),
  stopRun: (agentId: string, runId: string) => publicAgentsApi.stopRun(agentId, runId),
  login: () => api.post<WeChatLogin>(`${base}/logins`),
  poll: (id: string, verify_code?: string) => api.post<WeChatLogin>(`${base}/logins/${id}/poll`, { verify_code }, { timeout: 50000 }),
  disconnect: (id: string) => api.delete<{ id: string }>(`${base}/bindings/${id}`),
  receipts: () => api.get<WeChatReceipt[]>(`${base}/receipts`),
  agentReceipts: (bindingId?: string) => api.get<WeChatAgentReceipt[]>(`${base}/agent-receipts`, bindingId ? { params: { binding_id: bindingId } } : undefined),
  original: async (id: string, filename: string) => {
    const response = await fetch(`${API_BASE_URL}${base}/items/${id}/original`, { headers: api.getAuthHeaders() })
    if (!response.ok) throw new Error('Unable to download original')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url; link.download = filename; link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
