import { api } from './client'

// ============ Types ============

export type EntityType =
  | 'person'
  | 'preference'
  | 'skill'
  | 'project'
  | 'goal'
  | 'fact'
  | 'concept'
  | 'organization'
  | 'location'
  | 'custom'

export type RelationType =
  | 'prefers'
  | 'works_on'
  | 'knows'
  | 'uses'
  | 'works_at'
  | 'located_in'
  | 'has_goal'
  | 'related_to'
  | 'part_of'

export interface MemoryEntity {
  id: string
  user_id: string
  name: string
  entity_type: EntityType
  description: string
  properties: Record<string, unknown>
  embedding_id?: string | null
  embedding_model_id?: string | null
  source_conversation_id?: string | null
  source_message_id?: string | null
  access_count: number
  last_accessed_at?: string | null
  created_at: string
  updated_at: string
}

export interface MemoryRelation {
  id: string
  user_id: string
  source_entity_id: string
  target_entity_id: string
  relation_type: RelationType
  description?: string | null
  properties: Record<string, unknown>
  source_conversation_id?: string | null
  source_message_id?: string | null
  created_at: string
  updated_at: string
}

export interface MemoryEntityWithRelations extends MemoryEntity {
  outgoing_relations: Array<{
    relation: MemoryRelation
    target_entity: MemoryEntity
  }>
  incoming_relations: Array<{
    relation: MemoryRelation
    source_entity: MemoryEntity
  }>
}

export interface MemoryGraph {
  entities: MemoryEntity[]
  relations: MemoryRelation[]
}

export interface CreateEntityInput {
  name: string
  entity_type: EntityType
  description?: string | null
  properties?: Record<string, unknown>
}

export interface UpdateEntityInput {
  description?: string | null
  properties?: Record<string, unknown>
}

export interface CreateRelationInput {
  source_entity_id: string
  target_entity_id: string
  relation_type: RelationType
  description?: string | null
  properties?: Record<string, unknown>
}

export interface EntityQueryParams {
  entity_type?: EntityType
  search?: string
  limit?: number
  offset?: number
}

export interface RelationQueryParams {
  source_entity_id?: string
  target_entity_id?: string
  relation_type?: RelationType
  limit?: number
  offset?: number
}

// ============ Memory API ============

export const memoriesApi = {
  /**
   * 获取用户的记忆实体列表
   */
  getEntities: async (params: EntityQueryParams = {}): Promise<MemoryEntity[]> => {
    const queryParams = new URLSearchParams()
    if (params.entity_type) queryParams.append('entity_type', params.entity_type)
    if (params.search) queryParams.append('search', params.search)
    if (params.limit) queryParams.append('limit', String(params.limit))
    if (params.offset) queryParams.append('offset', String(params.offset))

    const query = queryParams.toString()
    return api.get<MemoryEntity[]>(`/memories/entities${query ? `?${query}` : ''}`)
  },

  /**
   * 获取单个记忆实体详情
   */
  getEntity: async (id: string): Promise<MemoryEntityWithRelations> => {
    return api.get<MemoryEntityWithRelations>(`/memories/entities/${id}`)
  },

  /**
   * 创建记忆实体
   */
  createEntity: async (data: CreateEntityInput): Promise<MemoryEntity> => {
    return api.post<MemoryEntity>('/memories/entities', data)
  },

  /**
   * 更新记忆实体
   */
  updateEntity: async (id: string, data: UpdateEntityInput): Promise<MemoryEntity> => {
    return api.put<MemoryEntity>(`/memories/entities/${id}`, data)
  },

  /**
   * 删除记忆实体
   */
  deleteEntity: async (id: string): Promise<void> => {
    return api.delete<void>(`/memories/entities/${id}`)
  },

  /**
   * 获取用户的记忆关系列表
   */
  getRelations: async (params: RelationQueryParams = {}): Promise<MemoryRelation[]> => {
    const queryParams = new URLSearchParams()
    if (params.source_entity_id) queryParams.append('source_entity_id', params.source_entity_id)
    if (params.target_entity_id) queryParams.append('target_entity_id', params.target_entity_id)
    if (params.relation_type) queryParams.append('relation_type', params.relation_type)
    if (params.limit) queryParams.append('limit', String(params.limit))
    if (params.offset) queryParams.append('offset', String(params.offset))

    const query = queryParams.toString()
    return api.get<MemoryRelation[]>(`/memories/relations${query ? `?${query}` : ''}`)
  },

  /**
   * 创建记忆关系
   */
  createRelation: async (data: CreateRelationInput): Promise<MemoryRelation> => {
    return api.post<MemoryRelation>('/memories/relations', data)
  },

  /**
   * 删除记忆关系
   */
  deleteRelation: async (id: string): Promise<void> => {
    return api.delete<void>(`/memories/relations/${id}`)
  },

  /**
   * 获取记忆图谱
   */
  getGraph: async (): Promise<MemoryGraph> => {
    return api.get<MemoryGraph>('/memories/graph')
  },
}
