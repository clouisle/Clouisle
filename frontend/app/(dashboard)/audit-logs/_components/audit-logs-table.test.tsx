import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const list = mock()
const getActions = mock(() => Promise.resolve([]))
const exportLogs = mock()
const toastSuccess = mock()

const element = (tag: string) => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  Component.displayName = tag
  return Component
}

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => Object.assign((key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key, { has: (key: string) => key === 'operationCreate' || key === 'actionLogin' }),
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/admin/audit-logs', () => ({ auditLogsApi: { list, getActions, export: exportLogs } }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/card', () => ({ Card: element('section'), CardContent: element('div'), CardHeader: element('header'), CardTitle: element('h2') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'), SelectContent: element('div'), SelectItem: element('option'), SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'),
  DropdownMenuTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</>,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement } & Record<string, unknown>) =>
    render ? React.cloneElement(render, { ...props, ...(children !== undefined ? { children } : {}) }) : <button {...props}>{children}</button>,
}))
mock.module('./audit-log-drawer', () => ({
  AuditLogDrawer: ({ log, open }: { log: { id: string } | null; open: boolean }) => open && log ? <aside role="dialog" aria-label={`log-${log.id}`} /> : null,
}))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({
  WorkflowRunDrawer: ({ open }: { open: boolean }) => open ? <aside role="dialog" aria-label="workflow-run" /> : null,
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Download', 'Eye', 'Search', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'FileText', 'FileJson',
].map((name) => [name, element('svg')])))

const { AuditLogsTable } = await import('./audit-logs-table')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

globalThis.window = {
  getSelection: () => ({ toString: () => '' }),
  URL: { createObjectURL: () => '', revokeObjectURL: () => {} },
} as unknown as Window & typeof globalThis

const renderers: ReactTestRenderer[] = []

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<AuditLogsTable />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  list.mockReset()
  getActions.mockReset().mockResolvedValue([])
  exportLogs.mockReset()
  toastSuccess.mockReset()
})

describe('AuditLogsTable', () => {
  test('keeps the table and loading state visible while logs load', async () => {
    list.mockImplementation(() => new Promise(() => {}))

    const renderer = await render()

    expect(renderer.root.findByType('table')).toBeDefined()
    expect(JSON.stringify(renderer.toJSON())).toContain('loading')
  })

  test('renders translated log data, filters, paginates, and opens details', async () => {
    list.mockResolvedValue({
      items: [{ id: 'log-1', created_at: '2026-01-01T10:00:00Z', status: 'success', action: 'login', operation: 'create', username: null, resource_type: 'session', resource_name: null, ip_address: null }],
      total_pages: 2,
    })
    getActions.mockResolvedValue([{ value: 'login', translation_key: 'auditLogs.actionLogin', fallback_label: 'Login' }])

    const renderer = await render()
    const tree = JSON.stringify(renderer.toJSON())
    expect(tree).toContain('system')
    expect(tree).toContain('actionLogin')
    expect(tree).toContain('operationCreate')
    expect(tree).toContain('pageInfo')
    expect(tree).toContain('total\\\":2')

    await act(async () => renderer.root.findByType('input').props.onChange({ target: { value: 'alex' } }))
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, search: 'alex' }))

    act(() => renderer.root.findAllByType('tr')[1].props.onClick())
    expect(renderer.root.findByProps({ role: 'dialog' }).props['aria-label']).toBe('log-log-1')

    await act(async () => renderer.root.findAllByType('button').find((node) => node.props.onClick && node.props.disabled === false)!.props.onClick())
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, search: 'alex' }))
  })

  test('exports CSV and confirms completion', async () => {
    list.mockResolvedValue({ items: [], total_pages: 0 })
    exportLogs.mockResolvedValue(new Blob(['id']))
    const createObjectURL = mock(() => 'blob:test')
    const revokeObjectURL = mock()
    const click = mock()
    const anchor = { href: '', download: '', click }
    globalThis.window.URL.createObjectURL = createObjectURL
    globalThis.window.URL.revokeObjectURL = revokeObjectURL
    globalThis.document = {
      createElement: () => anchor,
      body: { appendChild: () => anchor, removeChild: () => anchor },
    } as unknown as Document

    const renderer = await render()
    await act(async () => renderer.root.findAllByType('button').find((node) => node.children.includes('exportCSV'))!.props.onClick())

    expect(exportLogs).toHaveBeenCalledWith({ search: undefined, status: undefined, action: undefined }, 'csv')
    expect(createObjectURL).toHaveBeenCalled()
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
    expect(toastSuccess).toHaveBeenCalledWith('exportSuccess')
  })
})
