import { api } from './client'
import { API_BASE_URL } from '@/lib/constants'

import type { IntegrationLoginPublic } from './integrations'

export const ssoApi = {
  // Public endpoints
  getPublicIntegrations: async (): Promise<IntegrationLoginPublic[]> => {
    return api.get<IntegrationLoginPublic[]>('/sso/integrations')
  },

  initiateLogin: (providerName: string, redirect?: string) => {
    const params = redirect ? `?redirect=${encodeURIComponent(redirect)}` : ''
    // External backend SSO entrypoint (absolute API_BASE_URL), not an internal route.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `${API_BASE_URL}/sso/login/${providerName}${params}`
  },

  // User endpoints
  disconnectConnection: async (connectionId: string): Promise<void> => {
    return api.delete(`/sso/connections/${connectionId}`)
  },
}
