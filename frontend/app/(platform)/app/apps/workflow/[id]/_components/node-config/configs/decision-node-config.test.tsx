import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const Component = function Component() {}
const selectComponents = Object.fromEntries(
  ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue'].map((name) => [
    name,
    Object.assign(function SelectComponent() {}, { displayName: name }),
  ]),
)
const teamModel = {
  id: 'team-model-row-id',
  model_id: 'model-config-uuid',
  is_enabled: true,
  model: { name: 'Typed Model', model_id: 'vendor-model', provider: 'openai', provider_display_name: 'OpenAI' },
}
let hookIndex = 0
type TreeNode = { type?: unknown; props: Record<string, unknown> }
const findAll = (node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] => {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

const translations: Record<string, string> = {
  'decisionConfig.type': 'Question type',
  'decisionConfig.typeChoice': 'Choose an option',
  'decisionConfig.typeScore': 'Score against ordered levels',
  'decisionConfig.typeNoul': 'Yes / No probability',
  'decisionConfig.model': 'Decision model',
  'decisionConfig.selectModel': 'Select a decision model',
  'decisionConfig.state': 'State',
  'decisionConfig.instructions': 'Instructions',
  'decisionConfig.instructionsPlaceholder': 'What should the model decide?',
  'decisionConfig.options': 'Choice options',
  'decisionConfig.levels': 'Ordered score levels',
  'decisionConfig.scoreHint': 'Highest probability level selects the branch.',
  'decisionConfig.addOption': 'Add option',
  'decisionConfig.defaultHandle': 'Fallback branch',
  'decisionConfig.confidenceThreshold': 'Confidence threshold',
  'decisionConfig.optionLimit': 'Maximum {max} options or levels',
  'decisionConfig.noulHint': 'Noul routes to yes at probability 0.5 and has no confidence output.',
  'configCommon.noAvailableModels': 'No models',
}

mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = hookIndex++
    return [index === 0 ? [teamModel] as T : initial, () => {}] as const
  },
  useEffect: () => {},
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => translations[key] || key }))
mock.module('lucide-react', () => ({ AlertCircle: Component, ChevronDown: Component, Loader2: Component, Plus: Component, Search: Component, Trash2: Component, Variable: Component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/textarea', ['Textarea']],
  ['@/components/ui/select', Object.keys(selectComponents)],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) {
  mock.module(path, () => Object.fromEntries(names.map((name) => [name, selectComponents[name] || Component])))
}
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1' } }) }))
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels: async () => [teamModel] } }))
mock.module('../../nodes/decision-node', () => ({
  defaultDecisionNodeConfig: { stateTemplate: '', questionId: 'decision', questionType: 'choice', instructions: '', options: ['yes', 'no'] },
}))

const { DecisionNodeConfig } = await import('./decision-node-config')

test('selected question type label matches its menu option label', () => {
  hookIndex = 0
  const tree = DecisionNodeConfig({
    config: { stateTemplate: '', questionId: 'decision', questionType: 'score', instructions: '', options: ['low', 'high'] },
    variables: [],
    onConfigChange: () => {},
  }) as TreeNode


  const selectedValue = findAll(tree, (node) => node.type === selectComponents.SelectValue)[0]
  const scoreOption = findAll(tree, (node) => node.type === selectComponents.SelectItem && node.props.value === 'score')[0]
  expect(selectedValue.props.children).toBe('Score against ordered levels')
  expect(scoreOption.props.children).toBe('Score against ordered levels')
})

test('decision model selection stores the model UUID, not the team authorization ID', () => {
  hookIndex = 0
  let updated: Record<string, unknown> | undefined
  const tree = DecisionNodeConfig({
    config: { modelId: 'model-config-uuid', stateTemplate: '', questionId: 'decision', questionType: 'choice', instructions: '', options: ['yes', 'no'] },
    variables: [],
    onConfigChange: (config) => { updated = config },
  }) as TreeNode

  const selectedLabel = findAll(tree, (node) => node.props.children === 'OpenAI · Typed Model')[0]
  const modelButton = findAll(tree, (node) => node.type === 'button' && findAll(node.props.children, (child) => child.props.children === 'Typed Model').length > 0)[0]
  expect(selectedLabel).toBeDefined()
  ;(modelButton.props.onClick as () => void)()
  expect(updated?.modelId).toBe('model-config-uuid')
})

test('caps score levels at the provider maximum', () => {
  hookIndex = 0
  const tree = DecisionNodeConfig({
    config: { stateTemplate: '', questionId: 'decision', questionType: 'score', instructions: '', options: Array.from({ length: 10 }, (_, index) => `level-${index}`) },
    variables: [],
    onConfigChange: () => {},
  }) as TreeNode

  const addButton = findAll(tree, (node) => node.type === Component && node.props.size === 'sm' && node.props.disabled === true)[0]
  expect(addButton).toBeDefined()
})

test('does not present a confidence threshold for Noul', () => {
  hookIndex = 0
  const tree = DecisionNodeConfig({
    config: { stateTemplate: '', questionId: 'decision', questionType: 'noul', instructions: '', options: [] },
    variables: [],
    onConfigChange: () => {},
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'Confidence threshold')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.children === 'Noul routes to yes at probability 0.5 and has no confidence output.')).toHaveLength(1)
})
