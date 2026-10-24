import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window()
const documentNode = window.document
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = documentNode as unknown as Document
globalThis.HTMLElement = window.HTMLElement as unknown as typeof HTMLElement
globalThis.Element = window.Element as unknown as typeof Element
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const originalSetInterval = globalThis.setInterval
const originalClearInterval = globalThis.clearInterval
let intervalCallback: (() => void) | undefined
const clearIntervalMock = mock(() => {})

interface DocumentFixture {
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
  metadata: {
    embed_progress?: { embedded?: number; failed?: number; total?: number }
    feishu_source_url?: string
  } | null
  uploaded_by: string | null
  created_at: string
  updated_at: string
  processed_at: string | null
}

interface DocumentListParams {
  page: number
  pageSize: number
  search?: string
  status?: string[]
  doc_type?: string[]
}

const push = mock(() => {})
const toastSuccess = mock(() => {})
const toastError = mock(() => {})
const onRefresh = mock(() => {})
// Keep the transport signature for page-aware mock implementations.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const getDocuments = mock(async (_knowledgeBaseId: string, _params: DocumentListParams) => ({
  items: [
    makeDocument('pending-doc', 'Pending Guide', 'pending'),
    makeDocument('error-doc', 'Broken Guide', 'error'),
    makeDocument('done-doc', 'Done Guide', 'completed'),
  ] as DocumentFixture[],
  total: 3,
}))
const processDocument = mock(async () => undefined)
const retryFailedChunks = mock(async () => undefined)
const deleteDocument = mock(async () => undefined)
const downloadDocument = mock(async () => undefined)

mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) => {
    if (key === 'documentsSelected') return 'documents selected'
    if (key === 'confirmBulkDocumentsDelete') return `Delete ${values?.count} documents?`
    if (key === 'bulkDocumentsDeleted') return `Deleted ${values?.count} documents`
    return `${namespace}.${key}`
  },
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => permissions }) }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
const infiniteScrollCalls: Array<{ hasMore: boolean; loading: boolean; onLoadMore: () => void }> = []
mock.module('@/hooks/use-infinite-scroll', () => ({
  useInfiniteScroll: (options: { hasMore: boolean; loading: boolean; onLoadMore: () => void }) => {
    infiniteScrollCalls.length = 0
    infiniteScrollCalls.push(options)
    return { current: null }
  },
}))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { getDocuments, processDocument, retryFailedChunks, deleteDocument, downloadDocument },
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: () => void }) => <button role="checkbox" aria-checked={checked} onClick={onCheckedChange} />,
}))
mock.module('@/components/ui/input', () => ({
  Input: ({ onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input {...props} onInput={onChange as React.FormEventHandler<HTMLInputElement>} />
  ),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, onSelectionChange }: { title: string; onSelectionChange: (values: Set<string>) => void }) => (
    <button onClick={() => onSelectionChange(new Set(['pending']))}>{title}</button>
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <option>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: () => <span />,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open = true }: { children: React.ReactNode; open?: boolean }) => open ? <>{children}</> : null,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children, render, onClick, 'data-testid': dataTestId }: { children?: React.ReactNode; render?: React.ReactNode; onClick?: () => void; 'data-testid'?: string }) => render
    ? React.cloneElement(render as React.ReactElement<{ onClick?: () => void; 'data-testid'?: string }>, { onClick, 'data-testid': dataTestId })
    : <button data-testid={dataTestId} onClick={onClick}>{children}</button>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
import { DocumentsTable } from './documents-table'

function makeDocument(id: string, name: string, status: string): DocumentFixture {
  return {
    id,
    knowledge_base_id: 'kb-1',
    name,
    file_path: `/${id}.pdf`,
    file_size: 1024,
    source_url: null,
    doc_type: 'pdf',
    status,
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

async function renderTable() {
  const container = documentNode.createElement('div')
  documentNode.body.appendChild(container)
  const root = createRoot(container)
  await act(async () => {
    root.render(<DocumentsTable knowledgeBaseId="kb-1" refreshTrigger={0} onRefresh={onRefresh} />)
  })
  await act(async () => {})
  return { container, root }
}

function checkbox(container: HTMLElement, index: number) {
  return container.querySelectorAll('button[role="checkbox"]')[index] as HTMLButtonElement
}

function previousButtonForText(container: HTMLElement, text: string) {
  const nodes = Array.from(container.querySelectorAll('button, span'))
  const index = nodes.findLastIndex(node => node.textContent === text)
  return nodes.slice(0, index).reverse().find(node => node.tagName === 'BUTTON') as HTMLButtonElement
}

function buttonForText(container: HTMLElement, text: string, index = 0) {
  return Array.from(container.querySelectorAll('button')).filter(button => button.textContent === text)[index]!
}

let mounted: Root[] = []

let permissions = true

beforeEach(() => {
  permissions = true
  infiniteScrollCalls.length = 0
  intervalCallback = undefined
  clearIntervalMock.mockClear()
  globalThis.setInterval = ((callback: () => void) => {
    intervalCallback = callback
    return 1
  }) as unknown as typeof globalThis.setInterval
  globalThis.clearInterval = clearIntervalMock as unknown as typeof globalThis.clearInterval
  push.mockClear()
  toastSuccess.mockClear()
  toastError.mockClear()
  getDocuments.mockClear()
  getDocuments.mockImplementation(async () => ({
    items: [
      makeDocument('pending-doc', 'Pending Guide', 'pending'),
      makeDocument('error-doc', 'Broken Guide', 'error'),
      makeDocument('done-doc', 'Done Guide', 'completed'),
    ],
    total: 3,
  }))
  processDocument.mockClear()
  retryFailedChunks.mockClear()
  deleteDocument.mockClear()
  downloadDocument.mockClear()
  onRefresh.mockClear()
})

afterEach(() => {
  for (const root of mounted) act(() => root.unmount())
  mounted = []
  documentNode.body.replaceChildren()
  globalThis.setInterval = originalSetInterval
  globalThis.clearInterval = originalClearInterval
})

describe('platform DocumentsTable', () => {
  test('renders documents and bulk actions for selected rows', async () => {
    const view = await renderTable()
    mounted.push(view.root)

    expect(view.container.textContent).toContain('Pending Guide')
    expect(view.container.querySelector('[data-testid="kb-document-status-pending-pending-doc"]')).toBeTruthy()
    expect(view.container.querySelector('[data-testid="kb-document-status-error-error-doc"]')).toBeTruthy()
    expect(view.container.querySelector('[data-testid="kb-document-status-completed-done-doc"]')).toBeTruthy()
    expect(view.container.querySelector('[data-testid="kb-documents-table"]')).toBeTruthy()
    expect(view.container.textContent).toContain('Broken Guide')

    await act(async () => checkbox(view.container, 1).click())
    await act(async () => checkbox(view.container, 2).click())

    expect(view.container.textContent).toContain('2 documents selected')
    expect(view.container.textContent).toContain('knowledgeBases.bulkQuickProcess')
    expect(view.container.textContent).toContain('knowledgeBases.bulkRetryFailedChunks')
  })

  test('runs bulk process, retry, and delete for selected documents', async () => {
    const view = await renderTable()
    mounted.push(view.root)

    await act(async () => checkbox(view.container, 1).click())
    await act(async () => previousButtonForText(view.container, 'knowledgeBases.bulkQuickProcess').click())
    expect(processDocument).toHaveBeenCalledWith('kb-1', 'pending-doc')

    await act(async () => checkbox(view.container, 2).click())
    await act(async () => previousButtonForText(view.container, 'knowledgeBases.bulkRetryFailedChunks').click())
    expect(retryFailedChunks).toHaveBeenCalledWith('kb-1', 'error-doc')

    await act(async () => checkbox(view.container, 3).click())
    await act(async () => previousButtonForText(view.container, 'common.delete').click())
    expect(view.container.textContent).toContain('Delete 1 documents?')

    await act(async () => Array.from(view.container.querySelectorAll('button')).filter(button => button.textContent === 'common.delete').at(-1)!.click())
    expect(deleteDocument).toHaveBeenCalledWith('kb-1', 'done-doc')
    expect(onRefresh).toHaveBeenCalled()
  })

  test('runs row actions and toggles all documents', async () => {
    const view = await renderTable()
    mounted.push(view.root)

    await act(async () => checkbox(view.container, 0).click())
    expect(Array.from(view.container.querySelectorAll('button[role="checkbox"]')).every(button => button.getAttribute('aria-checked') === 'true')).toBe(true)
    await act(async () => checkbox(view.container, 0).click())
    await act(async () => checkbox(view.container, 1).click())
    await act(async () => checkbox(view.container, 1).click())

    await act(async () => buttonForText(view.container, 'knowledgeBases.configure').click())
    await act(async () => buttonForText(view.container, 'knowledgeBases.quickProcess').click())
    await act(async () => buttonForText(view.container, 'knowledgeBases.viewChunks').click())
    await act(async () => buttonForText(view.container, 'knowledgeBases.reprocess').click())
    await act(async () => buttonForText(view.container, 'knowledgeBases.retryFailedChunks').click())
    await act(async () => buttonForText(view.container, 'knowledgeBases.downloadOriginal').click())
    await act(async () => buttonForText(view.container, 'common.delete').click())
    await act(async () => Array.from(view.container.querySelectorAll('button')).filter(button => button.textContent === 'common.delete').at(-1)!.click())

    expect(push.mock.calls.map(call => call[0])).toEqual([
      '/app/kb/kb-1/documents/pending-doc',
      '/app/kb/kb-1/documents/error-doc',
      '/app/kb/kb-1/documents/preview?docs=error-doc',
    ])
    expect(processDocument).toHaveBeenCalledWith('kb-1', 'pending-doc')
    expect(retryFailedChunks).toHaveBeenCalledWith('kb-1', 'error-doc')
    expect(downloadDocument).toHaveBeenCalledWith('kb-1', 'pending-doc', 'Pending Guide')
  })

  test('auto-refreshes processing documents and shows embedding progress', async () => {
    getDocuments.mockResolvedValueOnce({
      items: [{
        ...makeDocument('processing-doc', 'Processing Guide', 'processing'),
        metadata: { embed_progress: { embedded: 2, failed: 1, total: 4 } },
      }],
      total: 1,
    })
    const view = await renderTable()
    mounted.push(view.root)

    expect(view.container.textContent).toContain('knowledgeBases.embeddingProgress')
    expect(view.container.textContent).toContain('knowledgeBases.failedCount')
    expect(view.container.querySelector('[data-testid="kb-document-status-processing-processing-doc"]')).toBeTruthy()
    expect(intervalCallback).toBeDefined()
    await act(async () => intervalCallback!())
    expect(getDocuments).toHaveBeenCalledTimes(2)
  })

  test('resets search filters and handles empty results', async () => {
    const view = await renderTable()
    mounted.push(view.root)
    await act(async () => buttonForText(view.container, 'knowledgeBases.status').click())
    expect(buttonForText(view.container, 'common.reset')).toBeDefined()
    await act(async () => buttonForText(view.container, 'common.reset').click())
    expect(buttonForText(view.container, 'common.reset')).toBeUndefined()

    getDocuments.mockResolvedValueOnce({ items: [], total: 0 })
    await act(async () => intervalCallback!())
    expect(view.container.textContent).toContain('knowledgeBases.noDocuments')
    expect(view.container.querySelector('[data-testid="kb-documents-table"]')).toBeTruthy()
  })

  test('renders processing without progress and reports failed downloads', async () => {
    getDocuments.mockResolvedValueOnce({
      items: [makeDocument('processing-doc', 'Processing Guide', 'processing')],
      total: 1,
    })
    downloadDocument.mockRejectedValueOnce(new Error('download failed'))
    const view = await renderTable()
    mounted.push(view.root)

    expect(view.container.textContent).toContain('knowledgeBases.statusProcessing')
    expect(view.container.querySelector('[data-testid="kb-document-status-processing-processing-doc"]')).toBeTruthy()
    await act(async () => buttonForText(view.container, 'knowledgeBases.downloadOriginal').click())
    expect(toastError).toHaveBeenCalledWith('knowledgeBases.downloadFailed')
  })

  test('appends pages when the sentinel intersects and stops at the total', async () => {
    const firstPage = Array.from({ length: 10 }, (_, index) => makeDocument(`doc-${index}`, `Doc ${index}`, 'completed'))
    const secondPage = [
      makeDocument('doc-9', 'Doc 9', 'completed'),
      makeDocument('doc-10', 'Doc 10', 'completed'),
      makeDocument('doc-10', 'Doc 10', 'completed'),
      ...Array.from({ length: 3 }, (_, index) => makeDocument(`doc-${11 + index}`, `Doc ${11 + index}`, 'completed')),
    ]
    getDocuments.mockImplementation(async (_id: string, params: { page: number }) => (
      params.page === 1 ? { items: firstPage, total: 14 } : { items: secondPage, total: 14 }
    ))

    const view = await renderTable()
    mounted.push(view.root)
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 1, pageSize: 10 })
    expect(infiniteScrollCalls.at(-1)!.hasMore).toBe(true)

    await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() })
    await act(async () => {})

    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 2, pageSize: 10 })
    expect(view.container.textContent).toContain('Doc 13')
    expect(view.container.querySelectorAll('button[role="checkbox"]')).toHaveLength(15)
    expect(infiniteScrollCalls.at(-1)!.hasMore).toBe(false)

    await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() })
    await act(async () => {})
    expect(getDocuments).toHaveBeenCalledTimes(2)
  })

  test('returns to the first page when the search changes', async () => {
    const firstPage = Array.from({ length: 10 }, (_, index) => makeDocument(`doc-${index}`, `Doc ${index}`, 'completed'))
    const secondPage = Array.from({ length: 5 }, (_, index) => makeDocument(`more-${index}`, `More ${index}`, 'completed'))
    getDocuments.mockImplementation(async (_id: string, params: { page: number }) => (
      params.page === 1 ? { items: firstPage, total: 15 } : { items: secondPage, total: 15 }
    ))

    const view = await renderTable()
    mounted.push(view.root)
    await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() })
    await act(async () => {})
    expect(view.container.textContent).toContain('More 4')

    getDocuments.mockImplementation(async () => ({
      items: [makeDocument('search-hit', 'Guide match', 'completed')],
      total: 1,
    }))
    const input = view.container.querySelector('input')!
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!
      setValue.call(input, 'guide')
      input.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    await act(async () => {})

    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 1, pageSize: 10, search: 'guide' })
    expect(view.container.textContent).toContain('Guide match')
    expect(view.container.textContent).not.toContain('More 4')
  })

  test('refreshes every loaded page without dropping appended documents and stops polling on failure', async () => {
    const pages: Record<number, { items: DocumentFixture[]; total: number }> = {
      1: { items: [makeDocument('p1', 'Page one', 'processing')], total: 3 },
      2: { items: [makeDocument('p2', 'Page two', 'completed'), makeDocument('p3', 'Page three', 'completed')], total: 3 },
    }
    getDocuments.mockImplementation(async (_id: string, params: { page: number }) => pages[params.page])

    const view = await renderTable()
    mounted.push(view.root)
    expect(intervalCallback).toBeDefined()
    await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() })
    await act(async () => {})
    expect(view.container.textContent).toContain('Page three')

    getDocuments.mockClear()
    await act(async () => { intervalCallback!() })
    await act(async () => {})
    expect(getDocuments.mock.calls.map(call => call[1].page)).toEqual([1, 2])
    expect(view.container.textContent).toContain('Page three')

    getDocuments.mockRejectedValueOnce(new Error('poll failed'))
    await act(async () => { intervalCallback!() })
    await act(async () => {})
    expect(view.container.textContent).toContain('Page three')
    expect(view.container.textContent).toContain('common.loadFailed')

    getDocuments.mockImplementation(async (_id: string, params: { page: number }) => pages[params.page])
    getDocuments.mockClear()
    await act(async () => { buttonForText(view.container, 'common.retry').click() })
    await act(async () => {})
    expect(getDocuments.mock.calls.map(call => call[1].page)).toEqual([1, 2])
    expect(view.container.textContent).toContain('Page three')
    expect(view.container.textContent).not.toContain('common.loadFailed')
  })

  test('retries a failed append with the same page instead of reloading the window', async () => {
    getDocuments.mockImplementation(async (_id: string, params: { page: number }) => (
      params.page === 1
        ? { items: [makeDocument('first-doc', 'First doc', 'completed')], total: 2 }
        : { items: [makeDocument('second-doc', 'Second doc', 'completed')], total: 2 }
    ))
    const view = await renderTable()
    mounted.push(view.root)

    getDocuments.mockRejectedValueOnce(new Error('append failed'))
    await act(async () => { infiniteScrollCalls.at(-1)!.onLoadMore() })
    await act(async () => {})
    expect(view.container.textContent).toContain('common.loadFailed')

    await act(async () => { buttonForText(view.container, 'common.retry').click() })
    await act(async () => {})
    expect(getDocuments.mock.calls.map(call => call[1].page)).toEqual([1, 2, 2])
    expect(view.container.textContent).toContain('Second doc')
    expect(view.container.textContent).not.toContain('common.loadFailed')
  })

  test('resets to page 1 when a filtered first load fails and is retried', async () => {
    const view = await renderTable()
    mounted.push(view.root)
    expect(view.container.textContent).toContain('Pending Guide')

    getDocuments.mockRejectedValueOnce(new Error('filter failed'))
    await act(async () => buttonForText(view.container, 'knowledgeBases.status').click())
    await act(async () => {})
    expect(view.container.textContent).toContain('common.loadFailed')
    expect(view.container.textContent).not.toContain('Pending Guide')

    await act(async () => buttonForText(view.container, 'common.retry').click())
    await act(async () => {})
    expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 1, pageSize: 10, status: ['pending'] })
    expect(view.container.textContent).toContain('Pending Guide')
  })

  test('honors missing permissions and exposes URL sources', async () => {
    permissions = false
    const open = mock(() => null)
    Object.defineProperty(window, 'open', { value: open, configurable: true })
    getDocuments.mockResolvedValueOnce({
      items: [{
        ...makeDocument('url-doc', 'Example link', 'completed'),
        doc_type: 'url',
        source_url: 'https://example.test',
        file_path: null,
      }],
      total: 1,
    })

    const view = await renderTable()
    mounted.push(view.root)

    await act(async () => checkbox(view.container, 1).click())
    expect(view.container.textContent).not.toContain('documents selected')
    expect(buttonForText(view.container, 'common.delete')).toBeUndefined()

    await act(async () => buttonForText(view.container, 'knowledgeBases.viewSourceUrl').click())
    expect(open).toHaveBeenCalledWith('https://example.test', '_blank')
  })

  test('keeps the delete dialog open and reports no success when deletion fails', async () => {
    deleteDocument.mockRejectedValueOnce(new Error('delete failed'))
    getDocuments.mockResolvedValueOnce({
      items: [makeDocument('gone-doc', 'Gone Guide', 'completed')],
      total: 1,
    })

    const view = await renderTable()
    mounted.push(view.root)

    await act(async () => buttonForText(view.container, 'common.delete').click())
    await act(async () => Array.from(view.container.querySelectorAll('button')).filter(button => button.textContent === 'common.delete').at(-1)!.click())

    expect(deleteDocument).toHaveBeenCalledWith('kb-1', 'gone-doc')
    expect(onRefresh).not.toHaveBeenCalled()
    expect(toastSuccess).not.toHaveBeenCalled()
  })
})
