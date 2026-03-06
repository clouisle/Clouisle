import { api } from './client'
import { API_BASE_URL } from '@/lib/constants'

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
  config: Record<string, unknown>
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
  config: Record<string, unknown>
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
  config?: Record<string, unknown>
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

  initiateLogin: (providerName: string, redirect?: string) => {
    const params = redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''
    window.location.href = `${API_BASE_URL}/sso/login/${providerName}${params}`
  },

  // User endpoints
  disconnectConnection: async (connectionId: string): Promise<void> => {
    return api.delete(`/sso/connections/${connectionId}`)
  },
}
