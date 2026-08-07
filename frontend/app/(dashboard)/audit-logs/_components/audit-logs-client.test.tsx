import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'

const api = {
  getStats: mock(),
  list: mock(),
  getActions: mock(),
}

let states: unknown[] = []
let stateIndex = 0
let effects: Array<() => void | Promise<void>> = []
let search = ''
let canExport = true
const originalConsoleError = console.error

const component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
  React.createElement('div', props, children)
const tableComponent = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
  React.createElement('table', props, children)

mock.module('react', () => ({
  ...React,
  useEffect: (effect: () => void | Promise<void>) => { effects.push(effect) },
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    states[index] ??= initial
    return [states[index] as T, (value: T | ((current: T) => T)) => {
      states[index] = typeof value === 'function' ? (value as (current: T) => T)(states[index] as T) : value
    }] as const
  },
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => Object.assign((key: string) => `${namespace}.${key}`, { has: () => false }),
}))
mock.module('@/lib/api/admin/audit-logs', () => ({ auditLogsApi: api }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => [search, (value: string) => { search = value }],
}))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => canExport ? React.createElement(React.Fragment, {}, children) : null,
}))
mock.module('@/components/ui/card', () => ({ Card: component, CardContent: component, CardHeader: component, CardTitle: component }))
mock.module('@/components/ui/table', () => ({
  Table: tableComponent, TableBody: component, TableCell: component, TableHead: component, TableHeader: component, TableRow: component,
}))
mock.module('@/components/ui/badge', () => ({ Badge: component }))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/input', () => ({ Input: component }))
mock.module('@/components/ui/select', () => ({ Select: component, SelectContent: component, SelectItem: component, SelectTrigger: component, SelectValue: component }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: component, DropdownMenuContent: component, DropdownMenuItem: component, DropdownMenuTrigger: component }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: component }))
mock.module('@/components/ui/sheet', () => ({ Sheet: component, SheetContent: component, SheetDescription: component, SheetHeader: component, SheetTitle: component }))
mock.module('@/components/ui/separator', () => ({ Separator: component }))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({
  WorkflowRunDrawer: ({ open }: { open: boolean }) => open ? React.createElement('aside', { role: 'dialog', 'aria-label': 'workflow-run' }) : null,
}))
mock.module('sonner', () => ({ toast: { success: mock() } }))

const { AuditLogsClient } = await import('./audit-logs-client')
const { AuditLogsTable } = await import('./audit-logs-table')
const { AuditLogDrawer } = await import('./audit-log-drawer')

function render(Component: () => React.ReactElement) {
  stateIndex = 0
  effects = []
  return Component()
}

function findDeep(node: unknown, predicate: (element: React.ReactElement) => boolean): React.ReactElement | undefined {
  if (!React.isValidElement(node)) return undefined
  if (predicate(node)) return node
  for (const child of React.Children.toArray(node.props.children)) {
    const found = findDeep(child, predicate)
    if (found) return found
  }
  return undefined
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!React.isValidElement(node)) return ''
  if (typeof node.type === 'function') return text(node.type(node.props))
  return React.Children.toArray(node.props.children).map(text).join('')
}

beforeEach(() => {
  states = []
  stateIndex = 0
  effects = []
  search = ''
  canExport = true
  api.getStats.mockReset()
  api.list.mockReset()
  api.getActions.mockReset()
  console.error = mock()
})

afterEach(() => {
  console.error = originalConsoleError
})

describe('audit-log dashboard behavior', () => {
  test('shows statistic placeholders while stats load, then renders formatted totals', async () => {
    let resolveStats!: (value: { total_logs: number; today_logs: number; failed_logs: number; active_users: number }) => void
    api.getStats.mockImplementation(() => new Promise((resolve) => { resolveStats = resolve }))

    expect(text(render(AuditLogsClient))).toContain('...')
    await effects[0]()
    resolveStats({ total_logs: 1234, today_logs: 12, failed_logs: 3, active_users: 7 })
    await Promise.resolve()

    expect(text(render(AuditLogsClient))).toContain('1,234')
    expect(text(render(AuditLogsClient))).toContain('auditLogs.failedLogs')
  })

  test('keeps dashboard usable when stats fail', async () => {
    api.getStats.mockRejectedValue(new Error('stats unavailable'))
    render(AuditLogsClient)
    await effects[0]()

    expect(text(render(AuditLogsClient))).toContain('0')
  })

  test('shows failed-log detail fields in the coupled drawer', () => {
    const tree = render(() => <AuditLogDrawer open onOpenChange={() => {}} log={{
      id: 'log-1', created_at: '2026-01-02T03:04:05Z', status: 'failed', action: 'login_failed', operation: 'read',
      username: 'ada', resource_type: 'session', error_message: 'denied', changes: { before: { role: 'user' }, after: { role: 'admin' } }, metadata: { source: 'sso' },
    }} />)

    expect(text(tree)).toContain('denied')
    expect(text(tree)).toContain('"role": "admin"')
    expect(text(tree)).toContain('"source": "sso"')
    const successTree = render(() => <AuditLogDrawer open onOpenChange={() => {}} log={{
      id: 'log-2', created_at: '2026-01-02T03:04:05Z', status: 'success', action: 'login', operation: '',
      username: 'ada', resource_type: '', changes: null, metadata: null,
    }} />)
    expect(text(successTree)).toContain('auditLogs.statusSuccess')
  })


  test('hides export controls without audit export permission', async () => {
    canExport = false
    api.getActions.mockResolvedValue([])
    api.list.mockResolvedValue({ items: [], total_pages: 0 })

    render(AuditLogsTable)
    await Promise.all(effects.map((effect) => effect()))
    expect(text(render(AuditLogsTable))).not.toContain('auditLogs.export')
  })

  test('loads logs, applies the search filter, and recovers from a failed refresh', async () => {
    const log = {
      id: 'log-1', created_at: '2026-01-02T03:04:05Z', status: 'failed', action: 'login_failed', operation: 'read',
      username: 'ada', resource_type: 'session', resource_name: 'primary', ip_address: '127.0.0.1', error_message: 'denied',
    }
    api.getActions.mockResolvedValue([{ value: 'login_failed', translation_key: 'auditLogs.actionLoginFailed', fallback_label: 'Login failed' }])
    api.list.mockResolvedValue({ items: [log], total_pages: 2 })

    expect(text(render(AuditLogsTable))).toContain('auditLogs.loading')
    await Promise.all(effects.map((effect) => effect()))
    let tree = render(AuditLogsTable)
    expect(text(tree)).toContain('ada')
    expect(text(tree)).toContain('Login failed')

    const input = findDeep(tree, (element) => element.props.placeholder === 'auditLogs.searchPlaceholder')
    expect(input).toBeDefined()
    input!.props.onChange({ target: { value: 'ada' } })
    tree = render(AuditLogsTable)
    await effects[0]()
    expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'ada', page: 1 }))

    api.list.mockRejectedValueOnce(new Error('refresh unavailable'))
    await effects[0]()
    expect(text(render(AuditLogsTable))).toContain('ada')
  })
})
