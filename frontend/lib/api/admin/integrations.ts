import { api } from '../client'
import type { EmailSettings, WebhookSettings } from '../site-settings'
import type { Integration, IntegrationCreate, IntegrationUpdate, IntegrationType, LoginSettings } from '../integrations'

export type { Integration, IntegrationCreate, IntegrationUpdate, IntegrationType, LoginSettings } from '../integrations'
export type { EmailSettings, WebhookSettings } from '../site-settings'

export interface FeishuDepartment {
  department_id: string
  name: string
  parent_department_id: string | null
  children: FeishuDepartment[]
}

export interface FeishuConfig {
  app_id: string
  app_secret_configured: boolean
  department_ids: string[]
  is_enabled: boolean
}

export const integrationsApi = {
  list: (): Promise<Integration[]> => api.get('/admin/integrations'),
  types: (): Promise<IntegrationType[]> => api.get('/admin/integrations/types'),
  create: (data: IntegrationCreate): Promise<Integration> => api.post('/admin/integrations', data),
  update: (id: string, data: IntegrationUpdate): Promise<Integration> => api.put(`/admin/integrations/${id}`, data),
  delete: (id: string): Promise<void> => api.delete(`/admin/integrations/${id}`),
  testConnection: (id: string): Promise<{ status: string; message: string }> => api.post(`/admin/integrations/${id}/test`),
  adminDisconnectConnection: (id: string): Promise<void> => api.delete(`/admin/integrations/connections/${id}`),
  getLoginSettings: (): Promise<LoginSettings> => api.get('/admin/integrations/login-settings'),
  updateLoginSettings: (data: Partial<LoginSettings>): Promise<LoginSettings> => api.put('/admin/integrations/login-settings', data),
  getEmail: (): Promise<EmailSettings> => api.get('/admin/integrations/email'),
  updateEmail: (data: Partial<EmailSettings>): Promise<EmailSettings> => api.put('/admin/integrations/email', data),
  sendTestEmail: (email: string): Promise<void> => api.post('/admin/integrations/email/test', { email }),
  getWebhook: (): Promise<WebhookSettings> => api.get('/admin/integrations/webhook'),
  updateWebhook: (data: Partial<WebhookSettings>): Promise<WebhookSettings> => api.put('/admin/integrations/webhook', data),
  sendTestWebhook: (): Promise<void> => api.post('/admin/integrations/webhook/test', null),
  getFeishuConfig: (): Promise<FeishuConfig> => api.get('/admin/integrations/feishu/config'),
  updateFeishuConfig: (data: { app_id?: string; app_secret?: string; is_enabled?: boolean }): Promise<FeishuConfig> => api.put('/admin/integrations/feishu/config', data),
  getFeishuDepartments: (): Promise<FeishuDepartment[]> => api.get('/admin/integrations/feishu/departments'),
  updateFeishuDepartmentScope: (department_ids: string[]): Promise<{ department_ids: string[] }> => api.put('/admin/integrations/feishu/department-scope', { department_ids }),
  syncFeishuContacts: (): Promise<{ created: number; updated: number; skipped: number; teams_created: number }> => api.post('/admin/integrations/feishu/sync', null, { timeout: 120000 }),
}
