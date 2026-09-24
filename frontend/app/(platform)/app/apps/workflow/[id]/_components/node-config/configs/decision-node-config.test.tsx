import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>, key?: unknown) => ({ type, props: { ...props, ...(key === undefined ? {} : { key }) } })
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
let pendingEffect: (() => void | (() => void)) | undefined
let getTeamModels: (teamId: string, modelType: string) => Promise<typeof teamModel[]> = async () => [teamModel]
const stateUpdates: unknown[] = []
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
    return [index === 0 ? [teamModel] as T : initial, (value: T) => { stateUpdates.push(value) }] as const
  },
  useEffect: (effect: () => void | (() => void)) => { pendingEffect = effect },
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
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels: (teamId: string, modelType: string) => getTeamModels(teamId, modelType) } }))
mock.module('../../nodes/decision-node', () => ({
  defaultDecisionNodeConfig: { stateTemplate: '', questionId: 'decision', questionType: 'choice', instructions: '', options: ['yes', 'no'] },
}))

const { DecisionNodeConfig } = await import('./decision-node-config')


test('loads enabled decision models for the current team', async () => {
  stateUpdates.length = 0
  hookIndex = 0
  pendingEffect = undefined
  const request = Promise.resolve([teamModel, { ...teamModel, id: 'disabled', is_enabled: false }])
  getTeamModels = async (teamId, modelType) => {
    expect([teamId, modelType]).toEqual(['team-1', 'decision'])
    return await request as typeof teamModel[]
  }
  DecisionNodeConfig({ config: { stateTemplate: '', questionId: 'decision', questionType: 'choice', instructions: '', options: [] }, variables: [], onConfigChange: () => {} })
  pendingEffect?.()
  await request
  await new Promise((resolve) => setTimeout(resolve, 0))
  expect(stateUpdates).toContainEqual([teamModel])
  expect(stateUpdates).toContain(false)
})


test('handles decision model loading errors', async () => {
  stateUpdates.length = 0
  hookIndex = 0
  pendingEffect = undefined
  getTeamModels = async () => { throw new Error('offline') }
  DecisionNodeConfig({ config: { stateTemplate: '', questionId: 'decision', questionType: 'choice', instructions: '', options: [] }, variables: [], onConfigChange: () => {} })
  pendingEffect?.()
  await new Promise((resolve) => setTimeout(resolve, 0))
  expect(stateUpdates).toContainEqual([])
  expect(stateUpdates).toContain(false)
  expect(pendingEffect).toBeFunction()
})

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


test('updates options, question type, and confidence threshold from controls', () => {
  hookIndex = 0
  const updates: Array<Record<string, unknown>> = []
  const tree = DecisionNodeConfig({
    config: {
      stateTemplate: 'state',
      questionId: 'decision',
      questionType: 'choice',
      instructions: 'Choose a route',
      options: ['yes', 'no'],
      defaultHandle: 'fallback',
      confidenceThreshold: 0.4,
    },
    variables: [],
    onConfigChange: (config) => updates.push(config),
  }) as TreeNode

  const optionInput = findAll(
    tree,
    (node) => node.type === Component && node.props.value === 'yes',
  )[0]
  ;(optionInput.props.onChange as (event: { target: { value: string } }) => void)(
    { target: { value: 'approve' } },
  )
  expect(updates.at(-1)?.options).toEqual(['approve', 'no'])

  const removeOption = findAll(
    tree,
    (node) => node.type === Component && node.props.size === 'icon',
  )[0]
  ;(removeOption.props.onClick as () => void)()
  expect(updates.at(-1)?.options).toEqual(['no'])

  const addOption = findAll(
    tree,
    (node) => node.type === Component && node.props.size === 'sm',
  )[0]
  expect(addOption.props.disabled).toBe(false)
  ;(addOption.props.onClick as () => void)()
  expect(updates.at(-1)?.options).toEqual(['yes', 'no', 'option_3'])

  const typeSelect = findAll(tree, (node) => node.type === selectComponents.Select)[0]
  ;(typeSelect.props.onValueChange as (value: string) => void)('noul')
  expect(updates.at(-1)?.questionType).toBe('noul')

  const threshold = findAll(
    tree,
    (node) => node.type === Component && node.props.type === 'number',
  )[0]
  ;(threshold.props.onChange as (event: { target: { value: string } }) => void)(
    { target: { value: '0.7' } },
  )
  expect(updates.at(-1)?.confidenceThreshold).toBe(0.7)
})


test('updates state, instructions, fallback, threshold, and model search controls', () => {
  hookIndex = 0
  stateUpdates.length = 0
  const updates: Array<Record<string, unknown>> = []
  const tree = DecisionNodeConfig({
    config: { stateTemplate: 'initial state', questionId: 'decision', questionType: 'choice', instructions: 'initial instruction', options: ['yes'], defaultHandle: 'fallback', confidenceThreshold: 0.4 },
    variables: [{ id: 'start.question', name: 'question', type: 'String', path: 'start.question' }, { id: 'start.count', name: 'count', type: 'Number', path: 'start.count' }],
    onConfigChange: (config) => updates.push(config),
  }) as TreeNode

  const state = findAll(tree, (node) => node.props.placeholder === '{{start.question}}')[0]
  ;(state.props.onChange as (value: string) => void)('new state')
  expect(updates.at(-1)?.stateTemplate).toBe('new state')

  const instructions = findAll(tree, (node) => node.type === Component && node.props.value === 'initial instruction')[0]
  ;(instructions.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'new instruction' } })
  expect(updates.at(-1)?.instructions).toBe('new instruction')

  const fallback = findAll(tree, (node) => node.type === Component && node.props.value === 'fallback')[0]
  ;(fallback.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'review' } })
  expect(updates.at(-1)?.defaultHandle).toBe('review')

  const threshold = findAll(tree, (node) => node.type === Component && node.props.type === 'number')[0]
  ;(threshold.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '' } })
  expect(updates.at(-1)?.confidenceThreshold).toBeUndefined()

  const search = findAll(tree, (node) => node.type === Component && node.props.placeholder === 'configCommon.searchModel')[0]
  ;(search.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'typed' } })
  expect(stateUpdates).toContain('typed')
})


test('preserves option row identity when an option label changes', () => {
  hookIndex = 0
  let updatedOptions: string[] = []
  const render = (options: string[]) => DecisionNodeConfig({
    config: { stateTemplate: '', questionId: 'decision', questionType: 'choice', instructions: '', options },
    variables: [],
    onConfigChange: (config) => { updatedOptions = config.options },
  }) as TreeNode

  const before = render(['yes', 'no'])
  const beforeRows = findAll(before, (node) => node.type === 'div' && node.props.className === 'flex gap-2')
  const yesInput = findAll(before, (node) => node.type === Component && node.props.value === 'yes')[0]
  ;(yesInput.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'approved' } })
  expect(updatedOptions).toEqual(['approved', 'no'])

  hookIndex = 0
  const after = render(updatedOptions)
  const afterRows = findAll(after, (node) => node.type === 'div' && node.props.className === 'flex gap-2')
  expect(afterRows.map((row) => row.props.key)).toEqual(beforeRows.map((row) => row.props.key))
})
