import { api } from '../client'

export interface MemoryEntity {
  id: string
  user_id: string
  user_name: string
  user_avatar_url: string | null
  name: string
  entity_type: string
  description: string | null
  properties: Record<string, unknown>
  access_count: number
  last_accessed_at: string | null
  created_at: string
  updated_at: string
  outgoing_relations_count?: number
  incoming_relations_count?: number
  outgoing_relations?: MemoryRelation[]
  incoming_relations?: MemoryRelation[]
}

export interface MemoryRelation {
  id: string
  user_id: string
  source_entity_id: string
  source_entity_name: string
  target_entity_id: string
  target_entity_name: string
  relation_type: string
  description: string | null
  properties: Record<string, unknown>
  created_at: string
}

export interface MemoryStats {
  total_entities: number
  total_relations: number
  by_type: Record<string, number>
  by_user: Record<string, number>
}

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export const memoriesApi = {
  getEntities: (params: {
    page?: number
    page_size?: number
    user_id?: string
    entity_type?: string
    search?: string
  }) => api.get<PageData<MemoryEntity>>('/admin/memories/entities', { params }),

  getStats: () => api.get<MemoryStats>('/admin/memories/entities/stats'),

  getEntity: (entityId: string) =>
    api.get<MemoryEntity>(`/admin/memories/entities/${entityId}`),

  updateEntity: (
    entityId: string,
    data: {
      description?: string
      properties?: Record<string, unknown>
    }
  ) => api.put<MemoryEntity>(`/admin/memories/entities/${entityId}`, data),

  deleteEntity: (entityId: string) =>
    api.delete(`/admin/memories/entities/${entityId}`),

  getRelations: (params: {
    page?: number
    page_size?: number
    user_id?: string
    relation_type?: string
  }) => api.get<PageData<MemoryRelation>>('/admin/memories/relations', { params }),

  deleteRelation: (relationId: string) =>
    api.delete(`/admin/memories/relations/${relationId}`),
}
