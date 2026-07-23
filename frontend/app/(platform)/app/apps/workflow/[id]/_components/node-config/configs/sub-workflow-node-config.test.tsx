import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = function Component() {}
const getWorkflows = mock(async () => ({ items: [] as Props[] }))
const getWorkflow = mock(async () => ({ variables: [] as Props[] }))
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
mock.module('lucide-react', () => Object.fromEntries(['Search', 'ChevronDown', 'Workflow', 'Check', 'Loader2', 'Trash2', 'ExternalLink'].map(name => [name, component])))
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
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1' } }) }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflows, getWorkflow } }))
mock.module('../utils', () => ({ isValidVariableName: (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) }))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/[{}]/g, '') }))

const { SubWorkflowNodeConfig, defaultSubWorkflowNodeConfig } = await import('./sub-workflow-node-config')

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
  return SubWorkflowNodeConfig({
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

beforeEach(() => {
  states = []
  effects = []
  setState.mockClear()
  getWorkflows.mockClear()
  getWorkflow.mockClear()
  getWorkflows.mockImplementation(async () => ({ items: [] }))
  getWorkflow.mockImplementation(async () => ({ variables: [] }))
})

test('shows loading and selects a published workflow without stale mappings', () => {
  states = [true, true, [], true, false, '']
  expect(text(render({ inputMappings: [], outputVariable: 'result' }))).toContain('configCommon.loading')

  const workflow = { id: 'workflow-2', name: 'Published Flow', description: 'Ready' }
  states = [true, true, [workflow], false, true, '']
  const onConfigChange = mock(() => {})
  const tree = render({ inputMappings: [{ name: 'old' }], outputVariable: 'result' }, { onConfigChange })
  descendants(tree).find(node => node.type === 'button' && text(node).includes('Published Flow'))!.props.onClick!()

  expect(onConfigChange).toHaveBeenCalledWith({
    ...defaultSubWorkflowNodeConfig,
    workflowId: 'workflow-2',
    workflowName: 'Published Flow',
    workflowDescription: 'Ready',
    inputMappings: [],
  })
  expect(setState).toHaveBeenCalledWith(false)
  expect(setState).toHaveBeenCalledWith('')
})

test('updates constant and variable mappings and validates the output name', () => {
  const onConfigChange = mock(() => {})
  const config = {
    workflowId: 'workflow-1', workflowName: 'Flow', outputVariable: 'not valid',
    inputMappings: [{ name: 'query', type: 'string', required: true, source: 'constant', constantValue: 'old' }],
  }
  const tree = render(config, { onConfigChange, openVariablePopover: 'param-query' })

  expect(text(tree)).toContain('configCommon.invalidVariableName')
  const inputs = descendants(tree).filter(node => node.type === component)
  ;(inputs.find(node => node.props.value === 'old')!.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'new' } })
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [expect.objectContaining({ constantValue: 'new' })] }))

  descendants(tree).find(node => node.type === component && typeof node.props.onClick === 'function' && text(node).includes('configCommon.variable'))!.props.onClick!()
  const variableTree = render({ ...config, inputMappings: [{ ...config.inputMappings[0], source: 'variable' }] }, { onConfigChange, openVariablePopover: 'param-query' })
  descendants(variableTree).find(node => node.type === 'button' && text(node).includes('Question'))!.props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [expect.objectContaining({ source: 'variable', variableRef: '{{input.question}}', variableRefNodeLabel: 'Input', constantValue: undefined })] }))

  ;(inputs.find(node => node.props.placeholder === 'result')!.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'result_2' } })
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'result_2' }))
})

test('recovers from list failure and builds mappings from workflow details', async () => {
  getWorkflows.mockImplementation(async () => { throw new Error('temporary failure') })
  getWorkflow.mockImplementation(async () => ({ variables: [{ name: 'query', type: 'string', required: true, description: 'Question', default: 7 }] }))
  const onConfigChange = mock(() => {})
  render({ workflowId: 'workflow-1', inputMappings: [], outputVariable: 'result' }, { onConfigChange })

  await Promise.all(effects.map(effect => effect()))

  expect(getWorkflows).toHaveBeenCalledWith({ teamId: 'team-1', status: 'published', pageSize: 100 })
  expect(getWorkflow).toHaveBeenCalledWith('workflow-1')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    inputMappings: [{ name: 'query', type: 'string', required: true, description: 'Question', source: 'constant', constantValue: '7' }],
  }))
  expect(setState).toHaveBeenCalledWith(false)
})

test('preserves compatible mappings, falls back to start parameters, and clears empty details', async () => {
  const onConfigChange = mock(() => {})
  getWorkflow.mockImplementation(async () => ({
    variables: [],
    definition: { nodes: [{ type: 'start', data: { parameters: [{ name: 'topic', type: 'string', required: false, defaultValue: 'news' }] } }] },
  }))
  render({ workflowId: 'workflow-1', inputMappings: [{ name: 'topic', type: 'string', required: true, source: 'variable', variableRef: '{{input.topic}}' }], outputVariable: 'result' }, { onConfigChange })
  await Promise.all(effects.map(effect => effect()))
  expect(onConfigChange).not.toHaveBeenCalled()

  getWorkflow.mockImplementation(async () => ({ variables: [] }))
  render({ workflowId: 'workflow-1', inputMappings: [{ name: 'old', type: 'string', required: false, source: 'constant' }], outputVariable: 'result' }, { onConfigChange })
  await Promise.all(effects.map(effect => effect()))
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputMappings: [] }))
})
