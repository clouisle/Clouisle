import { afterEach, beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLInputElement: window.HTMLInputElement,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const roles = [
  { id: 'system', name: 'Administrator', description: null, is_system_role: true, permissions: [] },
  { id: 'editor', name: 'Editor', description: 'Can edit', is_system_role: false, permissions: [{ id: 'edit' }] },
  { id: 'viewer', name: 'Viewer', description: 'Can view', is_system_role: false, permissions: [] },
]
const getRoles = mock(async () => ({ items: roles, total: 25, page: 1, page_size: 10 }))
const deleteRole = mock(async () => undefined)
const success = mock()
let permissions = new Set(['admin:role:create', 'admin:role:update', 'admin:role:delete'])
let search = ''

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    `${namespace}.${key}${values ? `:${JSON.stringify(values)}` : ''}`,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { getRoles, deleteRole } }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => {
    const [, rerender] = React.useState(0)
    return [search, (value: string) => { search = value; rerender((n) => n + 1) }] as const
  },
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
  PermissionGuard: ({ permission, children }: { permission: string; children: React.ReactNode }) =>
    permissions.has(permission) ? <>{children}</> : null,
}))
const Icon = ({ name, ...props }: React.SVGProps<SVGSVGElement> & { name: string }) => <svg data-icon={name} {...props} />
mock.module('lucide-react', () => Object.fromEntries([
  'Plus', 'Search', 'MoreHorizontal', 'Pencil', 'Trash2', 'Shield', 'ShieldCheck', 'X',
  'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight',
].map((name) => [name, (props: React.SVGProps<SVGSVGElement>) => <Icon name={name} {...props} />])))

function element(tag = 'div') {
  function MockElement({ children, render, ...props }: React.HTMLAttributes<HTMLElement> & { render?: React.ReactNode }) {
    return React.createElement(tag, props, render ?? children)
  }
  return MockElement
}
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({
  Input: ({ onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} onInput={onChange} />,
}))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, disabled, onCheckedChange }: { checked?: boolean; disabled?: boolean; onCheckedChange?: () => void }) =>
    <input type="checkbox" checked={checked} disabled={disabled} onChange={onCheckedChange} />,
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'),
  TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (value: string) => void }) =>
    <div>{children}<button onClick={() => onValueChange('20')}>select-20</button></div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: element(), SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element(), DropdownMenuContent: element(), DropdownMenuItem: element('button'),
  DropdownMenuSeparator: element('hr'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element(), TooltipContent: element(),
  TooltipTrigger: ({ render, ...props }: React.HTMLAttributes<HTMLElement> & { render: React.ReactElement }) => React.cloneElement(render, props),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <div data-dialog="bulk">{children}</div> : null,
  AlertDialogAction: element('button'), AlertDialogCancel: element('button'), AlertDialogContent: element(),
  AlertDialogDescription: element(), AlertDialogFooter: element(), AlertDialogHeader: element(), AlertDialogTitle: element(),
}))
function Dialog({ name, open, role, onOpenChange, onSuccess }: {
  name: string; open: boolean; role: { id: string } | null; onOpenChange: (open: boolean) => void; onSuccess: () => void
}) {
  return <div data-dialog={name} data-open={String(open)} data-role={role?.id ?? ''}>
    <button onClick={() => onOpenChange(false)}>{name}-close</button>
    <button onClick={onSuccess}>{name}-success</button>
  </div>
}
mock.module('./role-dialog', () => ({
  RoleDialog: (props: Omit<React.ComponentProps<typeof Dialog>, 'name'>) => <Dialog name="role" {...props} />,
}))
mock.module('./delete-role-dialog', () => ({
  DeleteRoleDialog: (props: Omit<React.ComponentProps<typeof Dialog>, 'name'>) => <Dialog name="delete" {...props} />,
}))

let RolesClient: typeof import('./roles-client').RolesClient
const roots: Root[] = []
const tick = () => new Promise((resolve) => setTimeout(resolve, 0))
beforeAll(async () => { ({ RolesClient } = await import('./roles-client')) })
beforeEach(() => {
  search = ''
  permissions = new Set(['admin:role:create', 'admin:role:update', 'admin:role:delete'])
  getRoles.mockClear()
  deleteRole.mockClear()
  success.mockClear()
  getRoles.mockImplementation(async () => ({ items: roles, total: 25, page: 1, page_size: 10 }))
  deleteRole.mockImplementation(async () => undefined)
})
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})
async function render() {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  await act(async () => { root.render(<RolesClient />); await tick() })
  return container
}
async function click(node: Element) {
  await act(async () => { (node as HTMLElement).click(); await tick() })
}
function button(container: HTMLElement, text: string, occurrence = 0) {
  return [...container.querySelectorAll('button')].filter((node) => node.textContent?.includes(text))[occurrence]!
}
function iconButton(container: HTMLElement, icon: string, occurrence = 0) {
  return [...container.querySelectorAll('button')].filter((node) => node.querySelector(`[data-icon="${icon}"]`))[occurrence]!
}
function enter(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, value)
  input.dispatchEvent(new window.Event('input', { bubbles: true }))
}

describe('RolesClient issue #255 coverage', () => {
  it('loads roles, renders row details, and handles list errors and empty results', async () => {
    const container = await render()
    expect(getRoles).toHaveBeenCalledWith(1, 10, undefined)
    expect(container.textContent).toContain('Administrator')
    expect(container.textContent).toContain('Editor')
    expect(container.textContent).toContain('roles.systemRole')
    expect(container.textContent).toContain('roles.customRole')
    expect(container.textContent).toContain('1 roles.permissionCount')

    getRoles.mockImplementationOnce(async () => { throw new Error('network') })
    const failed = await render()
    expect(failed.textContent).toContain('roles.noRoles')
    getRoles.mockImplementationOnce(async () => ({ items: [], total: 0, page: 1, page_size: 10 }))
    const empty = await render()
    expect(empty.textContent).toContain('roles.noRoles')
  })

  it('filters, resets, changes page size, and uses every pagination callback', async () => {
    const container = await render()
    const input = container.querySelector('input[placeholder="roles.filterRoles"]') as HTMLInputElement
    await act(async () => { enter(input, 'editor'); await tick() })
    expect(getRoles).toHaveBeenLastCalledWith(1, 10, 'editor')
    await click(button(container, 'common.reset'))
    expect(search).toBe('')
    expect(getRoles).toHaveBeenLastCalledWith(1, 10, undefined)

    await click(button(container, 'select-20'))
    expect(getRoles).toHaveBeenLastCalledWith(1, 20, undefined)
    await click(iconButton(container, 'ChevronRight'))
    expect(getRoles).toHaveBeenLastCalledWith(2, 20, undefined)
    await click(iconButton(container, 'ChevronLeft'))
    expect(getRoles).toHaveBeenLastCalledWith(1, 20, undefined)
    await click(iconButton(container, 'ChevronsRight'))
    expect(getRoles).toHaveBeenLastCalledWith(2, 20, undefined)
    await click(iconButton(container, 'ChevronsLeft'))
    expect(getRoles).toHaveBeenLastCalledWith(1, 20, undefined)
  })

  it('selects only custom roles, toggles individual and all selection, and clears it', async () => {
    const container = await render()
    const checks = container.querySelectorAll('input[type="checkbox"]')
    expect((checks[1] as HTMLInputElement).disabled).toBe(true)
    await click(checks[0])
    expect(container.textContent).toContain('2 roles.rolesSelected')
    await click(checks[0])
    expect(container.textContent).not.toContain('roles.rolesSelected')
    await click(checks[2])
    expect(container.textContent).toContain('1 roles.rolesSelected')
    await click(iconButton(container, 'X'))
    expect(container.textContent).not.toContain('roles.rolesSelected')
  })

  it('opens create, edit, and delete dialogs and runs their close and success callbacks', async () => {
    const container = await render()
    await click(button(container, 'roles.createRole'))
    expect(container.querySelector('[data-dialog="role"]')?.getAttribute('data-open')).toBe('true')
    expect(container.querySelector('[data-dialog="role"]')?.getAttribute('data-role')).toBe('')
    await click(button(container, 'role-close'))

    await click(button(container, 'common.edit', 1))
    expect(container.querySelector('[data-dialog="role"]')?.getAttribute('data-role')).toBe('editor')
    await click(button(container, 'role-success'))
    expect(getRoles.mock.calls.length).toBeGreaterThan(1)

    await click(button(container, 'common.delete'))
    expect(container.querySelector('[data-dialog="delete"]')?.getAttribute('data-role')).toBe('editor')
    await click(button(container, 'delete-close'))
    await click(button(container, 'common.delete'))
    await click(button(container, 'delete-success'))
    expect(getRoles.mock.calls.length).toBeGreaterThan(2)
  })

  it('bulk deletes selected roles on success and closes after API failure', async () => {
    const container = await render()
    await click(container.querySelectorAll('input[type="checkbox"]')[0])
    await click(iconButton(container, 'Trash2', 2))
    expect(container.querySelector('[data-dialog="bulk"]')).not.toBeNull()
    await click([...container.querySelectorAll('[data-dialog="bulk"] button')].at(-1)!)
    expect(deleteRole).toHaveBeenCalledTimes(2)
    expect(deleteRole).toHaveBeenCalledWith('editor')
    expect(deleteRole).toHaveBeenCalledWith('viewer')
    expect(success).toHaveBeenCalledWith('roles.bulkDeleted:{"count":2}')
    expect(container.textContent).not.toContain('roles.rolesSelected')

    await click(container.querySelectorAll('input[type="checkbox"]')[2])
    deleteRole.mockImplementationOnce(async () => { throw new Error('delete failed') })
    await click(iconButton(container, 'Trash2', 2))
    await click([...container.querySelectorAll('[data-dialog="bulk"] button')].at(-1)!)
    expect(container.querySelector('[data-dialog="bulk"]')).toBeNull()
    expect(container.textContent).toContain('1 roles.rolesSelected')
  })

  it('enforces create, update, and delete permission callbacks', async () => {
    permissions = new Set()
    const denied = await render()
    expect(denied.textContent).not.toContain('roles.createRole')
    expect(denied.textContent).not.toContain('common.edit')
    expect(denied.textContent).not.toContain('common.delete')

    permissions = new Set(['admin:role:update'])
    const updateOnly = await render()
    expect(updateOnly.textContent).toContain('common.edit')
    expect(updateOnly.textContent).not.toContain('common.delete')

    permissions = new Set(['admin:role:delete'])
    const deleteOnly = await render()
    expect(deleteOnly.textContent).not.toContain('common.edit')
    expect(button(deleteOnly, 'common.delete')).toBeDefined()
    await click(deleteOnly.querySelectorAll('input[type="checkbox"]')[2])
    expect(deleteOnly.textContent).toContain('roles.rolesSelected')
  })
})
