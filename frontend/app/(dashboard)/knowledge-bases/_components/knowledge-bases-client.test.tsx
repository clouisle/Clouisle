import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getKnowledgeBases = mock(() => Promise.resolve({ items: [], total: 0 }))
const updateKnowledgeBase = mock(() => Promise.resolve({}))
const deleteKnowledgeBase = mock(() => Promise.resolve({}))
const getTeams = mock(() => Promise.resolve({ items: [] }))
const exportPackage = mock(() => Promise.resolve({ blob: new Blob(), filename: 'kb.zip' }))
const downloadBlob = mock(() => {})
const toastSuccess = mock(() => {})
const push = mock(() => {})
let permissions = new Set<string>()

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  adminKnowledgeBasesApi: { getKnowledgeBases, updateKnowledgeBase, deleteKnowledgeBase },
  adminPackagesApi: { export: exportPackage },
  downloadBlob,
}))
mock.module('@/lib/api/admin', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ permission, children }: React.PropsWithChildren<{ permission: string }>) =>
    permissions.has(permission) ? children : null,
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Plus', 'Search', 'MoreHorizontal', 'Pencil', 'Trash2', 'ChevronLeft', 'ChevronRight',
  'ChevronsLeft', 'ChevronsRight', 'X', 'Database', 'FileText', 'Power', 'PowerOff',
  'Upload', 'Download',
].map((name) => [name, () => null])))

function element(tag: keyof React.JSX.IntrinsicElements) {
  return function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
}

mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) =>
    <input type="checkbox" checked={checked} onChange={onCheckedChange} readOnly />,
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: element('option'), SelectTrigger: element('span'), SelectValue: element('span'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DropdownMenuItem: element('button'), DropdownMenuSeparator: element('hr'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: element('span'),
  TooltipTrigger: ({ render, onClick }: { render: React.ReactElement; onClick: () => void }) =>
    React.cloneElement(render, { onClick } as Record<string, unknown>),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div>{children}</div> : null,
  AlertDialogAction: element('button'), AlertDialogCancel: element('button'), AlertDialogContent: element('section'),
  AlertDialogDescription: element('p'), AlertDialogFooter: element('footer'), AlertDialogHeader: element('header'),
  AlertDialogTitle: element('h2'),
}))
mock.module('./knowledge-base-dialog', () => ({ KnowledgeBaseDialog: element('aside') }))
mock.module('./delete-knowledge-base-dialog', () => ({ DeleteKnowledgeBaseDialog: element('aside') }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: element('aside') }))

const { KnowledgeBasesClient } = await import('./knowledge-bases-client')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer | undefined
const knowledgeBase = {
  id: 'kb-1', name: 'Handbook', description: 'Company docs', status: 'active',
  team: { name: 'Platform' }, document_count: 3, total_chunks: 1234, created_at: '2026-01-02',
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

async function renderClient() {
  await act(async () => { renderer = create(<KnowledgeBasesClient />) })
  return renderer!
}

function textNode(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textNode).join(' ')
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return textNode(node.props.children)
  if (node && typeof node === 'object' && 'children' in node) return textNode((node as { children?: unknown }).children)
  if (node && typeof node === 'object' && 'props' in node) return textNode((node as { props?: { children?: unknown } }).props?.children)
  return ''
}

function text(): string {
  return textNode(renderer!.toJSON())
}

function button(label: string) {
  return renderer!.root.findAllByType('button').find((node) => node.children.includes(label) || textNode(node).includes(label))!
}

function textNode(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textNode).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return textNode(node.props.children)
  if (node && typeof node === 'object' && 'children' in node) return textNode((node as { children?: unknown }).children)
  if (node && typeof node === 'object' && 'props' in node) return textNode((node as { props?: { children?: unknown } }).props?.children)
  return ''
}

beforeEach(() => {
  permissions = new Set()
  getKnowledgeBases.mockReset()
  getKnowledgeBases.mockResolvedValue({ items: [], total: 0 })
  updateKnowledgeBase.mockReset()
  updateKnowledgeBase.mockResolvedValue({})
  deleteKnowledgeBase.mockReset()
  getTeams.mockReset()
  getTeams.mockResolvedValue({ items: [] })
  exportPackage.mockReset()
  exportPackage.mockResolvedValue({ blob: new Blob(), filename: 'kb.zip' })
  downloadBlob.mockReset()
  toastSuccess.mockReset()
  push.mockReset()
})

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
})

describe('KnowledgeBasesClient', () => {
  test('shows loading, then renders API data and pagination', async () => {
    const pending = deferred<{ items: typeof knowledgeBase[]; total: number }>()
    getKnowledgeBases.mockReturnValueOnce(pending.promise)

    await renderClient()
    expect(text()).toContain('loading')
    expect(getKnowledgeBases).toHaveBeenCalledWith({ page: 1, pageSize: 10 })

    await act(async () => pending.resolve({ items: [knowledgeBase], total: 21 }))
    expect(text()).toContain('Handbook')
    expect(text()).toContain('Company docs')
    expect(text()).toContain('1,234')
    expect(text()).toContain('pageInfo')
  })

  test('finishes loading after list and team errors and shows the empty boundary', async () => {
    getKnowledgeBases.mockRejectedValueOnce(new Error('offline'))
    getTeams.mockRejectedValueOnce(new Error('offline'))

    await renderClient()

    expect(text()).not.toContain('loading')
    expect(text()).toContain('noKbs')
    expect(text()).toContain('createKbHint')
  })

  test('hides guarded actions without permission and navigates from a row', async () => {
    getKnowledgeBases.mockResolvedValueOnce({ items: [knowledgeBase], total: 1 })
    await renderClient()

    expect(text()).not.toContain('createKb')
    expect(text()).not.toContain('edit')
    expect(renderer!.root.findAllByType('tr').at(-1)!.findAllByType('button')).toHaveLength(0)

    act(() => renderer!.root.findAllByType('tr').at(-1)!.props.onClick())
    expect(push).toHaveBeenCalledWith('/knowledge-bases/kb-1')
  })

  test('exports and toggles status when permitted', async () => {
    permissions = new Set(['admin:knowledge-base:read', 'admin:knowledge-base:update'])
    getKnowledgeBases.mockResolvedValue({ items: [knowledgeBase], total: 1 })
    await renderClient()

    await act(async () => button('export').props.onClick())
    expect(exportPackage).toHaveBeenCalledWith('knowledge_base', 'kb-1')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'kb.zip')

    await act(async () => button('deactivate').props.onClick())
    expect(updateKnowledgeBase).toHaveBeenCalledWith('kb-1', { status: 'archived' })
    expect(toastSuccess).toHaveBeenCalledWith('kbDeactivated')
    expect(getKnowledgeBases.mock.calls.length).toBeGreaterThan(1)
  })

  test('filters, paginates, creates, imports, edits, and bulk exports', async () => {
    permissions = new Set(['admin:knowledge-base:create', 'admin:knowledge-base:read', 'admin:knowledge-base:update'])
    getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Platform' }] })
    getKnowledgeBases.mockResolvedValue({ items: [knowledgeBase], total: 25 })
    await renderClient()

    act(() => button('edit').props.onClick())
    expect(renderer!.root.findAllByType('aside').find((node) => node.props.knowledgeBase?.id === 'kb-1')?.props.open).toBe(true)

    act(() => button('createKb').props.onClick())
    expect(renderer!.root.findAllByType('aside').find((node) => node.props.knowledgeBase === null)?.props.open).toBe(true)

    act(() => button('import').props.onClick())
    expect(renderer!.root.findAllByType('aside').find((node) => node.props.expectedResourceType === 'knowledge_base')?.props.open).toBe(true)

    const search = renderer!.root.findByProps({ placeholder: 'filterKbs' })
    act(() => search.props.onChange({ target: { value: 'handbook' } }))
    expect(text()).toContain('reset')
    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'handbook' }))

    const status = renderer!.root.findByProps({ title: 'status' })
    act(() => status.props.onSelectionChange(new Set(['archived'])))
    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ status: ['archived'] }))

    const pageSizeSelect = renderer!.root.findAllByType('select').find((node) => node.props.value === '10')
    act(() => pageSizeSelect!.props.onValueChange('20'))
    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 20 }))

    act(() => button('reset').props.onClick())
    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 20 }))

    act(() => renderer!.root.findAllByType('input').find((input) => input.props.type === 'checkbox')!.props.onChange())
    await act(async () => renderer!.root.findAllByType('button').filter((node) => node.props.onClick && !node.props.className?.includes('text-destructive') && node.props.className?.includes('h-8 w-8')).at(-1)!.props.onClick())
    expect(exportPackage).toHaveBeenCalledWith('knowledge_base', 'kb-1')
  })

  test('bulk deletes selected knowledge bases and reloads after dialog success', async () => {
    permissions = new Set(['admin:knowledge-base:read', 'admin:knowledge-base:delete'])
    getKnowledgeBases.mockResolvedValue({ items: [knowledgeBase, { ...knowledgeBase, id: 'kb-2', name: 'Archive' }], total: 2 })
    await renderClient()

    act(() => renderer!.root.findAllByType('input').find((input) => input.props.type === 'checkbox')!.props.onChange())
    await act(async () => renderer!.root.findAllByType('button').find((node) => node.props.className?.includes('text-destructive'))!.props.onClick())
    await act(async () => renderer!.root.findAllByType('button').filter((node) => textNode(node).includes('delete')).at(-1)!.props.onClick())

    expect(deleteKnowledgeBase).toHaveBeenCalledWith('kb-1')
    expect(deleteKnowledgeBase).toHaveBeenCalledWith('kb-2')
    expect(toastSuccess).toHaveBeenCalledWith('bulkDeleted')

    act(() => renderer!.root.findAllByType('aside').find((node) => node.props.knowledgeBase === null)?.props.onSuccess())
    expect(getKnowledgeBases).toHaveBeenCalled()
  })
  test('clears selected rows after a successful edit-dialog save and reloads the list', async () => {
    permissions = new Set(['admin:knowledge-base:read', 'admin:knowledge-base:update'])
    getKnowledgeBases.mockResolvedValue({ items: [knowledgeBase], total: 1 })
    await renderClient()

    act(() => renderer!.root.findAllByType('input').find((input) => input.props.type === 'checkbox')!.props.onChange())
    expect(text()).toContain('1 kbsSelected')

    act(() => button('edit').props.onClick())
    const editDialog = renderer!.root.findAllByType('aside').find((node) => node.props.knowledgeBase?.id === 'kb-1')
    expect(editDialog?.props.open).toBe(true)
    act(() => editDialog!.props.onSuccess())

    expect(getKnowledgeBases.mock.calls.length).toBeGreaterThan(1)
    expect(text()).not.toContain('kbsSelected')
  })

  test('keeps selected rows and does not show success when bulk deletion fails', async () => {
    permissions = new Set(['admin:knowledge-base:read', 'admin:knowledge-base:delete'])
    getKnowledgeBases.mockResolvedValue({ items: [knowledgeBase], total: 1 })
    deleteKnowledgeBase.mockRejectedValue(new Error('offline'))
    await renderClient()

    act(() => renderer!.root.findAllByType('input').find((input) => input.props.type === 'checkbox')!.props.onChange())
    await act(async () => renderer!.root.findAllByType('button').find((node) => node.props.className?.includes('text-destructive'))!.props.onClick())
    await act(async () => renderer!.root.findAllByType('button').filter((node) => textNode(node).includes('delete')).at(-1)!.props.onClick())

    expect(deleteKnowledgeBase).toHaveBeenCalledWith('kb-1')
    expect(toastSuccess).not.toHaveBeenCalled()
    expect(text()).toContain('1 kbsSelected')
  })
  test('moves between pages and resets to the first page when filters change', async () => {
    getKnowledgeBases.mockResolvedValue({ items: [knowledgeBase], total: 25 })
    await renderClient()

    const pageButtons = () => renderer!.root.findAllByType('button').filter((node) => node.props.className === 'h-8 w-8')
    expect(pageButtons()).toHaveLength(4)
    expect(pageButtons()[0].props.disabled).toBe(true)
    expect(pageButtons()[1].props.disabled).toBe(true)

    await act(async () => pageButtons()[2].props.onClick())
    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 2, pageSize: 10 })
    expect(pageButtons()[0].props.disabled).toBe(false)

    await act(async () => pageButtons()[3].props.onClick())
    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 3, pageSize: 10 })
    expect(pageButtons()[2].props.disabled).toBe(true)

    const search = renderer!.root.findByProps({ placeholder: 'filterKbs' })
    await act(async () => search.props.onChange({ target: { value: 'handbook' } }))
    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: 'handbook' })
    expect(pageButtons()[0].props.disabled).toBe(true)

    await act(async () => pageButtons()[2].props.onClick())
    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 2, pageSize: 10, search: 'handbook' })
    await act(async () => renderer!.root.findByProps({ title: 'status' }).props.onSelectionChange(new Set(['archived'])))
    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: 'handbook', status: ['archived'] })
  })

  test('keeps the visible list and exits loading when a filtered request fails', async () => {
    getKnowledgeBases.mockResolvedValueOnce({ items: [knowledgeBase], total: 1 })
    getKnowledgeBases.mockRejectedValueOnce(new Error('offline'))
    await renderClient()
    expect(text()).toContain('Handbook')

    const search = renderer!.root.findByProps({ placeholder: 'filterKbs' })
    await act(async () => search.props.onChange({ target: { value: 'missing' } }))

    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: 'missing' })
    expect(text()).not.toContain('loading')
    expect(text()).toContain('Handbook')
    expect(text()).not.toContain('noKbs')
  })
  test('retries loading after an initial knowledge base list request fails', async () => {
    getKnowledgeBases.mockRejectedValueOnce(new Error('offline'))
    getKnowledgeBases.mockResolvedValueOnce({ items: [knowledgeBase], total: 1 })
    await renderClient()

    expect(text()).not.toContain('loading')
    expect(text()).toContain('noKbs')
    expect(getKnowledgeBases).toHaveBeenCalledTimes(1)

    await act(async () => renderer!.root.findByProps({ placeholder: 'filterKbs' }).props.onChange({ target: { value: 'handbook' } }))

    expect(getKnowledgeBases).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: 'handbook' })
    expect(text()).toContain('Handbook')
    expect(text()).not.toContain('loading')
  })
})
