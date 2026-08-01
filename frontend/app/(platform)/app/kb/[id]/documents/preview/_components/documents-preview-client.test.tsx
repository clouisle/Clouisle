import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const push = mock()
const toast = { success: mock(), error: mock() }
const api = {
  getKnowledgeBase: mock(),
  getDocument: mock(),
  previewChunks: mock(),
  processDocumentWithChunks: mock(),
}

let state: unknown[] = []
let stateIndex = 0
let effects: Array<() => void | (() => void)> = []

mock.module('react/jsx-dev-runtime', () => ({
  Fragment: 'fragment',
  jsxDEV: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
}))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api', () => ({ knowledgeBasesApi: api }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element('tooltip'),
  TooltipContent: element('tooltip-content'),
  TooltipTrigger: ({ render, children, ...props }: Record<string, unknown>) => {
    const target = render as { type?: unknown; props?: Record<string, unknown> } | undefined
    return target
      ? { type: target.type, props: { ...target.props, ...props, ...(children !== undefined ? { children } : {}) } }
      : element('button')(props)
  },
}))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange(value: boolean): void }) => ({
    type: 'button',
    props: { ...props, role: 'switch', 'aria-checked': checked, onClick: () => onCheckedChange(!checked) },
  }),
}))

const icons = ['ArrowLeft', 'Play', 'FileText', 'Loader2', 'Settings2', 'Eye', 'AlertTriangle', 'CheckCircle2', 'X', 'Pencil', 'Check', 'Trash2', 'Plus']
mock.module('lucide-react', () => Object.fromEntries(icons.map(name => [name, (props: Record<string, unknown>) => ({
  type: 'svg',
  props: { ...props, 'data-icon': name },
})])))

const { DocumentsPreviewClient } = await import('./documents-preview-client')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  if (Array.isArray(node)) return node.flatMap(child => findAll(child, predicate))
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const tree = resolved as Tree
  const matches = predicate(tree) ? [tree] : []
  const children = tree.props.children
  for (const child of Array.isArray(children) ? children : [children]) {
    matches.push(...findAll(child as ReactNode, predicate))
  }
  return matches
}

function text(node: ReactNode): string {
  const resolved = resolve(node)
  if (resolved == null || typeof resolved === 'boolean') return ''
  if (typeof resolved === 'string' || typeof resolved === 'number') return String(resolved)
  if (Array.isArray(resolved)) return resolved.map(text).join('')
  if (typeof resolved === 'object' && 'props' in resolved) return text((resolved as Tree).props.children as ReactNode)
  return ''
}

function render(documentIds = ['doc-1']) {
  stateIndex = 0
  effects = []
  return DocumentsPreviewClient({ knowledgeBaseId: 'kb-1', documentIds })
}

async function load(documentIds = ['doc-1']) {
  render(documentIds)
  const effect = effects[0]
  effect?.()
  for (let index = 0; index < 8; index++) await Promise.resolve()
  return render(documentIds)
}

function button(tree: ReactNode, name: string) {
  const match = findAll(tree, node => node.type === 'button' && text(node) === name)[0]
  if (!match) throw new Error(`Button not found: ${name}`)
  return match
}

function chunkAction(tree: ReactNode, index: number) {
  const match = findAll(tree, node => node.type === 'button' && node.props.className?.toString().startsWith('h-6 w-6'))[index]
  if (!match) throw new Error(`Chunk action not found: ${index}`)
  return match
}

const knowledgeBase = {
  id: 'kb-1',
  name: 'Product docs',
  settings: { chunk_size: 700, chunk_overlap: 70, separator: '\n\n' },
}
const document = {
  id: 'doc-1',
  name: 'Guide.pdf',
  status: 'pending',
}
const preview = {
  chunks: [
    { chunk_index: 0, content: 'Alpha beta', char_count: 10, token_count: 3, overlap_length: 0 },
    { chunk_index: 1, content: 'Beta gamma', char_count: 10, token_count: 3, overlap_length: 4 },
  ],
  total_chunks: 2,
  total_tokens: 6,
  total_chars: 20,
}

beforeEach(() => {
  state = []
  effects = []
  push.mockReset()
  toast.success.mockReset()
  toast.error.mockReset()
  Object.values(api).forEach(fn => fn.mockReset())
  api.getKnowledgeBase.mockResolvedValue(knowledgeBase)
  api.getDocument.mockResolvedValue(document)
  api.previewChunks.mockResolvedValue(preview)
  api.processDocumentWithChunks.mockResolvedValue({ ...document, status: 'processing' })
})

afterEach(() => {
  effects = []
})

describe('DocumentsPreviewClient', () => {
  test('shows loading, initializes settings, and keeps only documents that load', async () => {
    api.getDocument.mockImplementation((_kb: string, id: string) =>
      id === 'missing' ? Promise.reject(new Error('gone')) : Promise.resolve(document))

    const loading = render(['missing', 'doc-1'])
    expect(findAll(loading, node => node.props.className?.toString().includes('animate-spin')).length).toBe(1)

    const tree = await load(['missing', 'doc-1'])
    expect(text(tree)).toContain('batchPreviewTitle')
    expect(text(tree)).toContain('Product docs · 1 documentsCount')
    expect(text(tree)).toContain('Guide.pdf')
    expect(findAll(tree, node => node.props.id === 'chunk_size')[0].props.value).toBe(700)
    expect(findAll(tree, node => node.props.id === 'chunk_overlap')[0].props.value).toBe(70)
  })

  test('redirects on empty input or knowledge-base failure', async () => {
    await load([])
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1')

    state = []
    push.mockReset()
    api.getKnowledgeBase.mockRejectedValue(new Error('offline'))
    const tree = await load()
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1')
    expect(text(tree)).toContain('noDocuments')
  })

  test('shows the empty boundary and its back action when all documents fail', async () => {
    api.getDocument.mockRejectedValue(new Error('missing'))
    const tree = await load()

    expect(text(tree)).toContain('noDocuments')
    ;(button(tree, 'backToKnowledgeBase').props.onClick as () => void)()
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1')
  })

  test('previews chunks, edits content, deletes a chunk, and clears previews when settings change', async () => {
    let tree = await load()
    await (button(tree, 'previewChunks').props.onClick as () => Promise<void>)()
    tree = render()

    expect(api.previewChunks).toHaveBeenCalledWith('kb-1', 'doc-1', {
      chunk_size: 700,
      chunk_overlap: 70,
      separator: '\n\n',
      clean_text: true,
    })
    expect(text(tree)).toContain('previewStats:{"chunks":2,"tokens":6}')
    expect(text(tree)).toContain('Alpha beta')
    expect(text(tree)).toContain('overlapChars:{"count":4}')

    ;(chunkAction(tree, 0).props.onClick as () => void)()
    tree = render()
    const textarea = findAll(tree, node => node.type === 'textarea')[0]
    ;(textarea.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '  Revised content  ' } })
    tree = render()
    ;(button(tree, 'save').props.onClick as () => void)()
    tree = render()
    expect(text(tree)).toContain('Revised content')

    ;(chunkAction(tree, 2).props.onClick as () => void)()
    tree = render()
    expect(text(tree)).toContain('#20 tokens · 0 chars')

    ;(chunkAction(tree, 1).props.onClick as () => void)()
    tree = render()
    expect(text(tree)).not.toContain('Revised content')

    const chunkSize = findAll(tree, node => node.props.id === 'chunk_size')[0]
    ;(chunkSize.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '' } })
    tree = render()
    expect(findAll(tree, node => node.props.id === 'chunk_size')[0].props.value).toBe(1000)
    expect(text(tree)).toContain('noPreviewYet')
  })

  test('shows preview errors, retries non-Error failures, and previews all eligible documents', async () => {
    api.previewChunks.mockRejectedValueOnce(new Error('preview unavailable')).mockRejectedValueOnce('bad response')
    let tree = await load()

    await (button(tree, 'previewChunks').props.onClick as () => Promise<void>)()
    tree = render()
    expect(text(tree)).toContain('preview unavailable')

    await (button(tree, 'retryPreview').props.onClick as () => Promise<void>)()
    tree = render()
    expect(text(tree)).toContain('previewFailed')

    api.previewChunks.mockResolvedValue(preview)
    await (button(tree, 'retryPreview').props.onClick as () => Promise<void>)()
    tree = render()
    await (button(tree, 'previewAll (1)').props.onClick as () => Promise<void>)()
    expect(toast.success).toHaveBeenCalledWith('batchPreviewGenerated')
  })

  test('processes previewed chunks and returns to the knowledge base', async () => {
    let tree = await load()
    await (button(tree, 'previewChunks').props.onClick as () => Promise<void>)()
    tree = render()

    await (button(tree, 'startProcessingAll (1)').props.onClick as () => Promise<void>)()

    expect(api.processDocumentWithChunks).toHaveBeenCalledWith('kb-1', 'doc-1', [
      { content: 'Alpha beta', chunk_index: 0 },
      { content: 'Beta gamma', chunk_index: 1 },
    ])
    expect(toast.success).toHaveBeenCalledWith('documentProcessingStarted')
    expect(toast.success).toHaveBeenCalledWith('processStarted:{"count":1}')
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1')
  })

  test('reports processing errors from refreshed state and from a failed refresh', async () => {
    let tree = await load()
    await (button(tree, 'previewChunks').props.onClick as () => Promise<void>)()
    tree = render()

    api.processDocumentWithChunks.mockRejectedValue(new Error('submit failed'))
    api.getDocument.mockResolvedValue({ ...document, status: 'error', error_message: 'parser failed' })
    await (button(tree, 'startProcessingAll (1)').props.onClick as () => Promise<void>)()
    expect(toast.error).toHaveBeenCalledWith('parser failed')

    state = []
    toast.error.mockReset()
    api.getDocument.mockResolvedValueOnce(document)
    tree = await load()
    await (button(tree, 'previewChunks').props.onClick as () => Promise<void>)()
    tree = render()
    api.getDocument.mockRejectedValue(new Error('refresh failed'))
    await (button(tree, 'startProcessingAll (1)').props.onClick as () => Promise<void>)()
    expect(toast.error).toHaveBeenCalledWith('documentProcessFailed')
  })

  test('removes tabs with keyboard and redirects after removing the final document', async () => {
    const tree = await load()
    const remove = findAll(tree, node => node.props.role === 'button' && node.type === 'span')[0]
    ;(remove.props.onKeyDown as (event: { key: string; stopPropagation(): void }) => void)({ key: 'Escape', stopPropagation() {} })
    expect(push).not.toHaveBeenCalled()
    ;(remove.props.onKeyDown as (event: { key: string; stopPropagation(): void }) => void)({ key: 'Enter', stopPropagation() {} })
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1')
  })
})
