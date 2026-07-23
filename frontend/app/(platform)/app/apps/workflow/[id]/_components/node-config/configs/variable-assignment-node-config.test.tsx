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
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/textarea', ['Textarea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../../nodes/variable-assignment-node', () => ({
  defaultVariableAssignmentConfig: { assignments: [] },
  getAssignmentOperationConfig: () => ({
    overwrite: { label: 'Overwrite', description: 'Overwrite desc', icon: component },
    clear: { label: 'Clear', description: 'Clear desc', icon: component },
    set: { label: 'Set', description: 'Set desc', icon: component },
    append: { label: 'Append', description: 'Append desc', icon: component },
  }),
}))

const { VariableAssignmentNodeConfig } = await import('./variable-assignment-node-config')
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
const conversationVariables = [
  { id: 'conversation.topic', name: 'Topic', type: 'string', group: 'conversation', groupLabel: 'Conversation', isSystem: false },
]
function render(config: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  const onConfigChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {})
  const tree = VariableAssignmentNodeConfig({ config, variables, conversationVariables, variableSearch: '', openVariablePopover: null, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, ...overrides }) as TreeNode
  return { tree, onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange }
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })

test('adds an assignment and reports empty variable choices', () => {
  const empty = render({ assignments: [] }, { conversationVariables: [] })
  expect(findAll(empty.tree, (node) => node.props.children === 'configVariableAssignment.noAssignments')).toHaveLength(1)
  ;(findAll(empty.tree, (node) => node.props.className === 'h-6 w-6')[0].props.onClick as () => void)()
  expect(empty.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ targetVariable: '', operation: 'set', constantValue: '' })] }))

  const assignment = { id: 'one', targetVariable: '', operation: 'set', constantValue: '' }
  const noTargets = render({ assignments: [assignment] }, { conversationVariables: [], openVariablePopover: 'target-var-one' })
  expect(findAll(noTargets.tree, (node) => node.props.children === 'configVariableAssignment.noConversationVariables')).toHaveLength(1)
  const unmatched = render({ assignments: [assignment] }, { variableSearch: 'missing', openVariablePopover: 'target-var-one' })
  expect(findAll(unmatched.tree, (node) => node.props.children === 'configCommon.noMatchingVariables')).toHaveLength(1)
})

test('selects a target, edits constants, changes operations, and deletes', () => {
  const assignment = { id: 'one', targetVariable: '', operation: 'set', constantValue: 'old' }
  const current = render({ assignments: [assignment] }, { openVariablePopover: 'target-var-one' })
  const target = findAll(current.tree, (node) => node.type === 'button')[0]
  ;(target.props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ targetVariable: 'conversation.topic', targetVariableLabel: 'Topic', targetVariableNodeLabel: 'Conversation' })] }))
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('')

  change(findAll(current.tree, (node) => node.props.placeholder === 'configVariableAssignment.setValuePlaceholder')[0], '{"ok":true}')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ constantValue: '{"ok":true}' })] }))
  const operation = findAll(current.tree, (node) => node.props.value === 'set' && node.props.onValueChange)[0]
  ;(operation.props.onValueChange as (value: string) => void)('clear')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ operation: 'clear', constantValue: undefined })] }))
  ;(operation.props.onValueChange as (value: string) => void)('overwrite')
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ operation: 'overwrite', constantValue: undefined })] }))

  const remove = findAll(current.tree, (node) => String(node.props.className).includes('hover:text-destructive'))[0]
  ;(remove.props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [] }))
})

test('groups, searches, and selects source variables', () => {
  const assignment = { id: 'one', targetVariable: 'conversation.topic', targetVariableLabel: 'Topic', operation: 'overwrite', variableRef: '{{input.old}}' }
  const current = render({ assignments: [assignment] }, { openVariablePopover: 'source-var-one' })
  expect(findAll(current.tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(current.tree, (node) => node.props.children === 'System')).toHaveLength(1)
  const choices = findAll(current.tree, (node) => node.type === 'button')
  ;(choices[1].props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ variableRef: '{{input.name}}', variableRefNodeLabel: 'Input' })] }))
  ;(choices[2].props.onClick as () => void)()
  expect(current.onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ assignments: [expect.objectContaining({ variableRef: '{{system.user}}', variableRefNodeLabel: 'nodesCommon.system' })] }))

  const search = findAll(current.tree, (node) => node.props.placeholder === 'configCommon.searchVariable')[0]
  change(search, 'user')
  expect(current.onVariableSearchChange).toHaveBeenCalledWith('user')
  const popover = findAll(current.tree, (node) => node.props.open === true)[0]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(current.onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  const noMatch = render({ assignments: [assignment] }, { variableSearch: 'missing', openVariablePopover: 'source-var-one' })
  expect(findAll(noMatch.tree, (node) => node.props.children === 'configCommon.noMatchingVariables').length).toBeGreaterThan(0)
})
