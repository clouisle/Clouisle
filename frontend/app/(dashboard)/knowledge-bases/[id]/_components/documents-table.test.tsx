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
const open = mock()
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
  '@/components/ui/dropdown-menu',
]) mock.module(path, () => ui)
mock.module('@/components/ui/tooltip', () => ({
  ...ui,
  TooltipTrigger: ({ render, children, ...props }: { render?: ReactElement; children?: ReactNode }) =>
    render ? { ...render, props: { ...render.props, ...props } } : { type: 'tooltip-trigger', props: { ...props, children } },
}))
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
    push, toastSuccess, toastError, open, onRefresh]) fn.mockReset()
  Object.assign(globalThis, { window: { open } })
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

function resolve(node: ReactNode): ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const element = node as ReactElement<Record<string, unknown>>
  return typeof element.type === 'function' ? resolve(element.type(element.props)) : element
}

function elements(node: ReactNode): ReactElement[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const element = resolved as ReactElement<{ children?: ReactNode }>
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

  test('filters, paginates, retries, opens URL sources, and runs bulk actions', async () => {
    permissions = new Set(['kb:update', 'kb:delete'])
    const pending = { ...baseDocument, id: 'doc-pending', name: 'Todo.txt', doc_type: 'txt', status: 'pending', file_path: null, file_size: null }
    const failed = { ...baseDocument, id: 'doc-error', name: 'Broken URL', doc_type: 'url', status: 'error', file_path: null, source_url: 'https://example.test/source', error_message: 'bad chunks' }
    getDocuments.mockResolvedValue({ items: [pending, failed], total: 25, page: 1, page_size: 10 })
    processDocument.mockResolvedValue({})
    retryFailedChunks.mockResolvedValue({})
    deleteDocument.mockResolvedValue({})

    let tree = await flush()

    elements(tree).find(item => item.type === 'input')!.props.onChange({ target: { value: 'broken' } })
    tree = await flush()
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', expect.objectContaining({ search: 'broken' }))

    const filters = elements(tree).filter(item => item.type === 'faceted-filter')
    filters[0].props.onSelectionChange(new Set(['error']))
    filters[1].props.onSelectionChange(new Set(['url']))
    tree = await flush()
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', expect.objectContaining({ status: ['error'], doc_type: ['url'] }))

    find(tree, 'button', 'reset').props.onClick()
    tree = await flush()
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', expect.objectContaining({ page: 1, pageSize: 10 }))

    find(tree, 'select').props.onValueChange('20')
    tree = await flush()
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', expect.objectContaining({ pageSize: 20 }))

    elements(tree).filter(item => item.type === 'button' && item.props.className === 'h-8 w-8')[2].props.onClick()
    tree = await flush()
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', expect.objectContaining({ page: 2 }))

    find(tree, 'dropdown-item', 'retryFailedChunks').props.onClick()
    expect(retryFailedChunks).toHaveBeenCalledWith('kb-1', 'doc-error')
    find(tree, 'dropdown-item', 'viewSourceUrl').props.onClick()
    expect(open).toHaveBeenCalledWith('https://example.test/source', '_blank')
    find(tree, 'dropdown-item', 'reprocess').props.onClick()
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1/documents/preview?docs=doc-error')

    find(tree, 'checkbox').props.onCheckedChange()
    tree = render()
    expect(text(tree)).toContain('documentsSelected')
    await elements(tree).find(item => item.type === 'button' && String(item.props.className).includes('text-primary'))!.props.onClick()
    expect(processDocument).toHaveBeenCalledWith('kb-1', 'doc-pending')

    tree = render()
    find(tree, 'checkbox').props.onCheckedChange()
    tree = render()
    let destructiveBulkButtons = elements(tree).filter(item => item.type === 'button' && String(item.props.className).includes('h-8 w-8 text-destructive'))
    await destructiveBulkButtons[0].props.onClick()
    expect(retryFailedChunks).toHaveBeenCalledWith('kb-1', 'doc-error')

    tree = render()
    find(tree, 'checkbox').props.onCheckedChange()
    tree = render()
    destructiveBulkButtons = elements(tree).filter(item => item.type === 'button' && String(item.props.className).includes('h-8 w-8 text-destructive'))
    destructiveBulkButtons[1].props.onClick()
    tree = render()
    expect(text(tree)).toContain('confirmBulkDocumentsDelete:2')
    await find(tree, 'alert-action', 'delete').props.onClick()
    expect(deleteDocument).toHaveBeenCalledWith('kb-1', 'doc-pending')
    expect(deleteDocument).toHaveBeenCalledWith('kb-1', 'doc-error')
  })
})
