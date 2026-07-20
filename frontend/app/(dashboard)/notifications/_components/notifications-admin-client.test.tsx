import { afterEach, beforeEach, expect, mock, test } from 'bun:test'

import type { NotificationItem } from '@/lib/api/admin/notifications'

type ElementNode = { type: unknown; props: Record<string, unknown> }
type Setter<T> = (next: T | ((prev: T) => T)) => void

const jsx = (type: unknown, props: Record<string, unknown> = {}): ElementNode => ({ type, props })
const Fragment = Symbol.for('react.fragment')

let hookStates: unknown[] = []
let hookDeps: Array<unknown[] | undefined> = []
let hookIndex = 0
let pendingEffects: Array<() => void | Promise<void>> = []
let renderComponent!: () => ElementNode
let tree!: ElementNode

const depsChanged = (prev: unknown[] | undefined, next: unknown[] | undefined) =>
  !prev || !next || prev.length !== next.length || prev.some((value, index) => value !== next[index])

const fakeReact = {
  Fragment,
  useState<T>(initial: T | (() => T)): [T, Setter<T>] {
    const index = hookIndex++
    if (hookStates[index] === undefined) hookStates[index] = typeof initial === 'function' ? (initial as () => T)() : initial
    return [hookStates[index] as T, (next) => {
      hookStates[index] = typeof next === 'function' ? (next as (prev: T) => T)(hookStates[index] as T) : next
    }]
  },
  useEffect(effect: () => void | Promise<void>, deps?: unknown[]) {
    const index = hookIndex++
    if (depsChanged(hookDeps[index], deps)) {
      hookDeps[index] = deps
      pendingEffects.push(effect)
    }
  },
  useCallback<T extends (...args: never[]) => unknown>(fn: T): T {
    hookIndex++
    return fn
  },
}

mock.module('react', () => fakeReact)
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment }))

const adminList = mock(async () => ({ items: [], total: 0, page: 1, page_size: 10 }))
const adminDelete = mock(async (id: string) => ({ id }))
const toastSuccess = mock(() => undefined)
let searchValue = ''
let setSearchCalls: string[] = []
let consoleErrors: unknown[][] = []
const originalConsoleError = console.error

const text = (namespace: string, key: string, values?: Record<string, unknown>) => {
  const suffix = values?.count !== undefined ? `:${values.count}` : ''
  return `${namespace}.${key}${suffix}`
}

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => Object.assign(
    (key: string, values?: Record<string, unknown>) => text(namespace, key, values),
    { has: () => true },
  ),
}))
mock.module('@/lib/api/admin/notifications', () => ({ notificationsApi: { adminList, adminDelete } }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => [searchValue, (next: string) => { searchValue = next; setSearchCalls.push(next) }],
}))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))
mock.module('./create-notification-dialog', () => ({
  CreateNotificationDialog: ({ open, onOpenChange, onSuccess }: { open: boolean; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => (
    <div data-open={open} data-testid="create-dialog" onClick={() => { onSuccess(); onOpenChange(false) }} />
  ),
}))
mock.module('./notification-detail-dialog', () => ({
  NotificationDetailDialog: ({ notification, open }: { notification: NotificationItem | null; open: boolean }) => (
    <div data-open={open} data-title={notification?.title} data-testid="detail-dialog" />
  ),
}))

const passthrough = (tag: string) =>
  ({ children, render, onCheckedChange, onValueChange, ...props }: Record<string, unknown>) => {
    const ownProps = { ...props } as Record<string, unknown>
    if (onCheckedChange) ownProps.onClick = () => (onCheckedChange as (value: boolean) => void)(true)
    if (onValueChange) ownProps.onClick = () => (onValueChange as (value: string) => void)('20')
    return jsx(tag, { ...ownProps, children: render || children })
  }

mock.module('@/components/ui/button', () => ({ Button: passthrough('button') }))
mock.module('@/components/ui/input', () => ({ Input: passthrough('input') }))
mock.module('@/components/ui/select', () => ({
  Select: passthrough('div'), SelectContent: passthrough('div'), SelectItem: passthrough('button'),
  SelectTrigger: passthrough('button'), SelectValue: passthrough('span'),
}))
mock.module('@/components/ui/table', () => ({
  Table: passthrough('table'), TableBody: passthrough('tbody'), TableCell: passthrough('td'),
  TableHead: passthrough('th'), TableHeader: passthrough('thead'), TableRow: passthrough('tr'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: unknown; open: boolean }) => open ? jsx('div', { children }) : null,
  AlertDialogAction: passthrough('button'), AlertDialogCancel: passthrough('button'),
  AlertDialogContent: passthrough('div'), AlertDialogDescription: passthrough('p'), AlertDialogFooter: passthrough('div'),
  AlertDialogHeader: passthrough('div'), AlertDialogTitle: passthrough('h2'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: passthrough('div'), DropdownMenuContent: passthrough('div'),
  DropdownMenuItem: passthrough('button'), DropdownMenuTrigger: passthrough('button'),
}))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough('span') }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, options, onSelectionChange }: { title: string; options: Array<{ value: string }>; onSelectionChange: (next: Set<string>) => void }) => (
    <button onClick={() => onSelectionChange(new Set([options[0].value]))}>{title}</button>
  ),
}))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: passthrough('span'), TooltipContent: passthrough('span'), TooltipTrigger: passthrough('button') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: passthrough('input') }))
mock.module('lucide-react', () => ({
  Plus: passthrough('i'), Trash2: passthrough('i'), ChevronLeft: passthrough('i'), ChevronRight: passthrough('i'),
  ChevronsLeft: passthrough('i'), ChevronsRight: passthrough('i'), Search: passthrough('i'), X: passthrough('i'),
  Mail: passthrough('i'), MessageSquare: passthrough('i'), CheckCircle2: passthrough('i'), XCircle: passthrough('i'),
  Loader2: passthrough('i'), Clock: passthrough('i'), Eye: passthrough('i'), MoreHorizontal: passthrough('i'),
}))

const { NotificationsAdminClient } = await import('./notifications-admin-client')

const item = (overrides: Partial<NotificationItem> = {}): NotificationItem => ({
  id: 'n1', scope: 'global', type: 'system.notice', source: 'system', title: 'Release window', content: 'Ships tonight',
  level: 'high', status: 'active', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
  is_read: false, deliveries: [], ...overrides,
})

const normalizeChildren = (children: unknown) => Array.isArray(children) ? children : [children]
const walk = (node: unknown, visit: (node: ElementNode) => void) => {
  if (!node || typeof node !== 'object') return
  const current = node as ElementNode
  if (typeof current.type === 'function') {
    walk(current.type(current.props), visit)
    return
  }
  visit(current)
  normalizeChildren(current.props?.children).forEach(child => walk(child, visit))
}
const findAll = (predicate: (node: ElementNode) => boolean) => {
  const matches: ElementNode[] = []
  walk(tree, node => { if (predicate(node)) matches.push(node) })
  return matches
}
const render = async (runEffects = true) => {
  hookIndex = 0
  pendingEffects = []
  tree = renderComponent()
  if (!runEffects) return tree
  const effects = pendingEffects
  pendingEffects = []
  await Promise.all(effects.map(effect => effect()))
  hookIndex = 0
  tree = renderComponent()
  return tree
}
const click = async (node: ElementNode | undefined) => {
  expect(node).toBeTruthy()
  await node?.props.onClick?.({ target: { closest: () => null } })
  await render(false)
}
const byText = (textValue: string) => findAll(node => node.props?.children === textValue)
const buttons = () => findAll(node => node.type === 'button')
const rows = () => findAll(node => node.type === 'tr')

beforeEach(() => {
  searchValue = ''
  setSearchCalls = []
  consoleErrors = []
  hookStates = []
  hookDeps = []
  renderComponent = () => NotificationsAdminClient() as ElementNode
  adminList.mockClear()
  adminDelete.mockClear()
  toastSuccess.mockClear()
  adminList.mockImplementation(async () => ({ items: [], total: 0, page: 1, page_size: 10 }))
  adminDelete.mockImplementation(async (id: string) => ({ id }))
  console.error = (...args) => { consoleErrors.push(args) }
})

afterEach(() => {
  console.error = originalConsoleError
  mock.restore()
})

test('shows loading then empty success state', async () => {
  let resolveList!: (value: { items: NotificationItem[]; total: number; page: number; page_size: number }) => void
  adminList.mockImplementationOnce(() => new Promise(resolve => { resolveList = resolve }))

  await render(false)
  await Promise.all(pendingEffects.map(effect => effect()))
  await render(false)

  expect(byText('common.loading')).toHaveLength(1)

  await resolveList({ items: [], total: 0, page: 1, page_size: 10 })
  await render(false)

  expect(byText('notifications.empty')).toHaveLength(1)
  expect(adminList).toHaveBeenCalledWith({ page: 1, page_size: 10, scope: undefined, level: undefined, search: undefined })
})

test('logs fetch errors and leaves an empty table state', async () => {
  adminList.mockImplementationOnce(async () => { throw new Error('network down') })

  await render()

  expect(byText('notifications.empty')).toHaveLength(1)
  expect(consoleErrors[0]?.[0]).toBe('Failed to fetch notifications:')
})

test('applies filters, opens detail, and deletes one notification', async () => {
  adminList.mockImplementation(async () => ({ items: [item()], total: 1, page: 1, page_size: 10 }))
  await render()

  await click(buttons().find(button => button.props.children === 'notifications.scope'))
  await render()

  expect(adminList).toHaveBeenLastCalledWith({ page: 1, page_size: 10, scope: ['global'], level: undefined, search: undefined })

  await click(rows().find(row => row.props.className === 'cursor-pointer'))
  expect(findAll(node => node.props['data-testid'] === 'detail-dialog')[0].props).toMatchObject({ 'data-open': true, 'data-title': 'Release window' })

  await click(buttons().find(button => String(button.props.children).includes('common.delete')))
  await click(buttons().find(button => button.props.children === 'common.delete'))

  expect(adminDelete).toHaveBeenCalledWith('n1')
  expect(toastSuccess).toHaveBeenCalledWith('notifications.toast.deleted')
})

test('bulk selection deletes selected notifications and reset clears search filter', async () => {
  searchValue = 'release'
  adminList.mockImplementation(async () => ({ items: [item(), item({ id: 'n2', title: 'Incident' })], total: 2, page: 1, page_size: 10 }))
  await render()

  await click(findAll(node => node.type === 'input')[1])
  expect(byText('notifications.admin.selectedCount:2')).toHaveLength(1)

  await click(buttons().find(button => {
    const child = button.props.children as ElementNode | undefined
    return typeof button.props.onClick === 'function' && String(child?.props?.className).includes('destructive')
  }))
  await click(buttons().find(button => button.props.children === 'notifications.admin.delete'))
  expect(adminDelete.mock.calls.map(call => call[0]).sort()).toEqual(['n1', 'n2'])

  await click(buttons().find(button => String(button.props.children).includes('common.reset')))
  expect(setSearchCalls).toContain('')
})
