import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
let form: Record<string, unknown> = {}
const setForm = mock((next: Record<string, unknown>) => { form = next })

mock.module('react', () => ({
  useState: () => [form, setForm],
  useEffect: (effect: () => void) => effect(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Search: component }))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/input', () => ({ Input: component }))
mock.module('@/components/ui/label', () => ({ Label: component }))
mock.module('@/components/ui/dialog', () => ({ Dialog: component, DialogContent: component, DialogHeader: component, DialogTitle: component, DialogFooter: component }))
mock.module('@/components/ui/popover', () => ({ Popover: component, PopoverContent: component, PopoverTrigger: component }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: component }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { CodeInputDialog } = await import('./code-input-dialog')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

const variables = [
  { id: 'input.query', name: 'Query', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.user_id', name: 'User ID', type: 'string', group: 'system', groupLabel: 'System', isSystem: true },
]

function render(overrides: Record<string, unknown> = {}) {
  const onOpenChange = mock(() => {})
  const onVariableSearchChange = mock(() => {})
  const onOpenVariablePopoverChange = mock(() => {})
  const onSave = mock(() => {})
  const tree = CodeInputDialog({
    open: true,
    onOpenChange,
    editingInput: null,
    variables,
    variableSearch: '',
    openVariablePopover: 'code-input-value',
    onVariableSearchChange,
    onOpenVariablePopoverChange,
    onSave,
    ...overrides,
  }) as TreeNode
  return { tree, onOpenChange, onVariableSearchChange, onOpenVariablePopoverChange, onSave }
}

test('selects an upstream variable and searches grouped choices', () => {
  form = { name: 'query', value: '' }
  const { tree, onVariableSearchChange, onOpenVariablePopoverChange } = render()
  expect(findAll(tree, (node) => node.props.children === 'Input')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'System')).toHaveLength(1)

  const variableButton = findAll(tree, (node) => node.type === 'button' && findAll(node, (child) => child.props.children === 'Query').length > 0)[0]
  ;(variableButton.props.onClick as () => void)()
  expect(setForm).toHaveBeenCalledWith({ name: 'query', value: '{{input.query}}', valueSource: 'Input' })
  expect(onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(onVariableSearchChange).toHaveBeenCalledWith('')

  const searchInput = findAll(tree, (node) => node.type === component && node.props.placeholder === 'dialogs.codeInput.searchPlaceholder')[0]
  ;(searchInput.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'user' } })
  expect(onVariableSearchChange).toHaveBeenCalledWith('user')

  const popover = findAll(tree, (node) => node.type === component && node.props.open === true)[1]
  ;(popover.props.onOpenChange as (open: boolean) => void)(false)
  expect(onOpenVariablePopoverChange).toHaveBeenLastCalledWith(null)
})

test('saves a valid edit and closes the dialog', () => {
  form = { name: ' renamed ', value: '{{input.query}}', valueSource: 'Input' }
  const editingInput = { id: 'existing', name: 'old', value: '{{input.old}}' }
  const { tree, onSave, onOpenChange } = render({ editingInput, existingInputs: [{ id: 'other', name: 'taken', value: '{{x}}' }] })
  const save = findAll(tree, (node) => node.type === component && node.props.children === 'dialogs.codeInput.save')[0]

  ;(save.props.onClick as () => void)()
  expect(onSave).toHaveBeenCalledWith({ id: 'existing', name: 'renamed', value: '{{input.query}}', valueSource: 'Input' })
  expect(onOpenChange).toHaveBeenCalledWith(false)
})

test('shows invalid, duplicate, and no-match states without saving', () => {
  form = { name: 'bad name', value: '{{input.query}}' }
  const invalid = render().tree
  expect(findAll(invalid, (node) => node.props.children === 'dialogs.codeInput.nameFormatError')).toHaveLength(1)

  form = { name: 'taken', value: '{{input.query}}' }
  const duplicate = render({ existingInputs: [{ id: 'other', name: 'taken', value: '{{x}}' }] })
  expect(findAll(duplicate.tree, (node) => node.props.children === 'dialogs.codeInput.duplicateNameError')).toHaveLength(1)
  const disabledSave = findAll(duplicate.tree, (node) => node.type === component && node.props.children === 'dialogs.codeInput.add')[0]
  expect(disabledSave.props.disabled).toBe(true)
  ;(disabledSave.props.onClick as () => void)()
  expect(duplicate.onSave).not.toHaveBeenCalled()

  form = { name: '', value: '' }
  const empty = render({ variableSearch: 'missing' }).tree
  expect(findAll(empty, (node) => node.props.children === 'dialogs.codeInput.noMatch')).toHaveLength(1)
})
