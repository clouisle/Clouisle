import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getModels = mock()
const updateModel = mock(async () => ({}))
const setDefault = mock(async () => ({}))
const testConnection = mock(async () => ({ success: true }))
const deleteModel = mock(async () => ({}))
const getProviders = mock(async () => [{ code: 'openai' }, { code: 'custom' }])
const getModelTypes = mock(async () => [{ code: 'chat' }, { code: 'custom_type' }])
const toastSuccess = mock(() => {})
const toastLoading = mock(() => 'toast-1')
const toastError = mock(() => {})
const toastDismiss = mock(() => {})
let permissions = new Set(['admin:model:create', 'admin:model:update', 'admin:model:delete'])

mock.module('next-intl', () => ({
  useTranslations: () => {
    const translate = (key: string, values?: Record<string, unknown>) => values?.count === undefined ? key : `${key}:${values.count}`
    translate.has = (key: string) => key === 'providers.openai' || key === 'modelTypes.chat'
    return translate
  },
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, loading: toastLoading, error: toastError, dismiss: toastDismiss } }))
mock.module('lucide-react', () => ({
  Plus: () => null, Search: () => null, MoreHorizontal: () => null, Pencil: () => null,
  Trash2: () => null, ChevronLeft: () => null, ChevronRight: () => null, ChevronsLeft: () => null,
  ChevronsRight: () => null, X: () => null, Star: () => null, Power: () => null,
  PowerOff: () => null, TestTube: () => null, GraduationCap: () => null,
}))
mock.module('@/lib/api/admin/models', () => ({ modelsApi: { getModels, updateModel, setDefault, testConnection, deleteModel } }))
mock.module('@/lib/api/models', () => ({ modelsApi: { getProviders, getModelTypes } }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ permission, children }: React.PropsWithChildren<{ permission: string }>) => permissions.has(permission) ? <>{children}</> : null,
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/components/onboarding/onboarding-provider', () => ({
  useOptionalOnboarding: () => ({ startTour: mock() }),
}))

const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
const Button = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>
const FacetedFilter = ({ title, options, onSelectionChange }: { title: string; options: unknown[]; onSelectionChange: (values: Set<string>) => void }) => (
  <button data-filter={title} data-options={JSON.stringify(options)} onClick={() => onSelectionChange(new Set())}>{title}</button>
)
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) => <input type="checkbox" checked={checked} onChange={onCheckedChange} /> }))
mock.module('@/components/ui/table', () => ({ Table: passthrough, TableBody: passthrough, TableCell: passthrough, TableHead: passthrough, TableHeader: passthrough, TableRow: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div> }))
mock.module('@/components/ui/select', () => ({ Select: ({ children, onValueChange, ...props }: React.PropsWithChildren<{ onValueChange: (value: string) => void }>) => <select {...props} onChange={(event) => onValueChange(event.target.value)}>{children}</select>, SelectContent: passthrough, SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>, SelectTrigger: passthrough, SelectValue: passthrough }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: passthrough, DropdownMenuContent: passthrough, DropdownMenuItem: Button, DropdownMenuSeparator: () => null, DropdownMenuTrigger: passthrough }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: FacetedFilter }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: passthrough, TooltipContent: passthrough, TooltipTrigger: ({ render, ...props }: { render: React.ReactElement } & Record<string, unknown>) => React.cloneElement(render, props) }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: passthrough, AlertDialogAction: Button, AlertDialogCancel: passthrough, AlertDialogContent: passthrough, AlertDialogDescription: passthrough, AlertDialogFooter: passthrough, AlertDialogHeader: passthrough, AlertDialogTitle: passthrough }))
mock.module('./model-dialog', () => ({ ModelDialog: ({ open, model, onOpenChange, onSuccess }: { open: boolean; model: unknown; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => <div data-testid="model-dialog" data-open={open} data-model={model ? 'selected' : 'new'}><button onClick={() => onOpenChange(false)}>close-model</button><button onClick={onSuccess}>save-model</button></div> }))
mock.module('./delete-model-dialog', () => ({ DeleteModelDialog: ({ open, model, onOpenChange, onSuccess }: { open: boolean; model: unknown; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => <div data-testid="delete-dialog" data-open={open} data-model={model ? 'selected' : 'none'}><button onClick={() => onOpenChange(false)}>close-delete</button><button onClick={onSuccess}>deleted-model</button></div> }))

const { ModelsClient } = await import('./models-client')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const model = {
  id: 'model-1', name: 'GPT Test', provider: 'openai', model_id: 'gpt-test', model_type: 'chat',
  base_url: null, has_api_key: true, context_length: null, max_output_tokens: null, input_price: null,
  output_price: null, default_params: null, capabilities: null, config: null, is_enabled: true,
  is_default: false, sort_order: 0, created_at: '', updated_at: '',
}
const second = { ...model, id: 'model-2', name: 'Custom', provider: 'custom', provider_display_name: 'Acme Gateway', model_type: 'custom_type', has_api_key: false, is_enabled: false, is_default: true }
const page = (items = [model, second], total = items.length) => ({ items, total, page: 1, page_size: 10 })
const renderers: ReactTestRenderer[] = []

beforeEach(() => {
  permissions = new Set(['admin:model:create', 'admin:model:update', 'admin:model:delete'])
  getModels.mockReset(); getModels.mockResolvedValue(page())
  getProviders.mockReset(); getProviders.mockResolvedValue([{ code: 'openai' }, { code: 'custom' }])
  getModelTypes.mockReset(); getModelTypes.mockResolvedValue([{ code: 'chat' }, { code: 'custom_type' }])
  for (const fn of [updateModel, setDefault, testConnection, deleteModel]) { fn.mockReset(); fn.mockResolvedValue({}) }
  for (const fn of [toastSuccess, toastLoading, toastError, toastDismiss]) fn.mockClear()
  toastLoading.mockReturnValue('toast-1')
  Object.defineProperty(globalThis, 'window', { value: { confirm: mock(() => true) }, configurable: true })
})
afterEach(() => { for (const renderer of renderers) act(() => renderer.unmount()); renderers.length = 0 })

function render() {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<ModelsClient />) })
  renderers.push(renderer!)
  return renderer!
}
async function settle() { await act(async () => {}) }
function buttons(renderer: ReactTestRenderer, name: string) { return renderer.root.findAllByType('button').filter((button) => button.findAll((node) => node.children.includes(name)).length > 0) }
function checkbox(renderer: ReactTestRenderer, index: number) { return renderer.root.findAllByProps({ type: 'checkbox' })[index] }
function selectedRows(renderer: ReactTestRenderer) { return renderer.root.findAllByProps({ 'data-state': 'selected' }).filter((node) => typeof node.type === 'string') }
function filter(renderer: ReactTestRenderer, name: string) { return renderer.root.findByProps({ 'data-filter': name }) }

async function click(renderer: ReactTestRenderer, name: string, occurrence = 0) {
  await act(async () => buttons(renderer, name)[occurrence].props.onClick())
}

describe('models client issue 255 coverage', () => {
  test('loads metadata and models, rendering translated and fallback labels plus all row states', async () => {
    const renderer = render()
    expect(JSON.stringify(renderer.toJSON())).toContain('loading')
    await settle()

    expect(getModels).toHaveBeenCalledWith({ page: 1, pageSize: 10 })
    expect(filter(renderer, 'provider').props['data-options']).toContain('providers.openai')
    expect(filter(renderer, 'provider').props['data-options']).toContain('custom')
    expect(JSON.stringify(renderer.toJSON())).toContain('configured')
    expect(JSON.stringify(renderer.toJSON())).toContain('notConfigured')
    expect(JSON.stringify(renderer.toJSON())).toContain('default')
    expect(JSON.stringify(renderer.toJSON())).toContain('Acme Gateway')
  })

  test('swallows metadata and list failures and reaches the empty state', async () => {
    getProviders.mockRejectedValueOnce(new Error('metadata'))
    getModels.mockRejectedValueOnce(new Error('models'))
    const renderer = render()
    await settle()
    expect(JSON.stringify(renderer.toJSON())).toContain('noModels')
  })

  test('applies search and every server filter branch, then resets them', async () => {
    const renderer = render(); await settle()
    const search = renderer.root.findByProps({ placeholder: 'filterModels' })
    act(() => search.props.onChange({ target: { value: 'gpt' } }))
    const filters = renderer.root.findAllByType(FacetedFilter)
    act(() => filters[0].props.onSelectionChange(new Set(['openai'])))
    act(() => filters[1].props.onSelectionChange(new Set(['chat'])))
    act(() => filters[2].props.onSelectionChange(new Set(['enabled'])))
    await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: 'gpt', provider: ['openai'], model_type: ['chat'], is_enabled: true })

    act(() => filters[2].props.onSelectionChange(new Set(['disabled'])))
    await settle()
    expect(getModels).toHaveBeenLastCalledWith(expect.objectContaining({ is_enabled: false }))
    await click(renderer, 'reset')
    await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 10 })
  })

  test('omits status when multiple values are selected and clears selection when a filter changes', async () => {
    const renderer = render(); await settle()
    act(() => checkbox(renderer, 0).props.onChange())
    expect(JSON.stringify(renderer.toJSON())).toContain('modelsSelected')
    const status = renderer.root.findAllByType(FacetedFilter)[2]
    act(() => status.props.onSelectionChange(new Set(['enabled', 'disabled'])))
    await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 10 })
    expect(JSON.stringify(renderer.toJSON())).not.toContain('modelsSelected')
  })

  test('selects all, clears all, toggles one row, and clears from the bulk toolbar', async () => {
    const renderer = render(); await settle()
    act(() => checkbox(renderer, 0).props.onChange())
    expect(selectedRows(renderer)).toHaveLength(2)
    act(() => checkbox(renderer, 0).props.onChange())
    expect(selectedRows(renderer)).toHaveLength(0)
    act(() => checkbox(renderer, 1).props.onChange())
    expect(selectedRows(renderer)).toHaveLength(1)
    act(() => checkbox(renderer, 1).props.onChange())
    expect(selectedRows(renderer)).toHaveLength(0)
    act(() => checkbox(renderer, 1).props.onChange())
    for (const button of renderer.root.findAllByType('button').filter((candidate) => candidate.props.className === 'h-8 w-8' && candidate.props.onClick)) {
      await act(async () => button.props.onClick())
      if (selectedRows(renderer).length === 0) break
    }
    expect(selectedRows(renderer)).toHaveLength(0)
  })

  test('opens and closes create, edit, and delete dialogs and refreshes their success callbacks', async () => {
    const renderer = render(); await settle()
    await click(renderer, 'createModel')
    expect(renderer.root.findByProps({ 'data-testid': 'model-dialog' }).props).toMatchObject({ 'data-open': true, 'data-model': 'new' })
    await click(renderer, 'close-model')
    await click(renderer, 'edit')
    expect(renderer.root.findByProps({ 'data-testid': 'model-dialog' }).props).toMatchObject({ 'data-open': true, 'data-model': 'selected' })
    await click(renderer, 'save-model'); await settle()
    await click(renderer, 'delete')
    expect(renderer.root.findByProps({ 'data-testid': 'delete-dialog' }).props).toMatchObject({ 'data-open': true, 'data-model': 'selected' })
    await click(renderer, 'close-delete')
    await click(renderer, 'deleted-model'); await settle()
    expect(getModels.mock.calls.length).toBeGreaterThanOrEqual(3)
  })

  test('toggles both model states, sets default, and swallows mutation failures', async () => {
    const renderer = render(); await settle()
    await click(renderer, 'disable'); await settle()
    expect(updateModel).toHaveBeenCalledWith('model-1', { is_enabled: false })
    expect(toastSuccess).toHaveBeenCalledWith('modelDisabled')
    await click(renderer, 'enable'); await settle()
    expect(updateModel).toHaveBeenCalledWith('model-2', { is_enabled: true })
    expect(toastSuccess).toHaveBeenCalledWith('modelEnabled')
    await click(renderer, 'setDefault'); await settle()
    expect(setDefault).toHaveBeenCalledWith('model-1')

    updateModel.mockRejectedValueOnce(new Error('update'))
    setDefault.mockRejectedValueOnce(new Error('default'))
    await click(renderer, 'disable'); await settle()
    await click(renderer, 'setDefault'); await settle()
  })

  test('covers connection success, generic fallback failures, blocked endpoints, video cancellation, and request errors', async () => {
    const renderer = render(); await settle()
    testConnection.mockResolvedValueOnce({ success: true })
    await click(renderer, 'testConnection', 0); await settle()
    expect(toastSuccess).toHaveBeenCalledWith('testSuccess', { id: 'toast-1' })

    testConnection.mockResolvedValueOnce({ success: false, message: '' })
    await click(renderer, 'testConnection', 0); await settle()
    expect(toastError).toHaveBeenCalledWith('testFailed', { id: 'toast-1' })

    const blockedEndpointError = new Error('model_endpoint_not_allowlisted')
    blockedEndpointError.name = 'ApiError'
    testConnection.mockRejectedValueOnce(blockedEndpointError)
    await click(renderer, 'testConnection', 0); await settle()
    expect(toastError).toHaveBeenCalledWith('model_endpoint_not_allowlisted', { id: 'toast-1' })

    getModels.mockResolvedValue(page([{ ...model, model_type: 'text_to_video' }]))
    act(() => renderer.root.findByProps({ placeholder: 'filterModels' }).props.onChange({ target: { value: 'video' } }))
    await settle()
    const confirm = mock(() => false)
    Object.defineProperty(globalThis, 'window', { value: { confirm }, configurable: true })
    await click(renderer, 'testConnection', 0); await settle()
    expect(confirm).toHaveBeenCalledWith('videoTestCostWarning')

    confirm.mockReturnValue(true)
    testConnection.mockRejectedValueOnce(new Error('network'))
    await click(renderer, 'testConnection', 0); await settle()
    expect(toastError).toHaveBeenCalledWith('testFailed', { id: 'toast-1' })
  })

  test('bulk deletes, closes after failure, and clears selected rows after success', async () => {
    const renderer = render(); await settle()
    act(() => checkbox(renderer, 0).props.onChange())
    await click(renderer, 'delete', buttons(renderer, 'delete').length - 1)
    deleteModel.mockRejectedValueOnce(new Error('delete'))
    await click(renderer, 'delete', buttons(renderer, 'delete').length - 1); await settle()

    act(() => checkbox(renderer, 0).props.onChange())
    await click(renderer, 'delete', buttons(renderer, 'delete').length - 1)
    await click(renderer, 'delete', buttons(renderer, 'delete').length - 1); await settle()
    expect(deleteModel).toHaveBeenCalledWith('model-1')
    expect(deleteModel).toHaveBeenCalledWith('model-2')
    expect(toastSuccess).toHaveBeenCalledWith('bulkDeleted:2')
  })

  test('covers all pagination callbacks and ignores an empty page-size value', async () => {
    getModels.mockResolvedValue(page([model], 45))
    const renderer = render(); await settle()
    const select = renderer.root.findByType('select')
    act(() => select.props.onChange({ target: { value: '' } }))
    act(() => select.props.onChange({ target: { value: '20' } })); await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 20 })

    const paging = renderer.root.findAllByType('button').filter((button) => button.props.className?.includes('h-8 w-8'))
    act(() => paging[2].props.onClick()); await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 2, pageSize: 20 })
    act(() => paging[1].props.onClick()); await settle()
    act(() => paging[3].props.onClick()); await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 3, pageSize: 20 })
    act(() => paging[0].props.onClick()); await settle()
    expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 20 })
  })

  test('hides create, row actions, and bulk delete without permissions; supports delete-only access', async () => {
    permissions = new Set()
    const renderer = render(); await settle()
    expect(buttons(renderer, 'createModel')).toHaveLength(0)
    expect(buttons(renderer, 'edit')).toHaveLength(0)
    act(() => checkbox(renderer, 1).props.onChange())
    expect(JSON.stringify(renderer.toJSON())).not.toContain('modelsSelected')

    permissions = new Set(['admin:model:delete'])
    const deleteOnly = render(); await settle()
    expect(buttons(deleteOnly, 'edit')).toHaveLength(0)
    expect(buttons(deleteOnly, 'delete').length).toBeGreaterThan(0)
  })
})
