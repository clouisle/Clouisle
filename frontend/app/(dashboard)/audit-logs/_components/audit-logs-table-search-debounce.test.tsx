import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const list = mock()
const getActions = mock(async () => [])
const exportLogs = mock(async (...args: [unknown, 'csv' | 'json']) => { void args; return new Blob([]) })

const element = (tag: string) => {
  const Component = ({ children, render, ...props }: React.PropsWithChildren<{ render?: React.ReactElement } & Record<string, unknown>>) => {
    if (render) return React.cloneElement(render, props)
    return React.createElement(tag, props, children)
  }
  Component.displayName = tag
  return Component
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(value)) return text(value.props.children)
  if (value && typeof value === 'object' && 'children' in value) return text(value.children)
  return ''
}

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => Object.assign(
    (key: string, values?: Record<string, unknown>) =>
      values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
    { has: () => false },
  ),
}))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/lib/api/admin/audit-logs', () => ({
  auditLogsApi: { list, getActions, export: exportLogs },
}))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
// The debounce hook is intentionally not mocked: the real 300ms timer is under test.
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/card', () => ({
  Card: element('section'), CardContent: element('div'), CardHeader: element('header'), CardTitle: element('h2'),
}))
mock.module('@/components/ui/select', () => ({
  Select: element('select'), SelectContent: element('div'), SelectItem: element('option'),
  SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element('div'), TooltipContent: element('span'), TooltipTrigger: element('span'),
}))
mock.module('./audit-log-drawer', () => ({ AuditLogDrawer: () => null }))
mock.module('@/app/(dashboard)/activities/_components/workflow-run-drawer', () => ({ WorkflowRunDrawer: () => null }))
mock.module('lucide-react', () => Object.fromEntries([
  'Download', 'Eye', 'Search', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'FileText', 'FileJson',
].map((name) => [name, element('svg')])) )

// The component is imported after the module mocks above are registered, which a
// static import cannot guarantee.
const { AuditLogsTable } = await import('./audit-logs-table')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const log = {
  id: 'log-1', created_at: '2026-01-01T10:00:00Z', status: 'success', action: 'login', operation: 'create',
  username: 'Ada', resource_type: 'session', resource_name: null, ip_address: '127.0.0.1',
}

const renderers: ReactTestRenderer[] = []

async function render() {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<AuditLogsTable />)
    await Promise.resolve()
  })
  renderers.push(renderer)
  return renderer
}

function searchInput(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('input').find((node) => node.props.placeholder === 'auditLogs.searchPlaceholder')!
}

function pageButtons(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('button').filter((button) => button.props.className === 'h-8 w-8' && 'disabled' in button.props)
}

async function type(renderer: ReactTestRenderer, value: string) {
  await act(async () => searchInput(renderer).props.onChange({ target: { value } }))
}

async function waitForDebounce(ms: number) {
  await act(async () => {
    const { promise, resolve } = Promise.withResolvers<void>()
    setTimeout(resolve, ms)
    await promise
  })
}

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
  list.mockClear()
})

describe('AuditLogsTable search debounce', () => {
  test('keeps the input responsive, waits 300ms, and collapses rapid edits into one query', async () => {
    list.mockImplementation(async () => ({ items: [log], total_pages: 1 }))
    const renderer = await render()
    expect(list).toHaveBeenCalledTimes(1)
    list.mockClear()

    await type(renderer, 'a')
    expect(searchInput(renderer).props.value).toBe('a')
    expect(renderer.root.findAllByType('button').filter((button) => text(button).includes('common.reset')).length).toBe(1)

    await type(renderer, 'al')
    await type(renderer, 'ale')
    await type(renderer, 'alex')
    expect(searchInput(renderer).props.value).toBe('alex')
    expect(list).not.toHaveBeenCalled()

    await waitForDebounce(150)
    expect(list).not.toHaveBeenCalled()

    await waitForDebounce(500)
    expect(list).toHaveBeenCalledTimes(1)
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ page: 1, page_size: 20, search: 'alex' }))
  })

  test('settles an edit made on a later page into a single first-page request', async () => {
    list.mockImplementation(async () => ({ items: [log], total_pages: 3 }))
    const renderer = await render()
    await act(async () => pageButtons(renderer)[3].props.onClick())
    expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3 }))
    list.mockClear()

    await type(renderer, 'a')
    await type(renderer, 'ad')
    await type(renderer, 'admin')
    await waitForDebounce(500)

    expect(list).toHaveBeenCalledTimes(1)
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ page: 1, search: 'admin' }))
  })

  test('exports the current raw query on an explicit click', async () => {
    list.mockImplementation(async () => ({ items: [log], total_pages: 1 }))
    const renderer = await render()
    const createObjectURL = mock(() => 'blob:here')
    const originalCreateObjectURL = window.URL.createObjectURL
    const originalRevokeObjectURL = window.URL.revokeObjectURL
    window.URL.createObjectURL = createObjectURL
    window.URL.revokeObjectURL = mock(() => {})

    try {
      await type(renderer, 'admin')
      await act(async () => renderer.root.findAllByType('button').find((button) => text(button).includes('auditLogs.exportCSV'))!.props.onClick())

      expect(exportLogs).toHaveBeenCalledWith({ search: 'admin', status: undefined, action: undefined }, 'csv')
      expect(createObjectURL).toHaveBeenCalled()
    } finally {
      window.URL.createObjectURL = originalCreateObjectURL
      window.URL.revokeObjectURL = originalRevokeObjectURL
    }
  })
})
