import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const local = new Map<string, string>()
const getItem = mock((key: string) => local.get(key) ?? null)
const setItem = mock((key: string, value: string) => local.set(key, value))
const removeItem = mock((key: string) => local.delete(key))
const confirm = mock(() => true)
let intervalCallback: (() => void) | undefined
const setInterval = mock((callback: () => void) => { intervalCallback = callback; return 1 })
const clearInterval = mock(() => { intervalCallback = undefined })
const createObjectURL = mock(() => 'blob:evaluation')
const revokeObjectURL = mock()
const anchor = { href: '', download: '', click: mock() }
const createElement = mock(() => anchor)
Object.assign(globalThis, {
  localStorage: { getItem, setItem, removeItem },
  window: { confirm, setInterval, clearInterval, location: { href: 'http://localhost' } },
  document: { createElement },
})

mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))
mock.module('next/dynamic', () => ({ default: () => 'markdown-preview' }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
  formatDuration: (ms: number) => `${Math.round(ms)}ms`,
}))
const ui = { Badge: 'badge', Button: 'button', Card: 'card', CardContent: 'card-content', CardHeader: 'card-header', Checkbox: 'checkbox', Input: 'input', Label: 'label', Select: 'select', SelectContent: 'select-content', SelectItem: 'option', SelectTrigger: 'select-trigger', SelectValue: 'select-value', Switch: 'switch', Textarea: 'textarea' }
for (const path of ['@/components/ui/badge', '@/components/ui/button', '@/components/ui/card', '@/components/ui/checkbox', '@/components/ui/input', '@/components/ui/label', '@/components/ui/select', '@/components/ui/switch', '@/components/ui/textarea']) mock.module(path, () => ui)
mock.module('@/components/ui/popover', () => ({ Popover: 'popover', PopoverContent: 'popover-content', PopoverTrigger: 'button' }))
const Icon = () => null
mock.module('lucide-react', () => ({ ArrowLeft: Icon, ChevronDown: Icon, ChevronUp: Icon, FileText: Icon, HelpCircle: Icon, Loader2: Icon, Search: Icon, Send: Icon, Settings2: Icon }))
const toastError = mock()
mock.module('sonner', () => ({ toast: { error: toastError } }))

interface Slot { value?: unknown; deps?: readonly unknown[]; cleanup?: () => void }
const slots: Slot[] = []
let cursor = 0
let effects: Array<() => void> = []
let RetrievalLab: typeof import('./retrieval-lab').RetrievalLab
let BatchEvaluation: typeof import('./retrieval-lab').BatchEvaluation
let ApiError: typeof import('@/lib/api/client').ApiError

function sameDeps(a?: readonly unknown[], b?: readonly unknown[]) {
  return !!a && !!b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]))
}

beforeAll(async () => {
  const React = await import('react')
  mock.module('react', () => ({
    ...React,
    useState(initial: unknown) {
      const index = cursor++
      slots[index] ??= { value: typeof initial === 'function' ? (initial as () => unknown)() : initial }
      return [slots[index].value, (next: unknown) => { slots[index].value = typeof next === 'function' ? (next as (value: unknown) => unknown)(slots[index].value) : next }]
    },
    useEffect(effect: () => void | (() => void), deps?: readonly unknown[]) {
      const index = cursor++
      if (!sameDeps(slots[index]?.deps, deps)) {
        slots[index]?.cleanup?.()
        slots[index] = { deps }
        effects.push(() => { const cleanup = effect(); if (cleanup) slots[index].cleanup = cleanup })
      }
    },
    useCallback(callback: unknown, deps?: readonly unknown[]) {
      const index = cursor++
      if (!sameDeps(slots[index]?.deps, deps)) slots[index] = { value: callback, deps }
      return slots[index].value
    },
  }))
  ;({ ApiError } = await import('@/lib/api/client'))
  ;({ RetrievalLab, BatchEvaluation } = await import('./retrieval-lab'))
})

const getKnowledgeBase = mock()
const search = mock()
const updateKnowledgeBase = mock()
const listEvaluationDatasets = mock()
const createEvaluationDataset = mock()
const updateEvaluationDataset = mock()
const importEvaluationDataset = mock()
const createEvaluationCase = mock()
const updateEvaluationCase = mock()
const deleteEvaluationCase = mock()
const exportEvaluationDataset = mock()
const startEvaluationRun = mock()
const listEvaluationRuns = mock()
const getEvaluationRun = mock()
const cancelEvaluationRun = mock()
const api = { getKnowledgeBase, search, updateKnowledgeBase, listEvaluationDatasets, createEvaluationDataset, updateEvaluationDataset, importEvaluationDataset, createEvaluationCase, updateEvaluationCase, deleteEvaluationCase, exportEvaluationDataset, startEvaluationRun, listEvaluationRuns, getEvaluationRun, cancelEvaluationRun }
const kb = { id: 'kb-1', name: 'Handbook', settings: { rerank_candidate_k: 12 }, rerank_model: { name: 'Reranker' } }
const response = (id = 'chunk-1', diagnostics: object[] = []) => ({
  query: 'policy', total: 1, diagnostics, timings: [{ stage: 'recall', latency_ms: 12 }, { stage: 'total', latency_ms: 20 }],
  results: [{ chunk_id: id, document_id: 'doc-1', document_name: 'Guide', content: 'Policy keyword', score: 0.4, metadata: null, search_type: 'hybrid', dense_score: 0.81, dense_rank: 2, lexical_score: 7.4, lexical_rank: 1, fusion_score: 0.03, fusion_rank: 1, rerank_score: 0.4, rerank_rank: 1, final_score_stage: 'rerank', degradation_reasons: diagnostics.length ? [{ channel: 'dense', error: 'fallback' }] : [] }],
})

beforeEach(() => {
  slots.splice(0); effects = []; local.clear()
  intervalCallback = undefined
  for (const fn of [getKnowledgeBase, search, updateKnowledgeBase, listEvaluationDatasets, createEvaluationDataset, updateEvaluationDataset, importEvaluationDataset, createEvaluationCase, updateEvaluationCase, deleteEvaluationCase, exportEvaluationDataset, startEvaluationRun, listEvaluationRuns, getEvaluationRun, cancelEvaluationRun, getItem, setItem, removeItem, confirm, setInterval, clearInterval, toastError, createObjectURL, revokeObjectURL, createElement, anchor.click]) fn.mockClear()
  Object.assign(URL, { createObjectURL, revokeObjectURL })
  anchor.href = ''; anchor.download = ''
  getKnowledgeBase.mockResolvedValue(kb)
  listEvaluationDatasets.mockResolvedValue([])
  listEvaluationRuns.mockResolvedValue([])
  confirm.mockReturnValue(true)
})
afterEach(() => slots.forEach(slot => slot.cleanup?.()))

function render(props: Partial<Parameters<typeof RetrievalLab>[0]> = {}) {
  cursor = 0
  return RetrievalLab({ knowledgeBaseId: 'kb-1', api, backHref: '/back', canUpdate: true, ...props })
}
function renderBatch() {
  cursor = 0
  return BatchEvaluation({ knowledgeBaseId: 'kb-1', api, config: { search_mode: 'hybrid', top_k: 5, threshold: 0, dense_weight: 1, lexical_weight: 1, rrf_k: 60, rerank_enabled: true, rerank_candidate_k: 10, rerank_score_threshold: null }, hasRerankModel: true })
}
async function flushBatch(tree = renderBatch()) {
  while (effects.length) {
    effects.splice(0).forEach(effect => effect())
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    tree = renderBatch()
  }
  return tree
}
async function flush(tree = render()) {
  while (effects.length) {
    effects.splice(0).forEach(effect => effect())
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    tree = render()
  }
  return tree
}
function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const element = node as ReactElement<Record<string, unknown> & { children?: ReactNode }>
  return [element, ...elements(element.props.children)]
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join(' ')
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return text((node as ReactElement<{ children?: ReactNode }>).props.children)
}
function find(tree: ReactNode, type: string, predicate: (props: Record<string, unknown>) => boolean = () => true) {
  const found = elements(tree).find(element => element.type === type && predicate(element.props))
  if (!found) throw new Error(`Expected ${type}`)
  return found
}
function query(tree: ReactNode) { return find(tree, 'input', props => props.placeholder === 'searchPlaceholder') }
function searchButton(tree: ReactNode) { return find(tree, 'button', props => props['aria-label'] === 'search') }

async function enterQuery(tree: ReactNode, value = 'policy') {
  query(tree).props.onChange({ target: { value } })
  return render()
}
async function settle() {
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
  return render()
}
function expand(tree: ReactNode, props: Partial<Parameters<typeof RetrievalLab>[0]> = {}) {
  find(tree, 'card-header', header => typeof header.onClick === 'function').props.onClick()
  return render(props)
}
function button(tree: ReactNode, label: string) {
  const found = elements(tree).find(element => element.type === 'button' && text(element) === label)
  if (!found) throw new Error(`Expected button ${label}`)
  return found
}

describe('RetrievalLab', () => {
  test('loads settings, discards malformed local state, and reports load failure', async () => {
    local.set('retrieval-lab:kb-1', '{bad')
    const tree = await flush()
    expect(text(tree)).toContain('Handbook')
    expect(removeItem).toHaveBeenCalledWith('retrieval-lab:kb-1')
    expect(find(tree, 'switch', props => props.disabled === undefined)).toBeTruthy()

    slots.splice(0); effects = []
    const onLoadError = mock()
    getKnowledgeBase.mockRejectedValueOnce(new Error('missing'))
    render({ onLoadError })
    effects.splice(0).forEach(effect => effect())
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    expect(onLoadError).toHaveBeenCalled()
  })

  test('renders empty, degraded reranked results, raw ranks, and no-reranker controls', async () => {
    search.mockResolvedValueOnce({ query: 'policy', total: 0, diagnostics: [], results: [] })
      .mockResolvedValueOnce(response('degraded', [{ kb_id: 'kb-1', code: 'timeout', detail: 'dense timeout' }]))
    let tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(text(tree)).toContain('noResults')
    await searchButton(tree).props.onClick()
    tree = await settle()
    tree = expand(tree)
    expect(text(tree)).toContain('denseStage')
    expect(text(tree)).toContain('0.81')
    expect(text(tree)).toContain('dense: fallback')
    expect(text(tree)).toContain('timeout')
    expect(text(tree)).toContain('recall 12ms')
    expect(text(tree)).toContain('total 20ms')
    expect(text(tree)).not.toContain('%')
    expect(find(tree, 'switch', props => props.id === 'rerankA')).toBeTruthy()

    slots.splice(0); effects = []
    getKnowledgeBase.mockResolvedValueOnce({ ...kb, rerank_model: null })
    tree = await flush()
    expect(elements(tree).find(element => element.type === 'switch' && String(element.props.id).startsWith('rerank'))).toBeUndefined()
    expect(find(tree, 'switch', props => props.id === 'compare-toggle')).toBeTruthy()
  })

  test('preserves successful A/B side, attributes failures, overlap, and rank movement', async () => {
    search.mockResolvedValueOnce(response('shared')).mockRejectedValueOnce(new ApiError(4006, 'credential detail', { retrieval_error_category: 'provider_authentication' }))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = await enterQuery(render())
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(search).toHaveBeenCalledTimes(2)
    expect(search.mock.calls[0][1]).toMatchObject({
      dense_weight: 1,
      lexical_weight: 1,
      rrf_k: 60,
    })
    expect(text(tree)).toContain('Guide')
    expect(text(tree)).toContain('noResults')
    // Current behavior: the stage-less key is not camelized, so the snake_case category leaks into the key.
    expect(toastError).toHaveBeenCalledWith('B: retrievalErrorProviderAuthentication')
    expect(toastError.mock.calls.flat().join(' ')).not.toContain('credential detail')

    search.mockReset().mockResolvedValueOnce(response('shared')).mockResolvedValueOnce(response('shared'))
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(text(tree)).toContain('overlap:1,1')
    expect(text(tree)).toContain('→')
  })

  test('shows connectivity guidance only for request failures and ignores IME composition Enter', async () => {
    search.mockRejectedValue(new ApiError(-1, 'network detail'))
    let tree = await flush()
    tree = await enterQuery(tree)
    const preventDefault = mock()
    query(tree).props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: true }, preventDefault })
    expect(search).not.toHaveBeenCalled()
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(toastError).toHaveBeenCalledWith('retrievalErrorRequest')
    expect(toastError.mock.calls.flat().join(' ')).not.toContain('network detail')
    expect(text(tree)).toContain('noResults')
  })

  test('renders independent safe A/B guidance and clears failures on retry', async () => {
    search
      .mockRejectedValueOnce(new ApiError(4005, 'quota secret', { retrieval_error_category: 'quota_or_rate_limit' }))
      .mockRejectedValueOnce(new ApiError(5000, 'OpenSearch URL', { retrieval_error_category: 'lexical_unavailable' }))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = await enterQuery(render())
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(toastError).toHaveBeenCalledWith('A: retrievalErrorQuotaOrRateLimit')
    expect(toastError).toHaveBeenCalledWith('B: retrievalErrorLexicalUnavailable')
    const details = toastError.mock.calls.flat().join(' ')
    expect(details).not.toContain('quota secret')
    expect(details).not.toContain('OpenSearch URL')

    toastError.mockClear()
    search.mockReset().mockResolvedValueOnce(response('a')).mockResolvedValueOnce(response('b'))
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(toastError).not.toHaveBeenCalled()
    expect(text(tree)).not.toContain('noResults')
    expect(text(tree)).toContain('Guide')
  })

  test('maps controlled categories and hides malformed failure details', async () => {
    const categories = [
      'configuration_mismatch',
      'model_configuration',
      'provider_unavailable',
    ]
    const keys = [
      'retrievalErrorConfigurationMismatch',
      'retrievalErrorModelConfiguration',
      'retrievalErrorProviderUnavailable',
    ]
    for (let index = 0; index < categories.length; index += 1) {
      search.mockRejectedValueOnce(new ApiError(5000, 'raw provider body', { retrieval_error_category: categories[index] }))
      toastError.mockClear()
      let tree = await flush()
      tree = await enterQuery(tree)
      await searchButton(tree).props.onClick()
      await settle()
      expect(toastError).toHaveBeenCalledWith(keys[index])
      expect(toastError.mock.calls.flat().join(' ')).not.toContain('raw provider body')
      slots.splice(0); effects = []
    }

    search.mockRejectedValueOnce(new ApiError(5000, 'internal URL', { retrieval_error_category: 'unsafe_detail' }))
    toastError.mockClear()
    let tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    await settle()
    expect(toastError).toHaveBeenCalledWith('retrievalErrorUnknown')
    expect(toastError.mock.calls.flat().join(' ')).not.toContain('internal URL')
  })

  test('persists grades and presets, confirms updates, enforces permission, and exposes update failure', async () => {
    search.mockResolvedValue(response())
    let tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    tree = await settle()
    tree = expand(tree)
    button(tree, 'relevant').props.onClick()
    expect(JSON.parse(local.get('retrieval-lab:kb-1')!).grades['chunk-1']).toBe('relevant')

    find(tree, 'input', props => props['aria-label'] === 'presetName').props.onChange({ target: { value: 'Fast' } })
    tree = render()
    button(tree, 'savePreset').props.onClick()
    tree = render()
    find(tree, 'select', props => props['aria-label'] === 'presets').props.onValueChange('Fast')
    tree = render()
    updateKnowledgeBase.mockRejectedValueOnce(new Error('denied'))
    await button(tree, 'applyToProduction').props.onClick()
    tree = render()
    expect(confirm).toHaveBeenCalled()
    expect(updateKnowledgeBase).toHaveBeenCalledWith('kb-1', {
      settings: expect.objectContaining({
        search_mode: 'hybrid', top_k: 5, score_threshold: 0,
        dense_weight: 1, lexical_weight: 1, rrf_k: 60,
        rerank_enabled: true, rerank_candidate_k: 12,
        rerank_score_threshold: null,
      }),
    })
    expect(text(tree)).toContain('presetUpdateError')

    const calls = updateKnowledgeBase.mock.calls.length
    tree = render({ canUpdate: false })
    await button(tree, 'applyToProduction').props.onClick()
    expect(updateKnowledgeBase).toHaveBeenCalledTimes(calls)
  })

  test('exposes an accessible batch evaluation tab without changing interactive defaults', async () => {
    const tree = await flush()
    expect(find(tree, 'button', props => props.role === 'tab' && props['aria-selected'] === true)).toBeTruthy()
    expect(text(tree)).toContain('batchEvaluation')
    expect(listEvaluationDatasets).not.toHaveBeenCalled()
  })

  test('creates and imports a dataset through the injected API', async () => {
    const dataset = { id: 'dataset-1', knowledge_base_id: 'kb-1', name: 'Regression', description: 'Nightly', created_by_id: null, created_at: '2026-01-01', updated_at: '2026-01-01', cases: [] }
    createEvaluationDataset.mockResolvedValue(dataset)
    importEvaluationDataset.mockResolvedValue(dataset)
    let tree = await flushBatch()
    const inputs = elements(tree).filter(element => element.type === 'input')
    inputs[0].props.onChange({ target: { value: ' Regression ' } })
    inputs[1].props.onChange({ target: { value: ' Nightly ' } })
    tree = renderBatch()
    await button(tree, 'createDataset').props.onClick()
    expect(createEvaluationDataset).toHaveBeenCalledWith('kb-1', { name: 'Regression', description: 'Nightly' })
    tree = await flushBatch(renderBatch())
    const file = new File(['query\npolicy'], 'cases.csv', { type: 'text/csv' })
    await find(tree, 'input', props => props.type === 'file').props.onChange({ target: { files: [file] } })
    expect(importEvaluationDataset).toHaveBeenCalledWith('kb-1', 'dataset-1', file)
  })

  test('validates cases and incrementally creates or updates while preserving ids', async () => {
    const persisted = { id: 'case-1', query: 'policy', chunk_relevance: { 'chunk-1': 3 }, document_relevance: {}, expected_empty: false }
    const dataset = { id: 'dataset-1', knowledge_base_id: 'kb-1', name: 'Regression', description: null, created_by_id: null, created_at: '2026-01-01', updated_at: '2026-01-01', cases: [persisted] }
    listEvaluationDatasets.mockResolvedValue([dataset])
    updateEvaluationCase.mockResolvedValue({ ...persisted, query: 'updated policy' })
    createEvaluationCase.mockResolvedValue({ id: 'case-2', query: 'new case', chunk_relevance: {}, document_relevance: {}, expected_empty: false })
    let tree = await flushBatch()
    await button(tree, 'saveCases').props.onClick()
    expect(updateEvaluationCase).toHaveBeenCalledWith('kb-1', 'dataset-1', 'case-1', expect.objectContaining({ query: 'policy' }))
    button(renderBatch(), 'addCase').props.onClick()
    tree = renderBatch()
    const blankQuery = elements(tree).filter(element => element.type === 'input').at(-1)
    blankQuery!.props.onChange({ target: { value: 'new case' } })
    tree = renderBatch()
    await button(tree, 'saveCases').props.onClick()
    expect(createEvaluationCase).toHaveBeenCalledWith('kb-1', 'dataset-1', expect.objectContaining({ query: 'new case' }))
    expect(updateEvaluationDataset).not.toHaveBeenCalled()

    const areas = elements(renderBatch()).filter(element => element.type === 'textarea')
    areas[0].props.onChange({ target: { value: '{bad' } })
    await button(renderBatch(), 'saveCases').props.onClick()
    expect(text(renderBatch())).toContain('batchCaseError')
  })

  test('deletes persisted cases remotely, removes drafts locally, and preserves failed removals', async () => {
    const persisted = { id: 'case-1', query: 'policy', chunk_relevance: {}, document_relevance: {}, expected_empty: false }
    const dataset = { id: 'dataset-1', knowledge_base_id: 'kb-1', name: 'Regression', description: null, created_by_id: null, created_at: '2026-01-01', updated_at: '2026-01-01', cases: [persisted] }
    listEvaluationDatasets.mockResolvedValue([dataset])
    let tree = await flushBatch()
    button(tree, 'addCase').props.onClick()
    tree = renderBatch()
    const removeButtons = elements(tree).filter(element => element.type === 'button' && text(element) === 'removeCase')
    await removeButtons[1].props.onClick()
    expect(deleteEvaluationCase).not.toHaveBeenCalled()
    expect(elements(renderBatch()).filter(element => element.type === 'button' && text(element) === 'removeCase')).toHaveLength(1)

    deleteEvaluationCase.mockRejectedValueOnce(new Error('active run'))
    await button(renderBatch(), 'removeCase').props.onClick()
    expect(deleteEvaluationCase).toHaveBeenCalledWith('kb-1', 'dataset-1', 'case-1')
    expect(elements(renderBatch()).filter(element => element.type === 'input').some(element => element.props.value === 'policy')).toBe(true)
    expect(text(renderBatch())).toContain('batchCaseError')

    deleteEvaluationCase.mockResolvedValueOnce(undefined)
    await button(renderBatch(), 'removeCase').props.onClick()
    expect(elements(renderBatch()).filter(element => element.type === 'input').some(element => element.props.value === 'policy')).toBe(false)
  })

  test('exports JSON and CSV with returned content and offers an id-free empty starter', async () => {
    const dataset = { id: 'dataset-1', knowledge_base_id: 'kb-1', name: ' Regression / Set ', description: null, created_by_id: null, created_at: '2026-01-01', updated_at: '2026-01-01', cases: [] }
    listEvaluationDatasets.mockResolvedValue([dataset])
    exportEvaluationDataset
      .mockResolvedValueOnce({ format: 'json', content: '[{"query":"policy"}]' })
      .mockResolvedValueOnce({ format: 'csv', content: 'query\npolicy' })
    let tree = await flushBatch()
    const starter = button(tree, 'downloadStarter')
    starter.props.onClick()
    const starterBlob = createObjectURL.mock.calls[0][0] as Blob
    const starterContent = await starterBlob.text()
    expect(starterBlob.type).toBe('application/json;charset=utf-8')
    expect(starterContent).toContain('"chunk_relevance": {}')
    expect(starterContent).not.toContain('chunk-id')
    expect(starterContent).not.toContain('doc-id')
    expect(anchor.download).toBe('evaluation-starter.json')

    const exportButtons = elements(tree).filter(element => element.type === 'button' && element.props.onClick && text(element).includes('exportFormat'))
    expect(exportButtons.length).toBeGreaterThanOrEqual(2)
    await exportButtons[0].props.onClick()
    expect(exportEvaluationDataset).toHaveBeenCalledWith('kb-1', 'dataset-1', 'json')
    expect((createObjectURL.mock.calls.at(-1)?.[0] as Blob).type).toBe('application/json;charset=utf-8')
    expect(anchor.download).toBe('Regression-Set.json')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:evaluation')

    tree = renderBatch()
    const csvButton = elements(tree).find(element => element.type === 'button' && element.props.onClick && text(element).includes('exportFormat:CSV'))
    await csvButton!.props.onClick()
    expect(exportEvaluationDataset).toHaveBeenCalledWith('kb-1', 'dataset-1', 'csv')
    expect((createObjectURL.mock.calls.at(-1)?.[0] as Blob).type).toBe('text/csv;charset=utf-8')
    expect(anchor.download).toBe('Regression-Set.csv')
    expect(text(tree)).toContain('importReplacementWarning')
  })

  test('lists, starts, polls, cancels, renders nested metrics, maps case ids, and filters failures', async () => {
    const cases = [
      { id: 'case-a', query: 'edited first query', chunk_relevance: {}, document_relevance: {}, expected_empty: false },
      { id: 'case-b', query: 'edited failed query', chunk_relevance: {}, document_relevance: {}, expected_empty: false },
    ]
    const dataset = { id: 'dataset-1', knowledge_base_id: 'kb-1', name: 'Regression', description: null, created_by_id: null, created_at: '2026-01-01', updated_at: '2026-01-01', cases }
    const running = { id: 'run-1', dataset_id: 'dataset-1', created_by_id: null, status: 'running', config_snapshot: {}, version_snapshot: {}, summary_metrics: { precision: { mean: 0.75, count: 2 } }, error_message: null, created_at: '2026-01-01', started_at: null, finished_at: null, case_results: [
      { id: 'result-b', case_id: 'case-b', case_snapshot: { query: 'historical failed query', chunk_relevance: {}, document_relevance: {}, expected_empty: false }, candidates: [], metrics: { recall: { at_5: 0 } }, latency_ms: 20, error_message: 'timeout' },
      { id: 'result-a', case_id: 'case-a', case_snapshot: { query: 'historical first query', chunk_relevance: {}, document_relevance: {}, expected_empty: false }, candidates: [], metrics: { recall: 1 }, latency_ms: 10, error_message: null },
    ] }
    listEvaluationDatasets.mockResolvedValue([dataset])
    listEvaluationRuns.mockResolvedValue([running])
    startEvaluationRun.mockResolvedValue(running)
    getEvaluationRun.mockResolvedValue({ ...running, status: 'completed' })
    cancelEvaluationRun.mockResolvedValue({ ...running, status: 'canceled' })
    let tree = await flushBatch()
    expect(listEvaluationRuns).toHaveBeenCalledWith('kb-1', 'dataset-1')
    await button(tree, 'startRun').props.onClick()
    expect(startEvaluationRun.mock.calls[0][2]).toMatchObject({ search_mode: 'hybrid', top_k: 5, score_threshold: 0, rerank_candidate_k: 10 })
    tree = await flushBatch(renderBatch())
    expect(setInterval).toHaveBeenCalled()
    await intervalCallback?.()
    expect(getEvaluationRun).toHaveBeenCalledWith('kb-1', 'dataset-1', 'run-1')
    expect(text(tree)).toContain('{"mean":0.75,"count":2}')
    expect(text(tree)).toContain('recall: {"at_5":0}')
    expect(text(tree)).toContain('historical failed query')
    expect(text(tree)).not.toContain('edited failed query')
    expect(text(tree)).toContain('historical first query')
    await button(tree, 'cancelRun').props.onClick()
    expect(cancelEvaluationRun).toHaveBeenCalledWith('kb-1', 'dataset-1', 'run-1')
    elements(tree).filter(element => element.type === 'checkbox').at(-1)!.props.onCheckedChange(true)
    tree = renderBatch()
    expect(text(tree)).toContain('historical failed query')
    expect(text(tree)).not.toContain('historical first query')
  })

  test('reports dataset load, create, import, run, polling, and cancel failures', async () => {
    listEvaluationDatasets.mockRejectedValueOnce(new Error('offline'))
    expect(text(await flushBatch())).toContain('batchLoadError')

    slots.splice(0); effects = []
    createEvaluationDataset.mockRejectedValueOnce(new Error('create'))
    const tree = await flushBatch()
    find(tree, 'input', props => props.value === '').props.onChange({ target: { value: 'Broken' } })
    await button(renderBatch(), 'createDataset').props.onClick()
    expect(text(renderBatch())).toContain('batchSaveError')
  })

  test('authenticated markdown image uses bearer token and rejects unsafe sources', async () => {
    search.mockResolvedValue(response())
    local.set('access_token', 'token-1')
    const fetch = mock(() => Promise.resolve(new Response(new Blob(['image']))))
    Object.assign(globalThis, { fetch, URL: { createObjectURL: () => 'blob:image', revokeObjectURL: mock() } })
    let tree = await flush(render({ authenticatedMarkdown: true }))
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    tree = await settle()
    tree = expand(tree, { authenticatedMarkdown: true })
    const markdown = find(tree, 'markdown-preview')
    const Image = (markdown.props.components as { img: (props: { src?: string; alt?: string }) => ReactElement }).img
    const imageElement = Image({ src: '/api/v1/knowledge-bases/kb-1/image', alt: 'diagram' })

    slots.splice(0); effects = []; cursor = 0
    local.set('access_token', 'token-1')
    ;(imageElement.type as (props: { src?: string; alt?: string }) => ReactNode)(imageElement.props)
    effects.splice(0).forEach(effect => effect())
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    expect(fetch).toHaveBeenCalledWith('/api/v1/knowledge-bases/kb-1/image', expect.objectContaining({ headers: { Authorization: 'Bearer token-1' } }))

    slots.splice(0); effects = []; cursor = 0
    const unsafe = Image({ src: 'javascript:alert(1)', alt: 'unsafe' })
    expect(text((unsafe.type as (props: { src?: string; alt?: string }) => ReactNode)(unsafe.props))).toContain('unsafe')
  })
})
