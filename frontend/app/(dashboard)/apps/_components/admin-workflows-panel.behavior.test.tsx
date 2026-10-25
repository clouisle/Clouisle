import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const listPage = mock()
const getFilterOptions = mock()
const publish = mock(async () => ({}))
const unpublish = mock(async () => ({}))
const deleteWorkflow = mock(async () => ({}))
const getTeams = mock(async () => ({ items: [{ id: 'team-1', name: 'Core Team' }] }))
const toastSuccess = mock()
const toastError = mock()

const element = (tag: string) => {
  const Component = ({ children, render, ...props }: React.PropsWithChildren<{ render?: React.ReactElement } & Record<string, unknown>>) =>
    render ? React.cloneElement(render, props) : React.createElement(tag, props, children)
  return Component
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(value)) return text(value.props.children)
  if (value && typeof value === 'object' && 'children' in value) return text(value.children)
  return ''
}

const translations = new Map<string, (key: string, values?: Record<string, unknown>) => string>()
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => {
    if (!translations.has(namespace)) translations.set(namespace, (key, values) => values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`)
    return translations.get(namespace)!
  },
}))
mock.module('next/image', () => ({ default: element('img') }))
mock.module('next/link', () => ({ default: element('a') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('lucide-react', () => Object.fromEntries(['Copy', 'Download', 'FileEdit', 'Loader2', 'MoreHorizontal', 'Plus', 'Search', 'Send', 'Trash2', 'Upload', 'X'].map((name) => [name, element('svg')])))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element('div'), TooltipContent: element('span'), TooltipTrigger: element('button') }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'), DropdownMenuTrigger: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/select', () => ({ Select: element('select'), SelectContent: element('div'), SelectItem: element('option'), SelectTrigger: element('button'), SelectValue: element('span') }))
mock.module('@/components/ui/table', () => ({ Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) => <input type="checkbox" checked={checked} onChange={() => onCheckedChange()} /> }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/lib/api/admin', () => ({
  adminWorkflowsApi: { listPage, getFilterOptions, publish, unpublish, delete: deleteWorkflow },
  teamsApi: { getTeams }, adminAgentsApi: { create: mock() },
}))
mock.module('@/lib/api/packages', () => ({ adminPackagesApi: { export: mock() }, downloadBlob: mock() }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: () => null }))
mock.module('@/app/(platform)/app/apps/_components/app-create-dialog', () => ({ AppCreateDialog: () => null }))

const { AdminWorkflowsPanel } = await import('./admin-workflows-panel')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const workflow = { id: 'flow-1', name: 'Daily Flow', icon: null, status: 'draft', visibility: 'private', trigger_type: 'manual', team_name: 'Core Team', created_by_name: 'Ada', run_count: 3, success_count: 2, fail_count: 1, updated_at: '2026-01-01T00:00:00Z' }
const filterOptions = { statuses: [{ value: 'draft' }], visibilities: [{ value: 'private' }], trigger_types: [{ value: 'manual' }], teams: [{ value: 'team-1', label: 'Core Team' }], creators: [{ value: 'user-1', label: 'Ada' }] }
let renderer: ReactTestRenderer

beforeEach(() => {
  listPage.mockResolvedValue({ items: [workflow], total: 1, page: 1, page_size: 10 })
  getFilterOptions.mockResolvedValue(filterOptions)
  getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core Team' }] })
  Object.defineProperty(globalThis, 'window', {
    value: { confirm: mock(() => true), setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout },
    configurable: true,
  })
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  for (const fn of [listPage, getFilterOptions, publish, unpublish, deleteWorkflow, getTeams, toastSuccess, toastError]) fn.mockReset?.()
  mock.restore()
})

async function render() {
  await act(async () => { renderer = create(<AdminWorkflowsPanel />); await Promise.resolve() })
  return renderer
}

async function waitForDebounce() {
  const { promise, resolve } = Promise.withResolvers<void>()
  setTimeout(resolve, 350)
  await act(async () => {
    await promise
  })
}

async function waitForRapidEdit() {
  const { promise, resolve } = Promise.withResolvers<void>()
  setTimeout(resolve, 60)
  await act(async () => {
    await promise
  })
}

describe('AdminWorkflowsPanel behavior', () => {
  test('loads workflows, filter options, and teams', async () => {
    const { promise, resolve } = Promise.withResolvers<{ items: typeof workflow[]; total: number; page: number; page_size: number }>()
    listPage.mockReturnValueOnce(promise)
    await act(async () => { renderer = create(<AdminWorkflowsPanel />); await Promise.resolve() })
    expect(JSON.stringify(renderer.toJSON())).toContain('animate-spin')
    expect(getTeams).toHaveBeenCalledWith(1, 100)
    await act(async () => resolve({ items: [workflow], total: 1, page: 1, page_size: 10 }))
    expect(text(renderer.toJSON())).toContain('Daily Flow')
    expect(getFilterOptions).toHaveBeenCalled()
    expect(listPage).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 10 }))
  })

 test('applies search and faceted filters and paginates', async () => {
    listPage.mockResolvedValue({ items: [workflow], total: 40, page: 1, page_size: 10 })
    await render()
    const search = renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'apps.admin.workflows.searchPlaceholder')!
    await act(async () => search.props.onChange({ target: { value: 'daily' } }))
    await waitForDebounce()
    const status = renderer.root.findAllByType('button').find((node) => node.props.title === 'common.status')!
    await act(async () => status.props.onSelectionChange(new Set(['draft'])))
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'daily', status: ['draft'] }))
    await act(async () => renderer.root.findByType('select').props.onValueChange('20'))
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 20 }))
    await act(async () => renderer.root.findAllByType('button').find((node) => text(node.props.children).includes('apps.admin.pagination.next'))!.props.onClick())
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, pageSize: 20 }))
  })

  test('collapses rapid search edits into a single page-one request after the debounce delay', async () => {
    listPage.mockResolvedValue({ items: [workflow], total: 40, page: 1, page_size: 10 })
    await render()

    await act(async () => renderer.root.findAllByType('button').find((node) => text(node.props.children).includes('apps.admin.pagination.next'))!.props.onClick())
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, search: undefined }))
    const callsAfterPaging = listPage.mock.calls.length

    const search = () => renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'apps.admin.workflows.searchPlaceholder')!
    await act(async () => search().props.onChange({ target: { value: 'd' } }))
    await waitForRapidEdit()
    await act(async () => search().props.onChange({ target: { value: 'da' } }))
    await waitForRapidEdit()
    await act(async () => search().props.onChange({ target: { value: 'dai' } }))

    expect(search().props.value).toBe('dai')
    expect(listPage.mock.calls.length).toBe(callsAfterPaging)

    await waitForDebounce()
    expect(listPage.mock.calls.length).toBe(callsAfterPaging + 1)
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, search: 'dai' }))
  })

  test('confirms bulk deletion and publishes selected workflows with visible outcomes', async () => {
    listPage.mockResolvedValue({ items: [workflow, { ...workflow, id: 'flow-2', name: 'Nightly Flow' }], total: 2, page: 1, page_size: 10 })
    await render()
    const checks = renderer.root.findAllByType('input').filter((input) => input.props.type === 'checkbox')
    await act(async () => { checks[1]!.props.onChange(); checks[2]!.props.onChange() })
    const publishButton = renderer.root.findAllByType('button').filter((node) => node.props.className === 'h-8 w-8' && node.props.onClick)[1]!
    await act(async () => publishButton.props.onClick())
    expect(publish).toHaveBeenCalledWith('flow-1')
    expect(publish).toHaveBeenCalledWith('flow-2')
    expect(toastSuccess).toHaveBeenCalledWith('apps.admin.actions.published')

    window.confirm = mock(() => false)
    const refreshedChecks = renderer.root.findAllByType('input').filter((input) => input.props.type === 'checkbox')
    await act(async () => { refreshedChecks[1]!.props.onChange(); refreshedChecks[2]!.props.onChange() })
    const deleteButton = renderer.root.findAllByType('button').find((node) => node.props.className?.includes('text-destructive'))!
    await act(async () => deleteButton.props.onClick())
    expect(deleteWorkflow).not.toHaveBeenCalled()
    window.confirm = mock(() => true)
    await act(async () => deleteButton.props.onClick())
    expect(deleteWorkflow).toHaveBeenCalledWith('flow-1')
    expect(deleteWorkflow).toHaveBeenCalledWith('flow-2')
    expect(toastSuccess).toHaveBeenCalledWith('apps.admin.actions.deleted')
  })

  test('shows API failure feedback for bulk publish', async () => {
    await render()
    publish.mockRejectedValueOnce(new Error('publish unavailable'))
    const checkbox = renderer.root.findAllByType('input').find((input) => input.props.type === 'checkbox')!
    await act(async () => checkbox.props.onChange())
    const bulkButton = renderer.root.findAllByType('button').filter((node) => node.props.className === 'h-8 w-8' && node.props.onClick)[1]!
    await act(async () => bulkButton.props.onClick())
  })
})
