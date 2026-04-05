import { api } from '../client'

export interface AuditLog {
  id: string
  created_at: string
  status: 'success' | 'failed' | string
  action: string
  operation: string
  username?: string | null
  user_id?: string | null
  auth_method?: string | null
  resource_type: string
  resource_name?: string | null
  resource_id?: string | null
  ip_address?: string | null
  user_agent?: string | null
  error_message?: string | null
  changes?: {
    before?: Record<string, unknown> | null
    after?: Record<string, unknown> | null
  } | null
  metadata?: Record<string, unknown> | null
}

export interface AuditLogListParams {
  page?: number
  page_size?: number
  search?: string
  status?: string[]
  action?: string[]
}

export interface AuditLogActionOption {
  value: string
  translation_key: string
  fallback_label: string
}

export interface AuditLogStats {
  total_logs: number
  today_logs: number
  failed_logs: number
  active_users: number
}

export interface AuditLogRetentionStats {
  retention_days?: number
  archived_logs?: number
  active_logs?: number
  last_archive_at?: string | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

const buildAuditLogQuery = (params: AuditLogListParams & { format?: 'csv' | 'json' }) => {
  const queryParams = new URLSearchParams()
  if (params.page !== undefined) queryParams.append('page', String(params.page))
  if (params.page_size !== undefined) queryParams.append('page_size', String(params.page_size))
  if (params.search) queryParams.append('search', params.search)
  params.status?.forEach((value) => queryParams.append('status', value))
  params.action?.forEach((value) => queryParams.append('action', value))
  if (params.format) queryParams.append('format', params.format)
  return queryParams.toString()
}

export const auditLogsApi = {
  list: async (params: AuditLogListParams): Promise<PaginatedResponse<AuditLog>> =>
    api.get(`/admin/audit-logs?${buildAuditLogQuery(params)}`),

  get: async (id: string): Promise<AuditLog> =>
    api.get(`/admin/audit-logs/${id}`),

  getActions: async (): Promise<AuditLogActionOption[]> =>
    api.get('/admin/audit-logs/actions'),

  getStats: async (): Promise<AuditLogStats> =>
    api.get('/admin/audit-logs/stats'),

  getRetentionStats: async (): Promise<AuditLogRetentionStats> =>
    api.get('/admin/audit-logs/stats/retention'),

  triggerArchive: async (): Promise<{ task_id: string; message: string }> =>
    api.post('/admin/audit-logs/archive'),

  export: async (params: AuditLogListParams, format: 'csv' | 'json' = 'csv'): Promise<Blob> => {
    const { axiosInstance } = await import('../client')
    const response = await axiosInstance.get(`/admin/audit-logs/export?${buildAuditLogQuery({ ...params, format })}`, {
      responseType: 'blob',
    })
    return response.data
  },
}
