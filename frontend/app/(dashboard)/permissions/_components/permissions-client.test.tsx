import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getPermissions = mock(() => Promise.resolve({ items: [], total: 0 }))
const getPermissionScopes = mock(() => Promise.resolve([]))
const deletePermission = mock(() => Promise.resolve({}))
const toastSuccess = mock(() => {})
let permissions = new Set<string>()

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/admin/roles', () => ({
  permissionsApi: { getPermissions, getPermissionScopes, deletePermission },
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ permission, children }: React.PropsWithChildren<{ permission: string }>) =>
    permissions.has(permission) ? children : null,
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Plus', 'Search', 'MoreHorizontal', 'Pencil', 'Trash2', 'Key', 'X',
  'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight',
].map(name => [name, () => null])))

function element(tag: keyof React.JSX.IntrinsicElements) {
  return function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
}

mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, disabled, onCheckedChange }: {
    checked: boolean; disabled?: boolean; onCheckedChange: () => void
  }) => <input type="checkbox" checked={checked} disabled={disabled} onChange={onCheckedChange} readOnly />,
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: element('option'), SelectTrigger: element('span'), SelectValue: element('span'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DropdownMenuItem: element('button'), DropdownMenuSeparator: element('hr'),
  DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: (props: Record<string, unknown>) => <div data-testid="scope-filter" {...props} />,
}))
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
mock.module('./permission-dialog', () => ({
  PermissionDialog: (props: Record<string, unknown>) => <div data-testid="permission-dialog" {...props} />,
}))
mock.module('./delete-permission-dialog', () => ({
  DeletePermissionDialog: (props: Record<string, unknown>) => <div data-testid="delete-dialog" {...props} />,
}))

const { PermissionsClient } = await import('./permissions-client')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer | undefined
const customPermission = {
  id: 'permission-1', code: 'docs:read', scope: 'workspace', description: 'Read documents', is_system: false,
}
const systemPermission = {
  id: 'permission-2', code: '*', scope: 'system', description: null, is_system: true,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

async function renderClient() {
  await act(async () => { renderer = create(<PermissionsClient />) })
  return renderer!
}

function text() {
  return renderer!.root.findAll(() => true).flatMap(node => node.children)
    .filter(child => typeof child === 'string').join(' ')
}

function button(label: string) {
  return renderer!.root.findAllByType('button').find(node => node.children.includes(label))!
}

beforeEach(() => {
  permissions = new Set()
  getPermissions.mockReset()
  getPermissions.mockResolvedValue({ items: [], total: 0 })
  getPermissionScopes.mockReset()
  getPermissionScopes.mockResolvedValue([])
  deletePermission.mockReset()
  deletePermission.mockResolvedValue({})
  toastSuccess.mockReset()
})

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
})

describe('PermissionsClient', () => {
  test('shows loading, then renders permissions and pagination', async () => {
    const pending = deferred<{ items: typeof customPermission[]; total: number }>()
    getPermissions.mockReturnValueOnce(pending.promise)

    await renderClient()
    expect(text()).toContain('loading')
    expect(getPermissions).toHaveBeenCalledWith(1, 10, undefined, undefined)

    await act(async () => pending.resolve({ items: [customPermission], total: 21 }))
    expect(text()).toContain('docs:read')
    expect(text()).toContain('Read documents')
    expect(text()).toContain('pageInfo:1,3')
  })

  test('finishes loading after list and scope errors and shows the empty boundary', async () => {
    getPermissions.mockRejectedValueOnce(new Error('offline'))
    getPermissionScopes.mockRejectedValueOnce(new Error('offline'))

    await renderClient()

    expect(text()).not.toContain('loading')
    expect(text()).toContain('noPermissions')
  })

  test('passes search and scope filters to the API and resets them', async () => {
    await renderClient()
    const input = renderer!.root.findAllByType('input').find(node => node.props.type !== 'checkbox')!

    await act(async () => input.props.onChange({ target: { value: 'docs' } }))
    expect(getPermissions).toHaveBeenLastCalledWith(1, 10, undefined, 'docs')

    const scopeFilter = renderer!.root.findByProps({ 'data-testid': 'scope-filter' })
    await act(async () => scopeFilter.props.onSelectionChange(new Set(['workspace'])))
    expect(getPermissions).toHaveBeenLastCalledWith(1, 10, ['workspace'], 'docs')

    await act(async () => button('reset').props.onClick())
    expect(getPermissions).toHaveBeenLastCalledWith(1, 10, undefined, undefined)
  })

  test('hides mutation controls and disables system selection without authorization', async () => {
    getPermissions.mockResolvedValueOnce({ items: [customPermission, systemPermission], total: 2 })
    await renderClient()

    expect(text()).not.toContain('createPermission')
    expect(text()).not.toContain('edit')
    expect(text()).not.toContain('delete')
    const checkboxes = renderer!.root.findAllByType('input').filter(node => node.props.type === 'checkbox')
    expect(checkboxes[1].props.disabled).toBe(false)
    expect(checkboxes[2].props.disabled).toBe(true)
  })

  test('opens permitted create/edit/delete actions and bulk deletes selected permissions', async () => {
    permissions = new Set([
      'admin:permission:create', 'admin:permission:update', 'admin:permission:delete',
    ])
    getPermissions.mockResolvedValue({ items: [customPermission], total: 1 })
    await renderClient()

    act(() => button('createPermission').props.onClick())
    let dialog = renderer!.root.findByProps({ 'data-testid': 'permission-dialog' })
    expect(dialog.props.open).toBe(true)
    expect(dialog.props.permission).toBeNull()

    act(() => button('edit').props.onClick())
    dialog = renderer!.root.findByProps({ 'data-testid': 'permission-dialog' })
    expect(dialog.props.permission).toEqual(customPermission)

    act(() => button('delete').props.onClick())
    expect(renderer!.root.findByProps({ 'data-testid': 'delete-dialog' }).props.open).toBe(true)

    const rowCheckbox = renderer!.root.findAllByType('input')
      .filter(node => node.props.type === 'checkbox')[1]
    act(() => rowCheckbox.props.onChange())
    const bulkDelete = renderer!.root.findAllByType('button')
      .find(node => node.props.className?.includes('text-destructive'))!
    act(() => bulkDelete.props.onClick())
    await act(async () => renderer!.root.findAllByType('button')
      .filter(node => node.children.includes('delete')).at(-1)!.props.onClick())

    expect(deletePermission).toHaveBeenCalledWith('permission-1')
    expect(toastSuccess).toHaveBeenCalledWith('bulkDeleted:1')
    expect(getPermissions.mock.calls.length).toBeGreaterThan(1)
  })
})
