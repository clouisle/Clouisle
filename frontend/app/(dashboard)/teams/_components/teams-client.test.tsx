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
mock.module('sonner', () => ({ toast: { success: mock() } }))
mock.module('@/lib/utils', () => ({ formatDateTime: () => 'formatted-date' }))
mock.module('@/lib/api/admin', () => ({
  teamsApi: { getTeams: (...args: unknown[]) => getTeams(...args), deleteTeam: mock() },
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => ['', mock()] }))
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

beforeEach(() => {
  states = []
  getTeams = () => Promise.resolve({ items: [], total: 0 })
})

describe('TeamsClient', () => {
  test('shows loading placeholders, then renders the fetched team list', async () => {
    const team = {
      id: 'team-1', name: 'Platform', description: 'Builds the platform', avatar_url: null,
      is_default: false, owner: { username: 'alex' }, created_at: '2026-01-01', updated_at: '2026-01-01',
    }
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
})
