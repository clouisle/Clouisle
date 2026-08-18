import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const local = new Map<string, string>()
const getItem = mock((key: string) => local.get(key) ?? null)
const setItem = mock((key: string, value: string) => local.set(key, value))
const removeItem = mock((key: string) => local.delete(key))
Object.assign(globalThis, {
  localStorage: { getItem, setItem, removeItem },
  window: { location: { href: 'http://localhost' } },
})

const translate = Object.assign(
  (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key,
  { has: (key: string) => !key.startsWith('retrievalError_recall_') }
)
mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))
mock.module('next/dynamic', () => ({ default: () => 'markdown-preview' }))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
  formatDuration: (ms: number) => `${Math.round(ms)}ms`,
}))
const ui = { Badge: 'badge', Button: 'button', Card: 'card', Input: 'input', Label: 'label', Select: 'select', SelectContent: 'select-content', SelectItem: 'option', SelectTrigger: 'select-trigger', SelectValue: 'select-value', Switch: 'switch' }
for (const path of ['@/components/ui/badge', '@/components/ui/button', '@/components/ui/card', '@/components/ui/input', '@/components/ui/label', '@/components/ui/select', '@/components/ui/switch']) mock.module(path, () => ui)
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: 'alert-dialog', AlertDialogAction: 'alert-dialog-action', AlertDialogCancel: 'alert-dialog-cancel',
  AlertDialogContent: 'alert-dialog-content', AlertDialogDescription: 'alert-dialog-description',
  AlertDialogFooter: 'alert-dialog-footer', AlertDialogHeader: 'alert-dialog-header', AlertDialogTitle: 'alert-dialog-title',
}))
mock.module('@/components/ui/resizable', () => ({ ResizableHandle: 'resizable-handle', ResizablePanel: 'resizable-panel', ResizablePanelGroup: 'resizable-panel-group' }))
mock.module('@/components/ui/sheet', () => ({ Sheet: 'sheet', SheetContent: 'sheet-content', SheetDescription: 'sheet-description', SheetHeader: 'sheet-header', SheetTitle: 'sheet-title' }))
let mobile = false
mock.module('@/hooks/use-mobile', () => ({ useIsMobile: () => mobile }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: 'collapsible', CollapsibleContent: 'collapsible-content', CollapsibleTrigger: 'button' }))
mock.module('@/components/ui/popover', () => ({ Popover: 'popover', PopoverContent: 'popover-content', PopoverTrigger: 'button' }))
mock.module('@/components/ui/table', () => ({ Table: 'table', TableBody: 'tbody', TableCell: 'td', TableHead: 'th', TableHeader: 'thead', TableRow: 'tr' }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: 'tooltip', TooltipContent: 'tooltip-content', TooltipTrigger: 'button' }))
const Icon = () => null
mock.module('lucide-react', () => ({ ArrowLeft: Icon, ChevronDown: Icon, ChevronUp: Icon, FileText: Icon, HelpCircle: Icon, Loader2: Icon, Search: Icon, Send: Icon, Settings2: Icon, X: Icon }))
const toastError = mock()
mock.module('sonner', () => ({ toast: { error: toastError } }))

interface Slot { value?: unknown; deps?: readonly unknown[]; cleanup?: () => void }
const slots: Slot[] = []
let cursor = 0
let effects: Array<() => void> = []
let RetrievalLab: typeof import('./retrieval-lab').RetrievalLab
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
    useRef(initial: unknown) {
      const index = cursor++
      slots[index] ??= { value: { current: initial } }
      return slots[index].value
    },
  }))
  ;({ ApiError } = await import('@/lib/api/client'))
  ;({ RetrievalLab } = await import('./retrieval-lab'))
})

const getKnowledgeBase = mock()
const search = mock()
const searchBatch = mock()
const updateKnowledgeBase = mock()
const api = { getKnowledgeBase, search, searchBatch, updateKnowledgeBase }
const kb = { id: 'kb-1', name: 'Handbook', settings: { chunk_size: 400, rerank_candidate_k: 12 }, rerank_model: { name: 'Reranker' } }
const response = (id = 'chunk-1', diagnostics: object[] = []) => ({
  query: 'policy', total: 1, diagnostics, timings: [{ stage: 'recall', latency_ms: 12 }, { stage: 'total', latency_ms: 20 }],
  results: [{ chunk_id: id, document_id: 'doc-1', document_name: 'Guide', content: 'Policy keyword', score: 0.4, metadata: null, search_type: 'hybrid', dense_score: 0.81, dense_rank: 2, lexical_score: 7.4, lexical_rank: 1, fusion_score: 0.03, fusion_rank: 1, rerank_score: 0.4, rerank_rank: 1, final_score_stage: 'rerank', degradation_reasons: diagnostics.length ? [{ channel: 'dense', error: 'fallback' }] : [] }],
})
const fulfilled = (id: string, value = response(id)) => ({ id, status: 'fulfilled', response: value })
const rejected = (id: string, retrieval_error_category: string, code = 5000) => ({ id, status: 'rejected', error: { code, retrieval_error_category } })
const batch = (...outcomes: object[]) => ({ query: 'policy', outcomes })

beforeEach(() => {
  slots.splice(0); effects = []; local.clear(); mobile = false
  for (const fn of [getKnowledgeBase, search, searchBatch, updateKnowledgeBase, getItem, setItem, removeItem, toastError]) fn.mockClear()
  getKnowledgeBase.mockResolvedValue(kb)
})
afterEach(() => slots.forEach(slot => slot.cleanup?.()))

function render(props: Partial<Parameters<typeof RetrievalLab>[0]> = {}) {
  cursor = 0
  return RetrievalLab({ knowledgeBaseId: 'kb-1', api, backHref: '/back', canTest: true, canUpdate: true, ...props })
}
async function flush(tree = render()) {
  while (effects.length) {
    effects.splice(0).forEach(effect => effect())
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
    tree = render()
  }
  return tree
}
function renderDetail(node: ReactElement<Record<string, unknown>>) {
  return typeof node.type === 'function' && ['ResultDetail', 'Highlight'].includes(node.type.name)
    ? (node.type as (props: Record<string, unknown>) => ReactNode)(node.props)
    : node.props.children as ReactNode
}
function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const element = node as ReactElement<Record<string, unknown> & { children?: ReactNode }>
  return [element, ...elements(renderDetail(element))]
}
function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join(' ')
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return text(renderDetail(node as ReactElement<Record<string, unknown>>))
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
function button(tree: ReactNode, label: string) {
  const found = elements(tree).find(element => element.type === 'button' && text(element) === label)
  if (!found) throw new Error(`Expected button ${label}`)
  return found
}

describe('RetrievalLab', () => {
  test('loads settings, discards malformed local state, and reports load failure', async () => {
    local.set('retrieval-lab:kb-1', '{bad')
    const loadingTree = render()
    expect(find(loadingTree, 'div', props => props['data-testid'] === 'kb-search-lab')).toBeTruthy()
    const tree = await flush(loadingTree)
    expect(find(tree, 'div', props => props['data-testid'] === 'kb-search-lab')).toBeTruthy()
    expect(find(tree, 'input', props => props['data-testid'] === 'kb-search-query')).toBeTruthy()
    expect(find(tree, 'button', props => props['data-testid'] === 'kb-search-submit')).toBeTruthy()
    expect(elements(tree).find(element => element.props['data-testid'] === 'kb-search-results')).toBeUndefined()
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
    expect(find(tree, 'div', props => props['data-testid'] === 'kb-search-results')).toBeTruthy()
    await searchButton(tree).props.onClick()
    tree = await settle()
    find(tree, 'button', props => String(props['aria-label']).startsWith('selectResult')).props.onClick()
    tree = render()
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
    searchBatch.mockResolvedValueOnce(batch(fulfilled('a', response('shared')), rejected('b', 'provider_authentication', 4006)))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = await enterQuery(render())
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(search).not.toHaveBeenCalled()
    expect(searchBatch).toHaveBeenCalledTimes(1)
    expect(searchBatch.mock.calls[0][2]).toEqual([
      expect.objectContaining({ id: 'a', dense_weight: 1, lexical_weight: 1, rrf_k: 60 }),
      expect.objectContaining({ id: 'b' }),
    ])
    expect(text(tree)).toContain('Guide')
    expect(text(tree)).toContain('noResults')
    // Current behavior: the stage-less key is not camelized, so the snake_case category leaks into the key.
    expect(toastError).toHaveBeenCalledWith('B: retrievalErrorProviderAuthentication')
    expect(toastError.mock.calls.flat().join(' ')).not.toContain('credential detail')

    searchBatch.mockResolvedValueOnce(batch(fulfilled('a', response('shared')), fulfilled('b', response('shared'))))
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(text(tree)).toContain('overlap:1,1')
    expect(find(tree, 'div', props => props['data-testid'] === 'kb-search-results')).toBeTruthy()
    const resultHeader = elements(tree).find(element => element.type === 'span' && String(element.props.className).includes('items-center gap-2 text-xs'))!
    const headerItems = resultHeader.props.children as ReactElement<Record<string, unknown>>[]
    expect(headerItems[3].type).toBe('badge')
    expect(text(headerItems[3])).toContain('→')
    expect(headerItems[3].props.className).toContain('bg-muted')
    expect(headerItems[4].type).toBe('badge')
  })

  test('selects one side-aware desktop detail, hides chunk ids, closes, and falls back to B', async () => {
    const a = response('shared')
    a.results[0].content = 'Content from A'
    const b = response('shared')
    b.results[0].content = 'Content from B'
    searchBatch.mockResolvedValueOnce(batch(fulfilled('a', a), fulfilled('b', b)))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = await enterQuery(render())
    await searchButton(tree).props.onClick()
    tree = await settle()

    expect(find(tree, 'resizable-panel-group')).toBeTruthy()
    expect(elements(tree).filter(element => element.type === 'aside')).toHaveLength(0)
    expect(elements(tree).filter(element => element.type === 'resizable-handle')).toHaveLength(0)
    expect(text(tree)).not.toContain('shared')
    expect(elements(tree).filter(element => element.type === 'button' && String(element.props['aria-label']).startsWith('selectResult')).every(element => element.props['aria-pressed'] === false)).toBe(true)

    const resultButtons = elements(tree).filter(element => element.type === 'button' && String(element.props['aria-label']).startsWith('selectResult'))
    resultButtons[1].props.onClick()
    tree = render()
    const markdown = find(elements(tree).find(element => element.type === 'aside')!, 'markdown-preview')
    expect(markdown.props.source).toBe('Content from B')
    expect(markdown.props.source).not.toBe('Content from A')

    find(tree, 'button', props => props['aria-label'] === 'closeResultDetails').props.onClick()
    tree = render()
    expect(elements(tree).filter(element => element.type === 'aside')).toHaveLength(0)

    searchBatch.mockResolvedValueOnce(batch(rejected('a', 'provider_unavailable'), fulfilled('b', response('b-only'))))
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(elements(tree).filter(element => element.type === 'aside')).toHaveLength(0)
    expect(text(tree)).not.toContain('resultConfiguration:B')
    expect(text(tree)).not.toContain('b-only')
  })

  test('uses a controlled full-width Sheet on mobile and clears selection when it closes', async () => {
    mobile = true
    search.mockResolvedValueOnce(response('mobile-chunk'))
    let tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    tree = await settle()

    let sheet = find(tree, 'sheet')
    expect(sheet.props.open).toBe(false)
    find(tree, 'button', props => String(props['aria-label']).startsWith('selectResult')).props.onClick()
    tree = render()
    sheet = find(tree, 'sheet')
    expect(sheet.props.open).toBe(true)
    expect(find(tree, 'sheet-content').props.className).toContain('w-full')
    expect(text(tree)).toContain('resultDetails')
    sheet.props.onOpenChange(false)
    tree = render()
    expect(find(tree, 'sheet').props.open).toBe(false)
    expect(elements(tree).filter(element => element.type === 'aside')).toHaveLength(0)
    expect(text(tree)).not.toContain('mobile-chunk')
  })

  test('keeps configuration controls at the default height and displays the selected search mode', async () => {
    let tree = await flush()
    const settingsButton = find(tree, 'button', props => props['aria-label'] === 'settings')
    expect(settingsButton.props.className).toContain('h-9 w-9')
    expect(find(tree, 'popover-content').props.className).toContain('calc(100vw-1rem)')
    expect(find(tree, 'popover-content').props.className).toContain('calc(100dvh-1rem)')
    find(tree, 'button', props => text(props.children as ReactNode).includes('advancedSettings')).props.onClick()
    tree = render()
    expect(find(tree, 'input', props => props.id === 'rerankThresholdA').props.placeholder).toBe('rerankScoreThresholdPlaceholder')
    expect(find(tree, 'button', props => text(props.children as ReactNode).includes('advancedSettings')).props.size).toBeUndefined()
    expect(button(tree, 'savePreset').props.size).toBeUndefined()
    expect(button(tree, 'applyToProduction').props.size).toBeUndefined()
    const rerankSwitch = find(tree, 'switch', props => props.id === 'rerankA')
    const rerankControl = elements(tree).find(element => element.props.children === rerankSwitch)
    expect(rerankControl?.props.className).toContain('h-9')

    const searchMode = find(tree, 'select', props => props.value === 'hybrid')
    expect(text(searchMode)).toContain('hybridSearch')
    searchMode.props.onValueChange('vector')
    tree = render()
    expect(text(find(tree, 'select', props => props.value === 'vector'))).toContain('vectorSearch')
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
    searchBatch.mockResolvedValueOnce(batch(
      rejected('a', 'quota_or_rate_limit', 4005),
      rejected('b', 'lexical_unavailable')
    ))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = await enterQuery(render())
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(toastError).toHaveBeenCalledWith('A: retrievalErrorQuotaOrRateLimit')
    expect(toastError).toHaveBeenCalledWith('B: retrievalErrorLexicalUnavailable')
    const details = toastError.mock.calls.flat().join(' ')
    expect(details).not.toContain('quota secret')
    expect(details).not.toContain('PostgreSQL connection string')

    toastError.mockClear()
    searchBatch.mockResolvedValueOnce(batch(fulfilled('a'), fulfilled('b')))
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

  test('persists presets, confirms updates, enforces permission, and exposes update failure', async () => {
    let tree = await flush()
    find(tree, 'input', props => props['aria-label'] === 'presetName').props.onChange({ target: { value: 'Fast' } })
    tree = render()
    button(tree, 'savePreset').props.onClick()
    tree = render()
    expect(JSON.parse(local.get('retrieval-lab:kb-1')!).presets[0].name).toBe('Fast')
    find(tree, 'select', props => props['aria-label'] === 'presets').props.onValueChange('Fast')
    tree = render()
    updateKnowledgeBase.mockRejectedValueOnce(new Error('denied'))
    button(tree, 'applyToProduction').props.onClick()
    tree = render()
    expect(find(tree, 'alert-dialog').props.open).toBe(true)
    expect(text(find(tree, 'alert-dialog-description'))).toContain('applyPresetConfirm:Fast')
    expect(updateKnowledgeBase).not.toHaveBeenCalled()
    updateKnowledgeBase.mockResolvedValueOnce({ ...kb, settings: { ...kb.settings, top_k: 5 } })
    await find(tree, 'alert-dialog-action').props.onClick()
    tree = render()
    expect(updateKnowledgeBase).toHaveBeenCalledWith('kb-1', {
      settings: expect.objectContaining({
        chunk_size: 400,
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

  test('reports whole batch failures and falls back from missing stage keys', async () => {
    searchBatch.mockRejectedValueOnce(new ApiError(-1, 'network detail', { stage: 'recall' }))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = await enterQuery(render())
    await searchButton(tree).props.onClick()
    await settle()
    expect(toastError).toHaveBeenCalledWith('retrievalErrorRequest')

    search.mockRejectedValueOnce(new ApiError(5000, 'provider detail', {
      retrieval_error_category: 'provider_unavailable', stage: 'recall',
    }))
    slots.splice(0); effects = []
    tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    await settle()
    expect(toastError).toHaveBeenCalledWith('retrievalErrorProviderUnavailable')
  })

  test('disables testing without permission and clamps stored top-k', async () => {
    let tree = await flush()
    tree = render({ canTest: false })
    query(tree).props.onChange({ target: { value: 'policy' } })
    tree = render({ canTest: false })
    expect(searchButton(tree).props.disabled).toBe(true)
    await searchButton(tree).props.onClick()
    expect(search).not.toHaveBeenCalled()

    slots.splice(0); effects = []
    getKnowledgeBase.mockResolvedValueOnce({ ...kb, settings: { ...kb.settings, top_k: 100 } })
    search.mockResolvedValueOnce(response())
    tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    await settle()
    expect(search.mock.calls.at(-1)?.[1]).toMatchObject({ top_k: 20 })
  })

  test('blocks zero-weight hybrid paths per side but permits vector and fulltext', async () => {
    let tree = await flush()
    find(tree, 'button', props => text(props.children as ReactNode).includes('advancedSettings')).props.onClick()
    tree = render()
    find(tree, 'input', props => props.id === 'denseWeightA').props.onChange({ target: { value: '0' } })
    find(render(), 'input', props => props.id === 'lexicalWeightA').props.onChange({ target: { value: '0' } })
    tree = await enterQuery(render())

    expect(text(tree)).toContain('hybridWeightsRequired:A')
    expect(searchButton(tree).props.disabled).toBe(true)
    expect(button(tree, 'savePreset').props.disabled).toBe(true)
    const preventDefault = mock()
    query(tree).props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: false }, preventDefault })
    expect(search).not.toHaveBeenCalled()
    expect(preventDefault).toHaveBeenCalled()

    find(tree, 'select', props => props.value === 'hybrid').props.onValueChange('vector')
    tree = render()
    expect(text(tree)).not.toContain('hybridWeightsRequired:A')
    expect(searchButton(tree).props.disabled).toBe(false)
    search.mockResolvedValueOnce(response())
    await searchButton(tree).props.onClick()
    await settle()
    expect(search).toHaveBeenCalledTimes(1)

    find(render(), 'switch', props => props.id === 'compare-toggle').props.onCheckedChange(true)
    tree = render()
    find(tree, 'select', props => props.value === 'vector').props.onValueChange('fulltext')
    find(render(), 'select', props => props.value === 'vector').props.onValueChange('hybrid')
    tree = render()
    find(tree, 'input', props => props.id === 'denseWeightB').props.onChange({ target: { value: '0' } })
    find(render(), 'input', props => props.id === 'lexicalWeightB').props.onChange({ target: { value: '0' } })
    tree = render()
    expect(text(tree)).toContain('hybridWeightsRequired:B')
    expect(searchButton(tree).props.disabled).toBe(true)
  })

  test('merges legacy partial presets over current config', async () => {
    local.set('retrieval-lab:kb-1', JSON.stringify({ presets: [{ name: 'Legacy', config: { top_k: 9 } }] }))
    let tree = await flush()
    find(tree, 'button', props => text(props.children as ReactNode).includes('advancedSettings')).props.onClick()
    tree = render()
    find(tree, 'select', props => props['aria-label'] === 'presets').props.onValueChange('Legacy')
    tree = render()

    expect(find(tree, 'select', props => props.value === 'hybrid')).toBeTruthy()
    expect(find(tree, 'input', props => props.id === 'topKA').props.value).toBe(9)
    expect(find(tree, 'input', props => props.id === 'denseWeightA').props.value).toBe(1)
  })

  test('authenticated markdown image uses bearer token and rejects unsafe sources', async () => {
    search.mockResolvedValue(response())
    local.set('access_token', 'token-1')
    const fetch = mock(() => Promise.resolve(new Response(new Blob(['image']))))
    Object.assign(globalThis, { fetch, URL: { createObjectURL: () => 'blob:image', revokeObjectURL: mock() } })
    let tree = await flush(render({ authenticatedMarkdown: true }))
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    await settle()
    tree = render({ authenticatedMarkdown: true })
    find(tree, 'button', props => String(props['aria-label']).startsWith('selectResult')).props.onClick()
    tree = render({ authenticatedMarkdown: true })
    const markdown = find(tree, 'markdown-preview')
    expect(find(tree, 'div', props => String(props.className).includes('[&_a.anchor]:!ml-0'))).toBeTruthy()
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
