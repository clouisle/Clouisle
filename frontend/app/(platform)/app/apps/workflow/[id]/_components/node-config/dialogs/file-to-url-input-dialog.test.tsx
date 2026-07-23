import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
let form: Record<string, unknown> = {}
const setForm = mock((next: Record<string, unknown>) => { form = next })

mock.module('react', () => ({ useState: () => [form, setForm], useEffect: (effect: () => void) => effect() }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Search: component, File: component, Image: component, Files: component, Images: component }))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/input', () => ({ Input: component }))
mock.module('@/components/ui/label', () => ({ Label: component }))
mock.module('@/components/ui/dialog', () => ({ Dialog: component, DialogContent: component, DialogHeader: component, DialogTitle: component, DialogFooter: component }))
mock.module('@/components/ui/popover', () => ({ Popover: component, PopoverContent: component, PopoverTrigger: component }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: component }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { FileToUrlInputDialog } = await import('./file-to-url-input-dialog')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

const variables = [
  { id: 'input.photo', name: 'input.photo', type: 'image', group: 'input', groupLabel: 'Input', isSystem: false },
  { id: 'system.files', name: 'files', type: 'files', group: 'system', groupLabel: 'System', isSystem: true },
]

function render(overrides: Record<string, unknown> = {}) {
  const onOpenChange = mock(() => {})
  const onVariableSearchChange = mock(() => {})
  const onOpenVariablePopoverChange = mock(() => {})
  const onSave = mock(() => {})
  const tree = FileToUrlInputDialog({ open: true, onOpenChange, editingInput: null, existingInputs: [], variables, variableSearch: '', openVariablePopover: 'file-to-url-source', onVariableSearchChange, onOpenVariablePopoverChange, onSave, ...overrides }) as TreeNode
  return { tree, onOpenChange, onVariableSearchChange, onOpenVariablePopoverChange, onSave }
}

test('selects file variables and infers output names and types', () => {
  form = { name: '', sourceVariable: '', sourceType: 'file' }
  const { tree, onVariableSearchChange, onOpenVariablePopoverChange } = render()
  const buttons = findAll(tree, (node) => node.type === 'button')

  ;(buttons[0].props.onClick as () => void)()
  expect(setForm).toHaveBeenCalledWith({ name: 'photo_url', sourceVariable: '{{input.photo}}', sourceType: 'image' })
  ;(buttons[1].props.onClick as () => void)()
  expect(setForm).toHaveBeenCalledWith({ name: 'files_url', sourceVariable: '{{files}}', sourceType: 'files' })
  expect(onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
  expect(onVariableSearchChange).toHaveBeenCalledWith('')

  const search = findAll(tree, (node) => node.type === component && node.props.placeholder === 'dialogs.fileToUrlInput.searchPlaceholder')[0]
  ;(search.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'photo' } })
  expect(onVariableSearchChange).toHaveBeenCalledWith('photo')
})

test('saves an edited input and preserves its id', () => {
  form = { name: ' image_url ', sourceVariable: '{{input.photo}}', sourceType: 'image' }
  const editingInput = { id: 'existing', name: 'old', sourceVariable: '{{old}}', sourceType: 'file' as const }
  const { tree, onSave, onOpenChange } = render({ editingInput })
  const save = findAll(tree, (node) => node.type === component && node.props.children === 'dialogs.fileToUrlInput.save')[0]

  ;(save.props.onClick as () => void)()
  expect(onSave).toHaveBeenCalledWith({ id: 'existing', name: 'image_url', sourceVariable: '{{input.photo}}', sourceType: 'image' })
  expect(onOpenChange).toHaveBeenCalledWith(false)
})

test('shows invalid, duplicate, no-variable, and no-match states', () => {
  form = { name: 'bad name', sourceVariable: '{{input.photo}}' }
  const invalid = render().tree
  expect(findAll(invalid, (node) => node.props.children === 'dialogs.fileToUrlInput.nameFormatError')).toHaveLength(1)

  form = { name: 'taken', sourceVariable: '{{input.photo}}' }
  const duplicate = render({ existingInputs: [{ id: 'other', name: 'taken', sourceVariable: '{{x}}', sourceType: 'file' }] })
  expect(findAll(duplicate.tree, (node) => node.props.children === 'dialogs.fileToUrlInput.nameDuplicate')).toHaveLength(1)
  const save = findAll(duplicate.tree, (node) => node.type === component && node.props.children === 'dialogs.fileToUrlInput.add')[0]
  expect(save.props.disabled).toBe(true)

  form = { name: '', sourceVariable: '' }
  expect(findAll(render({ variables: [] }).tree, (node) => node.props.children === 'dialogs.fileToUrlInput.noFileVarsAvailable')).toHaveLength(1)
  expect(findAll(render({ variableSearch: 'missing' }).tree, (node) => node.props.children === 'dialogs.fileToUrlInput.noMatch')).toHaveLength(1)
})
