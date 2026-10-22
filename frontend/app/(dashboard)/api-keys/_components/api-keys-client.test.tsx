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
let allowedPermissions: Record<string, true> = { 'apikey:create': true, 'apikey:update': true, 'apikey:delete': true }
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
const TableRow = component()

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
mock.module('@/components/permission-guard', () => ({ PermissionGuard: component(), useCanPerform: () => ({ canPerform: (permission: string) => permission in allowedPermissions }) }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/badge', () => ({ Badge }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox }))
mock.module('@/components/ui/table', () => ({
  Table: component(), TableBody: component(), TableCell: component(), TableHead: component(), TableHeader: component(), TableRow,
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
  allowedPermissions = { 'apikey:create': true, 'apikey:update': true, 'apikey:delete': true }
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
  checkboxes[0].props.onCheckedChange(true)
  tree = render()
  expect(text(tree)).toContain('2 apiKeys.keysSelected')

  findAll(tree, (node) => node.type === Checkbox)[0].props.onCheckedChange(false)
  expect(text(render())).not.toContain('apiKeys.keysSelected')

  findAll(render(), (node) => node.type === Checkbox)[0].props.onCheckedChange(true)
  tree = render()
  findAll(tree, (node) => node.type === Checkbox)[1].props.onCheckedChange(true)
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

  findAll(tree, (node) => node.type === Checkbox)[1].props.onCheckedChange(true)
  tree = render()
  expect(text(tree)).toContain('1 apiKeys.keysSelected')

  const bulkTriggers = findAll(tree, (node) => node.type === TooltipTrigger)
  await bulkTriggers[0].props.onClick()
  expect(activateAPIKey).toHaveBeenCalledWith('key-1')
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.bulkActivated.1')

  findAll(render(), (node) => node.type === Checkbox)[1].props.onCheckedChange(false)
  tree = render()
  await findAll(tree, (node) => node.type === TooltipTrigger)[1].props.onClick()
  expect(deactivateAPIKey).toHaveBeenCalledTimes(2)
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.bulkDeactivated.1')

  findAll(render(), (node) => node.type === Checkbox)[1].props.onCheckedChange(true)
  tree = render()
  findAll(tree, (node) => node.type === TooltipTrigger)[2].props.onClick()
  tree = render()
  expect(findByType(tree, AlertDialog).props.open).toBe(true)
  await findByType(tree, AlertDialogAction).props.onClick()
  expect(deleteAPIKey).toHaveBeenCalledWith('key-1')
  expect(toastSuccess).toHaveBeenCalledWith('apiKeys.bulkDeleted.1')
})

test('paginates, changes page size, and renders optional key details', async () => {
  const keys = Array.from({ length: 25 }, (_, index) => ({
    ...apiKey,
    id: `key-${index + 1}`,
    name: `Key ${index + 1}`,
    user: undefined,
    rate_limit: 0,
    expires_at: null,
    last_used_at: null,
  }))
  getAPIKeys.mockImplementation(() => Promise.resolve({ items: keys.slice(0, 10), total: 25, page: 1, page_size: 10 }))
  render()
  await load()
  let tree = render()
  expect(text(tree)).toContain('apiKeys.unlimited')
  expect(text(tree)).toContain('apiKeys.neverUsed')
  expect(text(tree)).toContain('apiKeys.never')
  expect(text(tree)).toContain('-')

  const pageButtons = findAll(tree, (node) => node.type === Button)
  pageButtons[pageButtons.length - 2].props.onClick()
  tree = render()
  await load()
  tree = render()
  const lastPageButton = findAll(tree, (node) => node.type === Button).at(-1)!
  lastPageButton.props.onClick()
  render()
  await load()
  expect(getAPIKeys).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, pageSize: 10 }))

  tree = render()
  findAll(tree, (node) => node.type === Button).at(-4)!.props.onClick()
  render()
  await load()
  expect(getAPIKeys).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 10 }))

  tree = render()
  findByType(tree, Select).props.onValueChange('20')

  render()
  await load()
  expect(getAPIKeys).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 20 }))
})

test('respects action permissions and keeps the list usable when mutations fail', async () => {
  allowedPermissions = {}
  render()
  await load()
  let tree = render()
  expect(findAll(tree, (node) => node.type === DropdownMenuItem)).toHaveLength(0)
  findAll(tree, (node) => node.type === Checkbox)[1].props.onCheckedChange()
  tree = render()
  expect(findAll(tree, (node) => node.type === TableRow && node.props['data-state'] === 'selected')).toHaveLength(1)
  expect(text(tree)).not.toContain('apiKeys.keysSelected')
  expect(findAll(tree, (node) => node.type === TooltipTrigger)).toHaveLength(0)

  allowedPermissions = { 'apikey:update': true, 'apikey:delete': true }
  tree = render()
  deactivateAPIKey.mockImplementationOnce(() => Promise.reject(new Error('cannot deactivate')))
  findAll(tree, (node) => node.type === DropdownMenuItem)[1].props.onClick()
  await Promise.resolve()
  expect(toastSuccess).not.toHaveBeenCalled()

  tree = render()
  deleteAPIKey.mockImplementationOnce(() => Promise.reject(new Error('cannot delete')))
  activateAPIKey.mockImplementationOnce(() => Promise.reject(new Error('cannot activate')))
  await findAll(tree, (node) => node.type === TooltipTrigger)[0].props.onClick()
  expect(toastSuccess).not.toHaveBeenCalled()
  deactivateAPIKey.mockImplementationOnce(() => Promise.reject(new Error('cannot bulk deactivate')))
  await findAll(tree, (node) => node.type === TooltipTrigger)[1].props.onClick()
  expect(toastSuccess).not.toHaveBeenCalled()
  await findAll(tree, (node) => node.type === TooltipTrigger)[2].props.onClick()
  tree = render()
  await findByType(tree, AlertDialogAction).props.onClick()
  expect(findByType(render(), AlertDialog).props.open).toBe(false)
  expect(toastSuccess).not.toHaveBeenCalled()
  tree = render()
  const bulkActionBar = findAll(tree, (node) => node.type === 'div' && node.props.className === 'fixed bottom-8 left-1/2 -translate-x-1/2 z-50')[0]
  findAll(bulkActionBar, (node) => node.type === Button && node.props.size === 'icon')[0].props.onClick()
  expect(text(render())).not.toContain('apiKeys.keysSelected')
})
test('keeps key listing available when stats or owner-filter loading fails', async () => {
  getStats.mockImplementationOnce(() => Promise.reject(new Error('stats unavailable')))
  getUsers.mockImplementationOnce(() => Promise.reject(new Error('users unavailable')))
  render()
  await load()
  expect(text(render())).toContain('Production key')
  expect(getStats).toHaveBeenCalledTimes(1)
  expect(getUsers).toHaveBeenCalledTimes(1)
})
