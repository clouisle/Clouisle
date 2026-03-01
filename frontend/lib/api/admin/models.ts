import { api } from '../client'
import type {
  Model,
  ModelCreateInput,
  ModelUpdateInput,
  ModelQueryParams,
} from '../models'
import type { PageData } from '../users'

export type { Model, ModelCreateInput, ModelUpdateInput, ModelQueryParams }

export const modelsApi = {
  getModels: async (params: ModelQueryParams = {}): Promise<PageData<Model>> => {
    const { page = 1, pageSize = 20, provider, model_type, is_enabled, search } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (provider) queryParams.append('provider', provider)
    if (model_type) queryParams.append('model_type', model_type)
    if (is_enabled !== undefined) queryParams.append('is_enabled', String(is_enabled))
    if (search) queryParams.append('search', search)
    return api.get<PageData<Model>>(`/admin/models?${queryParams.toString()}`)
  },

  getModel: async (modelId: string): Promise<Model> =>
    api.get<Model>(`/admin/models/${modelId}`),

  createModel: async (data: ModelCreateInput): Promise<Model> =>
    api.post<Model>('/admin/models', data),

  updateModel: async (modelId: string, data: ModelUpdateInput): Promise<Model> =>
    api.put<Model>(`/admin/models/${modelId}`, data),

  deleteModel: async (modelId: string): Promise<Model> =>
    api.delete<Model>(`/admin/models/${modelId}`),

  testConnection: async (modelId: string): Promise<{ success: boolean; message: string; latency_ms?: number }> =>
    api.post(`/admin/models/${modelId}/test`),

  testModelConfig: async (data: {
    provider: string
    model_id: string
    model_type: string
    base_url?: string | null
    api_key: string
    config?: Record<string, unknown> | null
  }): Promise<{ success: boolean; message: string; latency_ms?: number }> =>
    api.post('/admin/models/test', data),

  setDefault: async (modelId: string): Promise<Model> =>
    api.post<Model>(`/admin/models/${modelId}/set-default`),
}
