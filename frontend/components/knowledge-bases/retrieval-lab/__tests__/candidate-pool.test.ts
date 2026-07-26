import { describe, expect, it } from 'bun:test'
import type { SearchParams } from '@/lib/api'
import { buildCandidatePool, defaultStrategies } from '../candidate-pool'
import type { Config, RetrievalApi } from '../shared'

const mockConfig: Config = {
  search_mode: 'hybrid',
  top_k: 10,
  threshold: 0.5,
  dense_weight: 0.5,
  lexical_weight: 0.5,
  rrf_k: 60,
  rerank_enabled: false,
  rerank_candidate_k: 20,
  rerank_score_threshold: null,
}

describe('defaultStrategies', () => {
  it('generates 3 strategies without rerank model', () => {
    const strategies = defaultStrategies(mockConfig, false)
    expect(strategies).toHaveLength(3)
    expect(strategies.map(s => s.label)).toEqual(['vector', 'fulltext', 'hybrid'])
  })

  it('generates 4 strategies with rerank model', () => {
    const strategies = defaultStrategies(mockConfig, true)
    expect(strategies).toHaveLength(4)
    expect(strategies.map(s => s.label)).toEqual(['vector', 'fulltext', 'hybrid', 'hybrid+rerank'])
  })

  it('sets score_threshold to 0 for pooling', () => {
    const strategies = defaultStrategies(mockConfig, false)
    strategies.forEach(s => {
      expect(s.score_threshold).toBe(0)
    })
  })

  it('preserves base config weights in hybrid strategy', () => {
    const strategies = defaultStrategies(mockConfig, false)
    const hybrid = strategies.find(s => s.label === 'hybrid')
    expect(hybrid?.dense_weight).toBe(mockConfig.dense_weight)
    expect(hybrid?.lexical_weight).toBe(mockConfig.lexical_weight)
    expect(hybrid?.rrf_k).toBe(mockConfig.rrf_k)
  })
})

describe('buildCandidatePool', () => {
  it('deduplicates chunks across strategies', async () => {
    const mockApi: RetrievalApi = {
      search: async () => ({
        results: [
          { chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Doc 1', content: 'Content 1', score: 0.9, rank: 1 },
          { chunk_id: 'chunk-2', document_id: 'doc-1', document_name: 'Doc 1', content: 'Content 2', score: 0.8, rank: 2 },
        ],
        diagnostics: { retrieved_at: '', timings: {} },
      }),
    } as RetrievalApi

    const strategies = defaultStrategies(mockConfig, false)
    const result = await buildCandidatePool(mockApi, 'kb-1', 'test query', strategies, 10)

    expect(result.candidates).toHaveLength(2)
    expect(result.candidates[0].chunk_id).toBe('chunk-1')
    expect(result.candidates[0].strategies).toHaveLength(3) // All 3 strategies returned same chunks
    expect(result.errors).toHaveLength(0)
  })

  it('preserves partial success when one strategy fails', async () => {
    let callCount = 0
    const mockApi: RetrievalApi = {
      search: async () => {
        callCount++
        if (callCount === 2) throw new Error('Fulltext unavailable')
        return {
          results: [
            { chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Doc 1', content: 'Content 1', score: 0.9, rank: 1 },
          ],
          diagnostics: { retrieved_at: '', timings: {} },
        }
      },
    } as RetrievalApi

    const strategies = defaultStrategies(mockConfig, false)
    const result = await buildCandidatePool(mockApi, 'kb-1', 'test query', strategies, 10)

    expect(result.candidates).toHaveLength(1)
    expect(result.candidates[0].strategies).toHaveLength(2) // vector + hybrid succeeded
    expect(result.errors).toHaveLength(1)
    expect(result.errors[0].strategy).toBe('fulltext')
  })

  it('computes best rank across strategies', async () => {
    let callCount = 0
    const mockApi: RetrievalApi = {
      search: async () => {
        callCount++
        if (callCount === 1) {
          // Vector: chunk-1 rank 1, chunk-2 rank 2
          return {
            results: [
              { chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Doc 1', content: 'C1', score: 0.9, rank: 1 },
              { chunk_id: 'chunk-2', document_id: 'doc-1', document_name: 'Doc 1', content: 'C2', score: 0.8, rank: 2 },
            ],
            diagnostics: { retrieved_at: '', timings: {} },
          }
        } else {
          // Fulltext/Hybrid: chunk-2 rank 1, chunk-1 rank 2
          return {
            results: [
              { chunk_id: 'chunk-2', document_id: 'doc-1', document_name: 'Doc 1', content: 'C2', score: 0.9, rank: 1 },
              { chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Doc 1', content: 'C1', score: 0.8, rank: 2 },
            ],
            diagnostics: { retrieved_at: '', timings: {} },
          }
        }
      },
    } as RetrievalApi

    const strategies = defaultStrategies(mockConfig, false)
    const result = await buildCandidatePool(mockApi, 'kb-1', 'test query', strategies, 10)

    const chunk1 = result.candidates.find(c => c.chunk_id === 'chunk-1')
    const chunk2 = result.candidates.find(c => c.chunk_id === 'chunk-2')

    expect(chunk1?.best_rank).toBe(1) // Best rank from vector
    expect(chunk2?.best_rank).toBe(1) // Best rank from fulltext/hybrid
    expect(chunk1?.ranks['vector']).toBe(1)
    expect(chunk1?.ranks['fulltext']).toBe(2)
  })

  it('sorts by best rank, then strategy count, then chunk_id', async () => {
    let callCount = 0
    const mockApi: RetrievalApi = {
      search: async () => {
        callCount++
        if (callCount === 1) {
          // Vector only returns chunk-1 and chunk-3
          return {
            results: [
              { chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Doc 1', content: 'C1', score: 0.9, rank: 1 },
              { chunk_id: 'chunk-3', document_id: 'doc-1', document_name: 'Doc 1', content: 'C3', score: 0.7, rank: 2 },
            ],
            diagnostics: { retrieved_at: '', timings: {} },
          }
        } else {
          // Fulltext/Hybrid return all three
          return {
            results: [
              { chunk_id: 'chunk-2', document_id: 'doc-1', document_name: 'Doc 1', content: 'C2', score: 0.9, rank: 1 },
              { chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Doc 1', content: 'C1', score: 0.8, rank: 2 },
              { chunk_id: 'chunk-3', document_id: 'doc-1', document_name: 'Doc 1', content: 'C3', score: 0.7, rank: 3 },
            ],
            diagnostics: { retrieved_at: '', timings: {} },
          }
        }
      },
    } as RetrievalApi

    const strategies = defaultStrategies(mockConfig, false)
    const result = await buildCandidatePool(mockApi, 'kb-1', 'test query', strategies, 10)

    // chunk-1: best_rank=1, 3 strategies
    // chunk-2: best_rank=1, 2 strategies
    // chunk-3: best_rank=2, 3 strategies
    // Sort: chunk-1 (rank 1, 3 strats), chunk-2 (rank 1, 2 strats), chunk-3 (rank 2, 3 strats)
    expect(result.candidates[0].chunk_id).toBe('chunk-1')
    expect(result.candidates[1].chunk_id).toBe('chunk-2')
    expect(result.candidates[2].chunk_id).toBe('chunk-3')
  })

  it('returns empty candidates when all strategies fail', async () => {
    const mockApi: RetrievalApi = {
      search: async () => {
        throw new Error('All strategies failed')
      },
    } as RetrievalApi

    const strategies = defaultStrategies(mockConfig, false)
    const result = await buildCandidatePool(mockApi, 'kb-1', 'test query', strategies, 10)

    expect(result.candidates).toHaveLength(0)
    expect(result.errors).toHaveLength(3)
  })

  it('uses depth parameter for pool top_k', async () => {
    const searchParams: SearchParams[] = []
    const mockApi: RetrievalApi = {
      search: async (_kbId, params) => {
        searchParams.push(params)
        return { results: [], diagnostics: { retrieved_at: '', timings: {} } }
      },
    } as RetrievalApi

    const strategies = defaultStrategies(mockConfig, false)
    await buildCandidatePool(mockApi, 'kb-1', 'test query', strategies, 25)

    searchParams.forEach(params => {
      expect(params.top_k).toBe(25)
    })
  })
})
