import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
let form: Record<string, unknown> = {}
const setForm = mock((next: Record<string, unknown>) => { form = next })

mock.module('react', () => ({ useState: () => [form, setForm], useEffect: (effect: () => void) => effect() }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  Plus: component, Trash2: component, Type: component, AlignLeft: component, ListChecks: component,
  Hash: component, CheckSquare: component, Brackets: component, Braces: component, File: component,
  Image: component, Files: component, Images: component,
}))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/textarea', ['Textarea']], ['@/components/ui/switch', ['Switch']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogHeader', 'DialogTitle', 'DialogFooter']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/constants', () => ({ GENERAL_UPLOAD_MAX_FILE_SIZE_MB: 20 }))

const { ParameterEditDialog } = await import('./parameter-edit-dialog')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
function render(overrides: Record<string, unknown> = {}) {
  const onOpenChange = mock(() => {}), onSave = mock(() => {})
  const tree = ParameterEditDialog({ open: true, onOpenChange, editingParam: null, existingParams: [], onSave, ...overrides }) as TreeNode
  return { tree, onOpenChange, onSave }
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })

 test('validates names, saves edits, and closes from either footer action', () => {
  form = { name: ' renamed ', type: 'text', required: true, defaultValue: 'hello', description: 'Greeting' }
  const editingParam = { id: 'existing', name: 'old', type: 'text', required: false }
  const valid = render({ editingParam, existingParams: [editingParam, { id: 'other', name: 'taken', type: 'text', required: false }] })
  const footerButtons = findAll(valid.tree, (node) => node.type === component && ['dialogs.parameterEdit.cancel', 'dialogs.parameterEdit.save'].includes(String(node.props.children)))
  ;(footerButtons[1].props.onClick as () => void)()
  expect(valid.onSave).toHaveBeenCalledWith({ id: 'existing', name: 'renamed', type: 'text', required: true, defaultValue: 'hello', description: 'Greeting', options: undefined, fileConfig: undefined })
  expect(valid.onOpenChange).toHaveBeenCalledWith(false)
  ;(footerButtons[0].props.onClick as () => void)()
  expect(valid.onOpenChange).toHaveBeenCalledTimes(2)

  form = { name: 'bad name', type: 'text' }
  expect(findAll(render().tree, (node) => node.props.children === 'dialogs.parameterEdit.nameFormatError')).toHaveLength(1)
  form = { name: 'TAKEN', type: 'text' }
  const duplicate = render({ existingParams: [{ id: 'other', name: 'taken', type: 'text', required: false }] }).tree
  expect(findAll(duplicate, (node) => node.props.children === 'dialogs.parameterEdit.nameDuplicate')).toHaveLength(1)
  expect(findAll(duplicate, (node) => node.props.children === 'dialogs.parameterEdit.add')[0].props.disabled).toBe(true)
})

test('updates scalar and structured defaults plus required metadata', () => {
  for (const [type, placeholder, value] of [
    ['text', 'dialogs.parameterEdit.defaultTextPlaceholder', 'plain'],
    ['paragraph', 'dialogs.parameterEdit.defaultParagraphPlaceholder', 'long'],
    ['number', 'dialogs.parameterEdit.defaultNumberPlaceholder', '42'],
    ['array', 'dialogs.parameterEdit.arrayExample', '[1]'],
    ['object', 'dialogs.parameterEdit.objectExample', '{}'],
  ]) {
    form = { name: 'value', type, defaultValue: '' }
    const input = findAll(render().tree, (node) => node.type === component && node.props.placeholder === placeholder)[0]
    change(input, value)
    expect(setForm).toHaveBeenCalledWith({ name: 'value', type, defaultValue: value })
  }

  form = { name: 'enabled', type: 'checkbox', defaultValue: 'false' }
  const checkbox = findAll(render().tree, (node) => node.type === component && node.props.id === 'param-default')[0]
  ;(checkbox.props.onCheckedChange as (checked: boolean) => void)(true)
  expect(setForm).toHaveBeenCalledWith({ name: 'enabled', type: 'checkbox', defaultValue: 'true' })

  form = { name: 'meta', type: 'text', required: false, description: '' }
  const metadata = render().tree
  change(findAll(metadata, (node) => node.props.id === 'param-desc')[0], 'Shown to users')
  ;(findAll(metadata, (node) => node.props.id === 'param-required')[0].props.onCheckedChange as (checked: boolean) => void)(true)
  expect(setForm).toHaveBeenCalledWith({ name: 'meta', type: 'text', required: true, description: '' })
})

test('edits select options and its default selection', () => {
  form = { name: 'choice', type: 'select', options: ['one', 'two'], defaultValue: 'one' }
  const tree = render().tree
  const option = findAll(tree, (node) => node.type === component && node.props.value === 'one' && node.props.onChange)[0]
  change(option, 'first')
  expect(setForm).toHaveBeenCalledWith({ name: 'choice', type: 'select', options: ['first', 'two'], defaultValue: 'one' })

  const iconButtons = findAll(tree, (node) => node.type === component && node.props.size === 'icon')
  ;(iconButtons[0].props.onClick as () => void)()
  expect(setForm).toHaveBeenCalledWith({ name: 'choice', type: 'select', options: ['two'], defaultValue: 'one' })
  const add = findAll(tree, (node) => node.type === component && node.props.className === 'w-full h-8 text-xs')[0]
  ;(add.props.onClick as () => void)()
  expect(setForm).toHaveBeenCalledWith({ name: 'choice', type: 'select', options: ['one', 'two', ''], defaultValue: 'one' })

  const defaultSelect = findAll(tree, (node) => node.type === component && node.props.value === 'one' && node.props.onValueChange)[0]
  ;(defaultSelect.props.onValueChange as (value: string | null) => void)(null)
  expect(setForm).toHaveBeenCalledWith({ name: 'choice', type: 'select', options: ['one', 'two'], defaultValue: undefined })
})

test('configures single and multiple file and image inputs', () => {
  for (const [type, numberValues, accept] of [
    ['image', ['12'], '.jpg, .png'],
    ['files', ['3', '18'], '.pdf, image/*'],
    ['images', ['6', '8'], '.jpg, .webp'],
  ] as const) {
    form = { name: 'upload', type, fileConfig: {} }
    const tree = render().tree
    const numbers = findAll(tree, (node) => node.type === component && node.props.type === 'number')
    numberValues.forEach((value, index) => change(numbers[index], value))
    const acceptInput = findAll(tree, (node) => node.type === component && typeof node.props.placeholder === 'string' && String(node.props.placeholder).startsWith('.'))[0]
    change(acceptInput, accept)
    expect(setForm).toHaveBeenCalledWith({ name: 'upload', type, fileConfig: { accept: accept.split(',').map((item) => item.trim()) } })
  }

  form = { name: 'upload', type: 'file', fileConfig: { maxSize: 5 } }
  const typeSelect = findAll(render().tree, (node) => node.type === component && node.props.value === 'file' && node.props.onValueChange)[0]
  ;(typeSelect.props.onValueChange as (value: string) => void)('images')
  expect(setForm).toHaveBeenCalledWith({ name: 'upload', type: 'images', fileConfig: undefined })
})
