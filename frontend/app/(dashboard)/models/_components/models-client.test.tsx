import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const getModels = mock()
const updateModel = mock(async () => ({}))
const getProviders = mock(async () => [])
const getModelTypes = mock(async () => [])
const success = mock()

mock.module('next-intl', () => ({
  useTranslations: () => {
    const translate = (key: string) => key
    translate.has = () => false
    return translate
  },
}))
mock.module('sonner', () => ({ toast: { success, loading: mock(), error: mock(), dismiss: mock() } }))
mock.module('lucide-react', () => ({
  Plus: () => null, Search: () => null, MoreHorizontal: () => null, Pencil: () => null,
  Trash2: () => null, ChevronLeft: () => null, ChevronRight: () => null, ChevronsLeft: () => null,
  ChevronsRight: () => null, X: () => null, Star: () => null, Power: () => null,
  PowerOff: () => null, TestTube: () => null,
}))
mock.module('@/lib/api/admin/models', () => ({ modelsApi: { getModels, updateModel, setDefault: mock(), testConnection: mock(), deleteModel: mock() } }))
mock.module('@/lib/api/models', () => ({ modelsApi: { getProviders, getModelTypes } }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))

const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={() => onCheckedChange(!checked)} /> }))
mock.module('@/components/ui/table', () => ({ Table: passthrough, TableBody: passthrough, TableCell: passthrough, TableHead: passthrough, TableHeader: passthrough, TableRow: passthrough }))
mock.module('@/components/ui/select', () => ({ Select: passthrough, SelectContent: passthrough, SelectItem: passthrough, SelectTrigger: passthrough, SelectValue: passthrough }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: passthrough, DropdownMenuContent: passthrough, DropdownMenuItem: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => <button onClick={onClick}>{children}</button>, DropdownMenuSeparator: () => null, DropdownMenuTrigger: passthrough }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: () => null }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: passthrough, TooltipContent: passthrough, TooltipTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</> }))
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
  getProviders.mockClear()
  getModelTypes.mockClear()
  success.mockClear()
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
