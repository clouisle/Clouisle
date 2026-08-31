import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const list = mock(() => Promise.resolve({ builtin: [], custom: [], mcp: [] }))
const getById = mock()
const createTool = mock()
const updateTool = mock()
const deleteTool = mock()
const getConfig = mock()
const createConfig = mock()
const updateConfig = mock()
const getMyTeams = mock(() => Promise.resolve([]))
const replace = mock()
const push = mock()
const toastError = mock()
const toastSuccess = mock()
let searchParams = new URLSearchParams()
let permissions = new Set(['tool:read', 'tool:create', 'tool:execute', 'skill:read'])
let hooks: unknown[] = []
let hookIndex = 0

type Tree = { type: unknown; props: Record<string, unknown> }
type HookState<T> = { value: T; deps?: readonly unknown[] }

const sameDeps = (left?: readonly unknown[], right?: readonly unknown[]) =>
  Boolean(left && right && left.length === right.length && left.every((value, index) => Object.is(value, right[index])))

mock.module('react/jsx-dev-runtime', () => ({
  Fragment: Symbol.for('fragment'),
  jsxDEV: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
}))
mock.module('react/jsx-runtime', () => ({
  jsx: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
  jsxs: (type: unknown, props: Record<string, unknown>) => ({ type, props }),
  Fragment: Symbol.for('fragment'),
}))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = hookIndex++
    const slot = (hooks[index] ??= { value: initial }) as HookState<T>
    return [slot.value, (next: T | ((previous: T) => T)) => {
      slot.value = typeof next === 'function' ? (next as (previous: T) => T)(slot.value) : next
    }] as const
  },
  useEffect: (effect: () => void, deps?: readonly unknown[]) => {
    const index = hookIndex++
    const previous = hooks[index] as HookState<undefined> | undefined
    if (!previous || !sameDeps(previous.deps, deps)) effect()
    hooks[index] = { value: undefined, deps }
  },
  useCallback: <T,>(callback: T, deps: readonly unknown[]) => {
    const index = hookIndex++
    const previous = hooks[index] as HookState<T> | undefined
    if (previous && sameDeps(previous.deps, deps)) return previous.value
    hooks[index] = { value: callback, deps }
    return callback
  },
  useMemo: <T,>(factory: () => T, deps: readonly unknown[]) => {
    const index = hookIndex++
    const previous = hooks[index] as HookState<T> | undefined
    if (previous && sameDeps(previous.deps, deps)) return previous.value
    const value = factory()
    hooks[index] = { value, deps }
    return value
  },
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  useSearchParams: () => searchParams,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  toolsApi: {
    list,
    getById,
    create: createTool,
    update: updateTool,
    delete: deleteTool,
    getConfig,
    createConfig,
    updateConfig,
  },
  teamsApi: { getMyTeams },
  isPresetToolCategory: () => false,
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1', role: 'member' } }) }))
mock.module('@/hooks/use-require-team', () => ({ useRequireTeam: mock() }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: (code: string) => permissions.has(code) }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: { id: 'user-1', is_superuser: false } }) }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/card', () => ({ Card: element('section'), CardContent: element('div'), CardDescription: element('p'), CardTitle: element('h2') }))
mock.module('@/components/ui/tabs', () => ({ Tabs: element('tabs'), TabsContent: element('tab-content'), TabsList: element('tab-list'), TabsTrigger: element('tab-trigger') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element('alert-dialog'), AlertDialogAction: element('button'), AlertDialogCancel: element('button'),
  AlertDialogContent: element('div'), AlertDialogDescription: element('p'), AlertDialogFooter: element('footer'),
  AlertDialogHeader: element('header'), AlertDialogTitle: element('h2'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('dropdown'), DropdownMenuContent: element('menu'),
  DropdownMenuItem: element('menuitem'), DropdownMenuTrigger: element('trigger'),
}))
mock.module('lucide-react', () => ({
  Wrench: element('svg'), Plus: element('svg'), RefreshCw: element('svg'), Loader2: element('svg'),
  Globe: element('svg'), Code: element('svg'), Plug: element('svg'), ChevronDown: element('svg'),
  PackageOpen: element('svg'), Upload: element('svg'), Search: element('svg'),
}))
mock.module('./_components/tool-card', () => ({ ToolCard: ({ tool, ...props }: { tool: { display_name: string } } & Record<string, unknown>) => ({ type: 'article', props: { ...props, children: tool.display_name } }) }))

const { ToolList } = await import('./_components/tool-list')
const component = (tag: string) => (props: Record<string, unknown>) => ({ type: tag, props })
mock.module('./_components', () => ({ SkillsPanel: component('skills-panel'), ToolList, ToolTestPanel: component('test-panel') }))
mock.module('./_components/tool-config-dialog', () => ({ ToolConfigDialog: component('config-dialog') }))
mock.module('./_components/http-tool-dialog', () => ({ HttpToolDialog: component('http-dialog') }))
mock.module('./_components/mcp-tool-dialog', () => ({ McpToolDialog: component('mcp-dialog') }))
mock.module('./_components/tool-share-dialog', () => ({ ToolShareDialog: component('share-dialog') }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: component('import-dialog') }))

const { default: CapabilitiesPage } = await import('./page')

function materialize(node: ReactNode): ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  if (typeof tree.type === 'function') return materialize((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
  const children = tree.props.children
  return {
    ...tree,
    props: {
      ...tree.props,
      children: Array.isArray(children) ? children.map(materialize) : materialize(children as ReactNode),
    },
  }
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean, found: Tree[] = []): Tree[] {
  if (!node || typeof node !== 'object' || !('type' in node)) return found
  const tree = node as Tree
  if (predicate(tree)) found.push(tree)
  const children = tree.props.children
  for (const child of Array.isArray(children) ? children : [children]) findAll(child as ReactNode, predicate, found)
  return found
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean) {
  const match = findAll(node, predicate)[0]
  if (!match) throw new Error('Element not found')
  return match
}

function render() {
  hookIndex = 0
  return materialize(CapabilitiesPage())
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

const builtin = { name: 'clock', display_name: 'Clock', description: 'Current time', type: 'builtin', category: 'time', parameters: [], is_enabled: true, requires_config: false, config_fields: [] }
const custom = { id: 'custom-1', name: 'weather', display_name: 'Weather', description: 'Forecast', type: 'custom', custom_type: 'http', category: 'network', parameters: [], is_enabled: true, requires_config: false, config_fields: [], created_by_id: 'user-1' }
const mcp = { id: 'mcp-1', name: 'files', display_name: 'Files', description: 'File access', type: 'mcp', category: 'storage', parameters: [], is_enabled: true, requires_config: false, config_fields: [] }

beforeEach(() => {
  list.mockReset()
  list.mockResolvedValue({ builtin: [builtin], custom: [custom], mcp: [mcp] })
  getById.mockReset()
  createTool.mockReset()
  updateTool.mockReset()
  deleteTool.mockReset()
  getConfig.mockReset()
  createConfig.mockReset()
  updateConfig.mockReset()
  getMyTeams.mockReset()
  getMyTeams.mockResolvedValue([])
  replace.mockReset()
  push.mockReset()
  toastError.mockReset()
  toastSuccess.mockReset()
  searchParams = new URLSearchParams()
  permissions = new Set(['tool:read', 'tool:create', 'tool:execute', 'skill:read'])
  Object.defineProperty(globalThis, 'window', { value: { location: { pathname: '/app/capabilities' } }, configurable: true })
  hooks = []
})

describe('CapabilitiesPage', () => {
  test('loads the merged tool list and supports search and type filters', async () => {
    let release!: (value: { builtin: typeof builtin[]; custom: typeof custom[]; mcp: typeof mcp[] }) => void
    list.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))

    expect(findAll(render(), (tree) => tree.type === 'article')).toHaveLength(0)
    release({ builtin: [builtin], custom: [custom], mcp: [mcp] })
    await settle()

    let tree = render()
    expect(findAll(tree, (node) => node.type === 'article').map((node) => node.props.children)).toEqual(['Clock', 'Weather', 'Files'])

    const search = find(tree, (node) => node.props.placeholder === 'searchPlaceholder')
    ;(search.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'weather' } })
    tree = render()
    expect(findAll(tree, (node) => node.type === 'article').map((node) => node.props.children)).toEqual(['Weather'])

    ;(find(tree, (node) => node.type === 'tabs' && node.props.value === 'all').props.onValueChange as (value: string) => void)('mcp')
    expect(findAll(render(), (node) => node.type === 'article')).toHaveLength(0)
  })

  test('honors read and execute permissions while routing tab changes', async () => {
    permissions = new Set(['skill:read'])
    searchParams = new URLSearchParams('tab=skills')
    await settle()
    let tree = render()

    expect(findAll(tree, (node) => node.props['data-testid'] === 'capabilities-tools-panel')).toHaveLength(0)
    expect(findAll(tree, (node) => node.props['data-testid'] === 'capabilities-skills-panel')).toHaveLength(1)
    expect(list).not.toHaveBeenCalled()

    permissions = new Set(['tool:read', 'skill:read'])
    hooks = []
    tree = render()
    ;(find(tree, (node) => node.props['data-testid'] === 'capabilities-tabs').props.onValueChange as (value: string) => void)('skills')
    expect(replace).toHaveBeenCalledWith('/app/capabilities?tab=skills', { scroll: false })
    await settle()
    await settle()
    tree = render()
    const toolCard = find(tree, (node) => node.type === 'article')
    expect(toolCard.props.onSelect).toBeUndefined()
    expect(toolCard.props.onTest).toBeUndefined()
  })

  test('recovers from a failed load through refresh and reload callbacks', async () => {
    const originalError = console.error
    console.error = mock()
    list.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ builtin: [builtin], custom: [], mcp: [] })
    render()
    await settle()

    let tree = render()
    expect(findAll(tree, (node) => node.type === 'article')).toHaveLength(0)
    await (find(tree, (node) => node.props['data-testid'] === 'capabilities-refresh-button').props.onClick as () => Promise<void>)()
    tree = render()
    expect(findAll(tree, (node) => node.type === 'article').map((node) => node.props.children)).toEqual(['Clock'])

    await (find(tree, (node) => node.type === 'import-dialog').props.onImported as () => Promise<void>)()
    await (find(tree, (node) => node.type === 'share-dialog').props.onSuccess as () => Promise<void>)()
    expect(list).toHaveBeenCalledTimes(4)
    console.error = originalError
  })

  test('opens tool edit dialogs and saves or deletes tools', async () => {
    getById.mockResolvedValue({ ...custom, http_config: { url: 'https://example.com', method: 'GET' } })
    updateTool.mockResolvedValue({})
    deleteTool.mockResolvedValue({})
    render()
    await settle()

    let tree = render()
    const weather = find(tree, (node) => node.type === 'article' && node.props.children === 'Weather')
    await (weather.props.onEdit as (tool: typeof custom) => Promise<void>)(custom)
    tree = render()
    await (find(tree, (node) => node.type === 'http-dialog').props.onSave as (data: Record<string, string>) => Promise<void>)({ display_name: 'Weather API' })
    expect(updateTool).toHaveBeenCalledWith('custom-1', { display_name: 'Weather API' })
    expect(toastSuccess).toHaveBeenCalledWith('tools.toolUpdated')

    ;(weather.props.onDelete as (tool: typeof custom) => void)(custom)
    tree = render()
    await (find(tree, (node) => node.type === 'button' && node.props.variant === 'destructive').props.onClick as () => Promise<void>)()
    expect(deleteTool).toHaveBeenCalledWith('custom-1')
  })

  test('creates tools and handles builtin config and guarded actions', async () => {
    const configurable = { ...builtin, requires_config: true, config_fields: ['API_KEY'] }
    list.mockResolvedValue({ builtin: [configurable], custom: [], mcp: [] })
    getConfig.mockRejectedValueOnce({ response: { status: 404 } }).mockResolvedValueOnce({})
    createConfig.mockResolvedValue({})
    updateConfig.mockResolvedValue({})
    createTool.mockResolvedValue({})
    searchParams = new URLSearchParams('action=create')

    let tree = render()
    await settle()
    tree = render()
    expect(replace).toHaveBeenCalledWith('/app/capabilities', { scroll: false })
    await (find(tree, (node) => node.type === 'http-dialog').props.onSave as (data: Record<string, string>) => Promise<void>)({ name: 'http' })
    expect(createTool).toHaveBeenCalledWith('team-1', { name: 'http' })

    const clock = find(render(), (node) => node.type === 'article' && node.props.children === 'Clock')
    await (clock.props.onEdit as (tool: typeof configurable) => Promise<void>)(configurable)
    tree = render()
    await (find(tree, (node) => node.type === 'config-dialog').props.onSave as (data: Record<string, string>) => Promise<void>)({ API_KEY: 'saved' })
    expect(createConfig).toHaveBeenCalledWith('clock', { API_KEY: 'saved' }, 'team-1')

    await (find(render(), (node) => node.type === 'config-dialog').props.onSave as (data: Record<string, string>) => Promise<void>)({ API_KEY: 'updated' })
    expect(updateConfig).toHaveBeenCalledWith('clock', { API_KEY: 'updated' }, 'team-1')

    ;(clock.props.onDelete as (tool: typeof configurable) => void)(configurable)
    ;(clock.props.onShare as (tool: typeof configurable) => void)(configurable)
    expect(toastError).toHaveBeenCalledWith('tools.error.cannotDeleteBuiltin')
    expect(toastError).toHaveBeenCalledWith('tools.error.cannotShareBuiltin')
  })

  test('routes tool actions through test, code, mcp, and unknown-detail flows', async () => {
    getById
      .mockResolvedValueOnce({ ...mcp })
      .mockResolvedValueOnce({ ...custom, custom_type: 'code' })
      .mockResolvedValueOnce({ ...custom, custom_type: 'unknown' })
    createTool.mockResolvedValue({})
    updateTool.mockResolvedValue({})
    render()
    await settle()

    let tree = render()
    const files = find(tree, (node) => node.type === 'article' && node.props.children === 'Files')
    ;(files.props.onSelect as (tool: typeof mcp) => void)(mcp)
    expect(find(render(), (node) => node.type === 'test-panel').props.tool).toBe(mcp)

    await (files.props.onEdit as (tool: typeof mcp) => Promise<void>)(mcp)
    tree = render()
    await (find(tree, (node) => node.type === 'mcp-dialog').props.onSave as (data: Record<string, string>) => Promise<void>)({ name: 'mcp' })
    expect(updateTool).toHaveBeenCalledWith('mcp-1', { name: 'mcp' })

    ;(findAll(tree, (node) => node.type === 'menuitem')[1].props.onClick as () => void)()
    expect(push).toHaveBeenCalledWith('/app/capabilities/code')
    ;(findAll(tree, (node) => node.type === 'menuitem')[2].props.onClick as () => void)()
    await (find(render(), (node) => node.type === 'mcp-dialog').props.onSave as (data: Record<string, string>) => Promise<void>)({ name: 'new-mcp' })
    expect(createTool).toHaveBeenCalledWith('team-1', { name: 'new-mcp' })

    await (find(render(), (node) => node.type === 'article' && node.props.children === 'Weather').props.onEdit as (tool: typeof custom) => Promise<void>)(custom)
    expect(push).toHaveBeenCalledWith('/app/capabilities/code?id=custom-1')
    await (find(render(), (node) => node.type === 'article' && node.props.children === 'Weather').props.onEdit as (tool: typeof custom) => Promise<void>)(custom)
    expect(toastError).toHaveBeenCalledWith('tools.error.unknownToolType')
  })
})
