import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = function Component() {}
const getAgents = mock(async () => ({ items: [] as Props[] }))
const getAgent = mock(async () => ({ variables: [] as Props[] }))
let states: unknown[] = []
let effects: (() => void | Promise<void>)[] = []
const setState = mock(() => {})

mock.module('react', () => ({
  default: {},
  useMemo: (factory: () => unknown) => factory(),
  useState: (initial: unknown) => [states.length ? states.shift() : initial, setState],
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => Object.fromEntries(['Bot', 'Check', 'ChevronDown', 'ExternalLink', 'Loader2', 'Search', 'Trash2'].map(name => [name, component])))
for (const [path, names] of [
  ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: component, TooltipContent: component, TooltipTrigger: component,
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1' } }) }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents, getAgent } }))
mock.module('../utils', () => ({ isValidVariableName: (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) }))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/[{}]/g, '') }))

const { AgentNodeConfig, defaultAgentNodeConfig, getAgentNodeOutputVariables } = await import('./agent-node-config')

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

function render(config: Props, overrides: Props = {}) {
  effects = []
  return AgentNodeConfig({
    config: config as never,
    variables: [{ id: 'input.question', name: 'Question', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false }],
    variableSearch: '',
    openVariablePopover: null,
    onConfigChange: mock(() => {}),
    onVariableSearchChange: mock(() => {}),
    onOpenVariablePopoverChange: mock(() => {}),
    ...overrides,
  }) as Node
}

function action(tree: Node, label: string) {
  return descendants(tree).find(node => typeof node.props.onClick === 'function' && text(node.props.children).includes(label))!
}

function actions(tree: Node, label: string) {
  return descendants(tree).filter(node => typeof node.props.onClick === 'function' && text(node.props.children).includes(label))
}

beforeEach(() => {
  states = []
  effects = []
  setState.mockClear()
  getAgents.mockClear()
  getAgent.mockClear()
  getAgents.mockImplementation(async () => ({ items: [] }))
  getAgent.mockImplementation(async () => ({ variables: [] }))
})

test('declares the fixed Agent runtime outputs and one distinct response alias', () => {
  expect(getAgentNodeOutputVariables({ outputVariable: 'response' }).map((output) => output.name)).toEqual([
    'response', 'toolCalls', 'usage', 'dialogue', 'artifacts',
  ])
  expect(getAgentNodeOutputVariables({ outputVariable: 'answer' }).map((output) => output.name)).toEqual([
    'answer', 'response', 'toolCalls', 'usage', 'dialogue', 'artifacts',
  ])
})

test('selects a published agent and clears stale mappings before detail loading', () => {
  const agent = { id: 'agent-2', name: 'Published Agent', description: 'Ready to use', icon: 'agent-icon' }
  states = [true, true, true, [agent], false, true, '']
  const onConfigChange = mock(() => {})
  const tree = render({ inputMappings: [{ name: 'old', type: 'string', required: false, source: 'constant' }], outputVariable: 'response' }, { onConfigChange })

  action(tree, 'Published Agent').props.onClick!()

  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ agentId: 'agent-2', agentName: 'Published Agent', agentDescription: 'Ready to use', agentIcon: 'agent-icon', inputMappings: [] }))
  expect(setState).toHaveBeenCalledWith(false)
  expect(setState).toHaveBeenCalledWith('')
})
test('validates output names and preserves default configuration on input changes', () => {
  const onConfigChange = mock(() => {})
  const tree = render({ inputMappings: undefined, outputVariable: 'not valid' }, { onConfigChange })
  const inputs = descendants(tree).filter(node => node.type === component && node.props.placeholder === 'response')

  expect(text(tree)).toContain('configCommon.invalidVariableName')
  expect(inputs).toHaveLength(1)
  ;(inputs[0].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'reply' } })
  expect(onConfigChange).toHaveBeenCalledWith({ ...defaultAgentNodeConfig, inputMappings: [], outputVariable: 'reply' })
})

test('changes selected agent message and parameter mappings without retaining stale variable references', () => {
  const agent = { id: 'agent-1', name: 'Helpful Agent', description: 'Answers questions' }
  states = [true, true, true, [agent], false, false, '']
  const onConfigChange = mock(() => {})
  const tree = render({
    agentId: 'agent-1', agentName: 'Helpful Agent', inputMappings: [{ name: 'topic', type: 'string', required: true, source: 'variable', variableRef: '{{old.topic}}', variableRefNodeLabel: 'Old' }],
    messageSource: 'variable', messageVariableRef: '{{old.message}}', messageVariableRefNodeLabel: 'Old', outputVariable: 'response',
  }, { onConfigChange })

  const constants = actions(tree, 'configCommon.constant')
  constants[0].props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ messageSource: 'constant', messageVariableRef: undefined, messageVariableRefNodeLabel: undefined }))
  constants[1].props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [expect.objectContaining({ source: 'constant', variableRef: undefined, variableRefNodeLabel: undefined })] }))
  descendants(tree).find(node => node.props.className === 'h-6 w-6 shrink-0' && !node.props.title)!.props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith({ ...defaultAgentNodeConfig, outputVariable: 'response' })
})

test('loads mappings after an earlier agent-list failure and ignores the recoverable list error', async () => {
  states = [true, true, true, [], false, false, '']
  const onConfigChange = mock(() => {})
  getAgents.mockImplementation(async () => { throw new Error('temporary failure') })
  getAgent.mockImplementation(async () => ({ variables: [{ name: 'query', type: 'string', label: 'Query', required: true, description: 'Question', default: 'hello' }] }))
  render({ agentId: 'agent-1', inputMappings: [], outputVariable: 'response' }, { onConfigChange })

  await Promise.all(effects.map(effect => effect()))

  expect(getAgents).toHaveBeenCalledWith({ teamId: 'team-1', status: 'published', pageSize: 100 })
  expect(getAgent).toHaveBeenCalledWith('agent-1')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [{ name: 'query', type: 'string', label: 'Query', required: true, description: 'Question', source: 'constant', constantValue: 'hello' }] }))
  expect(setState).toHaveBeenCalledWith(false)
})

test('reconciles selected Agent inputs without losing compatible mappings or retaining stale fields', async () => {
  const onConfigChange = mock(() => {})
  getAgent.mockImplementation(async () => ({ variables: [
    { name: 'topic', type: 'string', label: 'Topic', required: true, description: 'Current topic', default: '' },
    { name: 'limit', type: 'number', label: 'Limit', required: false, description: '', default: 5 },
  ] }))
  render({
    agentId: 'agent-1',
    inputMappings: [
      { name: 'topic', type: 'string', required: false, source: 'variable', variableRef: '{{start.topic}}', variableRefNodeLabel: 'Start' },
      { name: 'removed', type: 'string', required: false, source: 'constant', constantValue: 'stale' },
    ],
    outputVariable: 'response',
  }, { onConfigChange })

  await Promise.all(effects.map(effect => effect()))

  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    inputMappings: [
      { name: 'topic', type: 'string', label: 'Topic', required: true, description: 'Current topic', source: 'variable', variableRef: '{{start.topic}}', variableRefNodeLabel: 'Start' },
      { name: 'limit', type: 'number', label: 'Limit', required: false, description: undefined, source: 'constant', constantValue: 5 },
    ],
  }))
})

test('clears mappings when the selected Agent no longer declares inputs', async () => {
  const onConfigChange = mock(() => {})
  getAgent.mockImplementation(async () => ({ variables: [] }))
  render({
    agentId: 'agent-1',
    inputMappings: [{ name: 'removed', type: 'string', required: false, source: 'constant', constantValue: 'stale' }],
    outputVariable: 'response',
  }, { onConfigChange })

  await Promise.all(effects.map(effect => effect()))

  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [] }))
})
