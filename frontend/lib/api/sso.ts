import { api } from './client'
import { API_BASE_URL } from '@/lib/constants'

import type { IntegrationLoginPublic } from './integrations'

export interface SSOLinkStart {
  authorization_url: string
  session_id: string
}

/** sessionStorage key holding the pending Feishu link session id. */
export const SSO_LINK_PENDING_KEY = 'sso_link_pending_session'

export class SSOLinkStateError extends Error {
  constructor() {
    super('Unable to store the pending link state')
    this.name = 'SSOLinkStateError'
  }
}

function readPendingLinkSession(): string | null {
  try {
    return sessionStorage.getItem(SSO_LINK_PENDING_KEY)
  } catch {
    // Session storage is unavailable (private contexts); no pending link state.
    return null
  }
}

function storePendingLinkSession(sessionId: string): void {
  try {
    sessionStorage.setItem(SSO_LINK_PENDING_KEY, sessionId)
    if (sessionStorage.getItem(SSO_LINK_PENDING_KEY) !== sessionId) {
      throw new SSOLinkStateError()
    }
  } catch {
    throw new SSOLinkStateError()
  }
}

function clearPendingLinkSession(): void {
  try {
    sessionStorage.removeItem(SSO_LINK_PENDING_KEY)
  } catch {
    // Nothing to clear.
  }
}

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

  /** Enabled Feishu login providers this user has not linked yet. */
  getLinkableIntegrations: async (): Promise<IntegrationLoginPublic[]> => {
    return api.get<IntegrationLoginPublic[]>('/sso/links/integrations')
  },

  /**
   * Start linking a Feishu identity to the authenticated account.
   * The pending session id is stored before the browser navigates away so the
   * callback can verify it (link CSRF protection).
   */
  startLink: async (providerName: string): Promise<SSOLinkStart> => {
    const link = await api.post<SSOLinkStart>(
      `/sso/links?provider_name=${encodeURIComponent(providerName)}`
    )
    storePendingLinkSession(link.session_id)
    return link
  },

  /** Finalize the staged provider identity for the authenticated account. */
  completeLink: async (sessionId: string): Promise<void> => {
    return api.post('/sso/links/complete', { session_id: sessionId })
  },
}

/** Pending link session helpers shared by the binding flow and its callback. */
export const ssoLinkState = {
  read: readPendingLinkSession,
  clear: clearPendingLinkSession,
}
