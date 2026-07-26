/**
 * Multi-strategy candidate pooling for Retrieval Lab.
 *
 * Stage 4: Build evaluation datasets by running multiple retrieval strategies
 * in parallel, deduplicating by chunk ID, and preserving provenance.
 */

import type { SearchMode, SearchParams } from '@/lib/api'
import type { Config, RetrievalApi } from './shared'

export interface StrategyConfig {
  label: string
  search_mode: SearchMode
  top_k: number
  score_threshold: number
  dense_weight: number
  lexical_weight: number
  rrf_k: number
  rerank_enabled: boolean
  rerank_candidate_k: number
  rerank_score_threshold: number | null
}

export interface CandidateChunk {
  chunk_id: string
  document_id: string
  document_name: string
  content: string
  /** Which strategies retrieved this chunk */
  strategies: string[]
  /** Best (lowest) rank across all strategies */
  best_rank: number
  /** Per-strategy ranks */
  ranks: Record<string, number>
}

export interface PoolResult {
  candidates: CandidateChunk[]
  errors: Array<{ strategy: string; error: string }>
  depth: number
}

/**
 * Generate four default strategies: vector, fulltext, hybrid, hybrid+rerank.
 * Uses the current config as baseline but varies search_mode and rerank.
 */
export function defaultStrategies(
  baseConfig: Config,
  hasRerankModel: boolean
): StrategyConfig[] {
  const strategies: StrategyConfig[] = [
    {
      label: 'vector',
      search_mode: 'vector',
      top_k: baseConfig.top_k,
      score_threshold: 0, // Pool phase uses no threshold
      dense_weight: 1,
      lexical_weight: 0,
      rrf_k: 60,
      rerank_enabled: false,
      rerank_candidate_k: baseConfig.rerank_candidate_k,
      rerank_score_threshold: null,
    },
    {
      label: 'fulltext',
      search_mode: 'fulltext',
      top_k: baseConfig.top_k,
      score_threshold: 0,
      dense_weight: 0,
      lexical_weight: 1,
      rrf_k: 60,
      rerank_enabled: false,
      rerank_candidate_k: baseConfig.rerank_candidate_k,
      rerank_score_threshold: null,
    },
    {
      label: 'hybrid',
      search_mode: 'hybrid',
      top_k: baseConfig.top_k,
      score_threshold: 0,
      dense_weight: baseConfig.dense_weight,
      lexical_weight: baseConfig.lexical_weight,
      rrf_k: baseConfig.rrf_k,
      rerank_enabled: false,
      rerank_candidate_k: baseConfig.rerank_candidate_k,
      rerank_score_threshold: null,
    },
  ]

  if (hasRerankModel) {
    strategies.push({
      label: 'hybrid+rerank',
      search_mode: 'hybrid',
      top_k: baseConfig.top_k,
      score_threshold: 0,
      dense_weight: baseConfig.dense_weight,
      lexical_weight: baseConfig.lexical_weight,
      rrf_k: baseConfig.rrf_k,
      rerank_enabled: true,
      rerank_candidate_k: Math.max(baseConfig.top_k, baseConfig.rerank_candidate_k),
      rerank_score_threshold: baseConfig.rerank_score_threshold,
    })
  }

  return strategies
}

/**
 * Run all strategies in parallel and merge results.
 * Uses Promise.allSettled to preserve partial success.
 */
export async function buildCandidatePool(
  api: RetrievalApi,
  knowledgeBaseId: string,
  query: string,
  strategies: StrategyConfig[],
  depth: number
): Promise<PoolResult> {
  const results = await Promise.allSettled(
    strategies.map(async strategy => {
      const params: SearchParams = {
        query,
        search_mode: strategy.search_mode,
        top_k: depth, // Pool uses configurable depth, not strategy top_k
        threshold: strategy.score_threshold,
        dense_weight: strategy.dense_weight,
        lexical_weight: strategy.lexical_weight,
        rrf_k: strategy.rrf_k,
        rerank_enabled: strategy.rerank_enabled,
        rerank_candidate_k: strategy.rerank_enabled ? strategy.rerank_candidate_k : undefined,
        rerank_score_threshold: strategy.rerank_enabled ? strategy.rerank_score_threshold : undefined,
      }
      const response = await api.search(knowledgeBaseId, params)
      return { strategy: strategy.label, response }
    })
  )

  const errors: Array<{ strategy: string; error: string }> = []
  const chunkMap = new Map<string, CandidateChunk>()

  results.forEach((result, index) => {
    const strategyLabel = strategies[index].label

    if (result.status === 'rejected') {
      errors.push({ strategy: strategyLabel, error: String(result.reason) })
      return
    }

    const { response } = result.value
    response.results.forEach((item, rank) => {
      const chunkId = item.chunk_id
      const existing = chunkMap.get(chunkId)

      if (existing) {
        // Chunk already seen from another strategy
        existing.strategies.push(strategyLabel)
        existing.ranks[strategyLabel] = rank + 1
        existing.best_rank = Math.min(existing.best_rank, rank + 1)
      } else {
        // First time seeing this chunk
        chunkMap.set(chunkId, {
          chunk_id: chunkId,
          document_id: item.document_id,
          document_name: item.document_name,
          content: item.content,
          strategies: [strategyLabel],
          best_rank: rank + 1,
          ranks: { [strategyLabel]: rank + 1 },
        })
      }
    })
  })

  // Sort by: best rank ascending, strategy count descending, chunk_id ascending
  const candidates = Array.from(chunkMap.values()).sort((a, b) => {
    if (a.best_rank !== b.best_rank) return a.best_rank - b.best_rank
    if (a.strategies.length !== b.strategies.length) return b.strategies.length - a.strategies.length
    return a.chunk_id.localeCompare(b.chunk_id)
  })

  return { candidates, errors, depth }
}
