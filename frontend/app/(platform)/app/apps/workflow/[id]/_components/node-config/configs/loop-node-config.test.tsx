import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
function useState<T>(initial: T) {
  return [initial, mock(() => {})] as const
}
mock.module('react', () => ({ default: { useState }, useState }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, Pencil: component, Search: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']], ['@/components/ui/textarea', ['Textarea']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/switch', ['Switch']],
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogHeader', 'DialogTitle', 'DialogFooter']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../constants', () => ({
  loopVariableTypeConfig: Object.fromEntries(['string', 'number', 'boolean', 'array', 'object'].map(type => [type, {
    icon: component, valueType: type, labelKey: type,
  }])),
}))
mock.module('../../nodes/loop-node', () => ({}))
mock.module('../../nodes/condition-node', () => ({
  getConditionOperatorLabels: () => ({ equals: 'Equals', is_empty: 'Empty' }),
  getConditionOperatorShortLabels: () => ({ equals: '=', is_empty: 'empty' }),
  noValueOperators: ['is_empty'],
}))

const { LoopNodeConfig } = await import('./loop-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
type Config = Parameters<typeof LoopNodeConfig>[0]['config']
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap(child => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
const base: Config = {
  maxIterations: 20,
  indexVariable: 'index',
  loopVariables: [],
  exitConditions: [],
  exitLogicOperator: 'and',
  outputVariable: 'results',
}
const variables = [
  { id: 'start.query', name: 'Query', type: 'string', group: 'start', groupLabel: 'Start', isSystem: false, isArray: false, isIterable: false },
  { id: 'system.user', name: 'User', type: 'string', group: 'system', groupLabel: 'System', isSystem: true, isArray: false, isIterable: false },
]
function render(config: Config = base, overrides: Partial<Parameters<typeof LoopNodeConfig>[0]> = {}) {
  const onConfigChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = LoopNodeConfig({
    nodeId: 'loop-1', config, variables, variableSearch: '', openVariablePopover: null,
    onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides,
  }) as TreeNode
  return { tree, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange }
}
const change = (node: TreeNode, value: string) =>
  (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })

test('shows invalid and duplicate internal variable errors', () => {
  const config: Config = {
    ...base,
    indexVariable: 'item',
    outputVariable: 'bad name',
    loopVariables: [{ id: 'var-1', name: 'ITEM', type: 'string', defaultValue: '', description: '' }],
  }
  const { tree } = render(config)
  expect(findAll(tree, node => node.props.children === 'configCommon.duplicateVariableInNode')).toHaveLength(1)
  expect(findAll(tree, node => node.props.children === 'configCommon.invalidVariableName')).toHaveLength(1)
  expect(findAll(tree, node => String(node.props.className).includes('border-destructive!'))).toHaveLength(2)
})

test('updates loop limits and variable names, including the empty limit fallback', () => {
  const { tree, onConfigChange } = render()
  change(findAll(tree, node => node.props.type === 'number' && node.props.max === 1000)[0], '')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ maxIterations: 10 }))
  change(findAll(tree, node => node.props.placeholder === 'index')[0], 'position')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ indexVariable: 'position' }))
  change(findAll(tree, node => node.props.placeholder === 'results')[0], 'collected')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'collected' }))

  const addButtons = findAll(tree, node => node.props.className === 'h-6 px-2 text-xs')
  ;(addButtons[1].props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    exitConditions: [expect.objectContaining({ variable: '', operator: 'equals', value: '' })],
  }))
})

test('edits, searches, selects, and removes exit conditions', () => {
  const rule = { id: 'rule-1', variable: '', variableSource: '', operator: 'equals' as const, value: 'old' }
  const config: Config = { ...base, exitConditions: [rule] }
  const current = render(config, { openVariablePopover: 'exit-rule-1' })

  const operator = findAll(current.tree, node => node.props.value === 'equals' && node.props.onValueChange)[0]
  ;(operator.props.onValueChange as (value: string) => void)('is_empty')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    exitConditions: [expect.objectContaining({ operator: 'is_empty' })],
  }))
  change(findAll(current.tree, node => node.props.placeholder === 'configCommon.enterValue')[0], 'done')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    exitConditions: [expect.objectContaining({ value: 'done' })],
  }))

  const choices = findAll(current.tree, node => node.type === 'button')
  ;(choices[0].props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    exitConditions: [expect.objectContaining({ variable: '{{loop-1.index}}', variableSource: 'configLoop.currentLoop' })],
  }))
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('')

  change(findAll(current.tree, node => node.props.placeholder === 'configCommon.searchVariable')[0], 'query')
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('query')
  const popover = findAll(current.tree, node => node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)

  const remove = findAll(current.tree, node => node.props.className === 'h-7 w-7 shrink-0')[0]
  ;(remove.props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ exitConditions: [] }))

  expect(findAll(render(config, { variableSearch: 'missing' }).tree, node => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)
  expect(findAll(render({ ...config, exitConditions: [{ ...rule, operator: 'is_empty' }] }).tree, node => node.props.placeholder === 'configCommon.enterValue')).toHaveLength(0)
})
