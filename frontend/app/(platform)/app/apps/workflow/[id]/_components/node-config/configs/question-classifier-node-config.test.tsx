import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
let state: unknown[] = [], stateIndex = 0, effectDeps: unknown[][] = [], effectIndex = 0
let currentTeam: { id: string } | null = { id: 'team-1' }
const getTeamModels = mock(async () => models)
const models = [
  { id: 'enabled', is_enabled: true, model: { name: 'Claude' } },
  { id: 'disabled', is_enabled: false, model: { name: 'Hidden' } },
]
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T) => { state[index] = value }] as const
  },
  useEffect: (effect: () => void, deps: unknown[]) => {
    const index = effectIndex++
    if (!effectDeps[index] || deps.some((dep, i) => dep !== effectDeps[index][i])) {
      effectDeps[index] = deps
      effect()
    }
  },
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, Search: component, GripVertical: component, Loader2: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue', 'SelectEmpty']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/textarea', ['Textarea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels } }))
mock.module('../utils', () => ({ isValidVariableName: (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) }))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/[{}]/g, '').split('.').at(-1) }))
mock.module('../../nodes/question-classifier-node', () => ({
  defaultQuestionClassifierConfig: { categories: [], instruction: '' },
}))

const { QuestionClassifierNodeConfig } = await import('./question-classifier-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
const variables = [
  { id: 'input.question', name: 'Question', type: 'String', group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.query', name: 'System Query', type: 'String', group: 'system', groupLabel: 'System', isSystem: true },
  { id: 'input.count', name: 'Count', type: 'Number', group: 'input', groupLabel: 'Input', isSystem: false },
]
const baseConfig = { categories: [{ id: 'one', name: 'billing', description: 'Billing questions' }], instruction: '' }
function render(overrides: Record<string, unknown> = {}) {
  stateIndex = 0
  effectIndex = 0
  const onConfigChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = QuestionClassifierNodeConfig({ config: baseConfig, variables, variableSearch: '', openVariablePopover: 'source-var', onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides }) as TreeNode
  return { tree, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange }
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  state = []
  effectDeps = []
  currentTeam = { id: 'team-1' }
  getTeamModels.mockClear()
  getTeamModels.mockImplementation(async () => models)
})

test('filters, groups, searches, selects, and closes source variables', () => {
  const current = render()
  expect(findAll(current.tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'System')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'Count')).toHaveLength(0)
  const choices = findAll(current.tree, (node) => node.type === 'button')
  ;(choices[1].props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ sourceVariable: '{{system.query}}', sourceNodeLabel: 'nodesCommon.system' }))
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('')

  const search = findAll(current.tree, (node) => node.props.placeholder === 'configCommon.searchVariable')[0]
  change(search, 'query')
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('query')
  const popover = findAll(current.tree, (node) => node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(current.onOpenVariablePopoverChange).toHaveBeenLastCalledWith(null)
  const empty = render({ variableSearch: 'missing' })
  expect(findAll(empty.tree, (node) => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)
  const reordered = render({ variables: [variables[1], variables[0], { ...variables[0], id: 'other.text', group: 'other', groupLabel: 'Other' }] })
  expect(findAll(reordered.tree, (node) => node.props.children === 'Other')).toHaveLength(1)
})

test('shows selected source and updates instruction and categories', () => {
  const current = render({ config: { ...baseConfig, sourceVariable: '{{input.question}}', sourceNodeLabel: 'Start' } })
  expect(findAll(current.tree, (node) => node.props.children === 'Question').length).toBeGreaterThan(0)
  change(findAll(current.tree, (node) => node.props.placeholder === 'configQuestionClassifier.instructionPlaceholder')[0], 'Classify carefully')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ instruction: 'Classify carefully' }))

  const name = findAll(current.tree, (node) => node.props.value === 'billing')[0]
  change(name, 'support')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ categories: [expect.objectContaining({ name: 'support' })] }))
  const description = findAll(current.tree, (node) => node.props.value === 'Billing questions')[0]
  change(description, 'Support questions')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ categories: [expect.objectContaining({ description: 'Support questions' })] }))

  const add = findAll(current.tree, (node) => node.type === component && node.props.className === 'h-6 w-6')[0]
  ;(add.props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ categories: [baseConfig.categories[0], expect.objectContaining({ name: 'configQuestionClassifier.categoryPrefix2', description: '' })] }))
  const remove = findAll(current.tree, (node) => String(node.props.className).includes('hover:text-destructive'))[0]
  ;(remove.props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ categories: [] }))
})

test('reports empty, invalid, and duplicate categories', () => {
  const empty = render({ config: { categories: null } })
  expect(findAll(empty.tree, (node) => node.props.children === 'configQuestionClassifier.noCategories')).toHaveLength(1)
  const invalid = render({ config: { categories: [{ id: 'a', name: 'bad name', description: '' }, { id: 'b', name: 'bad name', description: '' }] } })
  expect(findAll(invalid.tree, (node) => node.props.children === 'configQuestionClassifier.invalidCategoryName')).toHaveLength(1)
  expect(findAll(invalid.tree, (node) => node.props.children === 'configQuestionClassifier.duplicateCategoryName')).toHaveLength(1)
  expect(findAll(invalid.tree, (node) => String(node.props.className).includes('border-destructive'))).toHaveLength(2)
})

test('loads enabled models, displays selection, and changes the model', async () => {
  render()
  await flush()
  const loaded = render({ config: { ...baseConfig, modelId: 'enabled' } })
  expect(getTeamModels).toHaveBeenCalledWith('team-1', 'chat')
  expect(findAll(loaded.tree, (node) => node.props.children === 'Claude').length).toBeGreaterThan(0)
  expect(findAll(loaded.tree, (node) => node.props.children === 'Hidden')).toHaveLength(0)
  const select = findAll(loaded.tree, (node) => node.props.value === 'enabled' && node.props.onValueChange)[0]
  ;(select.props.onValueChange as (value: string) => void)('enabled')
  expect(loaded.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ modelId: 'enabled', modelName: 'Claude' }))

  const fallback = render({ config: { ...baseConfig, modelId: 'removed', modelName: 'Legacy' } })
  expect(findAll(fallback.tree, (node) => node.props.children === 'Legacy')).toHaveLength(1)
})

test('covers model loading, error, empty, and absent-team states', async () => {
  state = [[], true]
  effectDeps = [[currentTeam]]
  const loading = render()
  expect(findAll(loading.tree, (node) => node.type === component && String(node.props.className).includes('animate-spin'))).toHaveLength(1)
  expect(findAll(loading.tree, (node) => node.props.disabled === true)).toHaveLength(1)

  state = []
  effectDeps = []
  getTeamModels.mockImplementation(async () => { throw new Error('failed') })
  render()
  await flush()
  const failed = render()
  expect(findAll(failed.tree, (node) => node.props.children === 'configCommon.noAvailableModels')).toHaveLength(1)

  state = []
  effectDeps = []
  currentTeam = null
  getTeamModels.mockClear()
  const absent = render()
  await flush()
  expect(getTeamModels).not.toHaveBeenCalled()
  expect(findAll(absent.tree, (node) => node.props.children === 'configCommon.noAvailableModels')).toHaveLength(1)
})
