import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const listPage = mock()
const getFilterOptions = mock()
const getById = mock(async () => ({}))
const update = mock(async () => ({}))
const publish = mock(async () => ({}))
const unpublish = mock(async () => ({}))
const duplicate = mock(async () => ({}))
const deleteAgent = mock(async () => ({}))
const createAgent = mock(async () => ({}))
const getTeams = mock(async () => ({ items: [{ id: 'team-1', name: 'Core Team' }] }))
const exportPackage = mock(async () => ({ blob: new Blob(['{}']), filename: 'agent.zip' }))
const downloadBlob = mock()
const toastSuccess = mock()
const toastError = mock()

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
  if (value && typeof value === 'object' && 'children' in value) return text((value as { children?: unknown }).children)
  if (value && typeof value === 'object' && 'props' in value) return text((value as { props?: { children?: unknown } }).props?.children)
  return ''
}

const translations = new Map<string, (key: string, values?: Record<string, unknown>) => string>()
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => {
    if (!translations.has(namespace)) {
      translations.set(namespace, (key: string, values?: Record<string, unknown>) =>
        values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`)
    }
    return translations.get(namespace)!
  },
}))
mock.module('next/image', () => ({ default: element('img') }))
mock.module('next/link', () => ({ default: element('a') }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('lucide-react', () => Object.fromEntries([
  'Copy', 'Download', 'FileEdit', 'Loader2', 'MoreHorizontal', 'Plus', 'Search', 'Send', 'Trash2', 'Upload', 'X',
].map((name) => [name, element('svg')])))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element('div'), TooltipContent: element('span'), TooltipTrigger: element('button') }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'), DropdownMenuSeparator: element('div'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/select', () => ({ Select: element('select'), SelectContent: element('div'), SelectItem: element('option'), SelectTrigger: element('button'), SelectValue: element('span') }))
mock.module('@/components/ui/table', () => ({ Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) => <input type="checkbox" checked={checked} onChange={onCheckedChange} /> }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/lib/api/admin', () => ({
  adminAgentsApi: { getById, update, publish, unpublish, listPage, getFilterOptions, duplicate, delete: deleteAgent, create: createAgent },
  adminWorkflowsApi: { listPage: mock(), getFilterOptions: mock() },
  teamsApi: { getTeams },
}))
mock.module('@/lib/api/packages', () => ({ adminPackagesApi: { export: exportPackage }, downloadBlob }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: () => null }))
mock.module('@/app/(platform)/app/apps/_components/app-create-dialog', () => ({ AppCreateDialog: () => null }))

const { AdminAgentsPanel } = await import('./admin-agents-panel')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const agent = { id: 'agent-1', name: 'Support Bot', status: 'draft', visibility: 'private', team_name: 'Core Team', created_by_name: 'Ada', conversation_count: 1, message_count: 2, updated_at: '2026-01-01T00:00:00Z', icon: null }
const filters = { statuses: [{ value: 'draft' }], visibilities: [{ value: 'private' }], teams: [{ value: 'team-1', label: 'Core Team' }], creators: [{ value: 'user-1', label: 'Ada' }] }
let renderer: ReactTestRenderer

beforeEach(() => {
  listPage.mockResolvedValue({ items: [agent], total: 25, page: 1, page_size: 10 })
  getFilterOptions.mockResolvedValue(filters)
  getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core Team' }] })
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  for (const fn of [listPage, getFilterOptions, getById, update, publish, unpublish, duplicate, deleteAgent, createAgent, getTeams, exportPackage, downloadBlob, toastSuccess, toastError]) fn.mockReset?.()
})

async function render() {
  await act(async () => { renderer = create(<AdminAgentsPanel />); await Promise.resolve() })
  return renderer
}

async function waitForDebounce() {
  const { promise, resolve } = Promise.withResolvers<void>()
  setTimeout(resolve, 350)
  await act(async () => { await promise })
}

async function waitForRapidEdit() {
  const { promise, resolve } = Promise.withResolvers<void>()
  setTimeout(resolve, 60)
  await act(async () => { await promise })
}

describe('AdminAgentsPanel search debounce', () => {
  test('collapses rapid search edits into a single page-one request after the debounce delay', async () => {
    await render()
    await act(async () => renderer.root.findAllByType('button').find((node) => text(node.props.children).includes('apps.admin.pagination.next'))!.props.onClick())
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, search: undefined }))
    const callsAfterPaging = listPage.mock.calls.length

    const search = () => renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'apps.admin.agents.searchPlaceholder')!
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
})
