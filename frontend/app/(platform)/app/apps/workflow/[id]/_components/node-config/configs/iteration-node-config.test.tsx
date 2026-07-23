import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
mock.module('react', () => ({ default: { useMemo: (factory: () => unknown) => factory() }, useMemo: (factory: () => unknown) => factory() }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Search: component, AlertCircle: component }))
for (const [path, names] of [
  ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']], ['@/components/ui/switch', ['Switch']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../../nodes/iteration-node', () => ({}))

const { IterationNodeConfig } = await import('./iteration-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
function text(node: unknown): string {
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}
const base = { iteratorVariable: '', iteratorType: 'array', itemVariable: 'item', indexVariable: 'index', outputVariable: 'results', parallel: false }
const variables = [
  { id: 'input.items', name: 'Items', type: 'array', group: 'input', groupLabel: 'Input', isSystem: false, isIterable: true, isArray: true },
  { id: 'system.map', name: 'Map', type: 'object', group: 'system', groupLabel: 'System', isSystem: true, isIterable: true, isArray: false },
  { id: 'input.text', name: 'Text', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false, isIterable: false },
]
function render(config: Record<string, unknown> = base, overrides: Record<string, unknown> = {}) {
  const onConfigChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = IterationNodeConfig({ config, variables, variableSearch: '', openVariablePopover: 'iteration-source', onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides }) as TreeNode
  return { tree, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange }
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })

test('filters, groups, searches, and selects iterable variables', () => {
  const selected = render()
  expect(findAll(selected.tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(selected.tree, (node) => node.props.children === 'System')).toHaveLength(1)
  expect(findAll(selected.tree, (node) => node.props.children === 'Text')).toHaveLength(0)
  const choices = findAll(selected.tree, (node) => node.type === 'button')
  ;(choices[0].props.onClick as () => void)()
  expect(selected.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ iteratorVariable: '{{input.items}}', iteratorSource: 'Input', iteratorType: 'array' }))
  ;(choices[1].props.onClick as () => void)()
  expect(selected.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ iteratorVariable: '{{system.map}}', iteratorType: 'object' }))
  const search = findAll(selected.tree, (node) => node.props.placeholder === 'configCommon.searchVariable')[0]
  change(search, 'map')
  expect(selected.onVariableSearchChange).toHaveBeenCalledWith('map')
  const popover = findAll(selected.tree, (node) => node.type === component && node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(selected.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
})

test('reports absent and unmatched iterable variables', () => {
  expect(findAll(render(base, { variables: [] }).tree, (node) => node.props.children === 'configIteration.noIterableVariables')).toHaveLength(1)
  expect(findAll(render(base, { variableSearch: 'missing' }).tree, (node) => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)
  expect(findAll(render().tree, (node) => text(node) === 'configIteration.selectIterableHint').length).toBeGreaterThan(0)
})

test('updates array, object, index, output, and parallel settings with validation', () => {
  const invalid = { ...base, iteratorType: 'object', iteratorVariable: '{{system.map}}', keyVariable: 'same', valueVariable: 'bad name', indexVariable: 'same', outputVariable: 'same', parallel: true, maxParallel: 4 }
  const { tree, onConfigChange } = render(invalid)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.invalidVariableName').length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.duplicateVariableInNode').length).toBeGreaterThan(0)
  for (const [placeholder, value, key] of [['key', 'key2', 'keyVariable'], ['value', 'value2', 'valueVariable'], ['index', 'i', 'indexVariable'], ['results', 'out', 'outputVariable']]) {
    change(findAll(tree, (node) => node.props.placeholder === placeholder)[0], value)
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ [key]: value }))
  }
  const parallel = findAll(tree, (node) => node.props.checked === true)[0]
  ;(parallel.props.onCheckedChange as (checked: boolean) => void)(false)
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ parallel: false }))
  change(findAll(tree, (node) => node.props.type === 'number')[0], '')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ maxParallel: 10 }))

  const array = render({ ...base, itemVariable: 'item' })
  change(findAll(array.tree, (node) => node.props.placeholder === 'item')[0], 'entry')
  expect(array.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ itemVariable: 'entry' }))
})
