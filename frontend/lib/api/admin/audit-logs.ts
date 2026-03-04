import { api } from '../client'
import type {
  AuditLog,
  AuditLogListParams,
  AuditLogStats,
  AuditLogRetentionStats,
  PaginatedResponse,
} from '../audit-logs'

export type { AuditLog, AuditLogListParams, AuditLogStats, AuditLogRetentionStats, PaginatedResponse }

export const auditLogsApi = {
  list: async (params: AuditLogListParams): Promise<PaginatedResponse<AuditLog>> =>
    api.get('/admin/audit-logs', { params }),

  get: async (id: string): Promise<AuditLog> =>
    api.get(`/admin/audit-logs/${id}`),

  getStats: async (): Promise<AuditLogStats> =>
    api.get('/admin/audit-logs/stats'),

  getRetentionStats: async (): Promise<AuditLogRetentionStats> =>
    api.get('/admin/audit-logs/stats/retention'),

  triggerArchive: async (): Promise<{ task_id: string; message: string }> =>
    api.post('/admin/audit-logs/archive'),

  export: async (params: AuditLogListParams, format: 'csv' | 'json' = 'csv'): Promise<Blob> => {
    const { axiosInstance } = await import('../client')
    const response = await axiosInstance.get('/admin/audit-logs/export', {
      params: { ...params, format },
      responseType: 'blob',
    })
    return response.data
  },
}
