import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const stateValues: unknown[] = []
const setState = mock(() => {})
const resetState = () => {
  stateValues.length = 0
  setState.mockClear()
}

mock.module('react', () => ({
  default: {},
  useMemo: (factory: () => unknown) => factory(),
  useState: (initial: unknown) => [stateValues.length ? stateValues.shift() : initial, setState],
  useEffect: () => {},
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
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: null }) }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/api/knowledge-bases', () => ({ knowledgeBasesApi: { getKnowledgeBases: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/api/workflows', () => ({ workflowsApi: { getWorkflows: mock(async () => ({ items: [] })) } }))
mock.module('@/lib/api', () => ({
  teamModelsApi: { getTeamModels: mock(async () => []) },
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
