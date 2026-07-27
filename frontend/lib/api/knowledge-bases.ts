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
  rerank_score_threshold?: number | null
  search_mode?: SearchMode | null
  top_k?: number | null
  score_threshold?: number | null
  dense_weight?: number | null
  lexical_weight?: number | null
  rrf_k?: number | null
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
  ownOnly?: boolean
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

export interface RetrievalReason {
  channel: string
  error: string
}

export interface RetrievalDiagnostic {
  kb_id: string
  code: 'inactive' | 'missing_embedding_model' | 'timeout' | 'failed'
  detail?: string
  stage?: string
  latency_ms?: number
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  document_name: string
  content: string
  score: number
  metadata: Record<string, unknown> | null
  search_type?: string
  dense_score?: number
  dense_rank?: number
  lexical_score?: number
  lexical_rank?: number
  fusion_score?: number
  fusion_rank?: number
  original_score?: number
  rerank_score?: number
  rerank_rank?: number
  rerank_reason?: string
  final_score_stage?: string
  degradation_reasons?: RetrievalReason[]
}

export type SearchMode = 'vector' | 'fulltext' | 'hybrid'

export interface SearchParams {
  query: string
  search_mode?: SearchMode
  top_k?: number
  threshold?: number
  dense_weight?: number
  lexical_weight?: number
  rrf_k?: number
  rerank_enabled?: boolean
  rerank_candidate_k?: number
  rerank_score_threshold?: number | null
}

export interface RetrievalTiming {
  stage: 'recall' | 'rerank' | 'context' | 'total'
  latency_ms: number
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  total: number
  diagnostics: RetrievalDiagnostic[]
  timings: RetrievalTiming[]
}

export interface EvaluationCaseInput {
  query: string
  chunk_relevance: Record<string, number>
  document_relevance: Record<string, number>
  expected_empty: boolean
}

export interface EvaluationCase extends EvaluationCaseInput {
  id: string
}

export interface EvaluationDataset {
  id: string
  knowledge_base_id: string
  name: string
  description: string | null
  created_by_id: string | null
  created_at: string
  updated_at: string
  cases: EvaluationCase[]
}

export interface EvaluationDatasetInput {
  name: string
  description?: string | null
  cases?: EvaluationCaseInput[]
}

export type EvaluationExportFormat = 'json' | 'csv'

export interface EvaluationDatasetExport {
  format: EvaluationExportFormat
  content: string
}

export type EvaluationRunConfig = Omit<SearchParams, 'query' | 'threshold'> & { score_threshold: number }
export type EvaluationRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'canceled'

export interface EvaluationCaseResult {
  id: string
  case_id: string
  case_snapshot: EvaluationCaseInput
  candidates: Array<Record<string, unknown>>
  metrics: Record<string, unknown>
  latency_ms: number
  error_message: string | null
}

export interface EvaluationRun {
  id: string
  dataset_id: string
  created_by_id: string | null
  status: EvaluationRunStatus
  config_snapshot: EvaluationRunConfig
  version_snapshot: Record<string, unknown>
  summary_metrics: Record<string, unknown> | null
  error_message: string | null
  metric_k?: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  case_results: EvaluationCaseResult[]
  // Sweep integration fields
  sweep_id?: string | null
  stage?: string | null
  candidate_key?: string | null
  label?: string | null
  dataset_revision?: number | null
  dataset_snapshot_hash?: string | null
}

export interface RunComparison {
  baseline_id: string
  candidate_id: string
  comparable: boolean
  incompatibility_reason: string | null
  metric_deltas: Record<string, number>
  improved_cases: number
  unchanged_cases: number
  regressed_cases: number
  unpaired_cases: number
  case_deltas: Array<{
    case_id: string
    query: string
    baseline_score: number
    candidate_score: number
    delta: number
    outcome: 'improved' | 'unchanged' | 'regressed'
  }>
  config_diff: Record<string, { baseline: unknown; candidate: unknown }>
}

// ============ Sweep Types ============

export type EvaluationSweepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'canceled'

export interface EvaluationSweepCreate {
  objective: string
  metric_k: number
  serving_top_k: number
  space: Record<string, unknown>
  guards: Record<string, unknown>
  baseline_config?: Record<string, unknown> | null
}

export interface EvaluationSweep {
  id: string
  dataset_id: string
  created_by_id: string | null
  status: EvaluationSweepStatus
  objective: string
  metric_k: number
  serving_top_k: number
  space: Record<string, unknown>
  guards: Record<string, unknown>
  baseline_config: Record<string, unknown>
  recommendation: Record<string, unknown> | null
  best_run_id: string | null
  verification_run_id: string | null
  stage: string | null
  progress: Record<string, { total: number; completed: number }>
  task_id: string | null
  heartbeat_at: string | null
  applied: boolean
  applied_at: string | null
  applied_by_id: string | null
  applied_diff: Record<string, unknown> | null
  error_message: string | null
  dataset_revision: number
  dataset_snapshot_hash: string
  version_snapshot: Record<string, unknown>
  created_at: string
  started_at: string | null
  finished_at: string | null
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
    const { page = 1, pageSize = 20, search, status, teamId, ownOnly } = params
    const queryParams = new URLSearchParams()
    queryParams.append('page', String(page))
    queryParams.append('page_size', String(pageSize))
    if (search) queryParams.append('search', search)
    status?.forEach((value) => queryParams.append('status', value))
    if (teamId) queryParams.append('team_id', teamId)
    if (ownOnly) queryParams.append('own_only', 'true')
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
      dense_weight: params.dense_weight,
      lexical_weight: params.lexical_weight,
      rrf_k: params.rrf_k,
      rerank_enabled: params.rerank_enabled,
      rerank_candidate_k: params.rerank_candidate_k,
      rerank_score_threshold: params.rerank_score_threshold,
    }
    return api.post<SearchResponse>(`${prefix}/${id}/search`, requestBody, { silent: true })
  },

  listEvaluationDatasets: (kbId: string): Promise<EvaluationDataset[]> =>
    api.get(`${prefix}/${kbId}/evaluation-datasets`),

  createEvaluationDataset: (kbId: string, data: EvaluationDatasetInput): Promise<EvaluationDataset> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets`, data),

  getEvaluationDataset: (kbId: string, datasetId: string): Promise<EvaluationDataset> =>
    api.get(`${prefix}/${kbId}/evaluation-datasets/${datasetId}`),

  updateEvaluationDataset: (kbId: string, datasetId: string, data: Partial<EvaluationDatasetInput>): Promise<EvaluationDataset> =>
    api.put(`${prefix}/${kbId}/evaluation-datasets/${datasetId}`, data),

  importEvaluationDataset: (kbId: string, datasetId: string, file: File): Promise<EvaluationDataset> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/import`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  /** 单个新增用例，不影响已有用例的 ID 与历史结果关联 */
  createEvaluationCase: (kbId: string, datasetId: string, data: EvaluationCaseInput): Promise<EvaluationCase> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/cases`, data),

  /** 原地更新单个用例，保留其 ID */
  updateEvaluationCase: (kbId: string, datasetId: string, caseId: string, data: EvaluationCaseInput): Promise<EvaluationCase> =>
    api.put(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/cases/${caseId}`, data),

  deleteEvaluationCase: (kbId: string, datasetId: string, caseId: string): Promise<void> =>
    api.delete(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/cases/${caseId}`),

  /** 导出用例，输出可直接回灌到导入接口 */
  exportEvaluationDataset: (kbId: string, datasetId: string, format: EvaluationExportFormat = 'json'): Promise<EvaluationDatasetExport> =>
    api.get(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/export?format=${format}`),

  /** Query-based case upsert: create if query not found, update if exactly one match */
  upsertEvaluationCaseByQuery: (kbId: string, datasetId: string, data: EvaluationCaseInput): Promise<EvaluationCase> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/upsert-case`, data),

  startEvaluationRun: (kbId: string, datasetId: string, config: EvaluationRunConfig): Promise<EvaluationRun> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/runs`, config),

  listEvaluationRuns: (kbId: string, datasetId: string, sweepId?: string): Promise<EvaluationRun[]> => {
    const url = sweepId
      ? `${prefix}/${kbId}/evaluation-datasets/${datasetId}/runs?sweep_id=${sweepId}`
      : `${prefix}/${kbId}/evaluation-datasets/${datasetId}/runs`
    return api.get(url)
  },

  getEvaluationRun: (kbId: string, datasetId: string, runId: string): Promise<EvaluationRun> =>
    api.get(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/runs/${runId}`),

  cancelEvaluationRun: (kbId: string, datasetId: string, runId: string): Promise<EvaluationRun> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/runs/${runId}/cancel`),

  compareEvaluationRuns: (kbId: string, datasetId: string, baselineRunId: string, candidateRunId: string): Promise<RunComparison> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/compare-runs`, { baseline_run_id: baselineRunId, candidate_run_id: candidateRunId }),

  // ============ Sweep API ============

  createEvaluationSweep: (kbId: string, datasetId: string, data: EvaluationSweepCreate): Promise<EvaluationSweep> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/sweeps`, data),

  getEvaluationSweep: (kbId: string, datasetId: string, sweepId: string): Promise<EvaluationSweep> =>
    api.get(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/sweeps/${sweepId}`),

  cancelEvaluationSweep: (kbId: string, datasetId: string, sweepId: string): Promise<{ success: boolean; message: string }> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/sweeps/${sweepId}/cancel`),

  applyEvaluationSweep: (kbId: string, datasetId: string, sweepId: string): Promise<{ applied: boolean; recommendation: Record<string, unknown>; baseline_config: Record<string, unknown> }> =>
    api.post(`${prefix}/${kbId}/evaluation-datasets/${datasetId}/sweeps/${sweepId}/apply`),

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
