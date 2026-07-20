import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
mock.module('react', () => ({ default: {} }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, ChevronDown: component, ChevronUp: component, GripVertical: component, Search: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../../nodes/condition-node', () => ({
  getConditionOperatorLabels: () => ({ equals: 'Equals', is_empty: 'Empty' }),
  getConditionOperatorShortLabels: () => ({ equals: '=', is_empty: 'empty' }),
  noValueOperators: ['is_empty'],
}))

const { ConditionNodeConfig } = await import('./condition-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
const variables = [
  { id: 'input.name', name: 'Name', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.user', name: 'User', type: 'string', group: 'system', groupLabel: 'System', isSystem: true },
]
const rule = { id: 'rule-one', variable: '', variableSource: 'Start', operator: 'equals', value: 'old' }
const branches = [
  { id: 'if', type: 'if', name: 'IF', conditions: [rule], logicOperator: 'and' },
  { id: 'else', type: 'else', name: 'ELSE', conditions: [], logicOperator: 'and' },
]
function render(overrides: Record<string, unknown> = {}) {
  const onBranchesChange = mock(() => {}), onExpandedBranchesChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = ConditionNodeConfig({ branches, expandedBranches: new Set(['if']), variables, variableSearch: '', openVariablePopover: 'if-rule-one', onBranchesChange, onExpandedBranchesChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides }) as TreeNode
  return { tree, onBranchesChange, onExpandedBranchesChange, onVariableSearchChange, onOpenVariablePopoverChange }
}
const event = (value: string) => ({ target: { value }, stopPropagation: mock(() => {}) })

test('edits branches, toggles expansion, and inserts and removes else-if branches', () => {
  const current = render()
  const name = findAll(current.tree, (node) => node.props.value === 'IF' && node.props.onChange)[0]
  ;(name.props.onChange as (e: ReturnType<typeof event>) => void)(event('Primary'))
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ name: 'Primary' }), branches[1]])
  const header = findAll(current.tree, (node) => String(node.props.className).includes('cursor-pointer') && node.props.onClick)[0]
  ;(header.props.onClick as () => void)()
  expect(current.onExpandedBranchesChange).toHaveBeenCalledWith(new Set())

  const addElseIf = findAll(current.tree, (node) => node.props.className === 'w-full h-8 text-xs border-dashed')[0]
  ;(addElseIf.props.onClick as () => void)()
  expect(current.onBranchesChange).toHaveBeenCalledWith([branches[0], expect.objectContaining({ type: 'else_if', name: 'ELIF 1' }), branches[1]])

  const elif = { id: 'elif', type: 'else_if', name: 'ELIF', conditions: [], logicOperator: 'and' }
  const removable = render({ branches: [branches[0], elif, branches[1]], expandedBranches: new Set(['elif']) })
  const remove = findAll(removable.tree, (node) => node.props.className === 'h-6 w-6')[0]
  ;(remove.props.onClick as (e: ReturnType<typeof event>) => void)(event(''))
  expect(removable.onBranchesChange).toHaveBeenCalledWith([branches[0], branches[1]])
})

test('adds, edits, selects, and removes condition rules', () => {
  const current = render()
  const addRule = findAll(current.tree, (node) => node.props.className === 'w-full h-7 text-xs text-muted-foreground hover:text-foreground')[0]
  ;(addRule.props.onClick as () => void)()
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ conditions: expect.arrayContaining([expect.objectContaining({ operator: 'equals', value: '' })]) }), branches[1]])

  const operator = findAll(current.tree, (node) => node.props.value === 'equals' && node.props.onValueChange)[0]
  ;(operator.props.onValueChange as (value: string) => void)('is_empty')
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ conditions: [expect.objectContaining({ operator: 'is_empty' })] }), branches[1]])
  const value = findAll(current.tree, (node) => node.props.placeholder === 'configCommon.enterValue')[0]
  ;(value.props.onChange as (e: ReturnType<typeof event>) => void)(event('new'))
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ conditions: [expect.objectContaining({ value: 'new' })] }), branches[1]])

  const choices = findAll(current.tree, (node) => node.type === 'button')
  ;(choices[0].props.onClick as () => void)()
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ conditions: [expect.objectContaining({ variable: '{{input.name}}', variableSource: 'nodesCommon.start' })] }), branches[1]])
  ;(choices[1].props.onClick as () => void)()
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ conditions: [expect.objectContaining({ variable: '{{system.user}}', variableSource: 'nodesCommon.system' })] }), branches[1]])
  const removeRule = findAll(current.tree, (node) => node.props.className === 'h-7 w-7 shrink-0')[0]
  ;(removeRule.props.onClick as () => void)()
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ conditions: [] }), branches[1]])
})

test('groups and searches variables, changes logic, and shows else and empty states', () => {
  const twoRules = [{ ...rule }, { ...rule, id: 'two' }]
  const current = render({ branches: [{ ...branches[0], conditions: twoRules }, branches[1]], expandedBranches: new Set(['if', 'else']) })
  expect(findAll(current.tree, (node) => node.props.children === 'Input')).toHaveLength(2)
  expect(findAll(current.tree, (node) => node.props.children === 'System')).toHaveLength(2)
  expect(findAll(current.tree, (node) => node.props.children === 'configCondition.elseDescription')).toHaveLength(1)
  const logic = findAll(current.tree, (node) => node.props.value === 'and' && node.props.onValueChange)[0]
  ;(logic.props.onValueChange as (value: string) => void)('or')
  expect(current.onBranchesChange).toHaveBeenCalledWith([expect.objectContaining({ logicOperator: 'or' }), branches[1]])
  const search = findAll(current.tree, (node) => node.props.placeholder === 'configCommon.searchVariable')[0]
  ;(search.props.onChange as (e: ReturnType<typeof event>) => void)(event('name'))
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('name')
  const popover = findAll(current.tree, (node) => node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  const noMatch = render({ variableSearch: 'missing' })
  expect(findAll(noMatch.tree, (node) => node.props.children === 'configCommon.noMatchingVariables').length).toBeGreaterThan(0)
  const emptyOperator = render({ branches: [{ ...branches[0], conditions: [{ ...rule, operator: 'is_empty' }] }, branches[1]] })
  expect(findAll(emptyOperator.tree, (node) => node.props.placeholder === 'configCommon.enterValue')).toHaveLength(0)
})
