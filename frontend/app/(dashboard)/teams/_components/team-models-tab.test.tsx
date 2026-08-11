import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Tree = { type: unknown; props: Record<string, unknown> }
type StateSetter<T> = (value: T | ((current: T) => T)) => void

type Model = {
  id: string
  name: string
  provider: string
  provider_display_name?: string | null
  model_id: string
  model_type: string
  is_enabled: boolean
}

type TeamModel = {
  id: string
  team_id: string
  model_id: string
  model: Model
  daily_token_limit: number | null
  monthly_token_limit: number | null
  daily_request_limit: number | null
  monthly_request_limit: number | null
  daily_tokens_used: number
  monthly_tokens_used: number
  daily_requests_used: number
  monthly_requests_used: number
  is_enabled: boolean
  priority: number
  created_at: string
  updated_at: string
}

const jsx = (type: unknown, props: Record<string, unknown> | null): unknown => {
  const safeProps = props ?? {}
  if (typeof type === 'function') return type(safeProps)
  return { type, props: safeProps }
}
const ui = ({ children }: { children?: unknown }) => children
const element = (type: string) => (props: Record<string, unknown>) => jsx(type, props)
const icon = (label: string) => () => jsx('span', { children: label })

let states: unknown[] = []
let stateIndex = 0
let effects: Array<() => void | Promise<void>> = []
let permissions = new Set<string>()

const getTeamModels = mock<() => Promise<TeamModel[]>>()
const getModels = mock<() => Promise<{ items: Model[] }>>()
const updateTeamModel = mock<(
  teamId: string,
  modelId: string,
  data: Record<string, unknown>
) => Promise<unknown>>()
const batchAddTeamModels = mock<(
  teamId: string,
  data: { model_ids: string[] }
) => Promise<unknown>>()
const removeTeamModel = mock<() => Promise<unknown>>()
const toastSuccess = mock<() => void>()

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
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('lucide-react', () => ({
  Plus: icon('plus'), Trash2: icon('trash'), Settings2: icon('settings'),
  Infinity: icon('∞'), AlertCircle: icon('alert'), Search: icon('search'),
}))
mock.module('@/lib/api', () => ({
  teamModelsApi: { getTeamModels, updateTeamModel, batchAddTeamModels, removeTeamModel },
}))
mock.module('@/lib/api/admin/models', () => ({ modelsApi: { getModels } }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ permission, children }: { permission: string; children?: unknown }) =>
    jsx('permission-guard', { permission, children: permissions.has(permission) ? children : null }),
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) =>
    jsx('input', { type: 'checkbox', role: 'switch', checked, onChange: onCheckedChange }),
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: () => void }) =>
    jsx('input', { type: 'checkbox', checked, onChange: onCheckedChange }),
}))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ui }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: element('div') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: { open: boolean; children?: unknown }) => open ? children : null,
  DialogContent: element('section'), DialogDescription: element('p'), DialogFooter: element('footer'),
  DialogHeader: element('header'), DialogTitle: element('h2'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: { open: boolean; children?: unknown }) => open ? children : null,
  AlertDialogAction: element('button'), AlertDialogCancel: element('button'),
  AlertDialogContent: element('section'), AlertDialogDescription: element('p'),
  AlertDialogFooter: element('footer'), AlertDialogHeader: element('header'), AlertDialogTitle: element('h2'),
}))
mock.module('@/components/ui/popover', () => ({
  Popover: ui,
  PopoverContent: element('section'),
  PopoverTrigger: ({ render }: { render: Tree }) => ({
    ...render,
    props: { ...render.props, onClick: () => { states[3] = true } },
  }),
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))

const { TeamModelsTab } = await import('./team-models-tab')

const model = (id: string, name = id, is_enabled = true): Model => ({
  id, name, provider: 'openai', provider_display_name: 'Acme Gateway', model_id: `${id}-api`, model_type: 'chat', is_enabled,
})
const teamModel = (overrides: Partial<TeamModel> = {}): TeamModel => ({
  id: 'team-model-1', team_id: 'team-1', model_id: 'model-1', model: model('model-1', 'GPT Team'),
  daily_token_limit: 2000, monthly_token_limit: null, daily_request_limit: 10,
  monthly_request_limit: null, daily_tokens_used: 1500, monthly_tokens_used: 2500000,
  daily_requests_used: 3, monthly_requests_used: 30, is_enabled: true, priority: 7,
  created_at: '', updated_at: '', ...overrides,
})

function render() {
  stateIndex = 0
  effects = []
  return TeamModelsTab({ teamId: 'team-1' }) as Tree
}

async function load() {
  render()
  effects.at(-1)?.()
  await Promise.resolve()
  await Promise.resolve()
  return render()
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object') return ''
  return [(node as Tree).props?.children].flat().map(textContent).join(' ')
}

function findAll(node: unknown, predicate: (element: Tree) => boolean): Tree[] {
  if (!node || typeof node !== 'object') return []
  const element = node as Tree
  return [
    ...(element.props && predicate(element) ? [element] : []),
    ...[element.props?.children].flat().flatMap((child) => findAll(child, predicate)),
  ]
}

function clickByText(tree: Tree, text: string) {
  const button = findAll(tree, (element) =>
    element.type === 'button' && textContent(element).includes(text)
  )[0]
  if (!button) throw new Error(`missing button: ${text}; saw ${textContent(tree)}`)
  ;(button.props.onClick as () => void)()
}

beforeEach(() => {
  states = []
  permissions = new Set()
  getTeamModels.mockReset()
  getModels.mockReset()
  updateTeamModel.mockReset()
  batchAddTeamModels.mockReset()
  removeTeamModel.mockReset()
  toastSuccess.mockReset()
  getTeamModels.mockResolvedValue([])
  getModels.mockResolvedValue({ items: [] })
  updateTeamModel.mockResolvedValue({})
  batchAddTeamModels.mockResolvedValue([])
  removeTeamModel.mockResolvedValue({})
})

describe('TeamModelsTab', () => {
  test('shows loading placeholders, then renders authorized model quotas', async () => {
    getTeamModels.mockResolvedValue([teamModel()])

    const loading = render()
    expect(findAll(loading, (element) => String(element.props.className).includes('h-10 w-full'))).toHaveLength(3)

    const loaded = await load()

    expect(getTeamModels).toHaveBeenCalledWith('team-1')
    expect(getModels).toHaveBeenCalledWith({ pageSize: 100 })
    expect(textContent(loaded)).toContain('authorizedModels')
    expect(textContent(loaded)).toContain('GPT Team')
    expect(textContent(loaded)).toContain('Acme Gateway')
    expect(textContent(loaded)).toContain('1.5K')
    expect(textContent(loaded)).toContain('2.0K')
    expect(textContent(loaded)).toContain('2.5M')
    expect(textContent(loaded)).toContain('∞')
  })

  test('ends loading after API errors and shows the empty boundary', async () => {
    getTeamModels.mockRejectedValue(new Error('offline'))

    const failed = await load()

    expect(findAll(failed, (element) => String(element.props.className).includes('h-10 w-full'))).toHaveLength(0)
    expect(textContent(failed)).toContain('noModelsAuthorized')
    expect(textContent(failed)).toContain('addModelHint')
  })

  test('hides model actions without team manage permission', async () => {
    getTeamModels.mockResolvedValue([teamModel()])
    getModels.mockResolvedValue({ items: [model('model-2', 'Available model')] })

    const tree = await load()

    expect(textContent(tree)).not.toContain('addModel')
    expect(findAll(tree, (element) => element.props.role === 'switch')).toHaveLength(0)
    expect(textContent(tree)).not.toContain('settings')
    expect(textContent(tree)).not.toContain('trash')
  })

  test('toggles enablement and saves edited limits for permitted users', async () => {
    permissions = new Set(['team:manage'])
    getTeamModels.mockResolvedValue([teamModel()])
    const tree = await load()

    findAll(tree, (element) => element.props.role === 'switch')[0].props.onChange()
    expect(updateTeamModel).toHaveBeenCalledWith('team-1', 'model-1', { is_enabled: false })

    clickByText(tree, 'settings')
    const edit = render()
    const dailyLimit = findAll(edit, (element) => element.type === 'input' && element.props.value === 2000)[0]
    dailyLimit.props.onChange({ target: { value: '3000' } })
    clickByText(render(), 'save')

    expect(updateTeamModel).toHaveBeenLastCalledWith('team-1', 'model-1', {
      daily_token_limit: 3000,
      monthly_token_limit: null,
      daily_request_limit: 10,
      monthly_request_limit: null,
      is_enabled: true,
      priority: 7,
    })
  })

  test('shows add-model empty states and batch-authorizes enabled available models', async () => {
    permissions = new Set(['team:manage'])
    getModels.mockResolvedValue({ items: [model('model-2', 'Available model'), model('model-3', 'Disabled model', false)] })
    await load()
    states[3] = true
    const open = render()

    expect(textContent(open)).toContain('Available model')
    expect(textContent(open)).not.toContain('Disabled model')

    const checkbox = findAll(open, (element) => element.type === 'input' && element.props.type === 'checkbox')[0]
    checkbox.props.onChange()
    clickByText(render(), 'authorizeModels')
    await Promise.resolve()

    expect(batchAddTeamModels).toHaveBeenCalledWith('team-1', { model_ids: ['model-2'] })
    expect(toastSuccess).toHaveBeenCalledWith('modelsAuthorized:{"count":1}')

    states = []
    permissions = new Set(['team:manage'])
    getTeamModels.mockResolvedValue([teamModel()])
    getModels.mockResolvedValue({ items: [model('model-1', 'GPT Team')] })
    expect(textContent(await load())).toContain('allModelsAuthorized')
  })
})
