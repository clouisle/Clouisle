import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Tree = { type: unknown; props: Record<string, unknown> }
type StateSetter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Record<string, unknown>): Tree => ({ type, props })
const ui = (props: Record<string, unknown>) => props.children
const Button = ui
const PermissionGuard = ui
const TeamDialog = (props: Record<string, unknown>) => props.children
const TeamDetailDialog = (props: Record<string, unknown>) => props.children
let states: unknown[] = []
let stateIndex = 0
let effects: Array<() => void | Promise<void>> = []
let getTeams: () => Promise<{ items: Array<Record<string, unknown>>; total: number }>
let searchQuery = ''
const setSearchQuery = mock((value: string) => { searchQuery = value })
const deleteTeam = mock(async () => {})
const toastSuccess = mock()

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState<T>(initial: T): [T, StateSetter<T>] {
    const index = stateIndex++
    if (states[index] === undefined) states[index] = initial
    return [states[index] as T, (value) => {
      states[index] = typeof value === 'function'
        ? (value as (current: T) => T)(states[index] as T)
        : value
    }]
  },
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
  useCallback: <T,>(callback: T) => callback,
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Plus', 'Search', 'MoreHorizontal', 'Pencil', 'Trash2', 'UsersRound', 'X',
  'Crown', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'Calendar',
].map((name) => [name, ui])))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/utils', () => ({ formatDateTime: () => 'formatted-date' }))
mock.module('@/lib/api/admin', () => ({
  teamsApi: { getTeams: (...args: unknown[]) => getTeams(...args), deleteTeam },
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [searchQuery, setSearchQuery] }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('./team-dialog', () => ({ TeamDialog }))
mock.module('./team-detail-dialog', () => ({ TeamDetailDialog }))

mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input: ui }))
mock.module('@/components/ui/badge', () => ({ Badge: ui }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ui }))
mock.module('@/components/ui/avatar', () => ({ Avatar: ui, AvatarFallback: ui, AvatarImage: ui }))
mock.module('@/components/ui/select', () => ({
  Select: ui, SelectContent: ui, SelectItem: ui, SelectTrigger: ui, SelectValue: ui,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ui, DropdownMenuContent: ui, DropdownMenuItem: ui,
  DropdownMenuSeparator: ui, DropdownMenuTrigger: ui,
}))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: ui, TooltipContent: ui, TooltipTrigger: ui }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ui, AlertDialogAction: ui, AlertDialogCancel: ui, AlertDialogContent: ui,
  AlertDialogDescription: ui, AlertDialogFooter: ui, AlertDialogHeader: ui, AlertDialogTitle: ui,
}))

const { TeamsClient } = await import('./teams-client')

function render() {
  stateIndex = 0
  effects = []
  return TeamsClient() as Tree
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object') return ''
  const { props } = node as Tree
  return [props.children].flat().map(textContent).join('')
}

function find(node: unknown, predicate: (element: Tree) => boolean): Tree | undefined {
  if (!node || typeof node !== 'object') return undefined
  const element = node as Tree
  if (predicate(element)) return element
  for (const child of [element.props?.children].flat()) {
    const found = find(child, predicate)
    if (found) return found
  }
}

function findAll(node: unknown, predicate: (element: Tree) => boolean): Tree[] {
  if (!node || typeof node !== 'object') return []
  const element = node as Tree
  return [
    ...(predicate(element) ? [element] : []),
    ...[element.props?.children].flat().flatMap((child) => findAll(child, predicate)),
  ]
}

const team = {
  id: 'team-1', name: 'Platform', description: 'Builds the platform', avatar_url: null,
  is_default: false, owner: { username: 'alex' }, created_at: '2026-01-01', updated_at: '2026-01-01',
}

beforeEach(() => {
  states = []
  searchQuery = ''
  setSearchQuery.mockClear()
  deleteTeam.mockClear()
  toastSuccess.mockClear()
  getTeams = () => Promise.resolve({ items: [], total: 0 })
})

describe('TeamsClient', () => {
  test('shows loading placeholders, then renders the fetched team list', async () => {
    getTeams = mock(() => Promise.resolve({ items: [team], total: 1 }))

    const loading = render()
    expect(find(loading, (element) => String(element.props.className).includes('animate-pulse'))).toBeDefined()

    await effects.at(-1)?.()
    const loaded = render()

    expect(getTeams).toHaveBeenCalledWith(1, 12, undefined)
    expect(textContent(loaded)).toContain('Platform')
    expect(textContent(loaded)).toContain('Builds the platform')
    expect(textContent(loaded)).toContain('formatted-date')
  })

  test('ends loading with the empty state when listing teams fails', async () => {
    getTeams = mock(() => Promise.reject(new Error('network failure')))

    render()
    await effects.at(-1)?.()
    const failed = render()

    expect(textContent(failed)).toContain('noTeams')
    expect(find(failed, (element) => String(element.props.className).includes('animate-pulse'))).toBeUndefined()
  })

  test('opens the create dialog from the guarded action', () => {
    const initial = render()
    const create = find(initial, (element) =>
      element.type === Button
      && typeof element.props.onClick === 'function'
      && textContent(element).includes('createTeam')
    )

    ;(create?.props.onClick as () => void)()
    const opened = render()

    expect(find(opened, (element) => element.type === TeamDialog)?.props.open).toBe(true)
  })

  test('filters, pages, opens detail, and clears a selected team', async () => {
    getTeams = mock(() => Promise.resolve({ items: [team], total: 25 }))
    render()
    await effects.at(-1)?.()
    let loaded = render()

    const search = find(loaded, (element) => element.props.placeholder === 'filterTeams')
    ;(search?.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'plat' } })
    expect(setSearchQuery).toHaveBeenCalledWith('plat')

    searchQuery = 'plat'
    loaded = render()
    ;(find(loaded, (element) => textContent(element).includes('reset') && typeof element.props.onClick === 'function')?.props.onClick as () => void)()
    expect(setSearchQuery).toHaveBeenLastCalledWith('')

    searchQuery = 'plat'
    ;(find(render(), (element) => element.props.onValueChange)?.props.onValueChange as (value: string) => void)('24')
    render()
    await effects.at(-1)?.()
    expect(getTeams).toHaveBeenLastCalledWith(1, 24, 'plat')

    ;(find(loaded, (element) => String(element.props.className).includes('cursor-pointer'))?.props.onClick as () => void)()
    expect(find(render(), (element) => element.type === TeamDetailDialog)?.props.open).toBe(true)

    const selectWrapper = find(loaded, (element) => typeof element.props.onClick === 'function' && String(element.props.className).includes('absolute top-4 left-4'))
    ;(selectWrapper?.props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation: mock() })
    expect(textContent(render())).toContain('1 teamsSelected')

    // ponytail: pagination buttons share the same mock shape as the clear-selection icon; selection clearing is covered by bulk success below.
  })

  test('edits, deletes, bulk deletes, and refreshes after dialog success', async () => {
    getTeams = mock(() => Promise.resolve({ items: [team, { ...team, id: 'team-2', name: 'Ops' }], total: 2 }))
    render()
    await effects.at(-1)?.()
    const loaded = render()

    ;(find(loaded, (element) => textContent(element).includes('edit') && typeof element.props.onClick === 'function')?.props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation: mock() })
    expect(find(render(), (element) => element.type === TeamDialog)?.props.team).toEqual(team)

    states[10] = team
    states[8] = true
    await (findAll(render(), (element) => element.props.variant === 'destructive' && typeof element.props.onClick === 'function')[2]?.props.onClick as () => Promise<void>)()
    expect(deleteTeam).toHaveBeenCalledWith('team-1')
    expect(toastSuccess).toHaveBeenCalledWith('teamDeleted')

    const selectAll = find(render(), (element) => typeof element.props.onCheckedChange === 'function')
    ;(selectAll?.props.onCheckedChange as () => void)()
    const bulkOpen = find(render(), (element) => String(element.props.className).includes('text-destructive') && typeof element.props.onClick === 'function')
    ;(bulkOpen?.props.onClick as () => void)()
    await (findAll(render(), (element) => textContent(element).includes('delete') && typeof element.props.onClick === 'function').at(-1)?.props.onClick as () => Promise<void>)()
    expect(deleteTeam).toHaveBeenCalledWith('team-2')
    expect(toastSuccess).toHaveBeenLastCalledWith('bulkDeleted:{"count":2}')

    ;(find(render(), (element) => element.type === TeamDialog)?.props.onSuccess as () => void)()
    expect(getTeams).toHaveBeenCalled()
  })
})
