import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'

let stateSlots: unknown[] = []
let stateIndex = 0

mock.module('react', () => ({
  ...React,
  useCallback: (callback: unknown) => callback,
  useEffect: () => undefined,
  useState: (initial: unknown) => {
    const current = stateIndex++
    if (current >= stateSlots.length) stateSlots[current] = typeof initial === 'function' ? initial() : initial
    return [stateSlots[current], (next: unknown) => { stateSlots[current] = typeof next === 'function' ? next(stateSlots[current]) : next }]
  },
}))

const apiCalls: Array<{ method: string; args: unknown[] }> = []
const routerPush = mock(() => {})
const toastSuccess = mock(() => {})
const toastError = mock(() => {})
let permissions = new Set<string>()

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
}))

mock.module('next/navigation', () => ({
  useRouter: () => ({ push: routerPush }),
}))

mock.module('sonner', () => ({
  toast: { success: toastSuccess, error: toastError },
}))

mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({
    canPerform: (permission: string) => permissions.has(permission),
    loading: false,
  }),
}))

mock.module('@/lib/api', () => ({
  knowledgeBasesApi: {
    getDocuments: (...args: unknown[]) => {
      apiCalls.push({ method: 'getDocuments', args })
      return Promise.resolve({ items: [], total: 0 })
    },
    deleteDocument: (...args: unknown[]) => {
      apiCalls.push({ method: 'deleteDocument', args })
      return Promise.resolve()
    },
    processDocument: (...args: unknown[]) => {
      apiCalls.push({ method: 'processDocument', args })
      return Promise.resolve({})
    },
    retryFailedChunks: (...args: unknown[]) => {
      apiCalls.push({ method: 'retryFailedChunks', args })
      return Promise.resolve({})
    },
    downloadDocument: (...args: unknown[]) => {
      apiCalls.push({ method: 'downloadDocument', args })
      return Promise.resolve()
    },
  },
}))

type NodeLike = {
  type: string | React.JSXElementConstructor<unknown>
  props?: Record<string, unknown> & { children?: React.ReactNode }
}

type DocumentsTableProps = {
  knowledgeBaseId: string
  refreshTrigger: number
  onRefresh: () => void
}

const completedDoc = {
  id: 'doc-completed',
  knowledge_base_id: 'kb-1',
  name: 'done.pdf',
  file_path: '/files/done.pdf',
  file_size: 2048,
  source_url: null,
  doc_type: 'pdf',
  status: 'completed',
  chunk_count: 4,
  error_message: null,
  metadata: null,
  created_at: '2026-01-02T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
}

const pendingDoc = { ...completedDoc, id: 'doc-pending', name: 'todo.txt', file_path: null, file_size: 0, doc_type: 'txt', status: 'pending', chunk_count: 0 }
const errorDoc = { ...completedDoc, id: 'doc-error', name: 'bad.url', file_path: null, source_url: 'https://example.test/bad', doc_type: 'url', status: 'error', error_message: 'embed failed' }
const processingDoc = { ...completedDoc, id: 'doc-processing', name: 'processing.json', doc_type: 'json', status: 'processing', metadata: { embed_progress: { embedded: 2, failed: 1, total: 5 } } }

function textOf(value: React.ReactNode): string {
  if (value == null || typeof value === 'boolean') return ''
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(textOf).join('')
  if (React.isValidElement(value)) {
    const props = (value as NodeLike).props
    return textOf([props?.children, props?.render])
  }
  return ''
}

function findAll(value: React.ReactNode, predicate: (node: NodeLike) => boolean): NodeLike[] {
  if (!React.isValidElement(value)) {
    return Array.isArray(value) ? value.flatMap((child) => findAll(child, predicate)) : []
  }

  const node = value as NodeLike
  return [
    ...(predicate(node) ? [node] : []),
    ...findAll([node.props?.children, node.props?.render], predicate),
  ]
}

function buttons(tree: React.ReactNode) {
  return findAll(tree, (node) => node.type === 'button')
}

function menuItems(tree: React.ReactNode) {
  return findAll(tree, (node) => typeof node.props?.onClick === 'function' && textOf(node).match(/knowledgeBases\.|common\./) !== null)
}

function checkboxes(tree: React.ReactNode) {
  return findAll(tree, (node) => node.props?.role === 'checkbox' || typeof node.props?.onCheckedChange === 'function')
}


function getDocumentsTable() {
  return import.meta.require('./documents-table').DocumentsTable as (props: DocumentsTableProps) => React.ReactNode
}

function renderWithState(rows: Array<typeof completedDoc>, options: { loading?: boolean; pageTotal?: number } = {}) {
  const states: unknown[] = [
    rows,
    options.loading ?? false,
    1,
    10,
    { items: rows, total: options.pageTotal ?? rows.length },
    '',
    new Set<string>(),
    new Set<string>(),
    new Set<string>(),
    false,
    false,
    null,
    false,
  ]
  stateSlots = states
  stateIndex = 0
  return getDocumentsTable()({ knowledgeBaseId: 'kb-1', refreshTrigger: 0, onRefresh: mock(() => {}) })
}

beforeEach(() => {
  apiCalls.length = 0
  permissions = new Set(['kb:update', 'kb:delete'])
  routerPush.mockClear()
  toastSuccess.mockClear()
  toastError.mockClear()
  mock.restore()
})

afterEach(() => {
  mock.restore()
})

describe('platform DocumentsTable behavior', () => {
  test('shows loading, empty, error, and processing states', () => {
    expect(textOf(renderWithState([], { loading: true }))).toContain('common.loading')
    expect(textOf(renderWithState([]))).toContain('knowledgeBases.noDocuments')

    const text = textOf(renderWithState([errorDoc, processingDoc]))
    expect(text).toContain('bad.url')
    expect(text).toContain('embed failed')
    expect(text).toContain('knowledgeBases.statusFailed')
    expect(text).toContain('knowledgeBases.embeddingProgress:{"embedded":2,"total":5}')
    expect(text).toContain('knowledgeBases.failedCount:{"count":1}')
  })

  test('keeps platform API and routes separate from dashboard table', async () => {
    const tree = renderWithState([pendingDoc, completedDoc, errorDoc])
    const items = menuItems(tree)

    items.find((item) => textOf(item).includes('knowledgeBases.configure') && typeof item.props?.onClick === 'function')?.props?.onClick?.({})
    expect(routerPush).toHaveBeenCalledWith('/app/kb/kb-1/documents/doc-pending')

    items.find((item) => textOf(item).includes('knowledgeBases.reprocess') && typeof item.props?.onClick === 'function')?.props?.onClick?.({})
    expect(routerPush).toHaveBeenCalledWith('/app/kb/kb-1/documents/preview?docs=doc-completed')

    await items.find((item) => textOf(item).includes('knowledgeBases.quickProcess') && typeof item.props?.onClick === 'function')?.props?.onClick?.({})
    await items.find((item) => textOf(item).includes('knowledgeBases.retryFailedChunks') && typeof item.props?.onClick === 'function')?.props?.onClick?.({})
    await items.find((item) => textOf(item).includes('knowledgeBases.downloadOriginal') && typeof item.props?.onClick === 'function')?.props?.onClick?.({})

    expect(apiCalls).toContainEqual({ method: 'processDocument', args: ['kb-1', 'doc-pending'] })
    expect(apiCalls).toContainEqual({ method: 'retryFailedChunks', args: ['kb-1', 'doc-error'] })
    expect(apiCalls).toContainEqual({ method: 'downloadDocument', args: ['kb-1', 'doc-completed', 'done.pdf'] })
  })

  test('hides update and delete actions without permissions but leaves safe read/source actions', () => {
    permissions = new Set()

    const text = textOf(renderWithState([pendingDoc, completedDoc, errorDoc]))

    expect(text).toContain('knowledgeBases.viewChunks')
    expect(text).toContain('knowledgeBases.viewSourceUrl')
    expect(text).not.toContain('knowledgeBases.configure')
    expect(text).not.toContain('knowledgeBases.quickProcess')
    expect(text).not.toContain('knowledgeBases.reprocess')
    expect(text).not.toContain('knowledgeBases.retryFailedChunks')
  })

  test('bulk toolbar honors selected documents and permission boundaries', async () => {
    const selected = new Set(['doc-pending', 'doc-error'])
    const states: unknown[] = [
      [pendingDoc, errorDoc], false, 1, 10, { items: [pendingDoc, errorDoc], total: 2 }, '', new Set<string>(), new Set<string>(), selected, false, false, null, false,
    ]
    stateSlots = states
    stateIndex = 0

    const tree = getDocumentsTable()({ knowledgeBaseId: 'kb-1', refreshTrigger: 0, onRefresh: mock(() => {}) })
    expect(textOf(tree)).toContain('2 knowledgeBases.documentsSelected')
    expect(textOf(tree)).toContain('knowledgeBases.bulkQuickProcess')
    expect(textOf(tree)).toContain('knowledgeBases.bulkRetryFailedChunks')

    permissions = new Set()
    const selectedWithoutPermission = renderWithState([pendingDoc, errorDoc])
    expect(textOf(selectedWithoutPermission)).not.toContain('knowledgeBases.documentsSelected')
  })

  test('selection and pagination controls update local table state only', () => {
    const tree = renderWithState([completedDoc], { pageTotal: 25 })
    const [selectAll, selectRow] = checkboxes(tree)

    selectAll.props?.onCheckedChange?.(true)
    selectRow.props?.onCheckedChange?.(true)

    expect(apiCalls).toEqual([])
    expect(textOf(tree)).toContain('knowledgeBases.pageInfo:{"page":1,"total":3}')
    expect(buttons(tree).filter((button) => button.props?.disabled === true).length).toBe(0)
  })
})
