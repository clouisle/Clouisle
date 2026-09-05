import { beforeEach, describe, expect, mock, test } from 'bun:test'

interface Node { type: unknown; props: Record<string, unknown> }
const jsx = (type: unknown, props: Record<string, unknown>): Node => ({ type, props })
const component = (name: string) => Object.assign(() => null, { displayName: name })
const Input = component('Input')
const Textarea = component('Textarea')
const Switch = component('Switch')
const ImageUpload = component('ImageUpload')
const Select = component('Select')
const Sheet = component('Sheet')
const DropdownMenuItem = component('DropdownMenuItem')
let states: unknown[] = []
let stateIndex = 0
let currentTeam: { id: string } | null = { id: 'team-1' }
const getTeamModels = mock(() => Promise.resolve<unknown[]>([]))

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (!(index in states)) states[index] = initial
    return [states[index] as T, (value: T | ((current: T) => T)) => {
      states[index] = typeof value === 'function' ? (value as (current: T) => T)(states[index] as T) : value
    }] as const
  },
  useEffect: (effect: () => void) => effect(),
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('lucide-react', () => ({
  Bot: component('Bot'), ChevronDown: component('ChevronDown'), MessageSquare: component('MessageSquare'),
  Wrench: component('Wrench'), AlertCircle: component('AlertCircle'),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/textarea', () => ({ Textarea }))
mock.module('@/components/ui/label', () => ({ Label: component('Label') }))
mock.module('@/components/ui/switch', () => ({ Switch }))
mock.module('@/components/ui/badge', () => ({ Badge: component('Badge') }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload }))
mock.module('@/components/ui/select', () => ({
  Select, SelectContent: component('SelectContent'), SelectItem: component('SelectItem'),
  SelectTrigger: component('SelectTrigger'), SelectValue: component('SelectValue'),
}))
mock.module('@/components/ui/sheet', () => ({
  Sheet, SheetContent: component('SheetContent'), SheetDescription: component('SheetDescription'),
  SheetHeader: component('SheetHeader'), SheetTitle: component('SheetTitle'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: component('DropdownMenu'), DropdownMenuContent: component('DropdownMenuContent'),
  DropdownMenuItem, DropdownMenuTrigger: component('DropdownMenuTrigger'),
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: component('Tooltip'), TooltipContent: component('TooltipContent'), TooltipTrigger: component('TooltipTrigger'),
}))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: component('Collapsible'), CollapsibleContent: component('CollapsibleContent'),
  CollapsibleTrigger: component('CollapsibleTrigger'),
}))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: component('ScrollArea') }))
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels } }))

const { AgentSettingsDrawer } = await import('./agent-settings-drawer')
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children), ...descendants(node.props.placeholder)]
}
const find = (tree: Node, type: unknown) => descendants(tree).filter((node) => node.type === type)
const text = (value: unknown): string => Array.isArray(value) ? value.map(text).join('')
  : value && typeof value === 'object' ? text((value as Node).props?.children)
    : typeof value === 'string' || typeof value === 'number' ? String(value) : ''

const callbacks = {
  onOpenChange: mock(() => undefined), onNameChange: mock(() => undefined),
  onDescriptionChange: mock(() => undefined), onIconChange: mock(() => undefined),
  onOpeningMessageChange: mock(() => undefined), onSuggestedQuestionsChange: mock(() => undefined),
  onPoweredByTextChange: mock(() => undefined),
  onVisibilityChange: mock(() => undefined), onModelChange: mock(() => undefined),
  onMaxIterationsChange: mock(() => undefined), onHideToolCallsChange: mock(() => undefined),
}
const agent = { model: { id: 'fallback', name: 'Fallback model' } } as never
function render(overrides: Record<string, unknown> = {}) {
  stateIndex = 0
  return AgentSettingsDrawer({
    agent, open: true, name: 'Agent', description: 'Description', icon: '/icon.png',
    openingMessage: 'Hello', suggestedQuestions: ['One', 'Two'], poweredByText: 'Acme Inc', visibility: 'private',
    modelId: null, maxIterations: 10, hideToolCalls: false, hasToolsEnabled: false,
    ...callbacks, ...overrides,
  } as never) as Node
}

beforeEach(() => {
  states = []
  currentTeam = { id: 'team-1' }
  getTeamModels.mockReset()
  getTeamModels.mockResolvedValue([])
  Object.values(callbacks).forEach((callback) => callback.mockClear())
})

describe('AgentSettingsDrawer', () => {
  test('loads enabled models, renders selection state, and delegates model changes', async () => {
    getTeamModels.mockResolvedValue([
      { id: 'enabled', is_enabled: true, model: { name: 'Enabled model' } },
      { id: 'disabled', is_enabled: false, model: { name: 'Disabled model' } },
    ])
    render({ modelId: 'enabled' })
    await flush()
    const tree = render({ modelId: 'enabled' })

    expect(getTeamModels).toHaveBeenCalledWith('team-1', 'chat')
    expect(text(tree)).toContain('Enabled model')
    expect(text(tree)).not.toContain('Disabled model')
    expect(text(tree)).toContain('agents.settings.current')
    const item = find(tree, DropdownMenuItem)[0]
    ;(item.props.onClick as () => void)()
    expect(callbacks.onModelChange).toHaveBeenCalledWith('enabled')
  })

  test('shows fallback and empty states, and skips loading when closed or teamless', async () => {
    let tree = render({ open: false })
    expect(getTeamModels).not.toHaveBeenCalled()
    expect(text(tree)).toContain('Fallback model')
    expect(text(tree)).toContain('agents.noModels')
    expect((find(tree, Sheet)[0].props.open)).toBe(false)
    ;(find(tree, Sheet)[0].props.onOpenChange as (open: boolean) => void)(true)
    expect(callbacks.onOpenChange).toHaveBeenCalledWith(true)

    currentTeam = null
    tree = render({ agent: { model: null }, modelId: 'missing' })
    expect(getTeamModels).not.toHaveBeenCalled()
    expect(text(tree)).toContain('agents.selectModel')

    currentTeam = { id: 'team-1' }
    getTeamModels.mockRejectedValue(new Error('unavailable'))
    render()
    await flush()
    expect(states[0]).toEqual([])
  })

  test('delegates editable fields, visibility, and switch', () => {
    const tree = render()
    ;(find(tree, ImageUpload)[0].props.onChange as (value: string) => void)('/new.png')
    const inputs = find(tree, Input)
    ;(inputs.find((node) => node.props.id === 'name')!.props.onChange as (event: unknown) => void)({ target: { value: 'New name' } })
    const poweredBy = inputs.find((node) => node.props.id === 'poweredByText')!
    expect(poweredBy.props.value).toBe('Acme Inc')
    ;(poweredBy.props.onChange as (event: unknown) => void)({ target: { value: 'New footer' } })
    const textareas = find(tree, Textarea)
    ;(textareas.find((node) => node.props.id === 'description')!.props.onChange as (event: unknown) => void)({ target: { value: 'New description' } })
    ;(find(tree, Select)[0].props.onValueChange as (value: string) => void)('team')
    ;(find(tree, Select)[0].props.onValueChange as (value: string) => void)('')
    ;(find(tree, Switch)[0].props.onCheckedChange as (value: boolean) => void)(true)

    expect(callbacks.onIconChange).toHaveBeenCalledWith('/new.png')
    expect(callbacks.onNameChange).toHaveBeenCalledWith('New name')
    expect(callbacks.onPoweredByTextChange).toHaveBeenCalledWith('New footer')
    expect(callbacks.onDescriptionChange).toHaveBeenCalledWith('New description')
    expect(callbacks.onVisibilityChange.mock.calls).toEqual([['team']])
    expect(callbacks.onHideToolCallsChange).toHaveBeenCalledWith(true)
  })

  test('normalizes suggested questions on blur', () => {
    const tree = render()
    const textareas = find(tree, Textarea)
    const opening = textareas.find((node) => node.props.id === 'openingMessage')!
    const questions = textareas.find((node) => node.props.id === 'suggestedQuestions')!
    ;(opening.props.onChange as (event: unknown) => void)({ target: { value: 'Welcome' } })
    ;(questions.props.onChange as (event: unknown) => void)({ target: { value: 'First\n\n Second ' } })
    ;(questions.props.onBlur as (event: unknown) => void)({ target: { value: 'First\n   \n Second ' } })

    expect(callbacks.onOpeningMessageChange).toHaveBeenCalledWith('Welcome')
    expect(callbacks.onSuggestedQuestionsChange.mock.calls).toEqual([
      [['First', '', ' Second ']],
      [['First', ' Second ']],
    ])
  })
})
