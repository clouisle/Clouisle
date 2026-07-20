import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
mock.module('react', () => ({ default: {} }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, Search: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../../nodes/answer-node', () => ({ defaultAnswerNodeConfig: { outputs: [] } }))

const { AnswerNodeConfig } = await import('./answer-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
const variables = [
  { id: 'input.query', name: 'Query', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.user', name: 'User', type: 'string', group: 'system', groupLabel: 'System', isSystem: true },
]
function render(overrides: Record<string, unknown> = {}) {
  const onConfigChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = AnswerNodeConfig({ config: { outputs: [] }, variables, variableSearch: '', openVariablePopover: null, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides }) as TreeNode
  return { tree, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange }
}

test('adds and removes answer outputs', () => {
  const empty = render()
  expect(findAll(empty.tree, (node) => node.props.children === 'configAnswer.noOutputVariables')).toHaveLength(1)
  const add = findAll(empty.tree, (node) => node.type === component && node.props.className === 'h-6 w-6')[0]
  ;(add.props.onClick as () => void)()
  expect(empty.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: [expect.objectContaining({ sourceVariable: '' })] }))

  const outputs = [{ id: 'first', sourceVariable: '{{input.query}}', sourceNodeLabel: 'Input', sourceVariableName: 'Query' }, { id: 'second', sourceVariable: '' }]
  const populated = render({ config: { outputs } })
  expect(findAll(populated.tree, (node) => node.props.children === 'configAnswer.outputIndex')).toHaveLength(2)
  const remove = findAll(populated.tree, (node) => node.type === component && String(node.props.className).includes('hover:text-destructive'))[0]
  ;(remove.props.onClick as () => void)()
  expect(populated.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: [outputs[1]] }))
  // The selected value and its still-rendered picker choice both expose the variable name.
  expect(findAll(populated.tree, (node) => node.props.children === 'Query').length).toBeGreaterThan(0)
})

test('groups, searches, and selects upstream variables', () => {
  const outputs = [{ id: 'answer', sourceVariable: '' }]
  const selected = render({ config: { outputs }, openVariablePopover: 'output-var-answer' })
  expect(findAll(selected.tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(selected.tree, (node) => node.props.children === 'System')).toHaveLength(1)
  const choices = findAll(selected.tree, (node) => node.type === 'button')
  ;(choices[1].props.onClick as () => void)()
  expect(selected.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: [expect.objectContaining({ sourceVariable: '{{system.user}}', sourceNodeLabel: 'nodesCommon.system', sourceVariableName: 'User' })] }))
  expect(selected.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(selected.onVariableSearchChange).toHaveBeenCalledWith('')

  const search = findAll(selected.tree, (node) => node.type === component && node.props.placeholder === 'configCommon.searchVariable')[0]
  ;(search.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'query' } })
  expect(selected.onVariableSearchChange).toHaveBeenCalledWith('query')
  const popover = findAll(selected.tree, (node) => node.type === component && node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(selected.onOpenVariablePopoverChange).toHaveBeenLastCalledWith(null)
})

test('shows an empty search result', () => {
  const tree = render({ config: { outputs: [{ id: 'answer', sourceVariable: '' }] }, variableSearch: 'missing' }).tree
  expect(findAll(tree, (node) => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)
})
