import { api } from './client'

export interface PageData<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ============ Knowledge Base Types ============

export interface KnowledgeBaseSettings {
  chunk_size?: number
  chunk_overlap?: number
  separator?: string | null
  rerank_enabled?: boolean
  rerank_candidate_k?: number
  rerank_fail_open?: boolean
  rerank_score_threshold?: number | null
}

export interface TeamInfo {
  id: string
  name: string
  avatar_url?: string | null
}

export interface CreatorInfo {
  id: string
  username: string
  avatar_url?: string | null
}

export interface EmbeddingModelInfo {
  id: string
  name: string
  provider: string
  model_id: string
}

export interface RerankModelInfo {
  id: string
  name: string
  provider: string
  model_id: string
}

export interface KnowledgeBase {
  id: string
  team: TeamInfo
  created_by?: CreatorInfo | null
  name: string
  description: string | null
  icon: string | null
  embedding_model_id: string | null
  embedding_model?: EmbeddingModelInfo | null
  rerank_model_id: string | null
  rerank_model?: RerankModelInfo | null
  settings: KnowledgeBaseSettings | null
  status: string
  document_count: number
  total_chunks: number
  total_tokens: number
  created_at: string
  updated_at: string
}

export interface KnowledgeBaseStats {
  id: string
  name: string
  document_count: number
  total_chunks: number
  total_tokens: number
  documents_by_status: Record<string, number>
  documents_by_type: Record<string, number>
}

export interface KnowledgeBaseCreateInput {
  name: string
  description?: string | null
  icon?: string | null
  team_id?: string
  embedding_model_id?: string | null
  rerank_model_id?: string | null
  settings?: KnowledgeBaseSettings | null
}

export interface KnowledgeBaseUpdateInput {
  name?: string
  description?: string | null
  icon?: string | null
  embedding_model_id?: string | null
  rerank_model_id?: string | null
  settings?: KnowledgeBaseSettings | null
  status?: string
}

export interface KnowledgeBaseQueryParams {
  page?: number
  pageSize?: number
  search?: string
  status?: string[]
  teamId?: string
}

// ============ Document Types ============

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'error'
export type DocumentType = 'pdf' | 'docx' | 'doc' | 'txt' | 'markdown' | 'html' | 'csv' | 'xlsx' | 'xls' | 'json' | 'url'

export interface Document {
  id: string
  knowledge_base_id: string
  name: string
  file_path: string | null
  file_size: number
  source_url: string | null
  doc_type: DocumentType
  status: DocumentStatus
  chunk_count: number
  error_message: string | null
  metadata: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface DocumentChunk {
  id: string
  document_id: string
  content: string
  chunk_index: number
  token_count: number
  metadata: Record<string, unknown> | null
  status: 'pending' | 'embedded' | 'failed'
  error_message: string | null
  created_at: string
}

export interface DocumentChunkUpdateInput {
  content: string
}

export interface RechunkInput {
  chunk_size?: number
  chunk_overlap?: number
  separator?: string | null
}

export interface ProcessInput {
  chunk_size?: number
  chunk_overlap?: number
  separator?: string | null
  clean_text?: boolean
}

export interface DocumentQueryParams {
  page?: number
  pageSize?: number
  status?: DocumentStatus[]
  doc_type?: DocumentType[]
  search?: string
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  document_name: string
  content: string
  score: number
  metadata: Record<string, unknown> | null
  search_type?: string
  original_score?: number
  rerank_score?: number
  rerank_reason?: string
}

export type SearchMode = 'vector' | 'fulltext' | 'hybrid'

export interface SearchParams {
  query: string
  search_mode?: SearchMode
  top_k?: number
  threshold?: number
  rerank_enabled?: boolean
  rerank_candidate_k?: number
  rerank_fail_open?: boolean
  rerank_score_threshold?: number | null
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  total: number
}

// ============ Chunk Preview Types ============

export interface ChunkPreviewInput {
  chunk_size: number
  chunk_overlap: number
  separator?: string | null
  clean_text?: boolean
}

export interface ChunkPreviewItem {
  chunk_index: number
  content: string
  token_count: number
  char_count: number
  overlap_length: number
}

export interface ChunkPreviewResponse {
  total_chunks: number
  total_tokens: number
  total_chars: number
  chunks: ChunkPreviewItem[]
}

// ============ Knowledge Base API ============

function createKnowledgeBasesApi(prefix: '/knowledge-bases' | '/admin/knowledge-bases') {
  return {
    /**
     * 获取知识库列表
     */
  getKnowledgeBases: async (params: KnowledgeBaseQueryParams = {}): Promise<PageData<KnowledgeBase>> => {
    const { page = 1, pageSize = 20, search, status, teamId } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('search', search)
    status?.forEach((value) => queryParams.append('status', value))
    if (teamId) queryParams.append('team_id', teamId)
    return api.get<PageData<KnowledgeBase>>(`${prefix}?${queryParams.toString()}`)
  },

  /**
   * 获取单个知识库
   */
  getKnowledgeBase: async (id: string): Promise<KnowledgeBase> => {
    return api.get<KnowledgeBase>(`${prefix}/${id}`)
  },

  /**
   * 创建知识库
   */
  createKnowledgeBase: async (data: KnowledgeBaseCreateInput): Promise<KnowledgeBase> => {
    return api.post<KnowledgeBase>(prefix, data)
  },

  /**
   * 更新知识库
   */
  updateKnowledgeBase: async (id: string, data: KnowledgeBaseUpdateInput): Promise<KnowledgeBase> => {
    return api.put<KnowledgeBase>(`${prefix}/${id}`, data)
  },

  /**
   * 删除知识库
   */
  deleteKnowledgeBase: async (id: string): Promise<void> => {
    return api.delete<void>(`${prefix}/${id}`)
  },

  /**
   * 获取知识库统计
   */
  getStats: async (id: string): Promise<KnowledgeBaseStats> => {
    return api.get<KnowledgeBaseStats>(`${prefix}/${id}/stats`)
  },

  /**
   * 搜索知识库
   */
  search: async (id: string, params: SearchParams): Promise<SearchResponse> => {
    // Map frontend params to backend params
    const requestBody = {
      query: params.query,
      search_mode: params.search_mode || 'hybrid',
      top_k: params.top_k || 5,
      score_threshold: params.threshold || 0,
      rerank_enabled: params.rerank_enabled,
      rerank_candidate_k: params.rerank_candidate_k,
      rerank_fail_open: params.rerank_fail_open,
      rerank_score_threshold: params.rerank_score_threshold,
    }
    return api.post<SearchResponse>(`${prefix}/${id}/search`, requestBody)
  },

  // ============ Document API ============

  /**
   * 获取文档列表
   */
  getDocuments: async (kbId: string, params: DocumentQueryParams = {}): Promise<PageData<Document>> => {
    const { page = 1, pageSize = 20, status, doc_type, search } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    status?.forEach((value) => queryParams.append('status', value))
    doc_type?.forEach((value) => queryParams.append('doc_type', value))
    if (search) queryParams.append('search', search)
    return api.get<PageData<Document>>(`${prefix}/${kbId}/documents?${queryParams.toString()}`)
  },

  /**
   * 获取单个文档
   */
  getDocument: async (kbId: string, docId: string): Promise<Document> => {
    return api.get<Document>(`${prefix}/${kbId}/documents/${docId}`)
  },

  /**
   * 上传文档
   */
  uploadDocument: async (kbId: string, file: File): Promise<Document> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post<Document>(`${prefix}/${kbId}/documents/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  },

  /**
   * 导入 URL
   */
  importUrl: async (kbId: string, url: string, name?: string): Promise<Document> => {
    return api.post<Document>(`${prefix}/${kbId}/documents/url`, { source_url: url, name })
  },

  /**
   * 删除文档
   */
  deleteDocument: async (kbId: string, docId: string): Promise<void> => {
    return api.delete<void>(`${prefix}/${kbId}/documents/${docId}`)
  },

  /**
   * 开始处理文档 (用于待处理的文档)
   */
  processDocument: async (kbId: string, docId: string, settings?: ProcessInput): Promise<Document> => {
    return api.post<Document>(`${prefix}/${kbId}/documents/${docId}/process`, settings || {})
  },

  /**
   * 使用前端已编辑的分块处理文档 (直接入库+向量化)
   */
  processDocumentWithChunks: async (
    kbId: string, 
    docId: string, 
    chunks: Array<{ content: string; chunk_index: number }>
  ): Promise<Document> => {
    return api.post<Document>(
      `${prefix}/${kbId}/documents/${docId}/process-with-chunks`,
      { chunks }
    )
  },

  /**
   * 重新处理文档
   */
  reprocessDocument: async (kbId: string, docId: string): Promise<Document> => {
    return api.post<Document>(`${prefix}/${kbId}/documents/${docId}/reprocess`)
  },

  /**
   * 重试失败的分块
   */
  retryFailedChunks: async (kbId: string, docId: string): Promise<Document> => {
    return api.post<Document>(`${prefix}/${kbId}/documents/${docId}/retry-failed-chunks`)
  },

  /**
   * 重试单个失败分块
   */
  retryFailedChunk: async (kbId: string, docId: string, chunkId: string): Promise<Document> => {
    return api.post<Document>(`${prefix}/${kbId}/documents/${docId}/chunks/${chunkId}/retry-embedding`)
  },

  /**
   * 获取文档分块
   */
  getDocumentChunks: async (
    kbId: string, 
    docId: string, 
    params: { page?: number; pageSize?: number } = {}
  ): Promise<PageData<DocumentChunk>> => {
    const { page = 1, pageSize = 20 } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    return api.get<PageData<DocumentChunk>>(
      `${prefix}/${kbId}/documents/${docId}/chunks?${queryParams.toString()}`
    )
  },

  /**
   * 更新分块内容
   */
  updateChunk: async (
    kbId: string,
    docId: string,
    chunkId: string,
    data: DocumentChunkUpdateInput
  ): Promise<DocumentChunk> => {
    return api.put<DocumentChunk>(
      `${prefix}/${kbId}/documents/${docId}/chunks/${chunkId}`,
      data
    )
  },

  /**
   * 删除分块
   */
  deleteChunk: async (
    kbId: string,
    docId: string,
    chunkId: string
  ): Promise<void> => {
    return api.delete<void>(
      `${prefix}/${kbId}/documents/${docId}/chunks/${chunkId}`
    )
  },

  /**
   * 创建新分块
   */
  createChunk: async (
    kbId: string,
    docId: string,
    data: DocumentChunkUpdateInput,
    afterIndex?: number
  ): Promise<DocumentChunk> => {
    const queryParams = afterIndex !== undefined ? `?after_index=${afterIndex}` : ''
    return api.post<DocumentChunk>(
      `${prefix}/${kbId}/documents/${docId}/chunks${queryParams}`,
      data
    )
  },

  /**
   * 重新分块文档
   */
  rechunkDocument: async (
    kbId: string,
    docId: string,
    settings: RechunkInput
  ): Promise<Document> => {
    return api.post<Document>(
      `${prefix}/${kbId}/documents/${docId}/rechunk`,
      settings
    )
  },

  /**
   * 预览分块效果
   */
  previewChunks: async (
    kbId: string,
    docId: string,
    settings: ChunkPreviewInput
  ): Promise<ChunkPreviewResponse> => {
    return api.post<ChunkPreviewResponse>(
      `${prefix}/${kbId}/documents/${docId}/preview-chunks`,
      settings
    )
  },

  /**
   * 下载文档原文件
   */
  downloadDocument: async (kbId: string, docId: string, filename: string): Promise<void> => {
    const token = localStorage.getItem('access_token')
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    const url = `${baseUrl}${prefix}/${kbId}/documents/${docId}/download`
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
    
    if (!response.ok) {
      throw new Error('Download failed')
    }
    
    const blob = await response.blob()
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  }
  }
}

export const knowledgeBasesApi = createKnowledgeBasesApi('/knowledge-bases')
export const adminKnowledgeBasesApi = createKnowledgeBasesApi('/admin/knowledge-bases')
