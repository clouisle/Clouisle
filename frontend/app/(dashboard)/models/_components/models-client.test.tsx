import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getModels = mock()
const updateModel = mock(async () => ({}))
const setDefault = mock(async () => ({}))
const testConnection = mock(async () => ({ success: true }))
const deleteModel = mock(async () => ({}))
const getProviders = mock(async () => [])
const getModelTypes = mock(async () => [])
const success = mock()
const loading = mock(() => 'toast-1')
const error = mock()
const dismiss = mock()

const startTour = mock()
let canCreate = true
mock.module('next-intl', () => ({
  useTranslations: () => {
    const translate = (key: string) => key
    translate.has = () => false
    return translate
  },
}))
mock.module('sonner', () => ({ toast: { success, loading, error, dismiss } }))
mock.module('lucide-react', () => ({
  Plus: () => null, Search: () => null, MoreHorizontal: () => null, Pencil: () => null,
  Trash2: () => null, ChevronLeft: () => null, ChevronRight: () => null, ChevronsLeft: () => null,
  ChevronsRight: () => null, X: () => null, Star: () => null, Power: () => null,
  PowerOff: () => null, TestTube: () => null, GraduationCap: () => null,
}))
mock.module('@/lib/api/admin/models', () => ({ modelsApi: { getModels, updateModel, setDefault, testConnection, deleteModel } }))
mock.module('@/lib/api/models', () => ({ modelsApi: { getProviders, getModelTypes } }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ permission, children }: React.PropsWithChildren<{ permission: string }>) =>
    permission === 'admin:model:create' && !canCreate ? null : <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/components/onboarding/onboarding-provider', () => ({
  useOptionalOnboarding: () => ({ startTour }),
}))

const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={() => onCheckedChange(!checked)} /> }))
mock.module('@/components/ui/table', () => ({ Table: passthrough, TableBody: passthrough, TableCell: passthrough, TableHead: passthrough, TableHeader: passthrough, TableRow: passthrough }))
mock.module('@/components/ui/select', () => ({ Select: passthrough, SelectContent: passthrough, SelectItem: passthrough, SelectTrigger: passthrough, SelectValue: passthrough }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: passthrough,
  DropdownMenuContent: passthrough,
  DropdownMenuItem: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
  DropdownMenuSeparator: () => null,
  DropdownMenuTrigger: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: () => null }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: passthrough, TooltipContent: passthrough, TooltipTrigger: ({ render, ...props }: { render: React.ReactElement } & Record<string, unknown>) => React.cloneElement(render, props) }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: passthrough, AlertDialogAction: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => <button onClick={onClick}>{children}</button>, AlertDialogCancel: passthrough, AlertDialogContent: passthrough, AlertDialogDescription: passthrough, AlertDialogFooter: passthrough, AlertDialogHeader: passthrough, AlertDialogTitle: passthrough }))
mock.module('./model-dialog', () => ({ ModelDialog: ({ open, onSuccess }: { open: boolean; onSuccess: () => void }) => open ? <button onClick={onSuccess}>save-model</button> : null }))
mock.module('./delete-model-dialog', () => ({ DeleteModelDialog: () => null }))

const { ModelsClient } = await import('./models-client')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const model = {
  id: 'model-1', name: 'GPT Test', provider: 'openai', model_id: 'gpt-test', model_type: 'chat',
  base_url: null, has_api_key: true, context_length: null, max_output_tokens: null, input_price: null,
  output_price: null, default_params: null, capabilities: null, config: null, is_enabled: true,
  is_default: false, sort_order: 0, created_at: '', updated_at: '',
}
const page = (items = [model]) => ({ items, total: items.length, page: 1, page_size: 10 })
let renderer: ReactTestRenderer

beforeEach(() => {
  getModels.mockReset()
  updateModel.mockClear()
  setDefault.mockClear()
  testConnection.mockClear()
  deleteModel.mockClear()
  getProviders.mockClear()
  getModelTypes.mockClear()
  success.mockClear()
  loading.mockClear()
  error.mockClear()
  dismiss.mockClear()
  startTour.mockClear()
  canCreate = true
})
afterEach(() => { if (renderer) act(() => renderer.unmount()) })

function render() {
  act(() => { renderer = create(<ModelsClient />) })
  return renderer
}

function buttonsNamed(name: string) {
  return renderer.root.findAllByType('button').filter((button) => button.children.includes(name))
}

function textCount(text: string) {
  return renderer.root.findAll((node) => node.children.includes(text)).length
}

test('loads and lists models, then refreshes after the model form saves', async () => {
  getModels.mockResolvedValue(page())
  render()
  await act(async () => {})

  expect(textCount('GPT Test')).toBeGreaterThan(0)
  expect(getModels).toHaveBeenCalledWith({ page: 1, pageSize: 10 })

  await act(async () => buttonsNamed('createModel')[0].props.onClick())
  await act(async () => buttonsNamed('save-model')[0].props.onClick())
  expect(getModels).toHaveBeenCalledTimes(2)
})

test('gates the admin model setup launcher and anchors its supported controls', async () => {
  getModels.mockResolvedValue(page())
  canCreate = false
  render()
  await act(async () => {})

  expect(renderer.root.findAllByProps({ 'data-testid': 'admin-models-onboarding-button' })).toHaveLength(0)
  act(() => renderer.unmount())

  canCreate = true
  render()
  await act(async () => {})

  expect(renderer.root.findByProps({ 'data-testid': 'admin-models-list' })).toBeTruthy()
  expect(renderer.root.findByProps({ 'data-testid': 'admin-models-create-button' })).toBeTruthy()
  expect(renderer.root.findByProps({ 'data-testid': 'admin-model-actions-model-1' })).toBeTruthy()
  expect(renderer.root.findByProps({ 'data-testid': 'admin-model-toggle-enabled-model-1' })).toBeTruthy()
  expect(renderer.root.findByProps({ 'data-testid': 'admin-model-test-connection-model-1' })).toBeTruthy()

  const launcher = renderer.root.findByProps({ 'data-testid': 'admin-models-onboarding-button' })
  act(() => launcher.props.onClick())
  expect(startTour).not.toHaveBeenCalled()
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 350))
  })
  expect(startTour).toHaveBeenCalledWith('adminModelSetup')
})

test('disables a model and reloads the listing', async () => {
  getModels.mockResolvedValue(page())
  render()
  await act(async () => {})

  await act(async () => buttonsNamed('disable')[0].props.onClick())
  expect(updateModel).toHaveBeenCalledWith('model-1', { is_enabled: false })
  expect(success).toHaveBeenCalledWith('modelDisabled')
  expect(getModels).toHaveBeenCalledTimes(2)
})

test('recovers from a failed list request on the next search', async () => {
  getModels.mockRejectedValueOnce(new Error('unavailable')).mockResolvedValueOnce(page([{ ...model, name: 'Recovered model' }]))
  render()
  await act(async () => {})
  expect(textCount('noModels')).toBeGreaterThan(0)

  const search = renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'filterModels')!
  await act(async () => search.props.onChange({ target: { value: 'recovered' } }))
  expect(textCount('Recovered model')).toBeGreaterThan(0)
  expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: 'recovered' })
})

test('sets defaults, tests connections, paginates, and bulk deletes selected models', async () => {
  getModels.mockResolvedValue(page([
    model,
    { ...model, id: 'model-2', name: 'Video Test', model_type: 'text_to_video', is_enabled: false, is_default: false },
  ]))
  testConnection.mockResolvedValueOnce({ success: true, latency_ms: 42 }).mockResolvedValueOnce({ success: false, message: 'no route ' })
  const confirm = mock(() => false)
  Object.defineProperty(globalThis, 'window', { value: { confirm }, configurable: true })
  render()
  await act(async () => {})

  await act(async () => buttonsNamed('setDefault')[0].props.onClick())
  expect(setDefault).toHaveBeenCalledWith('model-1')
  expect(success).toHaveBeenCalledWith('modelSetDefault')

  await act(async () => buttonsNamed('testConnection')[0].props.onClick())
  expect(loading).toHaveBeenCalledWith('testing')
  expect(testConnection).toHaveBeenCalledWith('model-1')
  expect(success).toHaveBeenCalledWith('testSuccess (42ms)', { id: 'toast-1' })

  await act(async () => buttonsNamed('testConnection')[1].props.onClick())
  expect(confirm).toHaveBeenCalledWith('videoTestCostWarning')
  expect(testConnection).toHaveBeenCalledTimes(1)
  confirm.mockReturnValueOnce(true)
  await act(async () => buttonsNamed('testConnection')[1].props.onClick())
  expect(error).toHaveBeenCalledWith('no route', { id: 'toast-1' })

  const checkboxes = renderer.root.findAllByType('input').filter((input) => input.props.type === 'checkbox')
  act(() => checkboxes[0]!.props.onChange())
  expect(textCount('2')).toBeGreaterThan(0)
  await act(async () => renderer.root.findAllByType('button').find((button) => button.props.className?.includes('text-destructive'))!.props.onClick())
  await act(async () => buttonsNamed('delete').at(-1)!.props.onClick())
  await act(async () => {})
  expect(deleteModel).toHaveBeenCalledWith('model-1')
  expect(deleteModel).toHaveBeenCalledWith('model-2')

  const selects = renderer.root.findAll((node) => node.props.onValueChange)
  await act(async () => selects.at(-1)!.props.onValueChange('20'))
  expect(getModels).toHaveBeenLastCalledWith({ page: 1, pageSize: 20 })
})
