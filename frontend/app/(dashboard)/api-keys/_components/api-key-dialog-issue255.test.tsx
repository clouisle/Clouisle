import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign((props: Props) => jsx(name, props), { displayName: name })
let states: unknown[] = [], effects: unknown[][] = [], stateIndex = 0, effectIndex = 0
const hooks = {
  useState: <T,>(initial: T) => { const i = stateIndex++; if (!(i in states)) states[i] = initial; return [states[i] as T, (value: T | ((old: T) => T)) => { states[i] = typeof value === 'function' ? (value as (old: T) => T)(states[i] as T) : value }] as const },
  useMemo: <T,>(factory: () => T) => factory(),
  useEffect: (effect: () => void, deps: unknown[]) => { const i = effectIndex++; if (!effects[i] || effects[i].some((v, x) => v !== deps[x])) { effects[i] = deps; effect() } },
}
const getAgents = mock(async () => ({ items: [] }))
const getWorkflows = mock(async () => ({ items: [] }))
const createAPIKey = mock(async () => ({ key: 'returned-once' }))
const updateAPIKey = mock(async () => ({}))
const toast = { success: mock(() => {}) }
let normalizedErrors: Props = {}

mock.module('react', () => ({ default: hooks, ...hooks }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: component('Fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: component('Fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => ({ Bot: component('Bot'), Loader2: component('Loader2'), Workflow: component('Workflow') }))
mock.module('@/lib/api', () => ({
  apiKeysApi: { createAPIKey, updateAPIKey }, agentsApi: { getAgents }, workflowsApi: { getWorkflows },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Props, field: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  getValidationSummaryEntries: (errors: Props) => Object.entries(errors), normalizeValidationErrors: () => normalizedErrors,
  formatValidationSummaryMessage: (field: string, message: unknown) => `${field}: ${message}`,
}))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/number-input', ['NumberInput']],
  ['@/components/ui/label', ['Label']], ['@/components/ui/switch', ['Switch']], ['@/components/ui/checkbox', ['Checkbox']],
  ['@/components/ui/scroll-area', ['ScrollArea']], ['@/components/ui/field', ['FieldError']],
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogDescription', 'DialogFooter', 'DialogHeader', 'DialogTitle']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component(name)])))

const { APIKeyDialog } = await import('./api-key-dialog')
const onOpenChange = mock(() => {})
const onSuccess = mock(() => {})
const agents = [{ id: 'agent-1', name: 'Writer', icon: null, avatar_url: null }, { id: 'agent-2', name: 'Reader', icon: '/icon.png' }]
const workflows = [{ id: 'wf-1', name: 'Publish', icon: null }, { id: 'wf-2', name: 'Review', icon: '/wf.png' }]
function render(overrides: Props = {}) { stateIndex = effectIndex = 0; return APIKeyDialog({ open: true, onOpenChange, onSuccess, ...overrides }) as Node }
function descendants(value: unknown): Node[] { if (Array.isArray(value)) return value.flatMap(descendants); if (!value || typeof value !== 'object' || !('type' in value)) return []; const node = value as Node; const rendered = typeof node.type === 'function' ? (node.type as (props: Props) => unknown)(node.props) : node; if (rendered !== node) return descendants(rendered); return [node, ...descendants(node.props.children)] }
function text(value: unknown): string { if (typeof value === 'string' || typeof value === 'number') return String(value); if (Array.isArray(value)) return value.map(text).join(''); if (!value || typeof value !== 'object' || !('props' in value)) return ''; return text((value as Node).props.children) }
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
const submit = (tree: Node) => descendants(tree).find((n) => n.type === 'form')!.props.onSubmit({ preventDefault: mock(() => {}) })

beforeEach(() => {
  states = []; effects = []; normalizedErrors = {}
  for (const fn of [getAgents, getWorkflows, createAPIKey, updateAPIKey, toast.success, onOpenChange, onSuccess]) fn.mockClear()
  getAgents.mockResolvedValue({ items: agents } as never); getWorkflows.mockResolvedValue({ items: workflows } as never)
  createAPIKey.mockResolvedValue({ key: 'returned-once' } as never); updateAPIKey.mockResolvedValue({} as never)
})

describe('dashboard API key dialog issue #255 coverage', () => {
  test('loads options, validates name, toggles scopes, and creates without exposing a secret', async () => {
    render(); await flush(); let tree = render()
    expect(getAgents).toHaveBeenCalledWith({ pageSize: 100, status: 'published' })
    expect(getWorkflows).toHaveBeenCalledWith({ pageSize: 100, status: 'published' })
    await submit(tree); tree = render()
    expect(text(tree)).toContain('nameRequired')
    expect(createAPIKey).not.toHaveBeenCalled()

    const name = descendants(tree).find((n) => n.type === 'Input' && n.props.id === 'name')!
    name.props.onChange({ target: { value: 'CI key' } })
    tree = render()
    let rows = descendants(tree).filter((n) => n.type === 'div' && String(n.props.className).includes('cursor-pointer'))
    rows[0].props.onClick(); tree = render()
    rows = descendants(tree).filter((n) => n.type === 'div' && String(n.props.className).includes('cursor-pointer'))
    rows[2].props.onClick(); tree = render()
    descendants(tree).find((n) => n.type === 'NumberInput')!.props.onChange(25); tree = render()
    descendants(tree).find((n) => n.type === 'Input' && n.props.id === 'expires_at')!.props.onChange({ target: { value: '2027-01-01' } })
    tree = render(); await submit(tree)

    expect(createAPIKey).toHaveBeenCalledWith(expect.objectContaining({ name: 'CI key', rate_limit: 25, agent_ids: ['agent-1'], workflow_ids: ['wf-1'] }))
    expect(onSuccess).toHaveBeenCalledWith('returned-once')
    expect(toast.success).toHaveBeenCalledWith('keyCreated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('prefills and updates an existing key including active state and removed scopes', async () => {
    const apiKey = { id: 'key-1', name: 'Existing', rate_limit: 10, expires_at: '2027-02-03T00:00:00Z', is_active: true, agents: [agents[0]], workflows: [workflows[0]] }
    render({ apiKey }); await flush(); let tree = render({ apiKey })
    expect((states[0] as Props).expires_at).toBe('2027-02-03')
    descendants(tree).find((n) => n.type === 'Switch')!.props.onCheckedChange(false)
    const rows = descendants(tree).filter((n) => n.type === 'div' && String(n.props.className).includes('cursor-pointer'))
    rows[0].props.onClick(); rows[2].props.onClick()
    tree = render({ apiKey }); await submit(tree)

    expect(updateAPIKey).toHaveBeenCalledWith('key-1', expect.objectContaining({ name: 'Existing', is_active: false, agent_ids: [], workflow_ids: [] }))
    expect(onSuccess).toHaveBeenCalledWith()
    expect(toast.success).toHaveBeenCalledWith('keyUpdated')
  })

  test('shows normalized API errors and safely handles option-loading failures', async () => {
    const error = new Error('invalid'); const consoleError = mock(() => {}); console.error = consoleError
    getAgents.mockRejectedValue(error); getWorkflows.mockRejectedValue(error); createAPIKey.mockRejectedValue(error)
    normalizedErrors = { rate_limit: 'too high', agent_ids: 'not allowed' }
    render(); await flush(); let tree = render()
    expect(consoleError).toHaveBeenCalledTimes(2)
    descendants(tree).find((n) => n.type === 'Input' && n.props.id === 'name')!.props.onChange({ target: { value: 'Broken' } })
    tree = render(); await submit(tree); tree = render()
    expect(text(tree)).toContain('rate_limit: too high')
    expect(text(tree)).toContain('agent_ids: not allowed')
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})
