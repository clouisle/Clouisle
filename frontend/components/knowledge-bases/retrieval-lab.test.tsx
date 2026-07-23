import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const local = new Map<string, string>()
const getItem = mock((key: string) => local.get(key) ?? null)
const setItem = mock((key: string, value: string) => local.set(key, value))
const removeItem = mock((key: string) => local.delete(key))
const confirm = mock(() => true)
Object.assign(globalThis, { localStorage: { getItem, setItem, removeItem }, window: { confirm } })

mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))
mock.module('next/dynamic', () => ({ default: () => 'markdown-preview' }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
const ui = { Badge: 'badge', Button: 'button', Card: 'card', CardContent: 'card-content', CardHeader: 'card-header', Input: 'input', Label: 'label', Switch: 'switch' }
for (const path of ['@/components/ui/badge', '@/components/ui/button', '@/components/ui/card', '@/components/ui/input', '@/components/ui/label', '@/components/ui/switch']) mock.module(path, () => ui)
const Icon = () => null
mock.module('lucide-react', () => ({ ArrowLeft: Icon, ChevronDown: Icon, ChevronUp: Icon, FileText: Icon, Loader2: Icon, Search: Icon, Send: Icon, Settings2: Icon }))

interface Slot { value?: unknown; deps?: readonly unknown[]; cleanup?: () => void }
const slots: Slot[] = []
let cursor = 0
let effects: Array<() => void> = []
let RetrievalLab: typeof import('./retrieval-lab').RetrievalLab

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
  }))
  ;({ RetrievalLab } = await import('./retrieval-lab'))
})

const getKnowledgeBase = mock()
const search = mock()
const updateKnowledgeBase = mock()
const api = { getKnowledgeBase, search, updateKnowledgeBase }
const kb = { id: 'kb-1', name: 'Handbook', settings: { rerank_candidate_k: 12 }, rerank_model: { name: 'Reranker' } }
const response = (id = 'chunk-1', diagnostics: object[] = []) => ({
  query: 'policy', total: 1, diagnostics, timings: [{ stage: 'recall', latency_ms: 12 }, { stage: 'total', latency_ms: 20 }],
  results: [{ chunk_id: id, document_id: 'doc-1', document_name: 'Guide', content: 'Policy keyword', score: 0.4, metadata: null, search_type: 'hybrid', dense_score: 0.81, dense_rank: 2, lexical_score: 7.4, lexical_rank: 1, fusion_score: 0.03, fusion_rank: 1, rerank_score: 0.4, rerank_rank: 1, final_score_stage: 'rerank', degradation_reasons: diagnostics.length ? [{ channel: 'dense', error: 'fallback' }] : [] }],
})

beforeEach(() => {
  slots.splice(0); effects = []; local.clear()
  for (const fn of [getKnowledgeBase, search, updateKnowledgeBase, getItem, setItem, removeItem, confirm]) fn.mockClear()
  getKnowledgeBase.mockResolvedValue(kb)
  confirm.mockReturnValue(true)
})
afterEach(() => slots.forEach(slot => slot.cleanup?.()))

function render(props: Partial<Parameters<typeof RetrievalLab>[0]> = {}) {
  cursor = 0
  return RetrievalLab({ knowledgeBaseId: 'kb-1', api, backHref: '/back', canUpdate: true, ...props })
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
    expect(text(tree)).toContain('denseStage')
    expect(text(tree)).toContain('0.81')
    expect(text(tree)).toContain('dense: fallback')
    expect(text(tree)).toContain('timeout')
    expect(text(tree)).toContain('recall 12ms')
    expect(text(tree)).toContain('total 20ms')
    expect(text(tree)).not.toContain('%')

    slots.splice(0); effects = []
    getKnowledgeBase.mockResolvedValueOnce({ ...kb, rerank_model: null })
    tree = await flush()
    expect(elements(tree).find(element => element.type === 'switch' && element.props.disabled === true)).toBeTruthy()
  })

  test('preserves successful A/B side, attributes failures, overlap, and rank movement', async () => {
    search.mockResolvedValueOnce(response('shared')).mockRejectedValueOnce(new Error('B failed'))
    let tree = await flush()
    find(tree, 'switch', props => props.id === 'compare').props.onCheckedChange(true)
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
    expect(text(tree)).toContain('searchPartialError')
    expect(text(tree)).toContain('searchSideError')

    search.mockReset().mockResolvedValueOnce(response('shared')).mockResolvedValueOnce(response('shared'))
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(text(tree)).toContain('overlap:1,1')
    expect(text(tree)).toContain('→')
  })

  test('shows total search errors and ignores IME composition Enter', async () => {
    search.mockRejectedValue(new Error('offline'))
    let tree = await flush()
    tree = await enterQuery(tree)
    const preventDefault = mock()
    query(tree).props.onKeyDown({ key: 'Enter', shiftKey: false, nativeEvent: { isComposing: true }, preventDefault })
    expect(search).not.toHaveBeenCalled()
    await searchButton(tree).props.onClick()
    tree = await settle()
    expect(text(tree)).toContain('searchError')
  })

  test('persists grades and presets, confirms updates, enforces permission, and exposes update failure', async () => {
    search.mockResolvedValue(response())
    let tree = await flush()
    tree = await enterQuery(tree)
    await searchButton(tree).props.onClick()
    tree = await settle()
    button(tree, 'relevant').props.onClick()
    expect(JSON.parse(local.get('retrieval-lab:kb-1')!).grades['chunk-1']).toBe('relevant')

    find(tree, 'input', props => props['aria-label'] === 'presetName').props.onChange({ target: { value: 'Fast' } })
    tree = render()
    button(tree, 'savePreset').props.onClick()
    tree = render()
    find(tree, 'select', props => props['aria-label'] === 'presets').props.onChange({ target: { value: 'Fast' } })
    tree = render()
    updateKnowledgeBase.mockRejectedValueOnce(new Error('denied'))
    await button(tree, 'applyToProduction').props.onClick()
    tree = render()
    expect(confirm).toHaveBeenCalled()
    expect(text(tree)).toContain('presetUpdateError')

    const calls = updateKnowledgeBase.mock.calls.length
    tree = render({ canUpdate: false })
    await button(tree, 'applyToProduction').props.onClick()
    expect(updateKnowledgeBase).toHaveBeenCalledTimes(calls)
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
    tree = render({ authenticatedMarkdown: true })
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
