import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const getDocumentChunks = mock()
const updateChunk = mock()
const toastSuccess = mock()

const ui = {
  Button: 'button',
  Badge: 'badge',
  ScrollArea: 'scroll-area',
  Textarea: 'textarea',
  Input: 'input',
  Label: 'label',
  Separator: 'separator',
  Dialog: 'dialog',
  DialogContent: 'dialog-content',
  DialogDescription: 'dialog-description',
  DialogHeader: 'dialog-header',
  DialogTitle: 'dialog-title',
  DialogFooter: 'dialog-footer',
  AlertDialog: 'alert-dialog',
  AlertDialogAction: 'alert-dialog-action',
  AlertDialogCancel: 'alert-dialog-cancel',
  AlertDialogContent: 'alert-dialog-content',
  AlertDialogDescription: 'alert-dialog-description',
  AlertDialogFooter: 'alert-dialog-footer',
  AlertDialogHeader: 'alert-dialog-header',
  AlertDialogTitle: 'alert-dialog-title',
  Tabs: 'tabs',
  TabsContent: 'tabs-content',
  TabsList: 'tabs-list',
  TabsTrigger: 'tabs-trigger',
  Tooltip: 'tooltip',
  TooltipContent: 'tooltip-content',
  TooltipTrigger: 'tooltip-trigger',
}

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  adminKnowledgeBasesApi: {
    getDocumentChunks,
    updateChunk,
    deleteChunk: mock(),
    createChunk: mock(),
    rechunkDocument: mock(),
  },
}))
for (const path of [
  '@/components/ui/button', '@/components/ui/badge', '@/components/ui/scroll-area',
  '@/components/ui/textarea', '@/components/ui/input', '@/components/ui/label',
  '@/components/ui/separator', '@/components/ui/dialog', '@/components/ui/alert-dialog',
  '@/components/ui/tabs', '@/components/ui/tooltip',
]) {
  mock.module(path, () => ui)
}
mock.module('lucide-react', () => ({
  ChevronLeft: 'chevron-left', ChevronRight: 'chevron-right', Loader2: 'loader',
  Save: 'save-icon', Trash2: 'trash-icon', Plus: 'plus-icon', RotateCcw: 'reset-icon',
  Settings2: 'settings-icon', GripVertical: 'grip-icon', AlertTriangle: 'alert-icon',
}))

interface HookSlot {
  value?: unknown
  deps?: readonly unknown[]
  cleanup?: () => void
}

const slots: HookSlot[] = []
let cursor = 0
let effects: Array<() => void | (() => void)> = []
let ChunkEditorDialog: typeof import('./chunk-editor-dialog').ChunkEditorDialog

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
  ;({ ChunkEditorDialog } = await import('./chunk-editor-dialog'))
})

beforeEach(() => {
  slots.splice(0)
  effects = []
  getDocumentChunks.mockReset()
  updateChunk.mockReset()
  toastSuccess.mockReset()
})

afterEach(() => slots.forEach(slot => slot.cleanup?.()))

const document = {
  id: 'doc-1', name: 'Guide', chunk_count: 1, status: 'completed',
} as Parameters<typeof ChunkEditorDialog>[0]['document']

function render(overrides: Partial<Parameters<typeof ChunkEditorDialog>[0]> = {}) {
  cursor = 0
  return ChunkEditorDialog({
    open: true,
    onOpenChange: mock(),
    knowledgeBaseId: 'kb-1',
    document,
    ...overrides,
  })
}

async function flush(overrides: Partial<Parameters<typeof ChunkEditorDialog>[0]> = {}) {
  let tree = render(overrides)
  while (effects.length) {
    const pending = effects.splice(0)
    pending.forEach(effect => effect())
    await Promise.resolve()
    await Promise.resolve()
    tree = render(overrides)
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
  if (Array.isArray(node)) return node.map(text).join('')
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return text((node as ReactElement<{ children?: ReactNode }>).props.children)
}

function find(tree: ReactNode, predicate: (element: ReactElement) => boolean) {
  const element = elements(tree).find(predicate)
  if (!element) throw new Error('Expected JSX element was not found')
  return element
}

const chunk = { id: 'chunk-1', content: 'Original content', chunk_index: 0, token_count: 3 }
const page = { items: [chunk], total: 1, page: 1, page_size: 20 }

describe('ChunkEditorDialog', () => {
  test('loads chunks only while open and closes through the controller', async () => {
    getDocumentChunks.mockResolvedValue(page)
    const onOpenChange = mock()

    let tree = await flush({ open: false, onOpenChange })
    expect(getDocumentChunks).not.toHaveBeenCalled()

    tree = await flush({ open: true, onOpenChange })
    expect(getDocumentChunks).toHaveBeenCalledWith('kb-1', 'doc-1', { page: 1, pageSize: 20 })
    expect(text(tree)).toContain('Original content')

    find(tree, element => element.type === 'button' && text(element) === 'close').props.onClick()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('edits and saves changed chunk content', async () => {
    getDocumentChunks.mockResolvedValue(page)
    updateChunk.mockResolvedValue({ ...chunk, content: 'Updated content' })
    const onDocumentUpdated = mock()
    let tree = await flush({ onDocumentUpdated })

    find(tree, element => element.type === 'p' && text(element) === 'Original content').props.onClick()
    tree = render({ onDocumentUpdated })
    const textarea = find(tree, element => element.type === 'textarea')
    textarea.props.onChange({ target: { value: 'Updated content' } })
    tree = render({ onDocumentUpdated })
    expect(text(tree)).toContain('unsavedChanges')

    await find(tree, element => element.type === 'button' && elements(element).some(child => child.type === 'save-icon')).props.onClick()
    tree = render({ onDocumentUpdated })
    expect(updateChunk).toHaveBeenCalledWith('kb-1', 'doc-1', 'chunk-1', { content: 'Updated content' })
    expect(text(tree)).toContain('Updated content')
    expect(toastSuccess).toHaveBeenCalledWith('chunkUpdated')
    expect(onDocumentUpdated).toHaveBeenCalledTimes(1)
  })

  test('does not submit empty or unchanged content', async () => {
    getDocumentChunks.mockResolvedValue(page)
    let tree = await flush()

    find(tree, element => element.type === 'p' && text(element) === 'Original content').props.onClick()
    tree = render()
    find(tree, element => element.type === 'textarea').props.onChange({ target: { value: '' } })
    tree = render()
    await find(tree, element => element.type === 'button' && elements(element).some(child => child.type === 'save-icon')).props.onClick()
    expect(updateChunk).not.toHaveBeenCalled()

    tree = render()
    expect(text(tree)).toContain('Original content')
  })

  test('keeps editing state when saving fails', async () => {
    getDocumentChunks.mockResolvedValue(page)
    updateChunk.mockRejectedValue(new Error('save failed'))
    const onDocumentUpdated = mock()
    let tree = await flush({ onDocumentUpdated })

    find(tree, element => element.type === 'p' && text(element) === 'Original content').props.onClick()
    tree = render({ onDocumentUpdated })
    find(tree, element => element.type === 'textarea').props.onChange({ target: { value: 'Retry content' } })
    tree = render({ onDocumentUpdated })
    await find(tree, element => element.type === 'button' && elements(element).some(child => child.type === 'save-icon')).props.onClick()
    tree = render({ onDocumentUpdated })

    expect(find(tree, element => element.type === 'textarea').props.value).toBe('Retry content')
    expect(toastSuccess).not.toHaveBeenCalled()
    expect(onDocumentUpdated).not.toHaveBeenCalled()
  })

  test('renders the empty path when loading fails', async () => {
    getDocumentChunks.mockRejectedValue(new Error('load failed'))
    const tree = await flush()

    expect(text(tree)).toContain('noChunks')
    expect(text(tree)).toContain('addFirstChunk')
  })
})
