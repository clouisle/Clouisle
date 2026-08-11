import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const stateValues: unknown[] = []
const effects: Array<() => void> = []
const setState = mock(() => {})
let currentTeam: { id: string } | null = null
const getTeamModels = mock(async () => [])
const resetState = () => {
  stateValues.length = 0
  effects.length = 0
  currentTeam = null
  setState.mockClear()
  getTeamModels.mockClear()
}

mock.module('react', () => ({
  default: {},
  useMemo: (factory: () => unknown) => factory(),
  useState: (initial: unknown) => [stateValues.length ? stateValues.shift() : initial, setState],
  useEffect: (effect: () => void) => effects.push(effect),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => Object.fromEntries([
  'AlertCircle', 'Bot', 'Calculator', 'ChartColumn', 'Check', 'ChevronDown', 'Clock3', 'Code2', 'Database',
  'ExternalLink', 'FolderOpen', 'Globe', 'History', 'Image', 'Info', 'Link', 'Loader2', 'Pencil', 'Plus',
  'Search', 'Settings2', 'Trash2', 'Workflow', 'Wrench',
].map((name) => [name, component])))
for (const [path, names] of [
  ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']],
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogFooter', 'DialogHeader', 'DialogTitle']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/slider', ['Slider']],
  ['@/components/ui/switch', ['Switch']],
  ['@/components/ui/tabs', ['Tabs', 'TabsList', 'TabsTrigger']],
  ['@/components/ui/textarea', ['Textarea']],
  ['@/components/ui/tooltip', ['Tooltip', 'TooltipContent', 'TooltipProvider', 'TooltipTrigger']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/api/knowledge-bases', () => ({ knowledgeBasesApi: { getKnowledgeBases: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflows: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/api', () => ({
  teamModelsApi: { getTeamModels },
  toolsApi: { getTools: mock(async () => ({ items: [] })), getMcpTools: mock(async () => []) },
  isPresetToolCategory: (category: string) => category !== 'other',
}))
mock.module('../components/prompt-textarea', () => ({ PromptTextarea: component }))
mock.module('../variable-selector', () => ({ VariableSelector: component }))
mock.module('../constants', () => ({
  loopVariableTypeConfig: { string: { icon: component, label: 'string', valueType: 'string' } },
}))
mock.module('../../nodes/loop-node', () => ({}))
mock.module('../../nodes/condition-node', () => ({
  getConditionOperatorLabels: () => ({ equals: 'equals' }),
  getConditionOperatorShortLabels: () => ({ equals: '=' }),
  noValueOperators: [],
}))

const { AgentNodeConfig, defaultAgentNodeConfig } = await import('./agent-node-config')
const { KnowledgeRetrievalNodeConfig, defaultKnowledgeRetrievalNodeConfig } = await import('./knowledge-retrieval-node-config')
const { LLMNodeConfig, defaultLLMNodeConfig } = await import('./llm-node-config')
const { LoopNodeConfig } = await import('./loop-node-config')
const { SubWorkflowNodeConfig, defaultSubWorkflowNodeConfig } = await import('./sub-workflow-node-config')
const { ToolNodeConfig, defaultToolNodeConfig } = await import('./tool-node-config')

type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

const variables = [{ id: 'input.query', name: 'Query', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false }]
const commonProps = () => ({
  variables,
  variableSearch: '',
  openVariablePopover: null,
  onConfigChange: mock(() => {}),
  onVariableSearchChange: mock(() => {}),
  onOpenVariablePopoverChange: mock(() => {}),
})

test('imports and renders workflow node configs for LCOV coverage', () => {
  resetState()
  const trees = [
    AgentNodeConfig({ config: defaultAgentNodeConfig, ...commonProps() }),
    KnowledgeRetrievalNodeConfig({ config: defaultKnowledgeRetrievalNodeConfig, ...commonProps() }),
    LLMNodeConfig({ config: defaultLLMNodeConfig, onChange: mock(() => {}), getAvailableVariables: () => variables }),
    LoopNodeConfig({ nodeId: 'loop-1', config: { mode: 'array', arrayVariable: '', loopVariables: [] }, ...commonProps() }),
    SubWorkflowNodeConfig({ config: defaultSubWorkflowNodeConfig, ...commonProps() }),
    ToolNodeConfig({ config: defaultToolNodeConfig, ...commonProps() }),
  ] as TreeNode[]

  expect(trees).toHaveLength(6)
  for (const tree of trees) {
    expect(tree).toBeTruthy()
    expect(findAll(tree, (node) => node.type === component).length).toBeGreaterThan(0)
  }
})

test('keeps node config defaults usable', () => {
  expect(defaultAgentNodeConfig.outputVariable).toBe('response')
  expect(defaultKnowledgeRetrievalNodeConfig.outputVariable).toBe('results')
  expect(defaultLLMNodeConfig.outputVariables?.response).toBe('response')
  expect(defaultSubWorkflowNodeConfig.outputVariable).toBe('result')
  expect(defaultToolNodeConfig.outputVariable).toBe('result')
})

const model = (id: string, provider: string, vision = false, enabled = true) => ({
  id,
  is_enabled: enabled,
  model: {
    name: `${provider} ${id}`,
    provider,
    provider_display_name: provider === 'open' ? 'Acme Gateway' : null,
    model_id: `${provider}/${id}`,
    capabilities: { vision },
  },
})
const one = (tree: TreeNode, predicate: (node: TreeNode) => boolean) => {
  const found = findAll(tree, predicate)[0]
  expect(found).toBeTruthy()
  return found
}

test('LLMNodeConfig loads enabled team chat models and recovers from API failure', async () => {
  resetState()
  currentTeam = { id: 'team-1' }
  getTeamModels.mockResolvedValueOnce([model('vision', 'open', true), model('off', 'open', false, false)])
  LLMNodeConfig({})
  await effects[0]()

  expect(getTeamModels).toHaveBeenCalledWith('team-1', 'chat')
  expect(setState).toHaveBeenCalledWith(true)
  expect(setState).toHaveBeenCalledWith([model('vision', 'open', true)])
  expect(setState).toHaveBeenLastCalledWith(false)

  resetState()
  currentTeam = { id: 'team-2' }
  getTeamModels.mockRejectedValueOnce(new Error('offline'))
  LLMNodeConfig({})
  await effects[0]()

  expect(getTeamModels).toHaveBeenCalledWith('team-2', 'chat')
  expect(setState).toHaveBeenLastCalledWith(false)
})

test('LLMNodeConfig filters grouped models and selects a matching vision model', () => {
  resetState()
  const onChange = mock(() => {})
  stateValues.push(
    [model('text', 'anthropic'), model('vision', 'open', true)], false, 'ACME GATEWAY', true,
    false, false, false, false,
  )
  const tree = LLMNodeConfig({ config: defaultLLMNodeConfig, onChange }) as TreeNode

  expect(findAll(tree, (node) => node.type === 'button')).toHaveLength(1)
  const choice = one(tree, (node) => node.type === 'button' && typeof node.props.onClick === 'function')
  ;(choice.props.onClick as () => void)()

  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ modelId: 'vision', modelName: 'open vision' }))
  expect(setState).toHaveBeenCalledWith(false)
  expect(setState).toHaveBeenCalledWith('')
})

test('LLMNodeConfig updates prompts, memory, advanced settings, and output names', () => {
  resetState()
  const onChange = mock(() => {})
  const config = {
    ...defaultLLMNodeConfig,
    responseFormat: 'json_schema' as const,
    jsonSchema: '{}',
    memoryConfig: { enabled: true, mode: 'window' as const, windowSize: 5, tokenLimit: 4000 },
  }
  stateValues.push([], false, '', false, true, false, true, false)
  const tree = LLMNodeConfig({ config, onChange, getAvailableVariables: () => [] }) as TreeNode

  const prompts = findAll(tree, (node) => node.props.minHeight !== undefined)
  ;(prompts[0].props.onChange as (value: string) => void)('system')
  ;(prompts[1].props.onChange as (value: string) => void)('user')
  const memorySwitch = one(tree, (node) => node.props.checked === true && typeof node.props.onCheckedChange === 'function')
  ;(memorySwitch.props.onCheckedChange as (value: boolean) => void)(false)
  const memoryMode = one(tree, (node) => node.props.value === 'window' && typeof node.props.onValueChange === 'function')
  ;(memoryMode.props.onValueChange as (value: string) => void)('token_limit')
  const sliders = findAll(tree, (node) => Array.isArray(node.props.value) && typeof node.props.onValueChange === 'function')
  ;(sliders[0].props.onValueChange as (value: number[]) => void)([12])
  ;(sliders[1].props.onValueChange as (value: number[]) => void)([0.2])
  ;(sliders[2].props.onValueChange as (value: number[]) => void)([0.8])
  const responseFormat = one(tree, (node) => node.props.value === 'json_schema' && typeof node.props.onValueChange === 'function')
  ;(responseFormat.props.onValueChange as (value: string) => void)('json')
  const schema = one(tree, (node) => node.props.placeholder === '{"type": "object", "properties": {...}}')
  ;(schema.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '{"type":"string"}' } })
  for (const [placeholder, value] of [['response', 'answer'], ['reasoning', 'thoughts'], ['usage', 'tokens']]) {
    const output = one(tree, (node) => node.props.placeholder === placeholder)
    ;(output.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
  }

  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ systemPrompt: 'system' }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ userPrompt: 'user' }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ memoryConfig: expect.objectContaining({ enabled: false }) }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ memoryConfig: expect.objectContaining({ mode: 'token_limit' }) }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ temperature: 0.2 }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ topP: 0.8 }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ responseFormat: 'json' }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ jsonSchema: '{"type":"string"}' }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariables: expect.objectContaining({ usage: 'tokens' }) }))
})

test('LLMNodeConfig configures vision variables, positioning, and token memory', () => {
  resetState()
  const onChange = mock(() => {})
  const imageVariable = { id: 'input.image', name: 'Image', type: 'Image', group: 'input', groupLabel: 'Input', isSystem: false }
  const config = {
    ...defaultLLMNodeConfig,
    modelId: 'vision',
    memoryConfig: { enabled: true, mode: 'token_limit' as const, windowSize: 10, tokenLimit: 4000 },
    visionConfig: { enabled: true, imagePosition: 'before' as const },
  }
  stateValues.push([model('vision', 'open', true)], false, '', false, false, true, true, true)
  const tree = LLMNodeConfig({ config, onChange, getAvailableVariables: () => [imageVariable] }) as TreeNode

  const selector = one(tree, (node) => Array.isArray(node.props.variables) && typeof node.props.onSelect === 'function')
  ;(selector.props.onSelect as (variable: { id: string }) => void)(imageVariable)
  const after = one(tree, (node) => node.type === component && node.props.variant === 'outline' && typeof node.props.onClick === 'function')
  ;(after.props.onClick as () => void)()
  const tokenInput = one(tree, (node) => node.props.type === 'number' && node.props.value === 4000)
  ;(tokenInput.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '8000' } })

  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ visionConfig: expect.objectContaining({ imageVariable: 'input.image' }) }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ visionConfig: expect.objectContaining({ imagePosition: 'after' }) }))
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ memoryConfig: expect.objectContaining({ tokenLimit: 8000 }) }))
  expect(setState).toHaveBeenCalledWith(false)
})
