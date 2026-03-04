import { api } from '../client'
import type { SSOProviderAdmin, SSOProviderCreate, SSOProviderUpdate } from '../sso'

export type { SSOProviderAdmin, SSOProviderCreate, SSOProviderUpdate }

export const ssoApi = {
  listProviders: async (): Promise<SSOProviderAdmin[]> =>
    api.get<SSOProviderAdmin[]>('/admin/sso/providers'),

  createProvider: async (data: SSOProviderCreate): Promise<SSOProviderAdmin> =>
    api.post<SSOProviderAdmin>('/admin/sso/providers', data),

  updateProvider: async (id: string, data: SSOProviderUpdate): Promise<SSOProviderAdmin> =>
    api.put<SSOProviderAdmin>(`/admin/sso/providers/${id}`, data),

  deleteProvider: async (id: string): Promise<void> =>
    api.delete(`/admin/sso/providers/${id}`),

  testConnection: async (id: string): Promise<{ status: string; message: string }> =>
    api.post<{ status: string; message: string }>(`/admin/sso/providers/${id}/test`),

  adminDisconnectConnection: async (connectionId: string): Promise<void> =>
    api.delete(`/admin/sso/connections/${connectionId}`),
}
