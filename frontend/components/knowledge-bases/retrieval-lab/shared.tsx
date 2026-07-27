import type {
  KnowledgeBase,
  KnowledgeBaseSettings,
  SearchMode,
  SearchParams,
  SearchResponse,
} from '@/lib/api'

export type RetrievalApi = {
  getKnowledgeBase(id: string): Promise<KnowledgeBase>
  search(id: string, params: SearchParams): Promise<SearchResponse>
  updateKnowledgeBase(id: string, data: { settings: KnowledgeBaseSettings }): Promise<KnowledgeBase>
}

export type Config = {
  search_mode: SearchMode
  top_k: number
  threshold: number
  dense_weight: number
  lexical_weight: number
  rrf_k: number
  rerank_enabled: boolean
  rerank_candidate_k: number
  rerank_score_threshold: number | null
}

export function runConfig(config: Config, hasRerankModel: boolean): Omit<SearchParams, 'query' | 'threshold'> & { score_threshold: number } {
  const rerank = hasRerankModel && config.rerank_enabled
  return {
    search_mode: config.search_mode,
    top_k: config.top_k,
    score_threshold: config.threshold,
    dense_weight: config.dense_weight,
    lexical_weight: config.lexical_weight,
    rrf_k: config.rrf_k,
    rerank_enabled: rerank,
    rerank_candidate_k: rerank ? Math.max(config.top_k, config.rerank_candidate_k) : config.top_k,
    rerank_score_threshold: rerank ? config.rerank_score_threshold : null,
  }
}
