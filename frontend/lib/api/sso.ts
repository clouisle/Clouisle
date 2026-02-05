import { api } from './client'

export interface SSOProvider {
  id: string
  name: string
  display_name: string
  icon_url: string | null
  button_text: string | null
  protocol: string
}

export interface SSOProviderAdmin {
  id: string
  name: string
  protocol: string
  display_name: string
  icon_url: string | null
  button_text: string | null
  config: Record<string, any>
  attribute_mapping: Record<string, string>
  is_enabled: boolean
  allow_signup: boolean
  require_approval: boolean
  default_role_id: string | null
  created_at: string
  updated_at: string
}

export interface SSOProviderCreate {
  name: string
  protocol: string
  display_name: string
  icon_url?: string | null
  button_text?: string | null
  config: Record<string, any>
  attribute_mapping?: Record<string, string>
  is_enabled?: boolean
  allow_signup?: boolean
  require_approval?: boolean
  default_role_id?: string | null
}

export interface SSOProviderUpdate {
  name?: string
  protocol?: string
  display_name?: string
  icon_url?: string | null
  button_text?: string | null
  config?: Record<string, any>
  attribute_mapping?: Record<string, string>
  is_enabled?: boolean
  allow_signup?: boolean
  require_approval?: boolean
  default_role_id?: string | null
}

export const ssoApi = {
  // Public endpoints
  getPublicProviders: async (): Promise<SSOProvider[]> => {
    return api.get<SSOProvider[]>('/sso/providers')
  },

  initiateLogin: (providerId: string, redirect?: string) => {
    const params = redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''
    // 使用环境变量或默认后端地址
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    window.location.href = `${apiBaseUrl}/api/v1/sso/login/${providerId}${params}`
  },

  // Admin endpoints
  listProviders: async (): Promise<SSOProviderAdmin[]> => {
    return api.get<SSOProviderAdmin[]>('/sso/admin/providers')
  },

  createProvider: async (data: SSOProviderCreate): Promise<SSOProviderAdmin> => {
    return api.post<SSOProviderAdmin>('/sso/admin/providers', data)
  },

  updateProvider: async (
    id: string,
    data: SSOProviderUpdate
  ): Promise<SSOProviderAdmin> => {
    return api.put<SSOProviderAdmin>(`/sso/admin/providers/${id}`, data)
  },

  deleteProvider: async (id: string): Promise<void> => {
    return api.delete(`/sso/admin/providers/${id}`)
  },

  testConnection: async (id: string): Promise<{ status: string; message: string }> => {
    return api.post<{ status: string; message: string }>(
      `/sso/admin/providers/${id}/test`
    )
  },

  // User endpoints
  disconnectConnection: async (connectionId: string): Promise<void> => {
    return api.delete(`/sso/connections/${connectionId}`)
  },

  // Admin endpoints
  adminDisconnectConnection: async (connectionId: string): Promise<void> => {
    return api.delete(`/sso/admin/connections/${connectionId}`)
  },
}
