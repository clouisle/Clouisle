import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const push = mock()
const toastSuccess = mock()
const defaultCreateAgent = mock()
const defaultCreateWorkflow = mock()
let currentTeam: { id: string } | undefined
let state: unknown[] = []
let stateIndex = 0
let effectDependencies: unknown[][] = []
let effectIndex = 0

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx }))
mock.module('react', () => ({
  useEffect: (effect: () => void, dependencies: unknown[]) => {
    const index = effectIndex++
    const previous = effectDependencies[index]
    if (!previous || dependencies.some((dependency, position) => !Object.is(dependency, previous[position]))) {
      effectDependencies[index] = dependencies
      effect()
    }
  },
  useMemo: <T,>(factory: () => T) => factory(),
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
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { createAgent: defaultCreateAgent } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { createWorkflow: defaultCreateWorkflow } }))
mock.module('@/contexts/team-context', () => ({ useOptionalTeam: () => ({ currentTeam }) }))
mock.module('@/components/onboarding/onboarding-provider', () => ({ useOptionalOnboarding: () => undefined }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) =>
    Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>, inline: string[]) =>
    Object.entries(errors).filter(([field]) => !inline.includes(field)),
  normalizeValidationErrors: (error: { errors?: Record<string, string> }) => error.errors ?? {},
}))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})
mock.module('@/components/ui/dialog', () => ({
  Dialog: element('dialog'),
  DialogContent: element('section'),
  DialogDescription: element('p'),
  DialogFooter: element('footer'),
  DialogHeader: element('header'),
  DialogTitle: element('h2'),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('span') }))
mock.module('@/components/ui/radio-group', () => ({
  RadioGroup: element('radio-group'),
  RadioGroupItem: element('radio'),
}))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: element('select-content'),
  SelectItem: element('option'),
  SelectTrigger: element('select-trigger'),
  SelectValue: element('select-value'),
}))
mock.module('lucide-react', () => ({
  GitBranch: element('svg'),
  Loader2: element('svg'),
  Sparkles: element('svg'),
}))

const { AppCreateDialog } = await import('./app-create-dialog')

type Tree = { type: unknown; props: Record<string, unknown> }
type Props = React.ComponentProps<typeof AppCreateDialog>

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  for (const child of Array.isArray(node) ? node : [node]) {
    const resolved = resolve(child)
    if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) continue
    const tree = resolved as Tree
    if (predicate(tree)) return tree
    try {
      return find(tree.props.children as ReactNode, predicate)
    } catch {
      // Continue searching sibling elements.
    }
  }
  throw new Error('Element not found')
}

function render(props: Props) {
  stateIndex = 0
  effectIndex = 0
  return AppCreateDialog(props)
}

function mount(props: Props) {
  render(props)
  return render(props)
}

function change(props: Props, id: string, value: string) {
  const input = find(render(props), (tree) => tree.props.id === id)
  ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
}

async function submit(props: Props) {
  const form = find(render(props), (tree) => tree.type === 'form')
  await (form.props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} })
}

beforeEach(() => {
  push.mockReset()
  toastSuccess.mockReset()
  defaultCreateAgent.mockReset()
  defaultCreateWorkflow.mockReset()
  currentTeam = undefined
  state = []
  effectDependencies = []
})

describe('AppCreateDialog', () => {
  test('creates an agent with trimmed values and follows the success flow', async () => {
    const createAgent = mock(async () => ({ id: 'agent-1' }))
    const createWorkflow = mock(async () => ({ id: 'workflow-1' }))
    const onOpenChange = mock()
    const onSuccess = mock()
    const props = {
      open: true,
      onOpenChange,
      onSuccess,
      api: { createAgent, createWorkflow },
      teamId: 'team-1',
      agentEditHref: (id: string) => `/agents/${id}/edit`,
    } as unknown as Props
    mount(props)

    change(props, 'name', '  Support agent  ')
    change(props, 'description', '  Handles requests  ')
    await submit(props)

    expect(createAgent).toHaveBeenCalledWith({
      team_id: 'team-1',
      name: 'Support agent',
      description: 'Handles requests',
    })
    expect(createWorkflow).not.toHaveBeenCalled()
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(toastSuccess).toHaveBeenCalledWith('appCreated')
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/agents/agent-1/edit')
  })

  test('creates the selected workflow and exposes normalized API errors', async () => {
    const createAgent = mock(async () => ({ id: 'agent-1' }))
    const createWorkflow = mock(async () => ({ id: 'workflow-1' }))
    const props = {
      open: true,
      onOpenChange: mock(),
      api: { createAgent, createWorkflow },
      teams: [{ id: 'team-1', name: 'Platform' }],
      workflowEditHref: (id: string) => `/workflows/${id}`,
    } as unknown as Props
    mount(props)

    const typeSelector = find(render(props), (tree) => tree.props['data-testid'] === 'app-create-type-selector')
    ;(typeSelector.props.onValueChange as (value: string) => void)('workflow')
    change(props, 'name', 'Release flow')
    createWorkflow.mockRejectedValueOnce({ errors: { name: 'Already exists', detail: 'Creation failed' } })
    await submit(props)

    expect(createWorkflow).toHaveBeenCalledWith({
      team_id: 'team-1',
      name: 'Release flow',
      description: undefined,
    })
    expect(createAgent).not.toHaveBeenCalled()
    expect(find(render(props), (tree) => tree.props.children === 'Already exists')).toBeDefined()
    expect(find(render(props), (tree) => tree.props.children === 'detail: Creation failed')).toBeDefined()
    expect(find(render(props), (tree) => tree.props.id === 'name').props['aria-invalid']).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })

  test('rejects blank names and missing team context before calling the API', async () => {
    const createAgent = mock(async () => ({ id: 'agent-1' }))
    const createWorkflow = mock(async () => ({ id: 'workflow-1' }))
    const props = {
      open: true,
      onOpenChange: mock(),
      api: { createAgent, createWorkflow },
    } as unknown as Props
    mount(props)

    change(props, 'name', '   ')
    await submit(props)
    expect(find(render(props), (tree) => tree.props.children === 'nameRequired')).toBeDefined()
    expect(find(render(props), (tree) => tree.props.id === 'name').props['aria-invalid']).toBe(true)

    change(props, 'name', 'Agent without a team')
    await submit(props)
    expect(createAgent).not.toHaveBeenCalled()
    expect(createWorkflow).not.toHaveBeenCalled()
  })
})
