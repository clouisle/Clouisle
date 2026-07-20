import { expect, mock, test } from 'bun:test'
import * as React from 'react'

const role = {
  id: 'editor',
  name: 'Editor',
  description: 'Can edit content',
  is_system_role: false,
  permissions: [{ id: 'edit', code: 'content:edit', scope: 'content' }],
}

let stateValues: unknown[] = []
let stateIndex = 0
const stateUpdates: unknown[][] = []
let effects: Array<() => void | (() => void)> = []

mock.module('react', () => ({
  ...React,
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    const setState = (value: T) => { stateUpdates[index]?.push(value) }
    return [stateValues[index] ?? initial, setState] as [T, typeof setState]
  },
  useCallback: <T,>(callback: T) => callback,
  useMemo: <T,>(factory: () => T) => factory(),
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
}))

const element = 'div'
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key }))
mock.module('lucide-react', () => Object.fromEntries(['Plus', 'Search', 'MoreHorizontal', 'Pencil', 'Trash2', 'Shield', 'ShieldCheck', 'X', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight'].map((name) => [name, element])))
mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/input', () => ({ Input: element }))
mock.module('@/components/ui/badge', () => ({ Badge: element }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element }))
mock.module('@/components/ui/table', () => ({ Table: element, TableBody: element, TableCell: element, TableHead: element, TableHeader: element, TableRow: element }))
mock.module('@/components/ui/select', () => ({ Select: element, SelectContent: element, SelectItem: element, SelectTrigger: element, SelectValue: element }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: element, DropdownMenuContent: element, DropdownMenuItem: element, DropdownMenuSeparator: element, DropdownMenuTrigger: element }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element, TooltipContent: element, TooltipTrigger: element }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: element, AlertDialogAction: element, AlertDialogCancel: element, AlertDialogContent: element, AlertDialogDescription: element, AlertDialogFooter: element, AlertDialogHeader: element, AlertDialogTitle: element }))
mock.module('./role-dialog', () => ({ RoleDialog: element }))
mock.module('./delete-role-dialog', () => ({ DeleteRoleDialog: element }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: element, useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => ['', () => {}] }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))

const getRoles = mock(() => Promise.resolve({ items: [role], total: 1 }))
mock.module('@/lib/api/admin/roles', () => ({ rolesApi: { getRoles, deleteRole: mock() } }))

const { RolesClient } = await import('./roles-client')

function render(values: unknown[]) {
  stateValues = values
  stateIndex = 0
  stateUpdates.length = 10
  for (let index = 0; index < stateUpdates.length; index++) stateUpdates[index] = []
  effects = []
  return RolesClient()
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!React.isValidElement(node)) return ''
  return React.Children.toArray(node.props.children).map(textContent).join('')
}

function find(node: unknown, predicate: (element: React.ReactElement) => boolean): React.ReactElement | undefined {
  if (!React.isValidElement(node)) return undefined
  if (predicate(node)) return node
  return React.Children.toArray(node.props.children).map((child) => find(child, predicate)).find(Boolean)
}

test('renders loading and loaded role list states', () => {
  expect(textContent(render([]))).toContain('loading')

  const loaded = render([[role], false, 1, 10, { items: [role], total: 1 }])
  expect(textContent(loaded)).toContain('Editor')
  expect(textContent(loaded)).toContain('permissionCount')
})

test('opens the create dialog and stops loading when list loading fails', async () => {
  const create = find(render([[], false]), (node) => node.props.onClick && textContent(node).includes('createRole'))
  create?.props.onClick()
  expect(stateUpdates[6]).toContain(true)

  getRoles.mockImplementationOnce(() => Promise.reject(new Error('network failed')))
  render([])
  effects.forEach((effect) => effect())
  await Promise.resolve()
  await Promise.resolve()

  expect(getRoles).toHaveBeenCalled()
  expect(stateUpdates[1]).toEqual([true, false])
})
