import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const icon = function Icon() {}

let stateValues: unknown[] = []
let stateIndex = 0
let urlSearch = ''
const effects: Array<() => void | Promise<void>> = []

const getAPIKeys = mock(() => Promise.resolve(pageData([apiKey])))
const getStats = mock(() => Promise.resolve({ total: 1, active: 1, inactive: 0, expired: 0 }))
const activateAPIKey = mock(() => Promise.resolve(apiKey))
const deactivateAPIKey = mock(() => Promise.resolve(apiKey))
const deleteAPIKey = mock(() => Promise.resolve(apiKey))
const getUsers = mock(() => Promise.resolve({ items: [user], total: 1, page: 1, page_size: 100 }))
const toastSuccess = mock(() => {})

function component() {
  return function Component() {}
}

const Button = component()
const Input = component()
const Badge = component()
const Checkbox = component()
const Select = component()
const DataTableFacetedFilter = component()
const DropdownMenuItem = component()
const APIKeyDialog = component()
const DeleteAPIKeyDialog = component()
const ShowKeyDialog = component()
const TooltipTrigger = component()
const AlertDialog = component()
const AlertDialogAction = component()

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
  useMemo: <T,>(factory: () => T) => factory(),
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
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) => (
    values?.count === undefined ? `${namespace}.${key}` : `${namespace}.${key}.${values.count}`
  ),
}))
mock.module('lucide-react', () => ({
  Plus: icon, Search: icon, MoreHorizontal: icon, Pencil: icon, Trash2: icon, Key: icon, KeyRound: icon,
  X: icon, ChevronLeft: icon, ChevronRight: icon, ChevronsLeft: icon, ChevronsRight: icon, Power: icon, PowerOff: icon,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({ apiKeysApi: { getAPIKeys, getStats, activateAPIKey, deactivateAPIKey, deleteAPIKey } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/lib/utils', () => ({ formatDateTime: (value: string) => `date:${value}` }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [urlSearch, (value: string) => { urlSearch = value }] }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: unknown) => value }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: component(), useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/badge', () => ({ Badge }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox }))
mock.module('@/components/ui/table', () => ({
  Table: component(), TableBody: component(), TableCell: component(), TableHead: component(), TableHeader: component(), TableRow: component(),
}))
mock.module('@/components/ui/select', () => ({
  Select, SelectContent: component(), SelectItem: component(), SelectTrigger: component(), SelectValue: component(),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: component(), DropdownMenuContent: component(), DropdownMenuItem, DropdownMenuSeparator: component(), DropdownMenuTrigger: component(),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: component(), TooltipContent: component(), TooltipTrigger }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog, AlertDialogAction, AlertDialogCancel: component(), AlertDialogContent: component(), AlertDialogDescription: component(),
  AlertDialogFooter: component(), AlertDialogHeader: component(), AlertDialogTitle: component(),
}))
mock.module('./api-key-dialog', () => ({ APIKeyDialog }))
mock.module('./delete-api-key-dialog', () => ({ DeleteAPIKeyDialog }))
mock.module('./show-key-dialog', () => ({ ShowKeyDialog }))

const { APIKeysClient } = await import('./api-keys-client')

const user = { id: 'user-1', username: 'Ada' }
const apiKey = {
  id: 'key-1', name: 'Production key', key_prefix: 'clsk_live', user_id: 'user-1', user,
  scopes: ['read'], rate_limit: 60, is_active: true, expires_at: null, last_used_at: null,
  agents: [], workflows: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z',
}

function pageData(items: typeof apiKey[]) {
  return { items, total: items.length, page: 1, page_size: 10 }
}

function render() {
  stateIndex = 0
  effects.length = 0
  return APIKeysClient() as { props: Record<string, unknown> }
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

beforeEach(() => {
  stateValues = []
  urlSearch = ''
  getAPIKeys.mockReset()
  getAPIKeys.mockImplementation(() => Promise.resolve(pageData([apiKey])))
  getStats.mockReset()
  getStats.mockImplementation(() => Promise.resolve({ total: 1, active: 1, inactive: 0, expired: 0 }))
  getUsers.mockReset()
  getUsers.mockImplementation(() => Promise.resolve({ items: [user], total: 1, page: 1, page_size: 100 }))
  activateAPIKey.mockReset()
  activateAPIKey.mockImplementation(() => Promise.resolve(apiKey))
  deactivateAPIKey.mockReset()
  deactivateAPIKey.mockImplementation(() => Promise.resolve(apiKey))
  deleteAPIKey.mockReset()
  deleteAPIKey.mockImplementation(() => Promise.resolve(apiKey))
  toastSuccess.mockReset()
})

test('loads keys, shows empty state after failed load, and fetches users for filters', async () => {
  getAPIKeys.mockImplementationOnce(() => new Promise(() => {}))
  expect(text(render())).toContain('common.loading')

  stateValues = []
  getAPIKeys.mockReset()
  getAPIKeys.mockImplementation(() => Promise.resolve(pageData([apiKey])))
  render()
  await load()
  expect(text(render())).toContain('Production key')
  expect(text(render())).toContain('clsk_live...')
  expect(getUsers).toHaveBeenCalledWith({ page: 1, pageSize: 100, search: undefined, excludeUserIds: [] })

  stateValues = []
  getAPIKeys.mockReset()
  getAPIKeys.mockImplementation(() => Promise.reject(new Error('nope')))
  render()
  await load()
  expect(text(render())).toContain('apiKeys.noKeys')
})

test('applies search, status, and owner filters, then resets them', async () => {
  render()
  await load()
  let tree = render()

  findByType(tree, Input).props.onChange({ target: { value: 'prod' } })
  const filters = findAll(tree, (node) => node.type === DataTableFacetedFilter)
  filters[0].props.onSelectionChange(new Set(['active']))
  filters[1].props.onSearchChange('ada')
  filters[1].props.onSelectionChange(new Set(['user-1']))

  tree = render()
  await load()
  expect(getAPIKeys).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'prod', status: ['active'], userId: ['user-1'] }))
  expect(getUsers).toHaveBeenLastCalledWith({ page: 1, pageSize: 100, search: 'ada', excludeUserIds: ['user-1'] })

  findAll(tree, (node) => node.type === Button && text(node).includes('common.reset'))[0].props.onClick()
  render()
  await load()
  expect(getAPIKeys).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined, status: undefined, userId: undefined }))
})

test('opens create/edit/delete dialogs and shows the newly created secret', async () => {
  render()
  await load()
  let tree = render()

  findAll(tree, (node) => node.type === Button && text(node).includes('apiKeys.createKey'))[0].props.onClick()
  tree = render()
  expect(findByType(tree, APIKeyDialog).props.open).toBe(true)
  expect(findByType(tree, APIKeyDialog).props.apiKey).toBeNull()

  findByType(tree, APIKeyDialog).props.onSuccess('secret-key')
  tree = render()
  expect(findByType(tree, ShowKeyDialog).props.open).toBe(true)
  expect(findByType(tree, ShowKeyDialog).props.apiKey).toBe('secret-key')
  await load()
  tree = render()

  const items = findAll(tree, (node) => node.type === DropdownMenuItem)
  items[0].props.onClick()
  tree = render()
  expect(findByType(tree, APIKeyDialog).props.apiKey).toEqual(apiKey)

  items[2].props.onClick()
  tree = render()
  expect(findByType(tree, DeleteAPIKeyDialog).props.open).toBe(true)
  expect(findByType(tree, DeleteAPIKeyDialog).props.apiKey).toEqual(apiKey)
})

test('selects all rows, clears all rows, deselects one row, and marks expired keys', async () => {
  getAPIKeys.mockImplementation(() => Promise.resolve(pageData([
    { ...apiKey, id: 'key-1', expires_at: '2000-01-01T00:00:00Z' },
    { ...apiKey, id: 'key-2', name: 'Backup key' },
  ])))
  render()
  await load()
  let tree = render()
  expect(text(tree)).toContain('apiKeys.expired')

  const checkboxes = findAll(tree, (node) => node.type === Checkbox)
  checkboxes[0].props.onCheckedChange()
  tree = render()
  expect(text(tree)).toContain('2 apiKeys.keysSelected')

  findAll(tree, (node) => node.type === Checkbox)[0].props.onCheckedChange()
  expect(text(render())).not.toContain('apiKeys.keysSelected')

  findAll(render(), (node) => node.type === Checkbox)[0].props.onCheckedChange()
  tree = render()
  findAll(tree, (node) => node.type === Checkbox)[1].props.onCheckedChange()
  expect(text(render())).toContain('1 apiKeys.keysSelected')
})

test('toggles one key and runs bulk activate, deactivate, and delete actions', async () => {
  getAPIKeys.mockImplementation(() => Promise.resolve(pageData([{ ...apiKey, is_active: false }])))
  render()
  await load()
  let tree = render()
  expect(text(tree)).toContain('apiKeys.inactive')

  findAll(tree, (node) => node.type === DropdownMenuItem)[1].props.onClick()
  await Promise.resolve()
  expect(activateAPIKey).toHaveBeenCalledWith('key-1')
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.keyActivated')

  stateValues = []
  getAPIKeys.mockReset()
  getAPIKeys.mockImplementation(() => Promise.resolve(pageData([apiKey])))
  render()
  await load()
  tree = render()
  findAll(tree, (node) => node.type === DropdownMenuItem)[1].props.onClick()
  await Promise.resolve()
  expect(deactivateAPIKey).toHaveBeenCalledWith('key-1')
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.keyDeactivated')

  findAll(tree, (node) => node.type === Checkbox)[1].props.onCheckedChange()
  tree = render()
  expect(text(tree)).toContain('1 apiKeys.keysSelected')

  const bulkTriggers = findAll(tree, (node) => node.type === TooltipTrigger)
  await bulkTriggers[0].props.onClick()
  expect(activateAPIKey).toHaveBeenCalledWith('key-1')
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.bulkActivated.1')

  findAll(render(), (node) => node.type === Checkbox)[1].props.onCheckedChange()
  tree = render()
  await findAll(tree, (node) => node.type === TooltipTrigger)[1].props.onClick()
  expect(deactivateAPIKey).toHaveBeenCalledTimes(2)
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.bulkDeactivated.1')

  findAll(render(), (node) => node.type === Checkbox)[1].props.onCheckedChange()
  tree = render()
  findAll(tree, (node) => node.type === TooltipTrigger)[2].props.onClick()
  tree = render()
  expect(findByType(tree, AlertDialog).props.open).toBe(true)
  await findByType(tree, AlertDialogAction).props.onClick()
  expect(deleteAPIKey).toHaveBeenCalledWith('key-1')
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.bulkDeleted.1')
})
