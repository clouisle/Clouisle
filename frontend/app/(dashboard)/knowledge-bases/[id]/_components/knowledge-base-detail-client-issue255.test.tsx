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

const push = mock(() => {})
const router = { push }
const getKnowledgeBase = mock(async () => knowledgeBase)
const getStats = mock(async () => stats)

mock.module('next/navigation', () => ({ useRouter: () => router }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/lib/api', () => ({ adminKnowledgeBasesApi: { getKnowledgeBase, getStats } }))
const icon = (name: string) => function MockIcon({ className }: { className?: string }) {
  return <span data-icon={name} className={className} />
}
mock.module('lucide-react', () => ({
  ArrowLeft: icon('ArrowLeft'),
  Upload: icon('Upload'),
  Link: icon('Link'),
  Settings: icon('Settings'),
  FileText: icon('FileText'),
  Layers: icon('Layers'),
  HardDrive: icon('HardDrive'),
  Clock: icon('Clock'),
  CheckCircle: icon('CheckCircle'),
  XCircle: icon('XCircle'),
  Loader2: icon('Loader2'),
  Search: icon('Search'),
  Cpu: icon('Cpu'),
  ArrowUpDown: icon('ArrowUpDown'),
}))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
mock.module('@/components/ui/button', () => ({ Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('./documents-table', () => ({
  DocumentsTable: ({ refreshTrigger, onRefresh }: { refreshTrigger: number; onRefresh: () => void }) => (
    <button data-testid="documents" data-refresh={refreshTrigger} onClick={onRefresh}>documents table</button>
  ),
}))
mock.module('./upload-document-dialog', () => ({
  UploadDocumentDialog: ({ open, onOpenChange, onSuccess }: { open: boolean; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => (
    <div data-testid="upload-dialog" data-open={open}>
      <button onClick={() => onOpenChange(false)}>close upload</button>
      <button onClick={onSuccess}>upload success</button>
    </div>
  ),
}))
mock.module('./import-url-dialog', () => ({
  ImportUrlDialog: ({ open, onOpenChange, onSuccess }: { open: boolean; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => (
    <div data-testid="import-dialog" data-open={open}>
      <button onClick={() => onOpenChange(false)}>close import</button>
      <button onClick={onSuccess}>import success</button>
    </div>
  ),
}))
mock.module('../../_components/knowledge-base-dialog', () => ({
  KnowledgeBaseDialog: ({ open, onOpenChange, onSuccess }: { open: boolean; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => (
    <div data-testid="settings-dialog" data-open={open}>
      <button onClick={() => onOpenChange(false)}>close settings</button>
      <button onClick={onSuccess}>settings success</button>
    </div>
  ),
}))

const { KnowledgeBaseDetailClient } = await import('./knowledge-base-detail-client')

const knowledgeBase = {
  id: 'kb-1',
  team: { id: 'team-1', name: 'Platform' },
  name: 'Product Docs',
  description: 'Internal documentation',
  icon: null,
  embedding_model_id: 'embedding-1',
  embedding_model: { id: 'embedding-1', name: 'Embed Pro', provider: 'Acme', model_id: 'embed-pro' },
  rerank_model_id: 'rerank-1',
  rerank_model: { id: 'rerank-1', name: 'Rerank Pro', provider: 'Acme', model_id: 'rerank-pro' },
  settings: null,
  status: 'active',
  document_count: 2,
  total_chunks: 12,
  total_tokens: 3456,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const stats = {
  id: 'kb-1',
  name: 'Product Docs',
  document_count: 2,
  total_chunks: 12,
  total_tokens: 3456,
  documents_by_status: { completed: 1, processing: 1, pending: 2, error: 0 },
  documents_by_type: { pdf: 2 },
}

let mounted: Root[] = []

async function renderDetail() {
  const container = documentNode.createElement('div')
  documentNode.body.appendChild(container)
  const root = createRoot(container)
  mounted.push(root)
  await act(async () => root.render(<KnowledgeBaseDetailClient knowledgeBaseId="kb-1" />))
  await act(async () => {})
  return container
}

function button(container: HTMLElement, text: string) {
  return Array.from(container.querySelectorAll('button')).find(node => node.textContent === text)!
}

beforeEach(() => {
  push.mockClear()
  getKnowledgeBase.mockReset()
  getStats.mockReset()
  getKnowledgeBase.mockResolvedValue(knowledgeBase)
  getStats.mockResolvedValue(stats)
})

afterEach(() => {
  for (const root of mounted) act(() => root.unmount())
  mounted = []
  documentNode.body.replaceChildren()
})

describe('KnowledgeBaseDetailClient', () => {
  test('shows loading state while details load and redirects when loading fails', async () => {
    let rejectLoad!: (error: Error) => void
    getKnowledgeBase.mockImplementation(() => new Promise((_resolve, reject) => { rejectLoad = reject }))
    const container = documentNode.createElement('div')
    documentNode.body.appendChild(container)
    const root = createRoot(container)
    mounted.push(root)

    act(() => root.render(<KnowledgeBaseDetailClient knowledgeBaseId="kb-1" />))
    expect(container.querySelector('[data-icon="Loader2"]')).not.toBeNull()

    await act(async () => rejectLoad(new Error('unavailable')))
    expect(push).toHaveBeenCalledWith('/knowledge-bases')
    expect(container.querySelector('[data-icon="Loader2"]')).not.toBeNull()
  })

  test('loads details and handles navigation and dialog controls', async () => {
    const container = await renderDetail()

    expect(getKnowledgeBase).toHaveBeenCalledWith('kb-1')
    expect(getStats).toHaveBeenCalledWith('kb-1')
    expect(container.textContent).toContain('Product Docs')
    expect(container.textContent).toContain('Embed Pro')
    expect(container.textContent).toContain('Rerank Pro')

    await act(async () => button(container, 'searchTest').click())
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1/search')
    await act(async () => container.querySelector<HTMLButtonElement>('[data-icon="ArrowLeft"]')!.closest('button')!.click())
    expect(push).toHaveBeenCalledWith('/knowledge-bases')

    await act(async () => button(container, 'importUrl').click())
    expect(container.querySelector('[data-testid="import-dialog"]')?.getAttribute('data-open')).toBe('true')
    await act(async () => button(container, 'close import').click())
    expect(container.querySelector('[data-testid="import-dialog"]')?.getAttribute('data-open')).toBe('false')

    await act(async () => button(container, 'uploadDocument').click())
    expect(container.querySelector('[data-testid="upload-dialog"]')?.getAttribute('data-open')).toBe('true')
    await act(async () => button(container, 'close upload').click())

    await act(async () => container.querySelector<HTMLButtonElement>('[data-icon="Settings"]')!.closest('button')!.click())
    expect(container.querySelector('[data-testid="settings-dialog"]')?.getAttribute('data-open')).toBe('true')
    await act(async () => button(container, 'close settings').click())
  })

  test('refreshes documents and statistics after document actions', async () => {
    const container = await renderDetail()
    expect(container.querySelector('[data-testid="documents"]')?.getAttribute('data-refresh')).toBe('0')

    await act(async () => button(container, 'documents table').click())
    expect(container.querySelector('[data-testid="documents"]')?.getAttribute('data-refresh')).toBe('1')
    expect(getKnowledgeBase).toHaveBeenCalledTimes(2)
    expect(getStats).toHaveBeenCalledTimes(2)

    await act(async () => button(container, 'upload success').click())
    await act(async () => button(container, 'import success').click())
    expect(container.querySelector('[data-testid="documents"]')?.getAttribute('data-refresh')).toBe('3')
    expect(getKnowledgeBase).toHaveBeenCalledTimes(4)
    expect(getStats).toHaveBeenCalledTimes(4)
  })

  test('reloads the knowledge base after settings are saved', async () => {
    const container = await renderDetail()

    await act(async () => button(container, 'settings success').click())

    expect(getKnowledgeBase).toHaveBeenCalledTimes(2)
    expect(getStats).toHaveBeenCalledTimes(2)
    expect(container.textContent).toContain('Product Docs')
  })
})
