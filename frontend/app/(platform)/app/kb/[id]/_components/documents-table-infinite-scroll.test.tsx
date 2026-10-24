import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

interface DocumentRow {
  id: string
  knowledge_base_id: string
  name: string
  file_path: string | null
  file_size: number
  source_url: string | null
  doc_type: string
  status: string
  error_message: string | null
  chunk_count: number
  token_count: number
  metadata: null
  uploaded_by: null
  created_at: string
  updated_at: string
  processed_at: null
}

interface DocumentListParams {
  page: number
  pageSize: number
}

function makeDocument(id: string, name: string): DocumentRow {
  return {
    id,
    knowledge_base_id: 'kb-1',
    name,
    file_path: `/${id}.pdf`,
    file_size: 1024,
    source_url: null,
    doc_type: 'pdf',
    status: 'completed',
    error_message: null,
    chunk_count: 1,
    token_count: 10,
    metadata: null,
    uploaded_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    processed_at: null,
  }
}

// Keep the transport signature for page-aware mock implementations.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const getDocuments = mock(async (_knowledgeBaseId: string, _params: DocumentListParams) => ({
  items: [] as DocumentRow[],
  total: 0,
}))

type ObserverCallback = (entries: Array<{ isIntersecting: boolean }>) => void

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []

  private readonly callback: ObserverCallback

  constructor(callback: ObserverCallback) {
    this.callback = callback
    FakeIntersectionObserver.instances.push(this)
  }

  observe() {}
  unobserve() {}
  disconnect() {}

  trigger(isIntersecting: boolean) {
    this.callback([{ isIntersecting }])
  }
}

globalThis.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => key,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push: mock(() => {}) }) }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/lib/utils', () => ({ formatDate: () => 'date' }))
mock.module('@/components/knowledge-bases/feishu-document-source', () => ({
  isFeishuManaged: () => false,
  FeishuDocumentSource: () => null,
}))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: {
    getDocuments,
    processDocument: mock(async () => undefined),
    retryFailedChunks: mock(async () => undefined),
    deleteDocument: mock(async () => undefined),
    downloadDocument: mock(async () => undefined),
  },
}))
mock.module('lucide-react', () => Object.fromEntries([
  'MoreHorizontal', 'Trash2', 'RefreshCw', 'Eye', 'FileText', 'FileType', 'Link',
  'CheckCircle', 'XCircle', 'Loader2', 'Clock', 'Search', 'X', 'Settings2', 'Play',
  'Download', 'ExternalLink', 'RotateCcw',
].map((name) => [name, () => null])))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked }: { checked?: boolean }) => <span data-checkbox={String(checked)} />,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/components/ui/table', () => {
  const element = ({ children }: React.PropsWithChildren) => <div>{children}</div>
  return { Table: element, TableBody: element, TableCell: element, TableHead: element, TableHeader: element, TableRow: element }
})
mock.module('@/components/ui/dropdown-menu', () => {
  const element = ({ children }: React.PropsWithChildren) => <div>{children}</div>
  return {
    DropdownMenu: element,
    DropdownMenuContent: element,
    DropdownMenuItem: element,
    DropdownMenuSeparator: () => null,
    DropdownMenuTrigger: element,
  }
})
mock.module('@/components/ui/alert-dialog', () => {
  const element = ({ children }: React.PropsWithChildren) => <div>{children}</div>
  return {
    AlertDialog: element,
    AlertDialogAction: element,
    AlertDialogCancel: element,
    AlertDialogContent: element,
    AlertDialogDescription: element,
    AlertDialogFooter: element,
    AlertDialogHeader: element,
    AlertDialogTitle: element,
  }
})
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ render, children }: { render?: React.ReactElement; children?: React.ReactNode }) =>
    render ? React.cloneElement(render, undefined, children) : <span>{children}</span>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: () => null,
}))

// Static import cannot work here: the component must load after mock.module() registers the UI/API stubs.
const { DocumentsTable } = await import('./documents-table')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

function text(node: ReactTestRenderer['root']): string {
  return node.children.map((child) => {
    if (typeof child === 'string' || typeof child === 'number') return String(child)
    if (child && typeof child === 'object') return text(child as ReactTestRenderer['root'])
    return ''
  }).join('')
}

beforeEach(() => {
  FakeIntersectionObserver.instances = []
  getDocuments.mockClear()
  getDocuments.mockImplementation(async (_id, params) => (
    params.page === 1
      ? {
          items: Array.from({ length: 5 }, (_, index) => makeDocument(`first-${index}`, `First page ${index}`)),
          total: 8,
        }
      : {
          items: Array.from({ length: 3 }, (_, index) => makeDocument(`second-${index}`, `Second page ${index}`)),
          total: 8,
        }
  ))
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

test('requests and appends the next page when the observed sentinel intersects', async () => {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<DocumentsTable knowledgeBaseId="kb-1" refreshTrigger={0} onRefresh={() => {}} />)
  })
  renderers.push(renderer)
  await act(async () => {})

  expect(getDocuments).toHaveBeenCalledTimes(1)
  expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 1, pageSize: 10 })
  expect(text(renderer.root)).toContain('First page 4')
  expect(text(renderer.root)).not.toContain('Second page 2')

  const observer = FakeIntersectionObserver.instances.at(-1)!
  expect(observer).toBeDefined()
  await act(async () => {
    observer.trigger(true)
    await Promise.resolve()
  })
  await act(async () => {})

  expect(getDocuments).toHaveBeenCalledTimes(2)
  expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 2, pageSize: 10 })
  expect(text(renderer.root)).toContain('First page 4')
  expect(text(renderer.root)).toContain('Second page 2')

  await act(async () => { observer.trigger(true) })
  await act(async () => {})
  expect(getDocuments).toHaveBeenCalledTimes(2)
})
