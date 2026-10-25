import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getEntities = mock()
const deleteEntity = mock(async () => ({}))
const toastSuccess = mock(() => {})

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => {
    const translate = (key: string) => key
    translate.has = () => false
    return translate
  },
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Search', 'MoreHorizontal', 'Pencil', 'Trash2', 'ChevronLeft', 'ChevronRight',
  'ChevronsLeft', 'ChevronsRight', 'X', 'Brain', 'User', 'ArrowRight', 'ArrowLeft',
].map((name) => [name, () => null])))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/admin/memories', () => ({ memoriesApi: { getEntities, deleteEntity } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
// The debounce hook is intentionally not mocked: the real 300ms timer is under test.
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))

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
  DropdownMenuItem: element('button'),
  DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: () => null }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: element('span'),
  TooltipTrigger: ({ render }: { render: React.ReactElement }) => render,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div>{children}</div> : null,
  AlertDialogAction: element('button'),
  AlertDialogCancel: element('button'),
  AlertDialogContent: element('section'),
  AlertDialogDescription: element('p'),
  AlertDialogFooter: element('footer'),
  AlertDialogHeader: element('header'),
  AlertDialogTitle: element('h2'),
}))
mock.module('./entity-dialog', () => ({ EntityDialog: () => null }))

// The component is imported after the module mocks above are registered, which a
// static import cannot guarantee.
const { MemoriesClient } = await import('./memories-client')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const entity = {
  id: 'memory-1', user_id: 'user-1', user_name: 'Ada', user_avatar_url: null,
  name: 'Likes tea', entity_type: 'preference', description: 'Strong tea', properties: {},
  access_count: 2, last_accessed_at: '2026-01-02T00:00:00Z', created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-03T00:00:00Z', outgoing_relations_count: 1, incoming_relations_count: 1,
}

let renderer: ReactTestRenderer | undefined

beforeEach(() => {
  getEntities.mockReset()
  getEntities.mockResolvedValue({ items: [entity], total: 45, page: 1, page_size: 20 })
  deleteEntity.mockReset()
  toastSuccess.mockReset()
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
})

describe('MemoriesClient search debounce', () => {
  test('collapses rapid edits into one first-page request after the delay', async () => {
    await act(async () => { renderer = create(<MemoriesClient />) })
    expect(getEntities).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, page_size: 20 }))

    const pageButtons = () => renderer!.root.findAllByType('button').filter((node) => node.props.className === 'h-8 w-8' && 'disabled' in node.props)
    await act(async () => pageButtons()[2].props.onClick())
    expect(getEntities).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, page_size: 20 }))

    getEntities.mockClear()
    const search = () => renderer!.root.findByProps({ placeholder: 'searchPlaceholder' })
    act(() => search().props.onChange({ target: { value: 't' } }))
    act(() => search().props.onChange({ target: { value: 'te' } }))
    act(() => search().props.onChange({ target: { value: 'tea' } }))

    expect(search().props.value).toBe('tea')
    expect(getEntities).not.toHaveBeenCalled()

    const beforeDelay = Promise.withResolvers<void>()
    setTimeout(beforeDelay.resolve, 150)
    await act(async () => { await beforeDelay.promise })
    expect(getEntities).not.toHaveBeenCalled()

    const { promise, resolve } = Promise.withResolvers<void>()
    setTimeout(resolve, 500)
    await act(async () => { await promise })

    expect(getEntities).toHaveBeenCalledTimes(1)
    expect(getEntities).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20, search: 'tea' }))
  })
})
