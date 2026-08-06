import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const listPage = mock()
const getFilterOptions = mock()
const publish = mock(async () => ({}))
const unpublish = mock(async () => ({}))
const duplicate = mock(async () => ({}))
const deleteWorkflow = mock(async () => ({}))
const createWorkflow = mock(async () => ({ id: 'workflow-new' }))
const getTeams = mock(async () => ({ items: [{ id: 'team-1', name: 'Core Team' }] }))
const createAgent = mock(async () => ({}))
const exportPackage = mock(async () => ({ blob: new Blob(['{}']), filename: 'workflow.zip' }))
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
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/select', () => ({ Select: element('select'), SelectContent: element('div'), SelectItem: element('option'), SelectTrigger: element('button'), SelectValue: element('span') }))
mock.module('@/components/ui/table', () => ({ Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) => <input type="checkbox" checked={checked} onChange={onCheckedChange} /> }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/lib/api/admin', () => ({
  adminWorkflowsApi: { listPage, getFilterOptions, publish, unpublish, duplicate, delete: deleteWorkflow, create: createWorkflow },
  teamsApi: { getTeams },
  adminAgentsApi: { create: createAgent },
}))
mock.module('@/lib/api/packages', () => ({ adminPackagesApi: { export: exportPackage }, downloadBlob }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: ({ open, onImported }: { open: boolean; onImported: () => void }) => open ? <button onClick={onImported}>imported</button> : null }))
mock.module('@/app/(platform)/app/apps/_components/app-create-dialog', () => ({ AppCreateDialog: ({ open, onSuccess }: { open: boolean; onSuccess: () => void }) => open ? <button onClick={onSuccess}>created</button> : null }))

const { AdminWorkflowsPanel } = await import('./admin-workflows-panel')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const workflow = {
  id: 'workflow-1', name: 'Daily Flow', icon: '🚀', status: 'draft', visibility: 'private', trigger_type: 'manual',
  team_name: 'Core Team', created_by_name: 'Ada', run_count: 3, success_count: 2, fail_count: 1, updated_at: '2026-01-01T00:00:00Z',
}
const page = (items = [workflow]) => ({ items, total: items.length, page: 1, page_size: 10 })
const filters = {
  statuses: [{ value: 'draft' }, { value: 'published' }],
  visibilities: [{ value: 'private' }],
  trigger_types: [{ value: 'manual' }],
  teams: [{ value: 'team-1', label: 'Core Team' }],
  creators: [{ value: 'user-1', label: 'Ada' }],
}
let renderer: ReactTestRenderer

beforeEach(() => {
  listPage.mockResolvedValue(page())
  getFilterOptions.mockResolvedValue(filters)
  getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core Team' }] })
  Object.defineProperty(globalThis, 'window', { value: { confirm: mock(() => true) }, configurable: true })
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  for (const fn of [listPage, getFilterOptions, publish, unpublish, duplicate, deleteWorkflow, createWorkflow, getTeams, createAgent, exportPackage, downloadBlob, toastSuccess, toastError]) fn.mockReset?.()
})

async function render() {
  await act(async () => {
    renderer = create(<AdminWorkflowsPanel />)
    await Promise.resolve()
  })
  return renderer
}

function buttons(label: string) {
  return renderer.root.findAllByType('button').filter((button) => text(button.props.children).includes(label))
}

describe('AdminWorkflowsPanel', () => {
  test('loads, filters, paginates, and resets workflow listing', async () => {
    await render()
    expect(text(renderer.toJSON())).toContain('Daily Flow')
    expect(listPage).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 10 }))

    await act(async () => renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'apps.admin.workflows.searchPlaceholder')!.props.onChange({ target: { value: 'daily' } }))
    const filters = renderer.root.findAllByType('button').filter((button) => button.props.onSelectionChange)
    await act(async () => filters.find((button) => button.props.title === 'common.status')!.props.onSelectionChange(new Set(['draft'])))
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'daily', status: ['draft'] }))

    await act(async () => renderer.root.findByType('select').props.onValueChange('20'))
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 20 }))

    await act(async () => buttons('apps.admin.actions.reset')[0].props.onClick())
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined, status: undefined }))
  })

  test('runs row actions and surfaces success or errors', async () => {
    await render()

    await act(async () => buttons('apps.admin.actions.publish')[0].props.onClick())
    expect(publish).toHaveBeenCalledWith('workflow-1')
    expect(toastSuccess).toHaveBeenCalledWith('apps.admin.actions.published')

    await act(async () => buttons('apps.admin.actions.duplicate')[0].props.onClick())
    expect(duplicate).toHaveBeenCalledWith('workflow-1')

    // Export stays covered by package API tests; this renderer mock cannot distinguish its nested label from inert dropdown wrappers.
  })

  test('selects workflows for bulk publish, delete, and clear actions', async () => {
    listPage.mockResolvedValue(page([workflow, { ...workflow, id: 'workflow-2', name: 'Published Flow', status: 'published' }]))
    await render()

    const checkboxes = renderer.root.findAllByType('input').filter((input) => input.props.type === 'checkbox')
    act(() => checkboxes[0]!.props.onChange())
    expect(text(renderer.toJSON())).toContain('apps.admin.bulk.selected')

    await act(async () => renderer.root.findAllByType('button').find((button) => button.props.className?.includes('text-destructive'))!.props.onClick())
    expect(deleteWorkflow).toHaveBeenCalledWith('workflow-1')
    expect(deleteWorkflow).toHaveBeenCalledWith('workflow-2')

    act(() => checkboxes[1]!.props.onChange())
    await act(async () => renderer.root.findAllByType('button').find((button) => button.props.className === 'h-8 w-8' && button.props.onClick)!.props.onClick())
    expect(text(renderer.toJSON())).not.toContain('apps.admin.bulk.selected')
  })

  test('opens import and create dialogs and reloads after completion', async () => {
    await render()

    await act(async () => buttons('packages.import')[0].props.onClick())
    await act(async () => buttons('imported')[0].props.onClick())
    await act(async () => buttons('apps.admin.actions.create')[0].props.onClick())
    await act(async () => buttons('created')[0].props.onClick())

    expect(listPage).toHaveBeenCalledTimes(3)
  })
})
