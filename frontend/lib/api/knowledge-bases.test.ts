import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'

import { api } from './client'
import {
  adminKnowledgeBasesApi,
  knowledgeBasesApi,
  type RetrievalDiagnostic,
  type SearchResult,
} from './knowledge-bases'

let get: ReturnType<typeof spyOn>
let post: ReturnType<typeof spyOn>
let put: ReturnType<typeof spyOn>
let remove: ReturnType<typeof spyOn>
let spies: Array<ReturnType<typeof spyOn>>

beforeEach(() => {
  get = spyOn(api, 'get').mockResolvedValue(undefined)
  post = spyOn(api, 'post').mockResolvedValue(undefined)
  put = spyOn(api, 'put').mockResolvedValue(undefined)
  remove = spyOn(api, 'delete').mockResolvedValue(undefined)
  spies = [get, post, put, remove]
})

afterEach(() => {
  for (const spy of spies) spy.mockRestore()
})

const apiVariants = [
  ['user', knowledgeBasesApi, '/knowledge-bases'],
  ['admin', adminKnowledgeBasesApi, '/admin/knowledge-bases'],
] as const

describe('knowledge base APIs', () => {
  test('types structured retrieval diagnostics and every score/rank stage', () => {
    const result: SearchResult = {
      chunk_id: 'chunk-1', document_id: 'doc-1', document_name: 'Guide', content: 'Policy',
      score: 0.4, metadata: null, search_type: 'hybrid', dense_score: 0.81, dense_rank: 2,
      lexical_score: 7.4, lexical_rank: 1, fusion_score: 0.03, fusion_rank: 1,
      original_score: 0.03, rerank_score: 0.4, rerank_rank: 1, rerank_reason: 'match',
      final_score_stage: 'rerank', degradation_reasons: [{ channel: 'dense', error: 'fallback' }],
    }
    const diagnostic: RetrievalDiagnostic = {
      kb_id: 'kb-1', code: 'timeout', stage: 'dense', latency_ms: 120, detail: 'fallback',
    }

    expect(result).toMatchObject({ dense_rank: 2, lexical_rank: 1, fusion_rank: 1, rerank_rank: 1 })
    expect(diagnostic).toMatchObject({ code: 'timeout', stage: 'dense', latency_ms: 120 })
  })

  for (const [name, knowledgeBasesApi, prefix] of apiVariants) {
    test(`${name} routes construct knowledge base requests`, async () => {
      await knowledgeBasesApi.getKnowledgeBases()
      await knowledgeBasesApi.getKnowledgeBases({
        page: 2,
        pageSize: 50,
        search: 'sales & support',
        status: ['active', 'archived'],
        teamId: 'team-1',
        ownOnly: true,
      })
      await knowledgeBasesApi.getKnowledgeBase('kb-1')
      await knowledgeBasesApi.createKnowledgeBase({ name: 'Sales', team_id: 'team-1' })
      await knowledgeBasesApi.updateKnowledgeBase('kb-1', { status: 'archived' })
      await knowledgeBasesApi.deleteKnowledgeBase('kb-1')
      await knowledgeBasesApi.getStats('kb-1')
      await knowledgeBasesApi.search('kb-1', { query: 'renewal' })
      await knowledgeBasesApi.search('kb-1', {
        query: 'renewal',
        search_mode: 'vector',
        top_k: 10,
        threshold: 0.8,
        dense_weight: 1.5,
        lexical_weight: 0.5,
        rrf_k: 80,
        rerank_enabled: false,
        rerank_candidate_k: 30,
        rerank_score_threshold: 0.5,
      })

      expect(get).toHaveBeenNthCalledWith(1, `${prefix}?page=1&page_size=20`)
      expect(get).toHaveBeenNthCalledWith(
        2,
        `${prefix}?page=2&page_size=50&search=sales+%26+support&status=active&status=archived&team_id=team-1&own_only=true`
      )
      expect(get).toHaveBeenNthCalledWith(3, `${prefix}/kb-1`)
      expect(post).toHaveBeenNthCalledWith(1, prefix, { name: 'Sales', team_id: 'team-1' })
      expect(put).toHaveBeenCalledWith(`${prefix}/kb-1`, { status: 'archived' })
      expect(remove).toHaveBeenCalledWith(`${prefix}/kb-1`)
      expect(get).toHaveBeenNthCalledWith(4, `${prefix}/kb-1/stats`)
      expect(post).toHaveBeenNthCalledWith(2, `${prefix}/kb-1/search`, {
        query: 'renewal',
        search_mode: 'hybrid',
        top_k: 5,
        score_threshold: 0,
        dense_weight: undefined,
        lexical_weight: undefined,
        rrf_k: undefined,
        rerank_enabled: undefined,
        rerank_candidate_k: undefined,
        rerank_score_threshold: undefined,
      }, { silent: true })
      expect(post).toHaveBeenNthCalledWith(3, `${prefix}/kb-1/search`, {
        query: 'renewal',
        search_mode: 'vector',
        top_k: 10,
        score_threshold: 0.8,
        dense_weight: 1.5,
        lexical_weight: 0.5,
        rrf_k: 80,
        rerank_enabled: false,
        rerank_candidate_k: 30,
        rerank_score_threshold: 0.5,
      }, { silent: true })
    })

    test(`${name} routes construct persistent evaluation requests`, async () => {
      const cases = [{ query: 'renewal', chunk_relevance: {}, document_relevance: {}, expected_empty: false }]
      const config = { search_mode: 'hybrid' as const, top_k: 5, score_threshold: 0, dense_weight: 1, lexical_weight: 1, rrf_k: 60, rerank_enabled: false, rerank_candidate_k: 5, rerank_fail_open: true, rerank_score_threshold: null }
      const file = new File(['query\nrenewal'], 'cases.csv', { type: 'text/csv' })
      await knowledgeBasesApi.listEvaluationDatasets('kb-1')
      await knowledgeBasesApi.createEvaluationDataset('kb-1', { name: 'Regression', cases })
      await knowledgeBasesApi.getEvaluationDataset('kb-1', 'dataset-1')
      await knowledgeBasesApi.updateEvaluationDataset('kb-1', 'dataset-1', { cases })
      await knowledgeBasesApi.importEvaluationDataset('kb-1', 'dataset-1', file)
      await knowledgeBasesApi.startEvaluationRun('kb-1', 'dataset-1', config)
      await knowledgeBasesApi.listEvaluationRuns('kb-1', 'dataset-1')
      await knowledgeBasesApi.getEvaluationRun('kb-1', 'dataset-1', 'run-1')
      await knowledgeBasesApi.cancelEvaluationRun('kb-1', 'dataset-1', 'run-1')

      const base = `${prefix}/kb-1/evaluation-datasets`
      expect(get).toHaveBeenNthCalledWith(1, base)
      expect(post).toHaveBeenNthCalledWith(1, base, { name: 'Regression', cases })
      expect(get).toHaveBeenNthCalledWith(2, `${base}/dataset-1`)
      expect(put).toHaveBeenCalledWith(`${base}/dataset-1`, { cases })
      expect(post.mock.calls[1][0]).toBe(`${base}/dataset-1/import`)
      expect(post.mock.calls[1][1]).toBeInstanceOf(FormData)
      expect(post).toHaveBeenNthCalledWith(3, `${base}/dataset-1/runs`, config)
      expect(get).toHaveBeenNthCalledWith(3, `${base}/dataset-1/runs`)
      expect(get).toHaveBeenNthCalledWith(4, `${base}/dataset-1/runs/run-1`)
      expect(post).toHaveBeenNthCalledWith(4, `${base}/dataset-1/runs/run-1/cancel`)
    })

    test(`${name} routes construct document and chunk requests`, async () => {
      const file = new File(['content'], 'sales.txt', { type: 'text/plain' })
      const settings = { chunk_size: 300, clean_text: false }
      const chunk = { content: 'corrected', chunk_index: 2 }

      await knowledgeBasesApi.getDocuments('kb-1')
      await knowledgeBasesApi.getDocuments('kb-1', {
        page: 3,
        pageSize: 40,
        status: ['pending', 'error'],
        doc_type: ['pdf', 'url'],
        search: 'quarterly report',
      })
      await knowledgeBasesApi.getDocument('kb-1', 'doc-1')
      await knowledgeBasesApi.uploadDocument('kb-1', file)
      await knowledgeBasesApi.importUrl('kb-1', 'https://example.test', 'Example')
      await knowledgeBasesApi.deleteDocument('kb-1', 'doc-1')
      await knowledgeBasesApi.processDocument('kb-1', 'doc-1')
      await knowledgeBasesApi.processDocument('kb-1', 'doc-1', settings)
      await knowledgeBasesApi.processDocumentWithChunks('kb-1', 'doc-1', [chunk])
      await knowledgeBasesApi.reprocessDocument('kb-1', 'doc-1')
      await knowledgeBasesApi.retryFailedChunks('kb-1', 'doc-1')
      await knowledgeBasesApi.retryFailedChunk('kb-1', 'doc-1', 'chunk-1')
      await knowledgeBasesApi.getDocumentChunks('kb-1', 'doc-1')
      await knowledgeBasesApi.updateChunk('kb-1', 'doc-1', 'chunk-1', chunk)
      await knowledgeBasesApi.deleteChunk('kb-1', 'doc-1', 'chunk-1')
      await knowledgeBasesApi.createChunk('kb-1', 'doc-1', chunk)
      await knowledgeBasesApi.createChunk('kb-1', 'doc-1', chunk, 4)
      await knowledgeBasesApi.rechunkDocument('kb-1', 'doc-1', { chunk_overlap: 20 })
      await knowledgeBasesApi.previewChunks('kb-1', 'doc-1', { chunk_size: 200, chunk_overlap: 10 })

      expect(get).toHaveBeenNthCalledWith(1, `${prefix}/kb-1/documents?page=1&page_size=20`)
      expect(get).toHaveBeenNthCalledWith(
        2,
        `${prefix}/kb-1/documents?page=3&page_size=40&status=pending&status=error&doc_type=pdf&doc_type=url&search=quarterly+report`
      )
      expect(get).toHaveBeenNthCalledWith(3, `${prefix}/kb-1/documents/doc-1`)
      expect(post).toHaveBeenNthCalledWith(
        1,
        `${prefix}/kb-1/documents/upload`,
        expect.any(FormData),
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      expect(post).toHaveBeenNthCalledWith(2, `${prefix}/kb-1/documents/url`, {
        source_url: 'https://example.test',
        name: 'Example',
      })
      expect(remove).toHaveBeenNthCalledWith(1, `${prefix}/kb-1/documents/doc-1`)
      expect(post).toHaveBeenNthCalledWith(3, `${prefix}/kb-1/documents/doc-1/process`, {})
      expect(post).toHaveBeenNthCalledWith(4, `${prefix}/kb-1/documents/doc-1/process`, settings)
      expect(post).toHaveBeenNthCalledWith(5, `${prefix}/kb-1/documents/doc-1/process-with-chunks`, { chunks: [chunk] })
      expect(post).toHaveBeenNthCalledWith(6, `${prefix}/kb-1/documents/doc-1/reprocess`)
      expect(post).toHaveBeenNthCalledWith(7, `${prefix}/kb-1/documents/doc-1/retry-failed-chunks`)
      expect(post).toHaveBeenNthCalledWith(8, `${prefix}/kb-1/documents/doc-1/chunks/chunk-1/retry-embedding`)
      expect(get).toHaveBeenNthCalledWith(4, `${prefix}/kb-1/documents/doc-1/chunks?page=1&page_size=20`)
      expect(put).toHaveBeenCalledWith(`${prefix}/kb-1/documents/doc-1/chunks/chunk-1`, chunk)
      expect(remove).toHaveBeenNthCalledWith(2, `${prefix}/kb-1/documents/doc-1/chunks/chunk-1`)
      expect(post).toHaveBeenNthCalledWith(9, `${prefix}/kb-1/documents/doc-1/chunks`, chunk)
      expect(post).toHaveBeenNthCalledWith(10, `${prefix}/kb-1/documents/doc-1/chunks?after_index=4`, chunk)
      expect(post).toHaveBeenNthCalledWith(11, `${prefix}/kb-1/documents/doc-1/rechunk`, { chunk_overlap: 20 })
      expect(post).toHaveBeenNthCalledWith(12, `${prefix}/kb-1/documents/doc-1/preview-chunks`, { chunk_size: 200, chunk_overlap: 10 })
    })
  }

  test('forwards client errors without masking them', async () => {
    const error = new Error('network unavailable')
    get.mockRejectedValueOnce(error)

    await expect(knowledgeBasesApi.getKnowledgeBase('kb-1')).rejects.toBe(error)
    expect(get).toHaveBeenCalledWith('/knowledge-bases/kb-1')
  })

  test('rejects an unsuccessful document download', async () => {
    const originalFetch = globalThis.fetch
    const originalLocalStorage = globalThis.localStorage
    const fetchMock = mock(() => Promise.resolve(new Response(null, { status: 500 })))
    Object.assign(globalThis, {
      fetch: fetchMock,
      localStorage: { getItem: () => 'token-1' },
    })

    try {
      await expect(knowledgeBasesApi.downloadDocument('kb-1', 'doc-1', 'sales.txt')).rejects.toThrow('Download failed')
      expect(fetchMock).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/knowledge-bases/kb-1/documents/doc-1/download',
        { method: 'GET', headers: { Authorization: 'Bearer token-1' } }
      )
    } finally {
      Object.assign(globalThis, { fetch: originalFetch, localStorage: originalLocalStorage })
    }
  })

  test('downloads a successful response and releases its object URL', async () => {
    const blob = new Blob(['report'])
    const link = { href: '', download: '', click: mock(() => {}) }
    const body = { appendChild: mock(() => {}), removeChild: mock(() => {}) }
    const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
    const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
    const fetch = spyOn(globalThis, 'fetch').mockResolvedValue(new Response(blob))
    const createObjectURL = spyOn(URL, 'createObjectURL').mockReturnValue('blob:report')
    const revokeObjectURL = spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    Object.defineProperties(globalThis, {
      document: { configurable: true, value: { createElement: () => link, body } },
      localStorage: { configurable: true, value: { getItem: () => 'token-1' } },
      window: { configurable: true, value: { URL } },
    })

    try {
      await knowledgeBasesApi.downloadDocument('kb-1', 'doc-1', 'report.pdf')

      expect(link).toMatchObject({ href: 'blob:report', download: 'report.pdf' })
      expect(body.appendChild).toHaveBeenCalledWith(link)
      expect(link.click).toHaveBeenCalled()
      expect(body.removeChild).toHaveBeenCalledWith(link)
      expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:report')
    } finally {
      fetch.mockRestore()
      createObjectURL.mockRestore()
      revokeObjectURL.mockRestore()
      if (originalDocument) Object.defineProperty(globalThis, 'document', originalDocument)
      else Reflect.deleteProperty(globalThis, 'document')
      if (originalLocalStorage) Object.defineProperty(globalThis, 'localStorage', originalLocalStorage)
      else Reflect.deleteProperty(globalThis, 'localStorage')
      if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
      else Reflect.deleteProperty(globalThis, 'window')
    }
  })
})
