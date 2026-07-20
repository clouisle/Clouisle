import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const getKnowledgeBase = mock()
const search = mock()
const push = mock()
const router = { push }

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({ useRouter: () => router }))
mock.module('@/lib/api', () => ({ adminKnowledgeBasesApi: { getKnowledgeBase, search } }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const ui = {
  Button: 'button', Input: 'input', Card: 'card', CardContent: 'card-content', CardHeader: 'card-header',
  Badge: 'badge', Label: 'label', Switch: 'switch', Popover: 'popover', PopoverContent: 'popover-content',
  PopoverTrigger: 'popover-trigger', ToggleGroup: 'toggle-group', ToggleGroupItem: 'toggle-group-item',
}
for (const path of [
  '@/components/ui/button', '@/components/ui/input', '@/components/ui/card', '@/components/ui/badge',
  '@/components/ui/label', '@/components/ui/switch', '@/components/ui/popover', '@/components/ui/toggle-group',
]) mock.module(path, () => ui)
mock.module('lucide-react', () => Object.fromEntries([
  'ArrowLeft', 'Search', 'FileText', 'Loader2', 'Send', 'Settings2', 'ChevronDown', 'ChevronUp', 'Zap',
  'FileSearch', 'Sparkles',
].map(name => [name, name])))

interface HookSlot { value?: unknown; deps?: readonly unknown[]; cleanup?: () => void }
const slots: HookSlot[] = []
let cursor = 0
let effects: Array<() => void> = []
let SearchTestClient: typeof import('./search-test-client').SearchTestClient

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
      return [slots[index].value, (next: unknown) => {
        slots[index].value = typeof next === 'function'
          ? (next as (current: unknown) => unknown)(slots[index].value)
          : next
      }]
    },
    useEffect(effect: () => void | (() => void), deps?: readonly unknown[]) {
      const index = cursor++
      if (!sameDeps(slots[index]?.deps, deps)) {
        slots[index]?.cleanup?.()
        slots[index] = { deps }
        effects.push(() => {
          const cleanup = effect()
          if (cleanup) slots[index].cleanup = cleanup
        })
      }
    },
  }))
  ;({ SearchTestClient } = await import('./search-test-client'))
})

const knowledgeBase = {
  id: 'kb-1', name: 'Handbook', settings: { rerank_enabled: true, rerank_candidate_k: 12, rerank_fail_open: false, rerank_score_threshold: 0.7 },
  rerank_model: { name: 'Reranker', provider: 'local' },
}

beforeEach(() => {
  slots.splice(0)
  effects = []
  for (const fn of [getKnowledgeBase, search, push]) fn.mockReset()
  getKnowledgeBase.mockResolvedValue(knowledgeBase)
})
afterEach(() => slots.forEach(slot => slot.cleanup?.()))

function render() {
  cursor = 0
  return SearchTestClient({ knowledgeBaseId: 'kb-1' })
}

async function flush() {
  let tree = render()
  while (effects.length) {
    effects.splice(0).forEach(effect => effect())
    await Promise.resolve()
    await Promise.resolve()
    tree = render()
  }
  return tree
}

function elements(node: ReactNode): ReactElement[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const element = node as ReactElement<{ children?: ReactNode }>
  return [element, ...elements(element.props.children)]
}

function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join(' ')
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return text((node as ReactElement<{ children?: ReactNode }>).props.children)
}

function find(tree: ReactNode, type: string, predicate: (props: Record<string, unknown>) => boolean = () => true) {
  const element = elements(tree).find(item => item.type === type && predicate(item.props))
  if (!element) throw new Error(`Expected ${type}`)
  return element as ReactElement<Record<string, unknown>>
}

function queryInput(tree: ReactNode) {
  return find(tree, 'input', props => props.placeholder === 'searchPlaceholder')
}

function searchButton(tree: ReactNode) {
  return find(tree, 'button', props => props.className === 'h-8 w-8 shrink-0 rounded-full')
}

describe('SearchTestClient', () => {
  test('keeps the loading boundary until knowledge-base data resolves, then shows the initial hint', async () => {
    let resolveKnowledgeBase!: (value: typeof knowledgeBase) => void
    getKnowledgeBase.mockImplementation(() => new Promise(resolve => { resolveKnowledgeBase = resolve }))

    let tree = render()
    effects.splice(0).forEach(effect => effect())
    expect(text(tree)).not.toContain('searchTestHint')
    expect(elements(tree).some(item => item.type === 'Loader2')).toBe(true)

    resolveKnowledgeBase(knowledgeBase)
    await Promise.resolve()
    await Promise.resolve()
    tree = render()
    expect(text(tree)).toContain('Handbook')
    expect(text(tree)).toContain('searchTestHint')
  })

  test('validates search controls and renders expandable reranked results', async () => {
    search.mockResolvedValue({ results: [{
      chunk_id: 'chunk-1', document_name: 'Guide', content: 'Detailed answer', score: 0.86,
      original_score: 0.72, rerank_score: 0.91, rerank_reason: 'semantic match',
    }] })
    let tree = await flush()

    queryInput(tree).props.onChange({ target: { value: '  policy  ' } })
    find(tree, 'input', props => props.id === 'topK').props.onChange({ target: { value: '99' } })
    find(tree, 'input', props => props.id === 'threshold').props.onChange({ target: { value: '0.6' } })
    find(tree, 'input', props => props.id === 'threshold').props.onChange({ target: { value: '1.2' } })
    tree = render()
    const pending = searchButton(tree).props.onClick()
    tree = render()
    expect(text(tree)).toContain('searching')
    await pending
    tree = render()

    expect(search).toHaveBeenCalledWith('kb-1', {
      query: 'policy', search_mode: 'hybrid', top_k: 20, threshold: 0.6,
      rerank_enabled: true, rerank_candidate_k: 12, rerank_fail_open: false, rerank_score_threshold: 0.7,
    })
    expect(text(tree)).toContain('searchResultsCount:1')
    expect(text(tree)).toContain('86.0%')
    expect(text(tree)).toContain('rerankReason')
    expect(text(tree)).toContain('semantic match')

    find(tree, 'card').props.onClick()
    tree = render()
    expect(text(tree)).toContain('originalScore')
    expect(text(tree)).toContain('72.0%')
  })

  test('shows no-results after an API failure and allows recovery', async () => {
    search.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({
      results: [{ chunk_id: 'chunk-2', document_name: 'Recovered', content: 'Available now', score: 0.5 }],
    })
    let tree = await flush()
    queryInput(tree).props.onChange({ target: { value: 'retry' } })
    tree = render()

    await searchButton(tree).props.onClick()
    tree = render()
    expect(text(tree)).toContain('noResults')

    await searchButton(tree).props.onClick()
    tree = render()
    expect(search).toHaveBeenCalledTimes(2)
    expect(text(tree)).toContain('Recovered')
    expect(text(tree)).toContain('Available now')
  })
})
