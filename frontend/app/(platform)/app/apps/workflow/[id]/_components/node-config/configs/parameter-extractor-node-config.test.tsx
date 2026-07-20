import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const getTeamModels = mock(() => Promise.resolve<TeamModel[]>([]))
const onConfigChange = mock()
const onVariableSearchChange = mock()
const onOpenVariablePopoverChange = mock()
let currentTeam: { id: string } | null = { id: 'team-1' }
let state: unknown[] = []
let stateIndex = 0
let effectDependencies: unknown[][] = []
let effectIndex = 0

type TeamModel = { id: string; is_enabled: boolean; model: { name: string } }
type Tree = { type: unknown; props: Record<string, unknown> }
type Config = {
  extractionMethod: 'llm' | 'regex' | 'json_path'
  sourceVariable: string
  sourceNodeLabel?: string
  modelId?: string
  modelName?: string
  useJsonSchema?: boolean
  parameters: Array<{
    id: string
    name: string
    type: 'string' | 'number' | 'boolean' | 'array' | 'object'
    description: string
    required: boolean
    pattern?: string
    jsonPath?: string
    defaultValue?: string
    enum?: string[]
    arrayItemType?: 'string' | 'number' | 'boolean' | 'array' | 'object'
  }>
}

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  createElement: jsx,
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
  useEffect: (effect: () => void, dependencies: unknown[]) => {
    const index = effectIndex++
    const previous = effectDependencies[index]
    if (!previous || dependencies.some((dependency, i) => dependency !== previous[i])) {
      effectDependencies[index] = dependencies
      effect()
    }
  },
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels } }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: element('select-content'),
  SelectItem: element('option'),
  SelectTrigger: element('select-trigger'),
  SelectValue: element('select-value'),
  SelectEmpty: element('select-empty'),
}))
mock.module('@/components/ui/popover', () => ({
  Popover: element('popover'),
  PopoverContent: element('popover-content'),
  PopoverTrigger: element('popover-trigger'),
}))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: element('scroll-area') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('checkbox') }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: element('collapsible'),
  CollapsibleContent: element('collapsible-content'),
  CollapsibleTrigger: element('collapsible-trigger'),
}))
mock.module('lucide-react', () => ({
  Plus: element('plus'),
  Trash2: element('trash'),
  Search: element('search'),
  ChevronDown: element('chevron'),
  Loader2: element('loader'),
}))

const icon = element('icon')
const methods = {
  llm: {
    label: 'LLM', description: 'LLM description', icon,
    supportedTypes: ['string', 'number', 'boolean', 'array', 'object'],
    defaultType: 'string', sourceVariableTypes: ['String', 'Object', 'Array'],
  },
  regex: {
    label: 'Regex', description: 'Regex description', icon,
    supportedTypes: ['string', 'number', 'array'],
    defaultType: 'string', sourceVariableTypes: ['String'],
  },
  json_path: {
    label: 'JSON Path', description: 'JSON Path description', icon,
    supportedTypes: ['string', 'number', 'boolean', 'array', 'object'],
    defaultType: 'object', sourceVariableTypes: ['String', 'Object', 'Array'],
  },
}
const typeConfig = Object.fromEntries(
  ['string', 'number', 'boolean', 'array', 'object'].map(type => [type, { labelKey: `type.${type}`, icon }]),
)
mock.module('../../nodes/parameter-extractor-node', () => ({
  defaultParameterExtractorConfig: {
    extractionMethod: 'llm', sourceVariable: '', modelId: '', modelName: '', useJsonSchema: true, parameters: [],
  },
  getExtractionMethodConfig: () => methods,
  extractedParamTypeConfig: typeConfig,
  generateJsonSchema: (parameters: Config['parameters']) => ({ properties: parameters.map(parameter => parameter.name) }),
}))

const { ParameterExtractorNodeConfig } = await import('./parameter-extractor-node-config')

const variables = [
  { id: 'node.text', name: 'Text result', type: 'String', group: 'node', groupLabel: 'Previous node', isSystem: false, isArray: false, isIterable: false },
  { id: 'node.object', name: 'Object result', type: 'Object', group: 'node', groupLabel: 'Previous node', isSystem: false, isArray: false, isIterable: false },
  { id: 'sys.query', name: 'System query', type: 'String', group: 'system', groupLabel: 'System', isSystem: true, isArray: false, isIterable: false },
]
const baseConfig: Config = { extractionMethod: 'llm', sourceVariable: '', useJsonSchema: true, parameters: [] }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  const found: Tree[] = []
  for (const child of Array.isArray(node) ? node : [node]) {
    if (Array.isArray(child)) {
      found.push(...findAll(child, predicate))
      continue
    }
    const tree = resolve(child)
    if (!tree || typeof tree !== 'object' || !('type' in tree)) continue
    if (predicate(tree as Tree)) found.push(tree as Tree)
    found.push(...findAll((tree as Tree).props.children as ReactNode, predicate))
  }
  return found
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  const match = findAll(node, predicate)[0]
  if (!match) throw new Error('Element not found')
  return match
}

function render(config: Config = baseConfig, overrides: Record<string, unknown> = {}) {
  stateIndex = 0
  effectIndex = 0
  return ParameterExtractorNodeConfig({
    config,
    variables,
    variableSearch: '',
    openVariablePopover: 'source-var',
    onConfigChange,
    onVariableSearchChange,
    onOpenVariablePopoverChange,
    ...overrides,
  })
}

beforeEach(() => {
  state = []
  effectDependencies = []
  currentTeam = { id: 'team-1' }
  getTeamModels.mockReset()
  getTeamModels.mockResolvedValue([])
  onConfigChange.mockReset()
  onVariableSearchChange.mockReset()
  onOpenVariablePopoverChange.mockReset()
})

describe('ParameterExtractorNodeConfig', () => {
  test('filters source variables by method and search, then selects the source', () => {
    const regexConfig = { ...baseConfig, extractionMethod: 'regex' as const }
    const tree = render(regexConfig, { variableSearch: 'text' })

    expect(JSON.stringify(tree)).toContain('Text result')
    expect(JSON.stringify(tree)).not.toContain('Object result')
    expect(JSON.stringify(tree)).not.toContain('System query')

    find(tree, node => node.type === 'button' && JSON.stringify(node.props.children).includes('Text result')).props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      sourceVariable: '{{node.text}}', sourceNodeLabel: 'Previous node',
    }))
    expect(onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
    expect(onVariableSearchChange).toHaveBeenCalledWith('')

    find(tree, node => node.type === 'popover').props.onOpenChange(false)
    expect(onOpenVariablePopoverChange).toHaveBeenLastCalledWith(null)
  })

  test('loads enabled team models, selects one, and tolerates absence or errors', async () => {
    getTeamModels.mockResolvedValueOnce([
      { id: 'enabled', is_enabled: true, model: { name: 'Enabled model' } },
      { id: 'disabled', is_enabled: false, model: { name: 'Disabled model' } },
    ])
    render()
    await Promise.resolve()
    await Promise.resolve()
    const loaded = render()

    expect(getTeamModels).toHaveBeenCalledWith('team-1', 'chat')
    expect(JSON.stringify(loaded)).toContain('Enabled model')
    expect(JSON.stringify(loaded)).not.toContain('Disabled model')
    find(loaded, node => node.type === 'select' && node.props.value === '').props.onValueChange('enabled')
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ modelId: 'enabled', modelName: 'Enabled model' }))

    state = []
    effectDependencies = []
    currentTeam = null
    render()
    expect(getTeamModels).toHaveBeenCalledTimes(1)

    state = []
    effectDependencies = []
    currentTeam = { id: 'team-2' }
    getTeamModels.mockRejectedValueOnce(new Error('unavailable'))
    render()
    await Promise.resolve()
    await Promise.resolve()
    expect(JSON.stringify(render())).toContain('configCommon.noAvailableModels')
  })

  test('adds, updates, validates, and deletes parameters', () => {
    const parameter = { id: 'param-1', name: 'bad name', type: 'string' as const, description: '', required: false }
    const config = { ...baseConfig, parameters: [parameter, { ...parameter, id: 'param-2' }] }
    const tree = render(config)

    expect(JSON.stringify(tree)).toContain('configParameterExtractor.invalidParamName')
    expect(JSON.stringify(tree)).toContain('configParameterExtractor.duplicateParamName')

    const addButton = find(tree, node => node.type === 'button' && findAll(node.props.children as ReactNode, child => child.type === 'plus').length > 0)
    addButton.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      parameters: expect.arrayContaining([expect.objectContaining({ name: 'param3', type: 'string', required: false })]),
    }))

    const inputs = findAll(tree, node => node.type === 'input')
    const nameInput = inputs.find(input => input.props.value === 'bad name')!
    nameInput.props.onChange({ target: { value: 'valid_name' } })
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      parameters: expect.arrayContaining([expect.objectContaining({ id: 'param-1', name: 'valid_name' })]),
    }))

    const required = find(tree, node => node.type === 'checkbox' && node.props.id === 'required-param-1')
    required.props.onCheckedChange(true)
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      parameters: expect.arrayContaining([expect.objectContaining({ id: 'param-1', required: true })]),
    }))

    const deleteButton = findAll(tree, node => node.type === 'button' && findAll(node.props.children as ReactNode, child => child.type === 'trash').length > 0)[0]
    deleteButton.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      parameters: [expect.objectContaining({ id: 'param-2' })],
    }))
  })

  test('shows and updates method-specific fields while coercing incompatible types', () => {
    const parameter = { id: 'param-1', name: 'value', type: 'boolean' as const, description: '', required: false }
    const llmTree = render({ ...baseConfig, parameters: [parameter] })
    expect(JSON.stringify(llmTree)).toContain('configParameterExtractor.descriptionHelpLLM')

    const methodSelect = find(llmTree, node => node.type === 'select' && node.props.value === 'llm')
    methodSelect.props.onValueChange('regex')
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      extractionMethod: 'regex',
      parameters: [expect.objectContaining({ type: 'string' })],
    }))

    const regexTree = render({ ...baseConfig, extractionMethod: 'regex', parameters: [{ ...parameter, type: 'string' }] })
    const pattern = find(regexTree, node => node.type === 'input' && node.props.placeholder === 'configParameterExtractor.regexPlaceholder')
    pattern.props.onChange({ target: { value: '(?<value>.*)' } })
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      parameters: [expect.objectContaining({ pattern: '(?<value>.*)' })],
    }))

    const jsonTree = render({ ...baseConfig, extractionMethod: 'json_path', parameters: [{ ...parameter, type: 'object' }] })
    const jsonPath = find(jsonTree, node => node.type === 'input' && node.props.placeholder === 'configParameterExtractor.jsonPathPlaceholder')
    jsonPath.props.onChange({ target: { value: '$.value' } })
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      parameters: [expect.objectContaining({ jsonPath: '$.value' })],
    }))
  })

  test('toggles structured output and only shows its schema preview when enabled', () => {
    const parameter = { id: 'param-1', name: 'answer', type: 'string' as const, description: 'Answer', required: true }
    const enabled = render({ ...baseConfig, parameters: [parameter] })

    expect(JSON.stringify(enabled)).toContain('configParameterExtractor.viewJsonSchema')
    expect(JSON.stringify(enabled)).toContain('answer')
    const schemaToggle = find(enabled, node => node.type === 'checkbox' && node.props.id === undefined)
    schemaToggle.props.onCheckedChange(false)
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ useJsonSchema: false }))

    const disabled = render({ ...baseConfig, useJsonSchema: false, parameters: [parameter] })
    expect(JSON.stringify(disabled)).not.toContain('configParameterExtractor.viewJsonSchema')
  })
})
