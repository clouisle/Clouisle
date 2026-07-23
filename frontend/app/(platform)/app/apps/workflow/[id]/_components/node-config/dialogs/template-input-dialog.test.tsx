import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
let form: Record<string, unknown> = {}
const setForm = mock((next: Record<string, unknown>) => { form = next })

mock.module('react', () => ({ useState: () => [form, setForm], useEffect: (effect: () => void) => effect() }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Search: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogHeader', 'DialogTitle', 'DialogFooter']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']], ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { TemplateInputDialog } = await import('./template-input-dialog')
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
  const onOpenChange = mock(() => {}), onVariableSearchChange = mock(() => {}), onOpenVariablePopoverChange = mock(() => {}), onSave = mock(() => {})
  const tree = TemplateInputDialog({ open: true, onOpenChange, editingInput: null, variables, variableSearch: '', openVariablePopover: 'template-input-value', onVariableSearchChange, onOpenVariablePopoverChange, onSave, ...overrides }) as TreeNode
  return { tree, onOpenChange, onVariableSearchChange, onOpenVariablePopoverChange, onSave }
}

test('selects, searches, and resets grouped upstream variables', () => {
  form = { name: 'query', value: '' }
  const { tree, onVariableSearchChange, onOpenVariablePopoverChange } = render()
  expect(findAll(tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'System')).toHaveLength(1)
  const choice = findAll(tree, (node) => node.type === 'button')[0]
  ;(choice.props.onClick as () => void)()
  expect(setForm).toHaveBeenCalledWith({ name: 'query', value: '{{input.query}}', valueSource: 'Input' })
  expect(onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  const search = findAll(tree, (node) => node.type === component && node.props.placeholder === 'dialogs.templateInput.searchPlaceholder')[0]
  ;(search.props.onChange as (e: { target: { value: string } }) => void)({ target: { value: 'user' } })
  expect(onVariableSearchChange).toHaveBeenCalledWith('user')
  const popover = findAll(tree, (node) => node.type === component && node.props.open === true)[1]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(onVariableSearchChange).toHaveBeenLastCalledWith('')
})

test('saves a valid edit and rejects invalid or empty input', () => {
  form = { name: ' renamed ', value: '{{input.query}}', valueSource: 'Input' }
  const editingInput = { id: 'existing', name: 'old', value: '{{old}}' }
  const valid = render({ editingInput })
  const save = findAll(valid.tree, (node) => node.type === component && node.props.children === 'dialogs.templateInput.save')[0]
  ;(save.props.onClick as () => void)()
  expect(valid.onSave).toHaveBeenCalledWith({ id: 'existing', name: 'renamed', value: '{{input.query}}', valueSource: 'Input' })
  expect(valid.onOpenChange).toHaveBeenCalledWith(false)

  form = { name: 'bad name', value: '{{x}}' }
  const invalid = render()
  expect(findAll(invalid.tree, (node) => node.props.children === 'dialogs.templateInput.nameFormatError')).toHaveLength(1)
  const disabled = findAll(invalid.tree, (node) => node.type === component && node.props.children === 'dialogs.templateInput.add')[0]
  expect(disabled.props.disabled).toBe(true)

  form = { name: '', value: '' }
  expect(findAll(render({ variableSearch: 'missing' }).tree, (node) => node.props.children === 'dialogs.templateInput.noMatch')).toHaveLength(1)
})
