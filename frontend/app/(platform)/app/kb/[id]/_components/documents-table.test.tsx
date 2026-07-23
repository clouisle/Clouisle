import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { DocumentsTable } from './documents-table'

const window = new Window()
const documentNode = window.document
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = documentNode as unknown as Document
globalThis.HTMLElement = window.HTMLElement as unknown as typeof HTMLElement
globalThis.Element = window.Element as unknown as typeof Element
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock(() => {})
const toastSuccess = mock(() => {})
const onRefresh = mock(() => {})
const getDocuments = mock(async () => ({
  items: [
    makeDocument('pending-doc', 'Pending Guide', 'pending'),
    makeDocument('error-doc', 'Broken Guide', 'error'),
    makeDocument('done-doc', 'Done Guide', 'completed'),
  ],
  total: 3,
}))
const processDocument = mock(async () => undefined)
const retryFailedChunks = mock(async () => undefined)
const deleteDocument = mock(async () => undefined)

mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) => {
    if (key === 'documentsSelected') return 'documents selected'
    if (key === 'confirmBulkDocumentsDelete') return `Delete ${values?.count} documents?`
    if (key === 'bulkDocumentsDeleted') return `Deleted ${values?.count} documents`
    return `${namespace}.${key}`
  },
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: mock(() => {}) } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { getDocuments, processDocument, retryFailedChunks, deleteDocument },
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: () => void }) => <button role="checkbox" aria-checked={checked} onClick={onCheckedChange} />,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title }: { title: string }) => <button>{title}</button>,
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
  TooltipTrigger: ({ children, render, onClick }: { children?: React.ReactNode; render?: React.ReactNode; onClick?: () => void }) => render ? React.cloneElement(render as React.ReactElement<{ onClick?: () => void }>, { onClick }) : <button onClick={onClick}>{children}</button>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

function makeDocument(id: string, name: string, status: string) {
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

let mounted: Root[] = []

beforeEach(() => {
  push.mockClear()
  toastSuccess.mockClear()
  getDocuments.mockClear()
  processDocument.mockClear()
  retryFailedChunks.mockClear()
  deleteDocument.mockClear()
  onRefresh.mockClear()
})

afterEach(() => {
  for (const root of mounted) act(() => root.unmount())
  mounted = []
  documentNode.body.replaceChildren()
})

describe('platform DocumentsTable', () => {
  test('renders documents and bulk actions for selected rows', async () => {
    const view = await renderTable()
    mounted.push(view.root)

    expect(view.container.textContent).toContain('Pending Guide')
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
})
