import { api } from "./client";

export interface AuditLog {
  id: string;
  user_id?: string;
  username?: string;
  team_id?: string;
  ip_address?: string;
  user_agent?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  resource_name?: string;
  operation: string;
  status: string;
  error_message?: string;
  changes?: {
    before?: Record<string, unknown>;
    after?: Record<string, unknown>;
  };
  metadata?: Record<string, unknown>;
  auth_method?: string;
  api_key_id?: string;
  created_at: string;
}

export interface AuditLogListParams {
  user_id?: string;
  team_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface AuditLogStats {
  total_logs: number;
  today_logs: number;
  failed_logs: number;
  active_users: number;
  top_actions: Array<{ action: string; count: number }>;
  top_users: Array<{ user_id: string; username: string; count: number }>;
}

export interface AuditLogRetentionStats {
  total_logs: number;
  logs_to_archive: number;
  oldest_log_date?: string;
  retention_days: number;
  cutoff_date: string;
  next_archive_date: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const auditLogsApi = {
  /**
   * 获取审计日志列表
   */
  list: async (
    params: AuditLogListParams
  ): Promise<PaginatedResponse<AuditLog>> => {
    return await api.get("/audit-logs", { params });
  },

  /**
   * 获取单个审计日志详情
   */
  get: async (id: string): Promise<AuditLog> => {
    return await api.get(`/audit-logs/${id}`);
  },

  /**
   * 获取审计日志统计
   */
  getStats: async (): Promise<AuditLogStats> => {
    return await api.get("/audit-logs/stats");
  },

  /**
   * 获取日志保留统计
   */
  getRetentionStats: async (): Promise<AuditLogRetentionStats> => {
    return await api.get("/audit-logs/stats/retention");
  },

  /**
   * 手动触发归档
   */
  triggerArchive: async (): Promise<{ task_id: string; message: string }> => {
    return await api.post("/audit-logs/archive");
  },

  /**
   * 导出审计日志（CSV/JSON）
   */
  export: async (params: AuditLogListParams, format: "csv" | "json" = "csv"): Promise<Blob> => {
    const { axiosInstance } = await import("./client");
    const response = await axiosInstance.get("/audit-logs/export", {
      params: { ...params, format },
      responseType: "blob",
    });
    return response.data;
  },
};
