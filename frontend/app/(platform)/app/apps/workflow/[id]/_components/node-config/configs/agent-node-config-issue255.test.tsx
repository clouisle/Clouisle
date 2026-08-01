import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign(function Component() {}, { displayName: name })
const components = Object.fromEntries([
  'Badge', 'Button', 'Collapsible', 'CollapsibleContent', 'CollapsibleTrigger', 'Input', 'Label',
  'Popover', 'PopoverContent', 'PopoverTrigger', 'ScrollArea',
  'Tooltip', 'TooltipContent', 'TooltipTrigger',
].map(name => [name, component(name)]))
const icons = Object.fromEntries([
  'Search', 'ChevronDown', 'Bot', 'Check', 'Loader2', 'Trash2', 'ExternalLink',
].map(name => [name, component(name)]))

let states: unknown[] = []
let stateIndex = 0
let effects: (() => void | Promise<void>)[] = []
const setters = Array.from({ length: 7 }, () => mock(() => {}))
const getAgents = mock(async () => ({ items: [] as Props[] }))
const getAgent = mock(async () => ({ variables: [] as Props[] }))

mock.module('react', () => ({
  default: {},
  useState: (initial: unknown) => [states[stateIndex] ?? initial, setters[stateIndex++]],
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => icons)
for (const [path, names] of [
  ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/tooltip', ['Tooltip', 'TooltipContent', 'TooltipTrigger']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, components[name]])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1' } }) }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents, getAgent } }))
mock.module('../utils', () => ({ isValidVariableName: (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) }))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/[{}]/g, '') }))

const { AgentNodeConfig, defaultAgentNodeConfig } = await import('./agent-node-config')

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  return text((value as Node).props.children)
}

const agent = { id: 'agent-1', name: 'Alpha Agent', description: 'Answers things', icon: null, avatar_url: null }
const variables = [
  { id: 'input.question', name: 'Question', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.now', name: 'Now', type: 'string', group: 'system', groupLabel: 'System', isSystem: true },
]

function render(config: Props = {}, overrides: Props = {}, stateValues: unknown[] = []) {
  states = stateValues
  stateIndex = 0
  effects = []
  return AgentNodeConfig({
    config: { ...defaultAgentNodeConfig, ...config } as never,
    variables,
    variableSearch: '',
    openVariablePopover: null,
    onConfigChange: mock(() => {}),
    onVariableSearchChange: mock(() => {}),
    onOpenVariablePopoverChange: mock(() => {}),
    ...overrides,
  }) as Node
}

beforeEach(() => {
  setters.forEach(setter => setter.mockClear())
  getAgents.mockClear()
  getAgent.mockClear()
  getAgents.mockImplementation(async () => ({ items: [] }))
  getAgent.mockImplementation(async () => ({ variables: [] }))
})

describe('AgentNodeConfig Issue #255 callbacks', () => {
  test('loads agents and maps agent detail variables', async () => {
    getAgents.mockImplementation(async () => ({ items: [agent] }))
    getAgent.mockImplementation(async () => ({ variables: [
      { name: 'topic', type: 'string', label: '', required: true, description: '', default: 'news' },
      { name: 'count', type: 'number', label: 'Count', required: false, description: 'Limit', default: undefined },
    ] }))
    const onConfigChange = mock(() => {})
    render({ agentId: 'agent-1' }, { onConfigChange })

    await Promise.all(effects.map(effect => effect()))

    expect(getAgents).toHaveBeenCalledWith({ teamId: 'team-1', status: 'published', pageSize: 100 })
    expect(getAgent).toHaveBeenCalledWith('agent-1')
    expect(setters[4]).toHaveBeenCalledWith(true)
    expect(setters[3]).toHaveBeenCalledWith([agent])
    expect(setters[4]).toHaveBeenLastCalledWith(false)
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [
      { name: 'topic', type: 'string', label: undefined, required: true, description: undefined, source: 'constant', constantValue: 'news' },
      { name: 'count', type: 'number', label: 'Count', required: false, description: 'Limit', source: 'constant', constantValue: '' },
    ] }))
  })

  test('ignores API failures and missing selection', async () => {
    getAgents.mockImplementation(async () => { throw new Error('offline') })
    getAgent.mockImplementation(async () => { throw new Error('offline') })
    render({ agentId: 'agent-1' })
    await Promise.all(effects.map(effect => effect()))
    expect(setters[4]).toHaveBeenLastCalledWith(false)

    render()
    await Promise.all(effects.map(effect => effect()))
    expect(getAgent).toHaveBeenCalledTimes(1)
  })

  test('searches and selects an agent', () => {
    const onConfigChange = mock(() => {})
    const tree = render({}, { onConfigChange }, [true, true, true, [agent], false, true, 'alpha'])
    const nodes = descendants(tree)

    const search = nodes.find(node => node.type === components.Input && node.props.placeholder === 'configAgent.searchAgent')!
    search.props.onChange({ target: { value: 'beta' } })
    expect(setters[6]).toHaveBeenCalledWith('beta')

    nodes.find(node => node.type === 'button' && text(node).includes('Alpha Agent'))!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      agentId: 'agent-1', agentName: 'Alpha Agent', agentDescription: 'Answers things', agentIcon: undefined, inputMappings: [],
    }))
    expect(setters[5]).toHaveBeenCalledWith(false)
    expect(setters[6]).toHaveBeenCalledWith('')
  })

  test('clears the agent and updates message inputs', () => {
    const onConfigChange = mock(() => {})
    const config = { agentId: 'agent-1', outputVariable: 'answer', messageSource: 'constant', messageConstantValue: 'old' }
    const tree = render(config, { onConfigChange }, [true, true, true, [agent]])
    const nodes = descendants(tree)

    nodes.find(node => node.type === components.Button && node.props.children?.type === icons.Trash2)!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith({ ...defaultAgentNodeConfig, outputVariable: 'answer' })

    const messageInput = nodes.find(node => node.type === components.Input && node.props.placeholder === 'configAgent.enterMessageContent')!
    messageInput.props.onChange({ target: { value: 'new message' } })
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ messageConstantValue: 'new message' }))

    nodes.find(node => node.type === components.Button && text(node) === 'configCommon.variable')!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ messageSource: 'variable' }))
  })

  test('filters variables and updates message and constant mapping values', () => {
    const onConfigChange = mock(() => {})
    const mapping = { name: 'topic', type: 'string', required: true, source: 'constant', constantValue: 'old' }
    const config = { agentId: 'agent-1', messageSource: 'variable', inputMappings: [mapping] }
    const tree = render(config, { onConfigChange, variableSearch: 'q', openVariablePopover: 'message-input' }, [true, true, true, [agent]])
    const nodes = descendants(tree)

    nodes.find(node => node.type === 'button' && text(node).includes('Question'))!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      messageVariableRef: '{{input.question}}', messageVariableRefNodeLabel: 'Input',
    }))
    nodes.find(node => node.type === components.Input && node.props.value === 'old')!.props.onChange({ target: { value: 'new' } })
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      inputMappings: [expect.objectContaining({ constantValue: 'new' })],
    }))

    expect(text(render(config, { variableSearch: 'missing' }, [true, true, true, [agent]]))).toContain('configCommon.noMatchingVariables')
    render(config, { variables: [...variables].reverse() }, [true, true, true, [agent]])
  })

  test('selects variables and updates mapping and output callbacks', () => {
    const onConfigChange = mock(() => {})
    const onVariableSearchChange = mock(() => {})
    const onOpenVariablePopoverChange = mock(() => {})
    const mapping = { name: 'topic', type: 'string', label: 'Topic', required: true, source: 'variable', variableRef: '{{input.old}}' }
    const config = { agentId: 'agent-1', messageSource: 'variable', inputMappings: [mapping], outputVariable: 'not valid' }
    const tree = render(config, {
      onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, openVariablePopover: 'param-topic', variableSearch: '',
    }, [true, true, true, [agent]])
    const nodes = descendants(tree)

    expect(text(tree)).toContain('configCommon.invalidVariableName')
    const popovers = nodes.filter(node => node.type === components.Popover)
    popovers.at(-1)!.props.onOpenChange(false)
    expect(onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
    expect(onVariableSearchChange).toHaveBeenCalledWith('')

    nodes.find(node => node.type === components.Input && node.props.placeholder === 'configCommon.searchVariable')!.props.onChange({ target: { value: 'now' } })
    expect(onVariableSearchChange).toHaveBeenCalledWith('now')

    nodes.filter(node => node.type === 'button' && text(node).includes('Question')).at(-1)!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [expect.objectContaining({
      source: 'variable', variableRef: '{{input.question}}', variableRefNodeLabel: 'Input', constantValue: undefined,
    })] }))

    const constantButtons = nodes.filter(node => node.type === components.Button && text(node) === 'configCommon.constant')
    constantButtons[0].props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ messageSource: 'constant' }))
    constantButtons.at(-1)!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [expect.objectContaining({ source: 'constant', variableRef: undefined })] }))

    nodes.find(node => node.type === components.Input && node.props.placeholder === 'response')!.props.onChange({ target: { value: 'answer' } })
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'answer' }))
  })
})
