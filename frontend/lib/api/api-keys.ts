import { api } from './client'
import type { PageData } from './users'

export interface APIKeyUser {
  id: string
  username: string
}

export interface APIKeyAgent {
  id: string
  name: string
  icon?: string | null
}

export interface APIKeyWorkflow {
  id: string
  name: string
  icon?: string | null
}

export interface APIKey {
  id: string
  name: string
  key_prefix: string
  user_id: string
  user?: APIKeyUser | null
  scopes: string[]
  rate_limit: number
  is_active: boolean
  expires_at: string | null
  last_used_at: string | null
  agents: APIKeyAgent[]
  workflows: APIKeyWorkflow[]
  created_at: string
  updated_at: string
}

export interface APIKeyWithSecret extends APIKey {
  key: string  // Full API key, only returned once at creation
}

export interface APIKeyStats {
  total: number
  active: number
  inactive: number
  expired: number
}

export interface APIKeyCreateInput {
  name: string
  scopes?: string[]
  rate_limit?: number
  expires_at?: string | null
  agent_ids?: string[]
  workflow_ids?: string[]
}

export interface APIKeyUpdateInput {
  name?: string
  scopes?: string[]
  rate_limit?: number
  expires_at?: string | null
  is_active?: boolean
  agent_ids?: string[]
  workflow_ids?: string[]
}

export interface APIKeyQueryParams {
  page?: number
  pageSize?: number
  status?: 'active' | 'inactive' | 'expired'
  userId?: string
  search?: string
}

export const apiKeysApi = {
  /**
   * 获取 API Key 列表（分页）
   */
  getAPIKeys: async (params: APIKeyQueryParams = {}): Promise<PageData<APIKey>> => {
    const { page = 1, pageSize = 20, status, userId, search } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (status) queryParams.append('status', status)
    if (userId) queryParams.append('user_id', userId)
    if (search) queryParams.append('search', search)
    return api.get<PageData<APIKey>>(`/api-keys?${queryParams.toString()}`)
  },

  /**
   * 获取 API Key 统计信息
   */
  getStats: async (): Promise<APIKeyStats> => {
    return api.get<APIKeyStats>('/api-keys/stats')
  },

  /**
   * 获取单个 API Key
   */
  getAPIKey: async (apiKeyId: string): Promise<APIKey> => {
    return api.get<APIKey>(`/api-keys/${apiKeyId}`)
  },

  /**
   * 创建 API Key
   */
  createAPIKey: async (data: APIKeyCreateInput): Promise<APIKeyWithSecret> => {
    return api.post<APIKeyWithSecret>('/api-keys', data)
  },

  /**
   * 更新 API Key
   */
  updateAPIKey: async (apiKeyId: string, data: APIKeyUpdateInput): Promise<APIKey> => {
    return api.put<APIKey>(`/api-keys/${apiKeyId}`, data)
  },

  /**
   * 删除 API Key
   */
  deleteAPIKey: async (apiKeyId: string): Promise<APIKey> => {
    return api.delete<APIKey>(`/api-keys/${apiKeyId}`)
  },

  /**
   * 激活 API Key
   */
  activateAPIKey: async (apiKeyId: string): Promise<APIKey> => {
    return api.post<APIKey>(`/api-keys/${apiKeyId}/activate`)
  },

  /**
   * 停用 API Key
   */
  deactivateAPIKey: async (apiKeyId: string): Promise<APIKey> => {
    return api.post<APIKey>(`/api-keys/${apiKeyId}/deactivate`)
  },
}
