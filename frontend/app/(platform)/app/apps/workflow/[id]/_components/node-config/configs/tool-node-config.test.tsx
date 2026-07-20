import { beforeEach, expect, mock, test } from 'bun:test'

interface TreeNode { type?: unknown, props: Record<string, unknown> }
const jsx = (type: unknown, props: Record<string, unknown> = {}) => ({ type, props })
const component = function Component() {}
const AlertCircle = function AlertCircle() {}
const stateValues = new Map<number, unknown>()
const setters = Array.from({ length: 11 }, () => mock(() => {}))
let hookIndex = 0
let currentTeam: { id: string } | null = { id: 'team-1' }
const list = mock(async () => ({ builtin: [], custom: [], mcp: [] }))
const listMcpTools = mock(async () => ({ tools: [] }))

mock.module('react', () => ({
  default: {
    useState: (initial: unknown) => {
      const index = hookIndex++
      return [stateValues.has(index) ? stateValues.get(index) : initial, setters[index]]
    },
    useMemo: (factory: () => unknown) => factory(),
    useEffect: (effect: () => void) => effect(),
  },
  useState: (initial: unknown) => {
    const index = hookIndex++
    return [stateValues.has(index) ? stateValues.get(index) : initial, setters[index]]
  },
  useMemo: (factory: () => unknown) => factory(),
  useEffect: (effect: () => void) => effect(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  AlertCircle, Trash2: component, Search: component, ChevronDown: component, Wrench: component, Check: component,
  Loader2: component, Clock3: component, Calculator: component, Globe: component, FolderOpen: component,
  Code2: component, Link: component, ChartColumn: component,
}))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']], ['@/components/ui/badge', ['Badge']],
  ['@/components/ui/tabs', ['Tabs', 'TabsList', 'TabsTrigger']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({
  toolsApi: { list, listMcpTools },
  isPresetToolCategory: (category: string) => ['time', 'math', 'search', 'web', 'file', 'code', 'sandbox', 'api', 'data', 'other'].includes(category),
}))

const { ToolNodeConfig } = await import('./tool-node-config')

const variables = [
  { id: 'input.query', name: 'Query', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false, isArray: false, isIterable: false },
  { id: 'system.user', name: 'User', type: 'string', group: 'system', groupLabel: 'System', isSystem: true, isArray: false, isIterable: false },
]
const builtin = {
  id: 'builtin-1', name: 'search', display_name: 'Web Search', description: 'Searches the web', icon: '', category: 'search',
  type: 'builtin', is_enabled: true, requires_config: true,
  parameters: [
    { name: 'query', type: 'string', required: true, description: 'Search terms', default: 'cats' },
    { name: 'limit', type: 'number', required: false },
  ],
}
const mcp = {
  id: 'mcp-1', name: 'server', display_name: 'MCP Server', description: 'Remote tools', icon: '', category: 'custom-category',
  type: 'mcp', is_enabled: true, requires_config: false, parameters: [], mcp_config: { url: 'https://mcp.test' },
}

function descendants(value: unknown): TreeNode[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as TreeNode
  return [node, ...descendants(node.props.children)]
}
function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (value && typeof value === 'object' && 'props' in value) return text((value as TreeNode).props.children)
  return ''
}
function find(tree: TreeNode, predicate: (node: TreeNode) => boolean) {
  const result = descendants(tree).filter(predicate)
  expect(result).toHaveLength(1)
  return result[0]
}
function render(config: Record<string, unknown>, states: Record<number, unknown> = {}, overrides: Record<string, unknown> = {}) {
  hookIndex = 0
  stateValues.clear()
  for (const [key, value] of Object.entries(states)) stateValues.set(Number(key), value)
  const props = {
    config, variables, variableSearch: '', openVariablePopover: null,
    onConfigChange: mock(() => {}), onVariableSearchChange: mock(() => {}), onOpenVariablePopoverChange: mock(() => {}),
    ...overrides,
  }
  return { tree: ToolNodeConfig(props as never) as TreeNode, ...props }
}
const click = (node: TreeNode) => (node.props.onClick as () => void)()
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() }

beforeEach(() => {
  for (const setter of setters) setter.mockClear()
  currentTeam = { id: 'team-1' }
  list.mockClear()
  listMcpTools.mockClear()
  list.mockImplementation(async () => ({ builtin: [], custom: [], mcp: [] }))
  listMcpTools.mockImplementation(async () => ({ tools: [] }))
})

test('selects configured tools and builds parameter mappings', () => {
  const current = render({ toolType: 'builtin', parameterMappings: [], outputVariable: 'result' }, { 2: [builtin] })
  const choice = find(current.tree, node => node.type === 'button' && text(node).includes('Web Search'))
  click(choice)

  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    toolName: 'search', toolType: 'builtin',
    parameterMappings: [
      expect.objectContaining({ name: 'query', source: 'constant', constantValue: 'cats' }),
      expect.objectContaining({ name: 'limit', source: 'constant', constantValue: '' }),
    ],
  }))
  expect(descendants(choice).some(node => node.type === AlertCircle)).toBe(true)
})

test('updates constants, variables, validation, output, and clearing', () => {
  const mappings = [{ name: 'query', type: 'string', required: true, description: 'Search terms', source: 'constant', constantValue: '' }]
  const config = { toolName: 'search', toolType: 'builtin', parameterMappings: mappings, outputVariable: 'bad output' }
  const current = render(config, { 2: [builtin] }, { openVariablePopover: 'param-query' })

  expect(find(current.tree, node => node.props.children === 'configCommon.invalidVariableName')).toBeTruthy()
  change(find(current.tree, node => node.props.placeholder === 'configCommon.enterValueFor'), 'dogs')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ parameterMappings: [expect.objectContaining({ constantValue: 'dogs' })] }))

  click(find(current.tree, node => node.props.onClick && node.props.children === 'configCommon.variable'))
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ parameterMappings: [expect.objectContaining({ source: 'variable' })] }))

  const variable = render({ ...config, parameterMappings: [{ ...mappings[0], source: 'variable' }] }, { 2: [builtin] }, { openVariablePopover: 'param-query' })
  click(find(variable.tree, node => node.type === 'button' && text(node).includes('Query') && text(node).includes('string')))
  expect(variable.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ parameterMappings: [expect.objectContaining({ variableRef: '{{input.query}}', variableRefNodeLabel: 'Input', constantValue: undefined })] }))
  expect(variable.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)

  change(find(current.tree, node => node.props.placeholder === 'result'), 'answer')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'answer' }))
  click(find(current.tree, node => node.props.className === 'h-6 w-6 shrink-0'))
  expect(current.onConfigChange).toHaveBeenCalledWith({ toolType: 'builtin', parameterMappings: [], outputVariable: 'bad output' })
})

test('handles variable search, empty results, and popover boundaries', () => {
  const mapping = { name: 'query', type: 'string', required: true, source: 'variable', variableRef: '{{system.user}}', variableRefNodeLabel: 'System' }
  const current = render(
    { toolName: 'search', toolType: 'builtin', parameterMappings: [mapping], outputVariable: 'result' },
    { 2: [builtin] },
    { variableSearch: 'missing', openVariablePopover: 'param-query' },
  )
  expect(find(current.tree, node => node.props.children === 'configCommon.noMatchingVariables')).toBeTruthy()
  change(find(current.tree, node => node.props.placeholder === 'configCommon.searchVariable'), 'query')
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('query')
  const popover = find(current.tree, node => node.props.open === true && node.props.onOpenChange && Array.isArray(node.props.children) && String((node.props.children as TreeNode[])[0]?.props?.className).startsWith('w-full h-8'))
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('')
})

test('selects and clears MCP tools from JSON schema', () => {
  const remoteTool = {
    name: 'lookup', description: 'Looks up a record',
    parameters: { properties: { id: { type: 'number', description: 'Record id' }, fallback: {} }, required: ['id'] },
  }
  const config = { toolId: 'mcp-1', toolName: 'server', toolType: 'mcp', parameterMappings: [], outputVariable: 'result' }
  const current = render(config, { 2: [mcp], 7: [remoteTool], 9: true })
  const mcpChoices = descendants(current.tree).filter(node => node.type === 'button' && text(node).includes('lookup'))
  expect(mcpChoices).not.toHaveLength(0)
  click(mcpChoices[mcpChoices.length - 1])
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    mcpToolName: 'lookup', mcpToolDescription: 'Looks up a record',
    parameterMappings: [
      expect.objectContaining({ name: 'id', type: 'number', required: true }),
      expect.objectContaining({ name: 'fallback', type: 'string', required: false }),
    ],
  }))

  const selected = render({ ...config, mcpToolName: 'lookup', mcpToolDescription: 'Looks up a record', parameterMappings: [{ name: 'id', type: 'number', required: true, source: 'constant' }] }, { 2: [mcp] })
  const clearButtons = descendants(selected.tree).filter(node => node.props.className === 'h-6 w-6 shrink-0' && node.props.onClick)
  expect(clearButtons).not.toHaveLength(0)
  click(clearButtons[clearButtons.length - 1])
  expect(selected.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ mcpToolName: undefined, mcpToolDescription: undefined, parameterMappings: [] }))
})

test('loads only enabled workflow tools and contains API failures', async () => {
  const disabled = { ...builtin, id: 'disabled', is_enabled: false }
  const skill = { ...builtin, id: 'skill', type: 'skill' }
  list.mockImplementationOnce(async () => ({ builtin: [builtin, disabled, skill], custom: [], mcp: [] }))
  render({ toolType: 'builtin', parameterMappings: [], outputVariable: 'result' })
  await flush()
  expect(list).toHaveBeenCalledWith('team-1')
  expect(setters[2]).toHaveBeenCalledWith([builtin])
  expect(setters[3]).toHaveBeenCalledWith(true)
  expect(setters[3]).toHaveBeenLastCalledWith(false)

  list.mockImplementationOnce(async () => { throw new Error('network') })
  render({ toolType: 'builtin', parameterMappings: [], outputVariable: 'result' })
  await flush()
  expect(setters[3]).toHaveBeenLastCalledWith(false)

  currentTeam = null
  list.mockClear()
  render({ toolType: 'builtin', parameterMappings: [], outputVariable: 'result' })
  await flush()
  expect(list).not.toHaveBeenCalled()
})

test('loads MCP credentials/config and resets state on service errors', async () => {
  listMcpTools.mockImplementationOnce(async config => {
    expect(config).toEqual({ url: 'https://mcp.test' })
    return { tools: [{ name: 'remote', parameters: {} }] }
  })
  render({ toolId: 'mcp-1', toolType: 'mcp', parameterMappings: [], outputVariable: 'result' }, { 2: [mcp] })
  await flush()
  expect(setters[7]).toHaveBeenCalledWith([{ name: 'remote', parameters: {} }])
  expect(setters[8]).toHaveBeenNthCalledWith(1, true)
  expect(setters[8]).toHaveBeenLastCalledWith(false)

  listMcpTools.mockImplementationOnce(async () => { throw new Error('credentials rejected') })
  render({ toolId: 'mcp-1', toolType: 'mcp', parameterMappings: [], outputVariable: 'result' }, { 2: [mcp] })
  await flush()
  expect(setters[7]).toHaveBeenCalledWith([])
  expect(setters[8]).toHaveBeenLastCalledWith(false)

  listMcpTools.mockClear()
  render({ toolType: 'builtin', parameterMappings: [], outputVariable: 'result' }, { 2: [builtin], 7: [{ name: 'stale' }] })
  expect(listMcpTools).not.toHaveBeenCalled()
  expect(setters[7]).toHaveBeenCalledWith([])
})
