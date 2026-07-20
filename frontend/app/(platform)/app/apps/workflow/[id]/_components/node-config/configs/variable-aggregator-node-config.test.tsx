import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const setOutputOpen = mock(() => {})
let outputOpen = true
mock.module('react', () => ({ default: { useState: () => [outputOpen, setOutputOpen] }, useState: () => [outputOpen, setOutputOpen] }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, Search: component, ChevronDown: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../../nodes/variable-aggregator-node', () => ({
  defaultVariableAggregatorConfig: { mode: 'array', variables: [], outputVariable: 'result' },
  getAggregationModeConfig: () => ({
    array: { label: 'Array', description: 'Array desc', outputType: 'array' }, object: { label: 'Object', description: 'Object desc', outputType: 'object' },
    concat: { label: 'Concat', description: 'Concat desc', outputType: 'string' }, merge: { label: 'Merge', description: 'Merge desc', outputType: 'object' },
  }),
}))

const { VariableAggregatorNodeConfig } = await import('./variable-aggregator-node-config')
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
function render(config: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  const onConfigChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = VariableAggregatorNodeConfig({ config, variables, variableSearch: '', openVariablePopover: null, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides }) as TreeNode
  return { tree, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange }
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })

test('adds variables, changes modes, and updates mode-specific options', () => {
  const empty = render({ mode: 'array', variables: [], outputVariable: 'result' })
  expect(findAll(empty.tree, (node) => node.props.children === 'configVariableAggregator.noVariables')).toHaveLength(1)
  ;(findAll(empty.tree, (node) => node.props.className === 'h-6 w-6')[0].props.onClick as () => void)()
  expect(empty.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ variables: [expect.objectContaining({ sourceVariable: '' })] }))
  const mode = findAll(empty.tree, (node) => node.props.value === 'array' && node.props.onValueChange)[0]
  ;(mode.props.onValueChange as (value: string) => void)('object')
  expect(empty.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ mode: 'object' }))

  const concat = render({ mode: 'concat', variables: [], outputVariable: 'result', separator: ',' })
  change(findAll(concat.tree, (node) => node.props.placeholder === 'configVariableAggregator.separatorPlaceholder')[0], '|')
  expect(concat.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ separator: '|' }))
  const merge = render({ mode: 'merge', variables: [], outputVariable: 'result', mergeStrategy: 'deep' })
  const strategy = findAll(merge.tree, (node) => node.props.value === 'deep' && node.props.onValueChange)[0]
  ;(strategy.props.onValueChange as (value: string) => void)('shallow')
  expect(merge.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ mergeStrategy: 'shallow' }))
})

test('selects, edits, validates, and removes object variables', () => {
  const mappings = [{ id: 'one', sourceVariable: '', targetKey: 'bad key' }, { id: 'two', sourceVariable: '{{input.name}}', sourceNodeLabel: 'Input', targetKey: 'bad key' }]
  const current = render({ mode: 'object', variables: mappings, outputVariable: 'bad output' }, { openVariablePopover: 'aggregator-var-one' })
  expect(findAll(current.tree, (node) => node.props.children === 'configVariableAggregator.invalidKeyName')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'configVariableAggregator.duplicateKeyName')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'configCommon.invalidVariableName')).toHaveLength(1)
  change(findAll(current.tree, (node) => node.props.placeholder === 'configVariableAggregator.keyName')[0], 'name')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ variables: [expect.objectContaining({ targetKey: 'name' }), mappings[1]] }))
  const choices = findAll(current.tree, (node) => node.type === 'button')
  ;(choices[0].props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ variables: [expect.objectContaining({ sourceVariable: '{{input.name}}' }), mappings[1]] }))
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  const remove = findAll(current.tree, (node) => node.type === component && String(node.props.className).includes('hover:text-destructive'))[0]
  ;(remove.props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ variables: [mappings[1]] }))
})

test('searches empty choices and updates output collapse', () => {
  outputOpen = false
  const current = render({ mode: 'array', variables: [{ id: 'one', sourceVariable: '' }], outputVariable: 'result' }, { variableSearch: 'missing' })
  expect(findAll(current.tree, (node) => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)
  const search = findAll(current.tree, (node) => node.props.placeholder === 'configCommon.searchVariable')[0]
  change(search, 'name')
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('name')
  const collapsible = findAll(current.tree, (node) => node.props.open === false && node.props.onOpenChange === setOutputOpen)[0]
  ;(collapsible.props.onOpenChange as (open: boolean) => void)(true)
  expect(setOutputOpen).toHaveBeenCalledWith(true)
  change(findAll(current.tree, (node) => node.props.placeholder === 'result')[0], 'output')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'output' }))
})
