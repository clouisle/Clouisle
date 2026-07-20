import { afterEach, beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const getDocuments = mock()
const deleteDocument = mock()
const processDocument = mock()
const retryFailedChunks = mock()
const downloadDocument = mock()
const push = mock()
const toastSuccess = mock()
const toastError = mock()
let permissions = new Set<string>()

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api', () => ({
  adminKnowledgeBasesApi: { getDocuments, deleteDocument, processDocument, retryFailedChunks, downloadDocument },
}))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))

const ui = {
  Button: 'button', Input: 'input', Badge: 'badge', Checkbox: 'checkbox',
  Table: 'table', TableBody: 'tbody', TableCell: 'td', TableHead: 'th',
  TableHeader: 'thead', TableRow: 'tr', Select: 'select', SelectContent: 'select-content',
  SelectItem: 'option', SelectTrigger: 'select-trigger', SelectValue: 'select-value',
  DropdownMenu: 'dropdown', DropdownMenuContent: 'dropdown-content',
  DropdownMenuItem: 'dropdown-item', DropdownMenuSeparator: 'dropdown-separator',
  DropdownMenuTrigger: 'dropdown-trigger', AlertDialogAction: 'alert-action',
  AlertDialogCancel: 'alert-cancel', AlertDialogContent: 'alert-content',
  AlertDialogDescription: 'alert-description', AlertDialogFooter: 'alert-footer',
  AlertDialogHeader: 'alert-header', AlertDialogTitle: 'alert-title',
  Tooltip: 'tooltip', TooltipContent: 'tooltip-content', TooltipTrigger: 'tooltip-trigger',
}
for (const path of [
  '@/components/ui/button', '@/components/ui/input', '@/components/ui/badge',
  '@/components/ui/checkbox', '@/components/ui/table', '@/components/ui/select',
  '@/components/ui/dropdown-menu', '@/components/ui/tooltip',
]) mock.module(path, () => ui)
mock.module('@/components/ui/alert-dialog', () => ({
  ...ui,
  AlertDialog: ({ open, children }: { open: boolean; children?: ReactNode }) => open ? children : null,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: 'faceted-filter' }))
mock.module('lucide-react', () => ({
  MoreHorizontal: 'MoreHorizontal', Trash2: 'Trash2', RefreshCw: 'RefreshCw', Eye: 'Eye',
  FileText: 'FileText', FileType: 'FileType', Link: 'Link', CheckCircle: 'CheckCircle',
  XCircle: 'XCircle', Loader2: 'Loader2', Clock: 'Clock', ChevronLeft: 'ChevronLeft',
  ChevronRight: 'ChevronRight', ChevronsLeft: 'ChevronsLeft', ChevronsRight: 'ChevronsRight',
  Search: 'Search', X: 'X', Settings2: 'Settings2', Play: 'Play', Download: 'Download',
  ExternalLink: 'ExternalLink', RotateCcw: 'RotateCcw',
}))

interface HookSlot {
  value?: unknown
  deps?: readonly unknown[]
  cleanup?: () => void
}

const slots: HookSlot[] = []
let cursor = 0
let effects: Array<() => void | (() => void)> = []
let DocumentsTable: typeof import('./documents-table').DocumentsTable

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
  ;({ DocumentsTable } = await import('./documents-table'))
})

const onRefresh = mock()
const baseDocument = {
  id: 'doc-1', knowledge_base_id: 'kb-1', name: 'Guide.pdf', file_path: '/guide.pdf',
  file_size: 1536, source_url: null, doc_type: 'pdf', status: 'completed', chunk_count: 4,
  error_message: null, metadata: null, created_at: '2026-01-01', updated_at: '2026-01-01',
}

beforeEach(() => {
  slots.splice(0)
  effects = []
  permissions = new Set()
  for (const fn of [getDocuments, deleteDocument, processDocument, retryFailedChunks, downloadDocument,
    push, toastSuccess, toastError, onRefresh]) fn.mockReset()
  getDocuments.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 })
})

afterEach(() => slots.forEach(slot => slot.cleanup?.()))

function render() {
  cursor = 0
  return DocumentsTable({ knowledgeBaseId: 'kb-1', refreshTrigger: 0, onRefresh })
}

async function flush() {
  let tree = render()
  while (effects.length) {
    const pending = effects.splice(0)
    pending.forEach(effect => effect())
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
  return element
}

describe('DocumentsTable', () => {
  test('loads and renders document data, status progress, and pagination', async () => {
    getDocuments.mockResolvedValue({
      items: [
        baseDocument,
        { ...baseDocument, id: 'doc-2', name: 'Working', file_size: 0, status: 'processing', metadata: { embed_progress: { embedded: 2, failed: 1, total: 5 } } },
      ],
      total: 12, page: 1, page_size: 10,
    })

    const tree = await flush()

    expect(getDocuments).toHaveBeenCalledWith('kb-1', { page: 1, pageSize: 10 })
    expect(text(tree)).toContain('Guide.pdf')
    expect(text(tree)).toContain('1.5 KB')
    expect(text(tree)).toContain('embeddingProgress:2,5')
    expect(text(tree)).toContain('failedCount:1')
    expect(text(tree)).toContain('pageInfo:1,2')
  })

  test('shows the empty boundary when loading fails', async () => {
    getDocuments.mockRejectedValue(new Error('offline'))

    const tree = await flush()

    expect(text(tree)).toContain('noDocuments')
    expect(text(tree)).toContain('uploadDocumentHint')
  })

  test('hides mutation actions without permission while retaining read actions', async () => {
    getDocuments.mockResolvedValue({ items: [baseDocument], total: 1, page: 1, page_size: 10 })

    const tree = await flush()
    const labels = text(tree)

    expect(labels).toContain('viewChunks')
    expect(labels).toContain('downloadOriginal')
    expect(labels).not.toContain('reprocess')
    expect(elements(tree).filter(item => item.type === 'dropdown-item').map(text)).not.toContain('delete')
    find(tree, 'dropdown-item', 'viewChunks').props.onClick()
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1/documents/doc-1')
  })

  test('runs permitted process and delete actions and reports download errors', async () => {
    permissions = new Set(['kb:update', 'kb:delete'])
    const pending = { ...baseDocument, status: 'pending' }
    getDocuments.mockResolvedValue({ items: [pending], total: 1, page: 1, page_size: 10 })
    processDocument.mockResolvedValue({})
    deleteDocument.mockResolvedValue({})
    downloadDocument.mockRejectedValue(new Error('download failed'))
    let tree = await flush()

    find(tree, 'dropdown-item', 'configure').props.onClick()
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1/documents/doc-1')

    await find(tree, 'dropdown-item', 'quickProcess').props.onClick()
    expect(processDocument).toHaveBeenCalledWith('kb-1', 'doc-1')
    expect(toastSuccess).toHaveBeenCalledWith('processStartedSingle')

    await find(tree, 'dropdown-item', 'downloadOriginal').props.onClick()
    expect(toastError).toHaveBeenCalledWith('downloadFailed')

    find(tree, 'dropdown-item', 'delete').props.onClick()
    tree = render()
    expect(text(tree)).toContain('deleteDocumentConfirm:Guide.pdf')
    await find(tree, 'alert-action', 'delete').props.onClick()
    expect(deleteDocument).toHaveBeenCalledWith('kb-1', 'doc-1')
    expect(toastSuccess).toHaveBeenCalledWith('documentDeleted')
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })
})
