import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const usersApi = {
  getUsers: mock(),
  getStats: mock(async () => ({ total: 1, active: 1, inactive: 0, pending: 0 })),
  deactivateUser: mock(),
  activateUser: mock(),
}
const toast = { success: mock(() => {}) }

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('sonner', () => ({ toast }))
mock.module('@/lib/api/admin/users', () => ({ usersApi }))
mock.module('@/lib/api', () => ({ siteSettingsApi: { getPublic: mock(async () => ({})) } }))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { getRoles: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => value }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/components/ui/button', () => ({ Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} /> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: (props: { checked?: boolean, onCheckedChange?: () => void }) => <input type="checkbox" checked={props.checked} onChange={props.onCheckedChange} /> }))
mock.module('@/components/ui/table', () => ({
  Table: ({ children }: React.PropsWithChildren) => <table>{children}</table>,
  TableBody: ({ children }: React.PropsWithChildren) => <tbody>{children}</tbody>,
  TableCell: ({ children, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) => <td {...props}>{children}</td>,
  TableHead: ({ children, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) => <th {...props}>{children}</th>,
  TableHeader: ({ children }: React.PropsWithChildren) => <thead>{children}</thead>,
  TableRow: ({ children, ...props }: React.HTMLAttributes<HTMLTableRowElement>) => <tr {...props}>{children}</tr>,
}))
mock.module('@/components/ui/select', () => ({ Select: ({ children }: React.PropsWithChildren) => <>{children}</>, SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>, SelectItem: ({ children }: React.PropsWithChildren) => <>{children}</>, SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>, SelectValue: () => null }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: ({ children }: React.PropsWithChildren) => <>{children}</>, DropdownMenuContent: ({ children }: React.PropsWithChildren) => <>{children}</>, DropdownMenuItem: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>, DropdownMenuSeparator: () => null, DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: () => null }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>, TooltipContent: ({ children }: React.PropsWithChildren) => <>{children}</>, TooltipTrigger: ({ children, render, ...props }: React.PropsWithChildren<{ render?: React.ReactElement }>) => render ? React.cloneElement(render, props) : <>{children}</> }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: ({ children }: React.PropsWithChildren) => <>{children}</>, AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>, AlertDialogCancel: ({ children }: React.PropsWithChildren) => <>{children}</>, AlertDialogContent: ({ children }: React.PropsWithChildren) => <>{children}</>, AlertDialogDescription: ({ children }: React.PropsWithChildren) => <>{children}</>, AlertDialogFooter: ({ children }: React.PropsWithChildren) => <>{children}</>, AlertDialogHeader: ({ children }: React.PropsWithChildren) => <>{children}</>, AlertDialogTitle: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('./user-dialog', () => ({ UserDialog: () => null }))
mock.module('./delete-user-dialog', () => ({ DeleteUserDialog: () => null }))
mock.module('./send-notification-dialog', () => ({ SendNotificationDialog: () => null }))
mock.module('lucide-react', () => new Proxy({}, { get: () => () => <span /> }))

import { UsersClient } from './users-client'

const user = {
  id: 'user-1', username: 'Ada', email: 'ada@example.com', is_active: true, approval_status: 'approved', status: 'active', is_superuser: false, email_verified: true, avatar_url: null, locale: 'en', created_at: '2026-01-02T03:04:00Z', last_login: null, auth_source: 'local', external_id: null, force_password_change: false, password_expiration_exempt: false, roles: [], sso_connections: [],
}

const renderers: ReactTestRenderer[] = []

function render() {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<UsersClient />) })
  renderers.push(renderer!)
  return renderer!
}

function button(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').find(node => node.children.includes(label))!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  usersApi.getUsers.mockReset()
  usersApi.getStats.mockResolvedValue({ total: 1, active: 1, inactive: 0, pending: 0 })
  usersApi.deactivateUser.mockReset()
  toast.success.mockClear()
})

describe('UsersClient', () => {
  test('shows loading before rendering the fetched user list', async () => {
    let resolveUsers!: (value: { items: typeof user[], total: number }) => void
    usersApi.getUsers.mockImplementation(() => new Promise(resolve => { resolveUsers = resolve }))
    const renderer = render()

    expect(renderer.root.findAllByType('td').some(cell => cell.children.includes('loading'))).toBe(true)

    await act(async () => {
      resolveUsers({ items: [user], total: 1 })
      await Promise.resolve()
    })

    expect(usersApi.getUsers).toHaveBeenCalledWith({ page: 1, pageSize: 10, status: undefined, roles: undefined, search: undefined })
    expect(JSON.stringify(renderer.toJSON())).toContain('Ada')
    expect(JSON.stringify(renderer.toJSON())).toContain('ada@example.com')
  })

  test('contains a failed status action without reporting success', async () => {
    usersApi.getUsers.mockResolvedValue({ items: [user], total: 1 })
    usersApi.deactivateUser.mockRejectedValueOnce(new Error('unavailable'))
    const renderer = render()
    await act(async () => {})

    await act(async () => button(renderer, 'deactivate').props.onClick())

    expect(usersApi.deactivateUser).toHaveBeenCalledWith('user-1')
    expect(toast.success).not.toHaveBeenCalled()
  })
})
