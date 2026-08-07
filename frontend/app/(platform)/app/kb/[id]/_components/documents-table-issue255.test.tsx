import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
type Setter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Props = {}) => ({ type, props })
const component = (name: string) => (props: Props) => jsx(name, props)
const stateValues: unknown[] = []
const effects: Array<() => void | (() => void)> = []
let stateIndex = 0
let permissions = true

function resolve(node: unknown): unknown {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const element = node as Node
  return typeof element.type === 'function'
    ? resolve((element.type as (props: Props) => unknown)(element.props))
    : element
}

function walk(node: unknown): Node[] {
  const resolved = resolve(node)
  if (Array.isArray(resolved)) return resolved.flatMap(walk)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const element = resolved as Node
  return [element, ...walk(element.props.children)]
}

function text(node: unknown): string {
  const resolved = resolve(node)
  if (typeof resolved === 'string' || typeof resolved === 'number') return String(resolved)
  if (Array.isArray(resolved)) return resolved.map(text).join('')
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return ''
  return text((resolved as Node).props.children)
}

function find(tree: unknown, value: string) {
  return walk(tree).find((node) => text(node) === value)
}

function render(initialStates: unknown[]) {
  stateIndex = 0
  stateValues.length = 0
  stateValues.push(...initialStates)
  effects.length = 0
  return DocumentsTable({ knowledgeBaseId: 'kb-1', refreshTrigger: 0, onRefresh })
}

const document = (id: string, status: string, overrides: Props = {}) => ({
  id,
  name: `${id}.pdf`,
  doc_type: 'pdf',
  status,
  file_size: 1024,
  chunk_count: 2,
  created_at: '2026-01-02T00:00:00Z',
  ...overrides,
})

const page = (items: Props[]) => ({ items, total: items.length, page: 1, page_size: 10 })
const baseState = (items: Props[]) => [items, false, 1, 10, page(items), '', new Set(), new Set(), new Set(), false, false, null, false]

const push = mock(() => {})
const onRefresh = mock(() => {})
const open = mock(() => {})
const getDocuments = mock(async () => page([]))
const deleteDocument = mock(async () => {})
const processDocument = mock(async () => {})
const retryFailedChunks = mock(async () => {})
const downloadDocument = mock(async () => {})
const success = mock(() => {})
const error = mock(() => {})

function TooltipTrigger(props: Props) {
  const rendered = resolve(props.render) as Node | undefined
  return rendered ? jsx(rendered.type, { ...rendered.props, ...props }) : jsx('tooltip-trigger', props)
}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useState: <T,>(initial: T): [T, Setter<T>] => {
    const index = stateIndex++
    if (stateValues[index] === undefined) stateValues[index] = initial
    return [stateValues[index] as T, (value) => {
      stateValues[index] = typeof value === 'function'
        ? (value as (current: T) => T)(stateValues[index] as T)
        : value
    }]
  },
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { getDocuments, deleteDocument, processDocument, retryFailedChunks, downloadDocument },
}))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => permissions }) }))
mock.module('lucide-react', () => Object.fromEntries([
  'MoreHorizontal', 'Trash2', 'RefreshCw', 'Eye', 'FileText', 'FileType', 'Link',
  'CheckCircle', 'XCircle', 'Loader2', 'Clock', 'ChevronLeft', 'ChevronRight',
  'ChevronsLeft', 'ChevronsRight', 'Search', 'X', 'Settings2', 'Play', 'Download',
  'ExternalLink', 'RotateCcw',
].map((name) => [name, component(name)])))
mock.module('@/components/ui/button', () => ({ Button: component('button') }))
mock.module('@/components/ui/input', () => ({ Input: component('input') }))
mock.module('@/components/ui/badge', () => ({ Badge: component('badge') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: component('checkbox') }))
mock.module('@/components/ui/table', () => ({
  Table: component('table'), TableBody: component('tbody'), TableCell: component('td'),
  TableHead: component('th'), TableHeader: component('thead'), TableRow: component('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: component('select'), SelectContent: component('select-content'), SelectItem: component('option'),
  SelectTrigger: component('select-trigger'), SelectValue: component('select-value'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: component('menu'), DropdownMenuContent: component('menu-content'),
  DropdownMenuItem: component('menu-item'), DropdownMenuSeparator: component('separator'),
  DropdownMenuTrigger: component('menu-trigger'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: component('alert'), AlertDialogAction: component('alert-action'),
  AlertDialogCancel: component('alert-cancel'), AlertDialogContent: component('alert-content'),
  AlertDialogDescription: component('alert-description'), AlertDialogFooter: component('alert-footer'),
  AlertDialogHeader: component('alert-header'), AlertDialogTitle: component('alert-title'),
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: component('tooltip'), TooltipContent: component('tooltip-content'), TooltipTrigger,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: component('facet-filter') }))

const { DocumentsTable } = await import('./documents-table')

beforeEach(() => {
  permissions = true
  for (const fn of [push, onRefresh, open, getDocuments, deleteDocument, processDocument, retryFailedChunks, downloadDocument, success, error]) fn.mockClear()
  getDocuments.mockImplementation(async () => page([]))
  deleteDocument.mockImplementation(async () => {})
  processDocument.mockImplementation(async () => {})
  retryFailedChunks.mockImplementation(async () => {})
  downloadDocument.mockImplementation(async () => {})
  globalThis.window = { open } as unknown as Window & typeof globalThis
})

test('loads, filters, resets, paginates, and changes page size', async () => {
  const docs = [document('pending', 'pending')]
  const tree = render(baseState(docs))
  await effects[0]()
  expect(getDocuments).toHaveBeenCalledWith('kb-1', { page: 1, pageSize: 10 })

  ;(walk(tree).find((node) => node.type === 'input')?.props.onChange as (event: Props) => void)({ target: { value: 'needle' } })
  expect(stateValues[5]).toBe('needle')
  const filters = walk(tree).filter((node) => node.type === 'facet-filter')
  ;(filters[0].props.onSelectionChange as (value: Set<string>) => void)(new Set(['error']))
  ;(filters[1].props.onSelectionChange as (value: Set<string>) => void)(new Set(['pdf']))
  expect(stateValues[6]).toEqual(new Set(['error']))
  expect(stateValues[7]).toEqual(new Set(['pdf']))

  const filtered = render([...baseState(docs).slice(0, 5), 'needle', new Set(['error']), new Set(['pdf']), ...baseState(docs).slice(8)])
  await effects[0]()
  expect(getDocuments).toHaveBeenLastCalledWith('kb-1', { page: 1, pageSize: 10, search: 'needle', status: ['error'], doc_type: ['pdf'] })
  ;(walk(filtered).find((node) => node.type === 'button' && text(node).includes('reset'))?.props.onClick as () => void)()
  expect(stateValues.slice(5, 8)).toEqual(['', new Set(), new Set()])

  ;(walk(tree).find((node) => node.type === 'select')?.props.onValueChange as (value: string) => void)('20')
  expect(stateValues[3]).toBe(20)
  const pagination = walk(tree).filter((node) => node.type === 'button').slice(-4)
  ;(pagination[2].props.onClick as () => void)()
  expect(stateValues[2]).toBe(1)
})

test('renders empty and status variants including processing progress', () => {
  expect(text(render(baseState([])))).toContain('noDocuments')
  const docs = [
    document('done', 'completed', { file_size: 0 }),
    document('work', 'processing', { metadata: { embed_progress: { embedded: 2, failed: 1, total: 4 } } }),
    document('wait', 'pending'),
    document('bad', 'error', { error_message: 'embedding broke', doc_type: 'unknown' }),
  ]
  const output = text(render(baseState(docs)))
  expect(output).toContain('statusCompleted')
  expect(output).toContain('embeddingProgress:2,4')
  expect(output).toContain('failedCount:1')
  expect(output).toContain('statusPending')
  expect(output).toContain('statusFailed')
  expect(output).toContain('embedding broke')
  expect(output).toContain('-')
})

test('selects rows, selects all, clears, and honors permissions', () => {
  const docs = [document('one', 'pending'), document('two', 'completed')]
  const tree = render(baseState(docs))
  const checks = walk(tree).filter((node) => node.type === 'checkbox')
  ;(checks[1].props.onCheckedChange as () => void)()
  expect(stateValues[8]).toEqual(new Set(['one']))

  const selectedTree = render([...baseState(docs).slice(0, 8), new Set(['one']), ...baseState(docs).slice(9)])
  ;(walk(selectedTree).filter((node) => node.type === 'checkbox')[0].props.onCheckedChange as () => void)()
  expect(stateValues[8]).toEqual(new Set(['one', 'two']))
  ;(find(selectedTree, '1 documentsSelected')?.props.children, walk(selectedTree).find((node) => node.type === 'button' && text(node) === '')?.props.onClick as (() => void))?.()

  permissions = false
  const restricted = render([...baseState(docs).slice(0, 8), new Set(['one']), ...baseState(docs).slice(9)])
  expect(text(restricted)).not.toContain('documentsSelected')
  expect(text(restricted)).not.toContain('quickProcess')
  expect(walk(restricted).filter((node) => node.type === 'menu-item').map(text)).not.toContain('delete')
})

test('navigates configure, view, and reprocess branches and opens URL sources', () => {
  const docs = [
    document('pending', 'pending'),
    document('done', 'completed'),
    document('url', 'completed', { doc_type: 'url', source_url: 'https://example.test', file_path: null }),
  ]
  const tree = render(baseState(docs))
  ;(find(tree, 'configure')?.props.onClick as () => void)()
  ;(walk(tree).filter((node) => text(node) === 'viewChunks')[0].props.onClick as () => void)()
  ;(find(tree, 'reprocess')?.props.onClick as () => void)()
  ;(find(tree, 'viewSourceUrl')?.props.onClick as () => void)()
  expect(push.mock.calls).toEqual([
    ['/app/kb/kb-1/documents/pending'],
    ['/app/kb/kb-1/documents/done'],
    ['/app/kb/kb-1/documents/preview?docs=done'],
  ])
  expect(open).toHaveBeenCalledWith('https://example.test', '_blank')
})

test('handles quick process, retry, and download success and errors', async () => {
  const docs = [
    document('pending', 'pending', { file_path: '/pending.pdf' }),
    document('bad', 'error', { file_path: '/bad.pdf' }),
  ]
  let tree = render(baseState(docs))
  await (find(tree, 'quickProcess')?.props.onClick as () => Promise<void>)()
  await (find(tree, 'retryFailedChunks')?.props.onClick as () => Promise<void>)()
  await (find(tree, 'downloadOriginal')?.props.onClick as () => Promise<void>)()
  expect(processDocument).toHaveBeenCalledWith('kb-1', 'pending')
  expect(retryFailedChunks).toHaveBeenCalledWith('kb-1', 'bad')
  expect(downloadDocument).toHaveBeenCalledWith('kb-1', 'pending', 'pending.pdf')
  expect(success.mock.calls.map((call) => call[0])).toEqual(expect.arrayContaining(['processStartedSingle', 'retryStarted', 'downloadStarted']))

  processDocument.mockImplementationOnce(async () => { throw new Error('process') })
  retryFailedChunks.mockImplementationOnce(async () => { throw new Error('retry') })
  downloadDocument.mockImplementationOnce(async () => { throw new Error('download') })
  tree = render(baseState(docs))
  await (find(tree, 'quickProcess')?.props.onClick as () => Promise<void>)()
  await (find(tree, 'retryFailedChunks')?.props.onClick as () => Promise<void>)()
  await (find(tree, 'downloadOriginal')?.props.onClick as () => Promise<void>)()
  expect(error).toHaveBeenCalledWith('downloadFailed')
})

test('confirms and rejects single deletion without false success', async () => {
  const doc = document('gone', 'completed')
  const tree = render([...baseState([doc]).slice(0, 11), doc, false])
  const deleteActions = walk(tree).filter((node) => node.type === 'alert-action')
  await (deleteActions[0].props.onClick as () => Promise<void>)()
  expect(deleteDocument).toHaveBeenCalledWith('kb-1', 'gone')
  expect(success).toHaveBeenCalledWith('documentDeleted')
  expect(onRefresh).toHaveBeenCalledTimes(1)

  deleteDocument.mockImplementationOnce(async () => { throw new Error('delete') })
  await (deleteActions[0].props.onClick as () => Promise<void>)()
  expect(onRefresh).toHaveBeenCalledTimes(1)
})

test('bulk processes and retries only eligible selected documents', async () => {
  const docs = [document('p1', 'pending'), document('p2', 'pending'), document('e1', 'error'), document('done', 'completed')]
  const selected = new Set(docs.map((doc) => doc.id as string))
  const tree = render([...baseState(docs).slice(0, 8), selected, ...baseState(docs).slice(9)])
  const clickable = walk(tree).filter((node) => node.props.onClick && (text(node) === '' || node.type === 'button'))
  const bulkProcess = clickable.find((node) => node.props.className?.toString().includes('text-primary'))
  const bulkRetry = clickable.find((node) => node.props.className?.toString().includes('text-destructive') && node.props.disabled !== undefined)
  await (bulkProcess?.props.onClick as () => Promise<void>)()
  expect(processDocument.mock.calls).toEqual([['kb-1', 'p1'], ['kb-1', 'p2']])
  expect(success).toHaveBeenCalledWith('processStarted:2')

  render([...baseState(docs).slice(0, 8), selected, ...baseState(docs).slice(9)])
  await (bulkRetry?.props.onClick as () => Promise<void>)()
  expect(retryFailedChunks).toHaveBeenCalledWith('kb-1', 'e1')
  expect(success).toHaveBeenCalledWith('retryStarted')
  expect(stateValues[12]).toBe(false)
})

test('bulk deletes selected documents and keeps dialog state on failure', async () => {
  const docs = [document('one', 'completed'), document('two', 'error')]
  const selected = new Set(['one', 'two'])
  let tree = render([...baseState(docs).slice(0, 8), selected, false, true, null, false])
  let action = walk(tree).filter((node) => node.type === 'alert-action')[1]
  await (action.props.onClick as () => Promise<void>)()
  expect(deleteDocument.mock.calls).toEqual([['kb-1', 'one'], ['kb-1', 'two']])
  expect(success).toHaveBeenCalledWith('bulkDocumentsDeleted:2')
  expect(stateValues[8]).toEqual(new Set())
  expect(stateValues[10]).toBe(false)
  expect(onRefresh).toHaveBeenCalled()

  deleteDocument.mockImplementationOnce(async () => { throw new Error('bulk') })
  tree = render([...baseState(docs).slice(0, 8), selected, false, true, null, false])
  action = walk(tree).filter((node) => node.type === 'alert-action')[1]
  await (action.props.onClick as () => Promise<void>)()
  expect(stateValues[10]).toBe(true)
})
