import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

let stateValues: unknown[] = []
let stateIndex = 0
let urlSearch = ''
const effects: Array<() => void | Promise<void>> = []
const getEntities = mock(() => Promise.resolve(pageData([entity])))
const deleteEntity = mock(() => Promise.resolve({}))
const toastSuccess = mock(() => {})

function component() {
  return function Component() {}
}

const Input = component('Input')
const Checkbox = component('Checkbox')
const Button = component('Button')
const DataTableFacetedFilter = component('DataTableFacetedFilter')
const AlertDialog = component('AlertDialog')
const AlertDialogAction = component('AlertDialogAction')
const EntityDialog = component('EntityDialog')
const DropdownMenuItem = component('DropdownMenuItem')

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (stateValues[index] === undefined) stateValues[index] = initial
    const setState = (value: T | ((current: T) => T)) => {
      stateValues[index] = typeof value === 'function' ? (value as (current: T) => T)(stateValues[index] as T) : value
    }
    return [stateValues[index], setState] as [T, typeof setState]
  },
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => Object.assign(
    (key: string, values?: Record<string, unknown>) => values?.count === undefined ? `${namespace}.${key}` : `${namespace}.${key}.${values.count}`,
    { has: (key: string) => key !== 'types.customType' }
  ),
}))
mock.module('lucide-react', () => ({
  Search: element, MoreHorizontal: element, Pencil: element, Trash2: element, ChevronLeft: element,
  ChevronRight: element, ChevronsLeft: element, ChevronsRight: element, X: element, Brain: element,
  User: element, ArrowRight: element, ArrowLeft: element,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/admin/memories', () => ({ memoriesApi: { getEntities, deleteEntity } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}`, cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [urlSearch, (value: string) => { urlSearch = value }] }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: component('PermissionGuard'), useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/badge', () => ({ Badge: component('Badge') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox }))
mock.module('@/components/ui/table', () => ({
  Table: component('Table'), TableBody: component('TableBody'), TableCell: component('TableCell'),
  TableHead: component('TableHead'), TableHeader: component('TableHeader'), TableRow: component('TableRow'),
}))
mock.module('@/components/ui/select', () => ({ Select: component('Select'), SelectContent: component('SelectContent'), SelectItem: component('SelectItem'), SelectTrigger: component('SelectTrigger'), SelectValue: component('SelectValue') }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: component('DropdownMenu'), DropdownMenuContent: component('DropdownMenuContent'), DropdownMenuItem, DropdownMenuTrigger: component('DropdownMenuTrigger') }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: component('Tooltip'), TooltipContent: component('TooltipContent'), TooltipTrigger: component('TooltipTrigger') }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog, AlertDialogAction, AlertDialogCancel: component('AlertDialogCancel'), AlertDialogContent: component('AlertDialogContent'),
  AlertDialogDescription: component('AlertDialogDescription'), AlertDialogFooter: component('AlertDialogFooter'),
  AlertDialogHeader: component('AlertDialogHeader'), AlertDialogTitle: component('AlertDialogTitle'),
}))
mock.module('./entity-dialog', () => ({ EntityDialog }))

const { MemoriesClient } = await import('./memories-client')

const entity = {
  id: 'memory-1', user_id: 'user-1', user_name: 'Ada', user_avatar_url: null,
  name: 'Likes tea', entity_type: 'preference', description: 'Strong tea', properties: {},
  access_count: 2, last_accessed_at: '2026-01-02T00:00:00Z', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-03T00:00:00Z',
  outgoing_relations_count: 1, incoming_relations_count: 1,
}

function pageData(items: typeof entity[]) {
  return { items, total: items.length, page: 1, page_size: 20 }
}

function render() {
  stateIndex = 0
  effects.length = 0
  return MemoriesClient() as { props: Record<string, unknown> }
}

async function load() {
  for (const effect of effects) await effect()
  await Promise.resolve()
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object') return ''
  const props = (node as { props?: Record<string, unknown> }).props
  return [props?.children, props?.render].flat().map(text).join('')
}

function findAll(node: unknown, predicate: (node: { type: unknown; props: Record<string, unknown> }) => boolean): Array<{ type: unknown; props: Record<string, unknown> }> {
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const elementNode = node as { type: unknown; props: Record<string, unknown> }
  return [
    ...(predicate(elementNode) ? [elementNode] : []),
    ...[elementNode.props.children, elementNode.props.render].flat().flatMap((child) => findAll(child, predicate)),
  ]
}

function findByType(node: unknown, type: unknown) {
  return findAll(node, (item) => item.type === type)[0]
}

function reset(apiResult: Promise<unknown> = Promise.resolve(pageData([entity]))) {
  stateValues = []
  urlSearch = ''
  getEntities.mockReset()
  getEntities.mockImplementation(() => apiResult)
  deleteEntity.mockReset()
  deleteEntity.mockImplementation(() => Promise.resolve({}))
  toastSuccess.mockReset()
}

test('renders loading, loaded rows, and failed load empty state', async () => {
  reset(new Promise(() => {}))
  expect(text(render())).toContain('common.loading')

  reset()
  render()
  await load()
  const loaded = render()
  expect(text(loaded)).toContain('Likes tea')
  expect(text(loaded)).toContain('date:2026-01-01T00:00:00Z')

  reset(Promise.reject(new Error('nope')))
  render()
  await load()
  expect(text(render())).toContain('common.noData')
})

test('applies search and type filters, then resets them', async () => {
  reset()
  let tree = render()
  await load()
  tree = render()

  findByType(tree, Input).props.onChange({ target: { value: 'tea' } })
  findByType(tree, DataTableFacetedFilter).props.onSelectionChange(new Set(['preference']))
  render()
  await load()

  expect(getEntities).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'tea', entity_type: ['preference'] }))

  tree = render()
  findAll(tree, (node) => node.type === Button && text(node).includes('common.reset'))[0].props.onClick()
  render()
  await load()
  expect(getEntities).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined, entity_type: undefined }))
})

test('opens edit/delete dialogs and confirms single delete', async () => {
  reset()
  render()
  await load()
  let tree = render()

  const items = findAll(tree, (node) => node.type === DropdownMenuItem)
  items[0].props.onClick()
  tree = render()
  expect(findByType(tree, EntityDialog).props.entity).toEqual(entity)

  items[1].props.onClick()
  tree = render()
  expect(findByType(tree, AlertDialog).props.open).toBe(true)
  await findAll(tree, (node) => node.type === AlertDialogAction)[0].props.onClick()

  expect(deleteEntity).toHaveBeenCalledWith('memory-1')
  expect(toastSuccess).toHaveBeenCalledWith('memories.deleteEntity')
})

test('selects rows, clears selection, and confirms bulk delete boundary', async () => {
  reset(Promise.resolve(pageData([entity, { ...entity, id: 'memory-2', name: 'Knows Bun' }])))
  render()
  await load()
  let tree = render()

  findAll(tree, (node) => node.type === Checkbox)[1].props.onCheckedChange()
  tree = render()
  expect(text(tree)).toContain('1 memories.entitiesSelected')

  findAll(tree, (node) => node.type === Button && node.props.variant === 'ghost' && node.props.onClick)[0].props.onClick()
  expect(text(render())).not.toContain('memories.entitiesSelected')

  tree = render()
  findAll(tree, (node) => node.type === Checkbox)[0].props.onCheckedChange()
  tree = render()
  expect(text(tree)).toContain('2 memories.entitiesSelected')
  findAll(tree, (node) => node.props.onClick && String(text(node)).includes(''))
    .find((node) => node.props.render)?.props.onClick()
  tree = render()
  expect(findAll(tree, (node) => node.type === AlertDialog)[1].props.open).toBe(true)
  await findAll(tree, (node) => node.type === AlertDialogAction)[1].props.onClick()

  expect(deleteEntity).toHaveBeenCalledWith('memory-1')
  expect(deleteEntity).toHaveBeenCalledWith('memory-2')
  expect(toastSuccess).toHaveBeenCalledWith('common.deleteSuccess')
})
