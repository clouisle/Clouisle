import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
type Setter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Props | null = {}) => ({ type, props: props ?? {} })
const icon = (name: string) => (props: Props) => jsx(name, props)
const states: unknown[] = []
const refs: Array<{ current: unknown }> = []
const effects: Array<() => void> = []
let stateIndex = 0
let refIndex = 0

function setState<T>(index: number, value: T | ((current: T) => T)) {
  states[index] = typeof value === 'function'
    ? (value as (current: T) => T)(states[index] as T)
    : value
}

function resolve(node: unknown): unknown {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const element = node as Node
  return typeof element.type === 'function'
    ? resolve((element.type as (props: Props) => unknown)(element.props))
    : element
}

function walk(node: unknown): Node[] {
  const resolved = resolve(node)
  if (Array.isArray(resolved)) return resolved.flatMap(walk)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const element = resolved as Node
  return [element, ...walk(element.props.children)]
}

function text(node: unknown): string {
  const resolved = resolve(node)
  if (typeof resolved === 'string' || typeof resolved === 'number') return String(resolved)
  if (Array.isArray(resolved)) return resolved.map(text).join('')
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return ''
  return text((resolved as Node).props.children)
}

const component = (name: string) => (props: Props) => jsx(name, props)
const Button = component('button')
const Input = component('input')
const Checkbox = component('checkbox')
const Select = component('select')

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('fragment') }))
mock.module('react', () => ({
  createElement: jsx,
  useEffect: (effect: () => void) => effects.push(effect),
  useRef: <T,>(initial: T) => {
    const index = refIndex++
    refs[index] ??= { current: initial }
    return refs[index]
  },
  useState: <T,>(initial: T): [T, Setter<T>] => {
    const index = stateIndex++
    if (states[index] === undefined) states[index] = initial
    return [states[index] as T, (value) => setState(index, value)]
  },
}))
mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string, values?: { index?: number }) => values?.index ? `${key}:${values.index}` : key,
    { has: (key: string) => key !== 'types.unknown' },
  ),
}))
mock.module('lucide-react', () => ({
  Type: icon('Type'), AlignLeft: icon('AlignLeft'), ChevronDown: icon('ChevronDown'),
  Hash: icon('Hash'), CheckSquare: icon('CheckSquare'), Trash2: icon('Trash2'),
  Plus: icon('Plus'), Pencil: icon('Pencil'), X: icon('X'),
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/label', () => ({ Label: component('label') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox }))
mock.module('@/components/ui/badge', () => ({ Badge: component('badge') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: component('dialog'), DialogContent: component('dialog-content'),
  DialogHeader: component('dialog-header'), DialogTitle: component('dialog-title'),
  DialogFooter: component('dialog-footer'),
}))
mock.module('@/components/ui/popover', () => ({
  Popover: component('popover'), PopoverContent: component('popover-content'),
  PopoverTrigger: component('popover-trigger'),
}))
mock.module('@/components/ui/select', () => ({
  Select, SelectContent: component('select-content'), SelectItem: component('select-item'),
  SelectTrigger: component('select-trigger'), SelectValue: component('select-value'),
}))

const { AddVariableButton, VariableEditor, createNewVariable } = await import('./variable-editor')

const baseVariable = {
  name: 'topic', type: 'text' as const, label: 'Topic', required: true, hidden: false,
  default: null, description: null, options: null, maxLength: null,
}

function renderEditor(props: Props) {
  stateIndex = 0
  refIndex = 0
  effects.length = 0
  return VariableEditor(props as Parameters<typeof VariableEditor>[0])
}

function find(tree: unknown, type: string, childText?: string) {
  return walk(tree).find((node) => node.type === type && (!childText || text(node).includes(childText)))
}

beforeEach(() => {
  states.length = 0
  refs.length = 0
  effects.length = 0
  stateIndex = 0
  refIndex = 0
})

test('creates collision-free defaults for checkbox and select variables', () => {
  expect(createNewVariable('checkbox', [baseVariable, { ...baseVariable, name: 'var' }])).toMatchObject({
    name: 'var_1', default: 'false', options: null,
  })
  expect(createNewVariable('select', [{ ...baseVariable, name: 'var' }, { ...baseVariable, name: 'var_1' }], ['A'])).toMatchObject({
    name: 'var_2', default: null, options: ['A'],
  })
})

test('add button reports the selected type and closes its popover', () => {
  const onAdd = mock(() => {})
  const tree = AddVariableButton({ onAdd })
  const popover = find(tree, 'popover')
  ;(popover?.props.onOpenChange as (open: boolean) => void)(true)
  const numberButton = walk(tree).find((node) => node.type === 'button' && text(node).includes('types.number'))
  ;(numberButton?.props.onClick as () => void)()

  expect(onAdd).toHaveBeenCalledWith('number')
  expect(states[0]).toBe(false)
})

test('renders empty state and delegates item hover, edit, and delete callbacks', () => {
  expect(text(renderEditor({ variables: [], onChange: mock(() => {}) }))).toContain('empty')

  const onChange = mock(() => {})
  const onEditingIndexChange = mock(() => {})
  const tree = renderEditor({ variables: [baseVariable], onChange, onEditingIndexChange })
  const buttons = walk(tree).filter((node) => node.type === 'button')
  const stopPropagation = mock(() => {})
  const edit = buttons.find((button) => walk(button).some((node) => node.type === 'Pencil'))
  const remove = buttons.find((button) => walk(button).some((node) => node.type === 'Trash2'))

  ;(remove?.props.onMouseEnter as () => void)()
  expect(states[1]).toBe(true)
  ;(remove?.props.onMouseLeave as () => void)()
  ;(edit?.props.onClick as (event: Props) => void)({ stopPropagation })
  ;(remove?.props.onClick as (event: Props) => void)({ stopPropagation })

  expect(stopPropagation).toHaveBeenCalledTimes(2)
  expect(onEditingIndexChange).toHaveBeenCalledWith(0)
  expect(onChange).toHaveBeenCalledWith([])
})

test('edits fields and saves the updated variable', () => {
  const onChange = mock(() => {})
  const onEditingIndexChange = mock(() => {})
  const props = { variables: [baseVariable], onChange, editingIndex: 0, onEditingIndexChange }
  let tree = renderEditor(props)
  effects.forEach((effect) => effect())
  ;(walk(tree).filter((node) => node.type === 'input')[0].props.onChange as (event: Props) => void)({ target: { value: 'new topic' } })
  tree = renderEditor(props)
  ;(walk(tree).filter((node) => node.type === 'input')[1].props.onChange as (event: Props) => void)({ target: { value: '' } })
  tree = renderEditor(props)
  ;(walk(tree).filter((node) => node.type === 'input')[2].props.onChange as (event: Props) => void)({ target: { value: '24' } })
  tree = renderEditor(props)
  ;(walk(tree).filter((node) => node.type === 'checkbox')[0].props.onCheckedChange as (checked: boolean) => void)(false)
  tree = renderEditor(props)
  ;(walk(tree).filter((node) => node.type === 'checkbox')[1].props.onCheckedChange as (checked: boolean) => void)(true)
  tree = renderEditor(props)
  const save = find(tree, 'button', 'dialog.save')
  ;(save?.props.onClick as () => void)()

  expect(onChange).toHaveBeenCalledWith([expect.objectContaining({
    name: 'new_topic', label: null, maxLength: 24, required: false, hidden: true,
  })])
  expect(onEditingIndexChange).toHaveBeenCalledWith(null)
  expect(refs[0].current).toBe(true)
})

test('covers select option callbacks and checkbox defaults', () => {
  const onChange = mock(() => {})
  const setEditing = mock(() => {})
  const selectVariable = { ...baseVariable, type: 'select' as const, options: ['A', 'B'], default: 'A' }
  let tree = renderEditor({ variables: [selectVariable], onChange, editingIndex: 0, onEditingIndexChange: setEditing })
  const optionInputs = walk(tree).filter((node) => node.type === 'input').slice(2)
  ;(optionInputs[0].props.onChange as (event: Props) => void)({ target: { value: 'Alpha' } })
  const removeOption = walk(tree).find((node) => node.type === 'button' && walk(node).some((child) => child.type === 'X'))
  ;(removeOption?.props.onClick as () => void)()
  const addOption = find(tree, 'button', 'dialog.addOption')
  ;(addOption?.props.onClick as () => void)()
  tree = renderEditor({ variables: [selectVariable], onChange, editingIndex: 0, onEditingIndexChange: setEditing })
  const select = walk(tree).find((node) => node.type === 'select' && typeof node.props.onValueChange === 'function')
  ;(select?.props.onValueChange as (value: string) => void)('B')

  states.length = 0
  const checkboxVariable = { ...baseVariable, type: 'checkbox' as const, default: 'false' }
  tree = renderEditor({ variables: [checkboxVariable], onChange, editingIndex: 0, onEditingIndexChange: setEditing })
  const defaultCheckbox = walk(tree).find((node) => node.type === 'checkbox')
  ;(defaultCheckbox?.props.onCheckedChange as (checked: boolean) => void)(true)

  expect((states[2] as typeof checkboxVariable).default).toBe('true')
})

test('discarding an unsaved new variable removes it through cancel and dialog close', () => {
  const onChange = mock(() => {})
  const setEditing = mock(() => {})
  let tree = renderEditor({
    variables: [baseVariable], onChange, editingIndex: 0,
    onEditingIndexChange: setEditing, isNewVariable: true,
  })
  ;(find(tree, 'button', 'dialog.cancel')?.props.onClick as () => void)()
  expect(onChange).toHaveBeenCalledWith([])
  expect(setEditing).toHaveBeenCalledWith(null)

  onChange.mockClear()
  tree = renderEditor({
    variables: [baseVariable], onChange, editingIndex: 0,
    onEditingIndexChange: setEditing, isNewVariable: true,
  })
  const dialog = find(tree, 'dialog')
  ;(dialog?.props.onOpenChange as (open: boolean) => void)(true)
  expect(onChange).not.toHaveBeenCalled()
  ;(dialog?.props.onOpenChange as (open: boolean) => void)(false)
  expect(onChange).toHaveBeenCalledWith([])
})
