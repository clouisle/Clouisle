import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const agentGetById = mock(() => Promise.resolve())
const agentUpdate = mock(() => Promise.resolve())
const agentPublish = mock(() => Promise.resolve())
const agentUnpublish = mock(() => Promise.resolve())
const agentListPage = mock(() => Promise.resolve({ items: [], total: 0, page: 1, page_size: 10 }))
const agentFilterOptions = mock(() => Promise.resolve({ statuses: [], visibilities: [], teams: [], creators: [] }))
const agentDuplicate = mock(() => Promise.resolve())
const agentDelete = mock(() => Promise.resolve())
const agentCreate = mock(() => Promise.resolve())

const workflowGetById = mock(() => Promise.resolve())
const workflowUpdate = mock(() => Promise.resolve())
const workflowPublish = mock(() => Promise.resolve())
const workflowUnpublish = mock(() => Promise.resolve())
const workflowListPage = mock(() => Promise.resolve({ items: [], total: 0, page: 1, page_size: 10 }))
const workflowFilterOptions = mock(() => Promise.resolve({ statuses: [], visibilities: [], trigger_types: [], teams: [], creators: [] }))
const workflowDuplicate = mock(() => Promise.resolve())
const workflowDelete = mock(() => Promise.resolve())
const workflowCreate = mock(() => Promise.resolve())

const teamsGet = mock(() => Promise.resolve({ items: [] }))
const packageExport = mock(() => Promise.resolve({ blob: new Blob(['x']), filename: 'export.json' }))
const downloadBlob = mock()
const toastSuccess = mock()
const toastError = mock()
const confirmMock = mock(() => true)

let state: unknown[] = []
let stateIndex = 0
let memoValues: unknown[] = []
let memoDeps: unknown[][] = []
let memoIndex = 0
let effectDeps: unknown[][] = []
let effectIndex = 0
let pendingEffects: Array<() => void | Promise<void>> = []
let searchValue = ''

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const sameDeps = (left?: unknown[], right?: unknown[]) =>
  Boolean(left && right && left.length === right.length && left.every((value, index) => Object.is(value, right[index])))

function resetHooks() {
  stateIndex = 0
  memoIndex = 0
  effectIndex = 0
  pendingEffects = []
}

function resetState() {
  state = []
  memoValues = []
  memoDeps = []
  effectDeps = []
  searchValue = ''
  resetHooks()
}

const translators = new Map<string, (key: string, values?: Record<string, unknown>) => string>()
function translator(namespace: string) {
  if (!translators.has(namespace)) {
    translators.set(namespace, (key, values) => values ? `${key}:${JSON.stringify(values)}` : key)
  }
  return translators.get(namespace)!
}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T, deps: unknown[]) => {
    const index = memoIndex++
    if (!sameDeps(memoDeps[index], deps)) {
      memoValues[index] = callback
      memoDeps[index] = deps
    }
    return memoValues[index] as T
  },
  useEffect: (effect: () => void | Promise<void>, deps: unknown[]) => {
    const index = effectIndex++
    if (!sameDeps(effectDeps[index], deps)) {
      effectDeps[index] = deps
      pendingEffects.push(effect)
    }
  },
  useMemo: <T,>(factory: () => T, deps: unknown[]) => {
    const index = memoIndex++
    if (!sameDeps(memoDeps[index], deps)) {
      memoValues[index] = factory()
      memoDeps[index] = deps
    }
    return memoValues[index] as T
  },
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
}))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: translator }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('next/image', () => ({ default: ({ children, ...props }: Record<string, unknown>) => ({ type: 'img', props: { ...props, children } }) }))
mock.module('next/link', () => ({ default: ({ children, ...props }: Record<string, unknown>) => ({ type: 'a', props: { ...props, children } }) }))
const icon = (name: string) => ({ children, ...props }: Record<string, unknown>) => ({ type: name, props: { ...props, children } })
mock.module('lucide-react', () => ({
  Copy: icon('Copy'),
  Download: icon('Download'),
  FileEdit: icon('FileEdit'),
  Loader2: icon('Loader2'),
  MoreHorizontal: icon('MoreHorizontal'),
  Plus: icon('Plus'),
  Search: icon('Search'),
  Send: icon('Send'),
  Trash2: icon('Trash2'),
  Upload: icon('Upload'),
  X: icon('X'),
}))

const element = (tag: string) => ({ children, ...props }: Record<string, unknown>) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/badge', () => ({ Badge: element('badge') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/table', () => ({
  Table: element('table'),
  TableBody: element('tbody'),
  TableCell: element('td'),
  TableHead: element('th'),
  TableHeader: element('thead'),
  TableRow: element('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: element('select-content'),
  SelectItem: element('option'),
  SelectTrigger: element('select-trigger'),
  SelectValue: element('select-value'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('dropdown'),
  DropdownMenuContent: element('dropdown-content'),
  DropdownMenuItem: ({ render, children, ...props }: Record<string, unknown>) => render ?? { type: 'dropdown-item', props: { ...props, children } },
  DropdownMenuTrigger: ({ render }: { render: ReactNode }) => render,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: element('tooltip'),
  TooltipContent: element('tooltip-content'),
  TooltipTrigger: ({ render }: { render: ReactNode }) => render,
}))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('checkbox') }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, options, onSelectionChange }: { title: string; options: Array<{ value: string }>; onSelectionChange: (values: Set<string>) => void }) => ({
    type: 'filter',
    props: { title, onClick: () => onSelectionChange(new Set([options[0]?.value ?? title])) },
  }),
}))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: { children: ReactNode }) => children }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: element('import-dialog') }))
mock.module('@/app/(platform)/app/apps/_components/app-create-dialog', () => ({ AppCreateDialog: element('create-dialog') }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => [searchValue, (value: string) => { searchValue = value }] as const,
}))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
}))
mock.module('@/lib/api/admin', () => ({
  adminAgentsApi: {
    getById: agentGetById,
    update: agentUpdate,
    publish: agentPublish,
    unpublish: agentUnpublish,
    listPage: agentListPage,
    getFilterOptions: agentFilterOptions,
    duplicate: agentDuplicate,
    delete: agentDelete,
    create: agentCreate,
  },
  adminWorkflowsApi: {
    getById: workflowGetById,
    update: workflowUpdate,
    publish: workflowPublish,
    unpublish: workflowUnpublish,
    listPage: workflowListPage,
    getFilterOptions: workflowFilterOptions,
    duplicate: workflowDuplicate,
    delete: workflowDelete,
    create: workflowCreate,
  },
  teamsApi: { getTeams: teamsGet },
}))
mock.module('@/lib/api/packages', () => ({ adminPackagesApi: { export: packageExport }, downloadBlob }))
mock.module('@/app/(platform)/app/apps/[id]/page', () => ({ AgentEditor: element('agent-editor') }))
mock.module('@/app/(platform)/app/apps/workflow/[id]/page', () => ({ WorkflowEditorContent: element('workflow-editor') }))
mock.module('@xyflow/react', () => ({ ReactFlowProvider: element('flow-provider') }))

const { AdminAgentEditClient } = await import('./admin-agent-edit-client')
const { AdminWorkflowEditClient } = await import('./admin-workflow-edit-client')
const { AdminAgentsPanel } = await import('./admin-agents-panel')
const { AdminWorkflowsPanel } = await import('./admin-workflows-panel')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  for (const child of Array.isArray(node) ? node : [node]) {
    const resolved = resolve(child)
    if (Array.isArray(resolved)) {
      try { return find(resolved, predicate) } catch {}
      continue
    }
    if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) continue
    const tree = resolved as Tree
    if (predicate(tree)) return tree
    try { return find(tree.props.children as ReactNode, predicate) } catch {}
  }
  throw new Error('Element not found')
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  const matches: Tree[] = []
  for (const child of Array.isArray(node) ? node : [node]) {
    const resolved = resolve(child)
    if (Array.isArray(resolved)) {
      matches.push(...findAll(resolved, predicate))
      continue
    }
    if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) continue
    const tree = resolved as Tree
    if (predicate(tree)) matches.push(tree)
    matches.push(...findAll(tree.props.children as ReactNode, predicate))
  }
  return matches
}

async function renderPanel(component: () => ReactNode) {
  resetHooks()
  const tree = component()
  const effects = pendingEffects
  pendingEffects = []
  for (const effect of effects) await effect()
  await Promise.resolve()
  return tree
}

async function settledPanel(component: () => ReactNode) {
  await renderPanel(component)
  return renderPanel(component)
}

beforeEach(() => {
  for (const fn of [
    agentGetById, agentUpdate, agentPublish, agentUnpublish, agentListPage, agentFilterOptions, agentDuplicate, agentDelete, agentCreate,
    workflowGetById, workflowUpdate, workflowPublish, workflowUnpublish, workflowListPage, workflowFilterOptions, workflowDuplicate, workflowDelete, workflowCreate,
    teamsGet, packageExport, downloadBlob, toastSuccess, toastError, confirmMock,
  ]) fn.mockReset()
  resetState()
  Object.assign(globalThis, { window: { confirm: confirmMock } })
  confirmMock.mockReturnValue(true)
  teamsGet.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core' }] })
  packageExport.mockResolvedValue({ blob: new Blob(['x']), filename: 'export.json' })
})

describe('admin app edit clients', () => {
  test('wire admin agent editor permissions and API methods', async () => {
    const tree = AdminAgentEditClient({ agentId: 'agent-1' })
    const editor = find(tree, (node) => node.type === 'agent-editor')

    expect(editor.props).toMatchObject({ agentId: 'agent-1', backHref: '/apps', allowPermissionUpdate: true, baseUrl: '/apps/agents/agent-1/edit' })
    await (editor.props.api as { updateAgent: (id: string, data: { name: string }) => Promise<unknown> }).updateAgent('agent-1', { name: 'New' })
    expect(agentUpdate).toHaveBeenCalledWith('agent-1', { name: 'New' })
    expect((editor.props.api as { publishAgent: unknown }).publishAgent).toBe(agentPublish)
    expect((editor.props.api as { unpublishAgent: unknown }).unpublishAgent).toBe(agentUnpublish)
  })

  test('wire admin workflow editor permissions and API methods', async () => {
    const tree = AdminWorkflowEditClient({ workflowId: 'workflow-1' })
    const editor = find(tree, (node) => node.type === 'workflow-editor')

    expect(editor.props).toMatchObject({ workflowId: 'workflow-1', backHref: '/apps?tab=workflows', updatePermission: 'admin:app:update', allowPermissionUpdate: true, baseUrl: '/apps/workflows/workflow-1/edit' })
    await (editor.props.api as { updateWorkflow: (id: string, data: { name: string }) => Promise<unknown> }).updateWorkflow('workflow-1', { name: 'New' })
    expect(workflowUpdate).toHaveBeenCalledWith('workflow-1', { name: 'New' })
    expect((editor.props.api as { publishWorkflow: unknown }).publishWorkflow).toBe(workflowPublish)
    expect((editor.props.api as { unpublishWorkflow: unknown }).unpublishWorkflow).toBe(workflowUnpublish)
  })
})

describe('admin app panels', () => {
  test('loads agents, forwards search filters, and publishes a draft row', async () => {
    agentListPage.mockResolvedValue({
      items: [{ id: 'agent-1', name: 'Support Bot', status: 'draft', visibility: 'team', team: { name: 'Core' }, created_by: { username: 'ada' }, conversation_count: 2, message_count: 5, updated_at: '2026-01-01T00:00:00Z' }],
      total: 1,
      page: 1,
      page_size: 10,
    })
    agentFilterOptions.mockResolvedValue({
      statuses: [{ value: 'draft' }],
      visibilities: [{ value: 'team' }],
      teams: [{ value: 'team-1', label: 'Core' }],
      creators: [{ value: 'ada', label: 'Ada' }],
    })

    let tree = await settledPanel(() => AdminAgentsPanel())
    expect(agentListPage).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: undefined, status: undefined, visibility: undefined, team_id: undefined, creator: undefined })
    expect(JSON.stringify(tree)).toContain('Support Bot')
    expect(find(tree, (node) => node.type === 'create-dialog').props).toMatchObject({ initialType: 'agent', allowedTypes: ['agent'] })

    ;(find(tree, (node) => node.type === 'input').props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'support' } })
    tree = await settledPanel(() => AdminAgentsPanel())
    expect(agentListPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'support' }))

    const publishItem = find(tree, (node) => node.type === 'dropdown-item' && JSON.stringify(node).includes('actions.publish'))
    await (publishItem.props.onClick as () => Promise<void>)()
    expect(agentPublish).toHaveBeenCalledWith('agent-1')
    expect(toastSuccess).toHaveBeenCalledWith('actions.published')
  })

  test('handles agent filters, pagination, dialogs, row actions, and bulk actions', async () => {
    agentListPage.mockResolvedValue({
      items: [
        { id: 'agent-1', name: 'Support Bot', status: 'published', visibility: 'public', team: { name: 'Core' }, created_by: { username: 'ada' }, conversation_count: 2, message_count: 5, updated_at: '2026-01-01T00:00:00Z', icon: '🤖' },
        { id: 'agent-2', name: 'Draft Bot', status: 'draft', visibility: 'team', team: null, created_by: null, conversation_count: 0, message_count: 1, updated_at: '2026-01-02T00:00:00Z', avatar_url: 'https://example.test/avatar.png' },
      ],
      total: 25,
      page: 1,
      page_size: 10,
    })
    agentFilterOptions.mockResolvedValue({
      statuses: [{ value: 'published' }],
      visibilities: [{ value: 'public' }],
      teams: [{ value: 'team-1', label: 'Core' }],
      creators: [{ value: 'ada', label: 'Ada' }],
    })

    let tree = await settledPanel(() => AdminAgentsPanel())

    for (const title of ['status', 'columns.visibility', 'columns.team', 'columns.creator']) {
      ;(find(tree, (node) => node.type === 'filter' && node.props.title === title).props.onClick as () => void)()
      tree = await settledPanel(() => AdminAgentsPanel())
    }
    expect(agentListPage).toHaveBeenLastCalledWith(expect.objectContaining({ status: ['published'], visibility: ['public'], team_id: ['team-1'], creator: ['ada'] }))

    ;(find(tree, (node) => node.type === 'button' && JSON.stringify(node).includes('actions.reset')).props.onClick as () => void)()
    tree = await settledPanel(() => AdminAgentsPanel())
    expect(agentListPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, status: undefined, visibility: undefined, team_id: undefined, creator: undefined }))

    ;(find(tree, (node) => node.type === 'select').props.onValueChange as (value: string) => void)('20')
    tree = await settledPanel(() => AdminAgentsPanel())
    expect(agentListPage).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 20 }))

    ;(findAll(tree, (node) => node.type === 'button' && JSON.stringify(node).includes('pagination.next')).at(-1)!.props.onClick as () => void)()
    tree = await settledPanel(() => AdminAgentsPanel())
    expect(agentListPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))

    ;(find(tree, (node) => node.type === 'button' && JSON.stringify(node).includes('import')).props.onClick as () => void)()
    expect(find(await settledPanel(() => AdminAgentsPanel()), (node) => node.type === 'import-dialog').props.open).toBe(true)

    ;(find(tree, (node) => node.type === 'button' && JSON.stringify(node).includes('actions.create')).props.onClick as () => void)()
    expect(find(await settledPanel(() => AdminAgentsPanel()), (node) => node.type === 'create-dialog').props.open).toBe(true)

    const items = findAll(tree, (node) => node.type === 'dropdown-item')
    await (items.find((node) => JSON.stringify(node).includes('actions.unpublish'))!.props.onClick as () => Promise<void>)()
    expect(agentUnpublish).toHaveBeenCalledWith('agent-1')
    await (items.find((node) => JSON.stringify(node).includes('actions.duplicate'))!.props.onClick as () => Promise<void>)()
    expect(agentDuplicate).toHaveBeenCalledWith('agent-1')
    await (items.find((node) => JSON.stringify(node).includes('actions.export'))!.props.onClick as () => Promise<void>)()
    expect(packageExport).toHaveBeenCalledWith('agent', 'agent-1')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'export.json')
    await (items.find((node) => JSON.stringify(node).includes('actions.delete'))!.props.onClick as () => Promise<void>)()
    expect(confirmMock).toHaveBeenCalledWith('agents.deleteConfirm:{"name":"Support Bot"}')
    expect(agentDelete).toHaveBeenCalledWith('agent-1')

    ;(find(tree, (node) => node.type === 'checkbox').props.onCheckedChange as () => void)()
    tree = await renderPanel(() => AdminAgentsPanel())
    const bulkButtons = findAll(tree, (node) => node.type === 'button' && node.props.className === 'h-8 w-8' && typeof node.props.onClick === 'function')
    await (bulkButtons[1].props.onClick as () => Promise<void>)()
    expect(agentPublish).toHaveBeenCalledWith('agent-2')
    await (bulkButtons[2].props.onClick as () => Promise<void>)()
    expect(agentUnpublish).toHaveBeenCalledWith('agent-2')
    await (find(tree, (node) => node.type === 'button' && String(node.props.className).includes('text-destructive')).props.onClick as () => Promise<void>)()
    expect(agentDelete).toHaveBeenCalledWith('agent-2')
  })

  test('loads workflows, forwards trigger filters, and exports a workflow package', async () => {
    workflowListPage.mockResolvedValue({
      items: [{ id: 'workflow-1', name: 'Nightly Sync', status: 'published', visibility: 'public', trigger_type: 'manual', team_name: 'Core', created_by_name: 'ada', run_count: 3, success_count: 2, fail_count: 1, updated_at: '2026-01-01T00:00:00Z', icon: null }],
      total: 1,
      page: 1,
      page_size: 10,
    })
    workflowFilterOptions.mockResolvedValue({
      statuses: [{ value: 'published' }],
      visibilities: [{ value: 'public' }],
      trigger_types: [{ value: 'manual' }],
      teams: [{ value: 'team-1', label: 'Core' }],
      creators: [{ value: 'ada', label: 'Ada' }],
    })

    let tree = await settledPanel(() => AdminWorkflowsPanel())
    expect(workflowListPage).toHaveBeenLastCalledWith({ page: 1, pageSize: 10, search: undefined, status: undefined, visibility: undefined, trigger_type: undefined, team_id: undefined, creator: undefined })
    expect(JSON.stringify(tree)).toContain('Nightly Sync')
    expect(find(tree, (node) => node.type === 'create-dialog').props).toMatchObject({ initialType: 'workflow', allowedTypes: ['workflow'] })

    ;(find(tree, (node) => node.type === 'filter' && node.props.title === 'columns.trigger').props.onClick as () => void)()
    tree = await settledPanel(() => AdminWorkflowsPanel())
    expect(workflowListPage).toHaveBeenLastCalledWith(expect.objectContaining({ trigger_type: ['manual'] }))

    const exportItem = findAll(tree, (node) => node.type === 'dropdown-item').find((node) => JSON.stringify(node).includes('actions.export'))
    expect(exportItem).toBeDefined()
    await (exportItem!.props.onClick as () => Promise<void>)()
    expect(packageExport).toHaveBeenCalledWith('workflow', 'workflow-1')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'export.json')
  })
})
