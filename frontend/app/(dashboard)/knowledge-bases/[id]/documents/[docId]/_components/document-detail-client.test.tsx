import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const api = Object.fromEntries([
  'getKnowledgeBase', 'getDocument', 'getDocumentChunks', 'processDocument', 'previewChunks',
  'retryFailedChunks', 'retryFailedChunk', 'deleteDocument', 'updateChunk', 'deleteChunk', 'createChunk',
].map(name => [name, mock()])) as Record<string, ReturnType<typeof mock>>
const push = mock()
const toastSuccess = mock()
const toastError = mock()
const router = { push }
const translate = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join(',')}` : key

const windowListeners = new Map<string, EventListener>()
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
Object.defineProperty(globalThis, 'window', {
  configurable: true,
  value: {
    addEventListener: (type: string, listener: EventListener) => windowListeners.set(type, listener),
    removeEventListener: (type: string) => windowListeners.delete(type),
  },
})

mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('next/navigation', () => ({ useRouter: () => router }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api', () => ({ adminKnowledgeBasesApi: api }))
mock.module('@/components/ui/chunk-markdown', () => ({ ChunkMarkdown: 'chunk-markdown' }))

const ui = {
  Button: 'button', Badge: 'badge', Input: 'input', Label: 'label', Textarea: 'textarea',
  ScrollArea: 'scroll-area', Switch: 'switch', AlertDialog: 'alert-dialog',
  AlertDialogAction: 'alert-action', AlertDialogCancel: 'alert-cancel',
  AlertDialogContent: 'alert-content', AlertDialogDescription: 'alert-description',
  AlertDialogFooter: 'alert-footer', AlertDialogHeader: 'alert-header', AlertDialogTitle: 'alert-title',
  Tooltip: 'tooltip', TooltipContent: 'tooltip-content', TooltipTrigger: 'tooltip-trigger',
}
for (const path of [
  '@/components/ui/button', '@/components/ui/badge', '@/components/ui/input', '@/components/ui/label',
  '@/components/ui/textarea', '@/components/ui/scroll-area', '@/components/ui/switch',
  '@/components/ui/alert-dialog', '@/components/ui/tooltip',
]) mock.module(path, () => ui)
mock.module('lucide-react', () => Object.fromEntries([
  'ArrowLeft', 'Play', 'RefreshCw', 'Trash2', 'Settings2', 'FileText', 'Loader2', 'CheckCircle',
  'XCircle', 'Clock', 'ChevronLeft', 'ChevronRight', 'Save', 'RotateCcw', 'Plus', 'GripVertical',
  'AlertTriangle', 'Eye',
].map(name => [name, name])))

interface HookSlot { value?: unknown; deps?: readonly unknown[]; cleanup?: () => void }
const slots: HookSlot[] = []
let cursor = 0
let effects: Array<() => void> = []
let DocumentDetailClient: typeof import('./document-detail-client').DocumentDetailClient

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
    useRef(initial: unknown) {
      const index = cursor++
      slots[index] ??= { value: { current: initial } }
      return slots[index].value
    },
    useCallback(callback: unknown, deps: readonly unknown[]) {
      const index = cursor++
      if (!sameDeps(slots[index]?.deps, deps)) slots[index] = { value: callback, deps }
      return slots[index].value
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
  ;({ DocumentDetailClient } = await import('./document-detail-client'))
})

const knowledgeBase = {
  id: 'kb-1', name: 'Platform Handbook', settings: {
    chunk_size: 800, chunk_overlap: 80, separator: '\n', clean_text: true,
  },
}
const document = {
  id: 'doc-1', knowledge_base_id: 'kb-1', name: 'Guide.pdf', file_path: '/guide.pdf',
  file_size: 1536, source_url: null, doc_type: 'pdf', status: 'completed', chunk_count: 2,
  error_message: null, metadata: null, created_at: '2026-01-01', updated_at: '2026-01-01',
}
const chunk = {
  id: 'chunk-1', document_id: 'doc-1', content: 'First chunk', chunk_index: 0,
  token_count: 12, status: 'completed', error_message: null, metadata: null,
  created_at: '2026-01-01', updated_at: '2026-01-01',
}

beforeEach(() => {
  slots.splice(0)
  effects = []
  for (const fn of [...Object.values(api), push, toastSuccess, toastError]) fn.mockReset()
  windowListeners.clear()
  api.getKnowledgeBase.mockResolvedValue(knowledgeBase)
  api.getDocument.mockResolvedValue(document)
  api.getDocumentChunks.mockResolvedValue({ items: [chunk], total: 1, page: 1, page_size: 20 })
})
afterEach(() => slots.forEach(slot => slot.cleanup?.()))
afterAll(() => {
  if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
  else Reflect.deleteProperty(globalThis, 'window')
})

function render() {
  cursor = 0
  return DocumentDetailClient({ knowledgeBaseId: 'kb-1', documentId: 'doc-1' })
}

async function flush() {
  let tree = render()
  for (let pass = 0; pass < 8 && effects.length; pass++) {
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

function find(tree: ReactNode, type: string, label?: string) {
  const element = elements(tree).find(item => item.type === type && (!label || text(item).includes(label)))
  if (!element) throw new Error(`Expected ${type} ${label ?? ''}`)
  return element as ReactElement<Record<string, unknown>>
}

function buttonWithIcon(tree: ReactNode, icon: string) {
  return elements(tree).find(item => item.type === 'button' && elements(item).some(child => child.type === icon)) as
    | ReactElement<Record<string, unknown>> | undefined
}

function tooltipButton(tree: ReactNode, label: string) {
  const tooltip = find(tree, 'tooltip', label)
  return find(tooltip.props.children as ReactNode, 'tooltip-trigger').props.render as ReactElement<Record<string, unknown>>
}

function chunkPreview(tree: ReactNode, source: string) {
  const preview = elements(tree).find(item =>
    item.type === 'div' &&
    typeof item.props.onClick === 'function' &&
    elements(item).some(child => child.type === 'chunk-markdown' && child.props.source === source)
  )
  if (!preview) throw new Error(`Expected chunk preview ${source}`)
  return preview as ReactElement<Record<string, unknown>>
}

const outsideTarget = { closest: () => null }

function dispatchWindow(type: string) {
  const event = {
    target: outsideTarget,
    preventDefault: mock(),
    stopPropagation: mock(),
  }
  windowListeners.get(type)?.(event as unknown as Event)
  return event
}

function dialog(tree: ReactNode, index: number) {
  return elements(tree).filter(item => item.type === 'alert-dialog')[index] as ReactElement<Record<string, unknown>>
}

describe('dashboard DocumentDetailClient', () => {
  test('keeps loading visible until data resolves and redirects when loading fails', async () => {
    let resolveDocument!: (value: typeof document) => void
    api.getDocument.mockImplementation(() => new Promise(resolve => { resolveDocument = resolve }))

    let tree = render()
    effects.splice(0).forEach(effect => effect())
    expect(elements(tree).some(item => item.type === 'Loader2')).toBe(true)
    expect(text(tree)).not.toContain('Guide.pdf')

    resolveDocument(document)
    await Promise.resolve()
    await Promise.resolve()
    tree = await flush()
    expect(text(tree)).toContain('Guide.pdf')
    expect(text(tree)).toContain('Platform Handbook')
    expect(text(tree)).toContain('1.5 KB')
    expect(text(tree)).toContain('2 chunks')

    slots.splice(0)
    effects = []
    api.getKnowledgeBase.mockRejectedValue(new Error('offline'))
    await flush()
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1')
  })

  test('renders completed chunks and exposes navigation, paging, edit, create, and delete actions', async () => {
    api.getDocumentChunks.mockResolvedValue({ items: [chunk], total: 21, page: 1, page_size: 20 })
    api.updateChunk.mockResolvedValue({ ...chunk, content: 'Updated chunk' })
    api.createChunk.mockResolvedValue({})
    api.deleteChunk.mockResolvedValue({})
    let tree = await flush()

    expect(api.getDocumentChunks).toHaveBeenCalledWith('kb-1', 'doc-1', { page: 1, pageSize: 20 })
    expect(find(tree, 'chunk-markdown').props.source).toBe('First chunk')
    expect(text(tree)).toContain('pageInfo:1,2')
    find(tree, 'button', 'reprocess').props.onClick()
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1/documents/preview?docs=doc-1')

    chunkPreview(tree, 'First chunk').props.onClick()
    tree = render()
    const editor = find(tree, 'textarea')
    editor.props.onChange({ target: { value: 'Updated chunk' } })
    tree = render()
    await tooltipButton(tree, 'save').props.onClick()
    tree = render()
    expect(api.updateChunk).toHaveBeenCalledWith('kb-1', 'doc-1', 'chunk-1', { content: 'Updated chunk' })
    expect(find(tree, 'chunk-markdown').props.source).toBe('Updated chunk')
    expect(toastSuccess).toHaveBeenCalledWith('chunkUpdated')

    await tooltipButton(tree, 'insertChunkAfter').props.onClick()
    expect(api.createChunk).toHaveBeenCalledWith('kb-1', 'doc-1', { content: 'newChunkPlaceholder' }, 0)

    buttonWithIcon(render(), 'Trash2')!.props.onClick()
    tree = render()
    expect(dialog(tree, 0).props.open).toBe(true)
    await find(dialog(tree, 0), 'alert-action', 'delete').props.onClick()
    expect(api.deleteDocument).toHaveBeenCalledWith('kb-1', 'doc-1')
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1')
  })

  test('previews and starts processing a pending document with edited settings', async () => {
    api.getDocument.mockResolvedValue({ ...document, status: 'pending', chunk_count: 0, metadata: { chunk_size: 640, clean_text: false } })
    api.previewChunks.mockResolvedValue({
      chunks: [{ chunk_index: 0, content: 'Preview text', token_count: 3, char_count: 12, overlap_length: 0 }],
      total_chunks: 1, total_tokens: 3, total_chars: 12,
    })
    api.processDocument.mockResolvedValue({})
    let tree = await flush()

    expect(text(tree)).toContain('documentPending')
    expect(find(tree, 'input').props.value).toBe(640)
    find(tree, 'input', undefined).props.onChange({ target: { value: '700' } })
    tree = render()
    await find(tree, 'button', 'previewChunks').props.onClick()
    tree = render()
    expect(api.previewChunks).toHaveBeenCalledWith('kb-1', 'doc-1', {
      chunk_size: 700, chunk_overlap: 80, separator: '\n', clean_text: false,
    })
    expect(find(tree, 'chunk-markdown').props.source).toBe('Preview text')
    expect(text(tree)).toContain('previewStats:1,3')
    expect(toastSuccess).toHaveBeenCalledWith('previewGenerated')

    await find(tree, 'button', 'startProcessing').props.onClick()
    expect(api.processDocument).toHaveBeenCalledWith('kb-1', 'doc-1', {
      chunk_size: 700, chunk_overlap: 80, separator: '\n', clean_text: false,
    })
    expect(toastSuccess).toHaveBeenCalledWith('processStartedSingle')
  })

  test('exits clean edits and guards dirty mouse and keyboard exits', async () => {
    let tree = await flush()
    chunkPreview(tree, 'First chunk').props.onClick()
    tree = await flush()
    expect(find(tree, 'textarea').props.autoFocus).toBe(true)

    dispatchWindow('mousedown')
    tree = await flush()
    expect(elements(tree).some(item => item.type === 'textarea')).toBe(false)

    chunkPreview(tree, 'First chunk').props.onClick()
    tree = await flush()
    find(tree, 'textarea').props.onChange({ target: { value: 'Dirty chunk' } })
    tree = await flush()

    dispatchWindow('focusin')
    tree = render()
    expect(dialog(tree, 2).props.open).toBe(true)

    const click = dispatchWindow('click')
    expect(click.preventDefault).toHaveBeenCalled()
    expect(click.stopPropagation).toHaveBeenCalled()
  })

  test('keeps the unsaved dialog open until saving succeeds', async () => {
    let resolveUpdate!: (value: typeof chunk) => void
    api.updateChunk.mockImplementation(() => new Promise(resolve => { resolveUpdate = resolve }))
    let tree = await flush()
    chunkPreview(tree, 'First chunk').props.onClick()
    tree = await flush()
    find(tree, 'textarea').props.onChange({ target: { value: 'Saved chunk' } })
    tree = await flush()
    dispatchWindow('focusin')
    tree = render()

    const save = find(dialog(tree, 2), 'alert-action', 'save')
    const saving = save.props.onClick() as Promise<void>
    tree = render()
    expect(dialog(tree, 2).props.open).toBe(true)
    expect(find(dialog(tree, 2), 'alert-action', 'save').props.disabled).toBe(true)

    resolveUpdate({ ...chunk, content: 'Saved chunk' })
    await saving
    tree = render()
    expect(dialog(tree, 2).props.open).toBe(false)
    expect(find(tree, 'chunk-markdown').props.source).toBe('Saved chunk')
  })

  test('keeps the unsaved dialog open when saving fails', async () => {
    api.updateChunk.mockRejectedValue(new Error('offline'))
    let tree = await flush()
    chunkPreview(tree, 'First chunk').props.onClick()
    tree = await flush()
    find(tree, 'textarea').props.onChange({ target: { value: 'Unsaved chunk' } })
    tree = await flush()
    dispatchWindow('focusin')
    tree = render()

    await find(dialog(tree, 2), 'alert-action', 'save').props.onClick()
    tree = render()
    expect(dialog(tree, 2).props.open).toBe(true)
    expect(find(tree, 'textarea').props.value).toBe('Unsaved chunk')
  })

  test('shows document and chunk failures and recovers through retry actions', async () => {
    api.getDocument.mockResolvedValue({ ...document, status: 'error', error_message: 'Embedding failed' })
    api.getDocumentChunks.mockResolvedValue({
      items: [{ ...chunk, status: 'failed', error_message: 'Provider unavailable' }],
      total: 1, page: 1, page_size: 20,
    })
    api.retryFailedChunks.mockResolvedValue({})
    api.retryFailedChunk.mockResolvedValue({})
    let tree = await flush()

    expect(text(tree)).toContain('Embedding failed')
    expect(text(tree)).toContain('chunkErrorMessage:Provider unavailable')
    await find(tree, 'button', 'retryFailedChunks').props.onClick()
    expect(api.retryFailedChunks).toHaveBeenCalledWith('kb-1', 'doc-1')
    expect(toastSuccess).toHaveBeenCalledWith('retryStarted')

    await tooltipButton(tree, 'retryFailedChunk').props.onClick()
    expect(api.retryFailedChunk).toHaveBeenCalledWith('kb-1', 'doc-1', 'chunk-1')
    expect(toastSuccess).toHaveBeenCalledWith('retryChunkStarted')

    api.retryFailedChunks.mockRejectedValueOnce(new Error('offline'))
    tree = render()
    await find(tree, 'button', 'retryFailedChunks').props.onClick()
    expect(api.retryFailedChunks).toHaveBeenCalledTimes(2)
  })
})
