import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'
import type { VariableDefinition } from '@/lib/api'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})

let state: unknown[] = []
let refs: Array<{ current: unknown }> = []
let dependencies: unknown[][] = []
let hookIndex = 0

mock.module('react', () => ({
  createElement: jsx,
  Fragment: Symbol.for('react.fragment'),
  useState: <T,>(initial: T) => {
    const index = hookIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
  useRef: <T,>(initial: T) => {
    const index = hookIndex++
    return (refs[index] ??= { current: initial }) as { current: T }
  },
  useEffect: (effect: () => void, nextDependencies: unknown[]) => {
    const index = hookIndex++
    const previous = dependencies[index]
    dependencies[index] = nextDependencies
    if (!previous || nextDependencies.some((value, dependencyIndex) => value !== previous[dependencyIndex])) effect()
  },
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => true }),
}))
mock.module('lucide-react', () => ({
  Type: element('svg'),
  AlignLeft: element('svg'),
  ChevronDown: element('svg'),
  Hash: element('svg'),
  CheckSquare: element('svg'),
  Trash2: element('svg'),
  Plus: element('svg'),
  Pencil: element('svg'),
  X: element('svg'),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('checkbox') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('badge') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: element('dialog'),
  DialogContent: element('dialog-content'),
  DialogHeader: element('dialog-header'),
  DialogTitle: element('dialog-title'),
  DialogFooter: element('dialog-footer'),
}))
mock.module('@/components/ui/popover', () => ({
  Popover: element('popover'),
  PopoverContent: element('popover-content'),
  PopoverTrigger: element('popover-trigger'),
}))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: element('select-content'),
  SelectItem: element('option'),
  SelectTrigger: element('select-trigger'),
  SelectValue: element('select-value'),
}))

const { AddVariableButton, VariableEditor, createNewVariable } = await import('./variable-editor')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): ReactNode {
  if (Array.isArray(node)) return node.map(resolve)
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  if (typeof tree.type === 'function') return resolve(tree.type(tree.props))
  return { ...tree, props: { ...tree.props, children: resolve(tree.props.children as ReactNode) } } as ReactNode
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('type' in node)) return []
  const tree = node as Tree
  return [
    ...(predicate(tree) ? [tree] : []),
    ...findAll(tree.props.children as ReactNode, predicate),
  ]
}

function text(node: ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as Tree).props.children as ReactNode)
  return ''
}

function renderEditor(props: Parameters<typeof VariableEditor>[0]) {
  hookIndex = 0
  return resolve(VariableEditor(props))
}

const variables: VariableDefinition[] = [
  createNewVariable('text', []),
  { ...createNewVariable('number', []), name: 'count', label: 'Count', required: true },
]

beforeEach(() => {
  state = []
  refs = []
  dependencies = []
})

describe('variable editor', () => {
  test('creates collision-free defaults and dispatches the selected add type', () => {
    const existing = [
      { ...createNewVariable('text', []), name: 'var' },
      { ...createNewVariable('text', []), name: 'var_1' },
      { ...createNewVariable('text', []), name: 'var_3' },
    ]

    expect(createNewVariable('checkbox', existing)).toMatchObject({
      name: 'var_2',
      default: 'false',
      required: false,
      hidden: false,
    })
    expect(createNewVariable('select', existing, ['one', 'two']).options).toEqual(['one', 'two'])

    hookIndex = 0
    const onAdd = mock(() => {})
    const tree = resolve(AddVariableButton({ onAdd }))
    const selectType = findAll(tree, (node) => node.type === 'button' && text(node as ReactNode) === 'types.select')[0]
    ;(selectType.props.onClick as () => void)()
    expect(onAdd).toHaveBeenCalledWith('select')
  })

  test('renders empty state and edits a variable with normalized boundary values', () => {
    expect(text(renderEditor({ variables: [], onChange: () => {} }))).toBe('empty')

    const onChange = mock(() => {})
    const onEditingIndexChange = mock(() => {})
    const props = { variables, onChange, editingIndex: 0, onEditingIndexChange }
    let tree = renderEditor(props)
    const name = findAll(tree, (node) => node.props.placeholder === 'dialog.variableNamePlaceholder')[0]
    ;(name.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'user full\tname' } })

    tree = renderEditor(props)
    const maxLength = findAll(tree, (node) => node.props.placeholder === 'dialog.unlimited')[0]
    ;(maxLength.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '0' } })

    tree = renderEditor(props)
    const save = findAll(tree, (node) => node.type === 'button' && text(node as ReactNode) === 'dialog.save')[0]
    ;(save.props.onClick as () => void)()

    expect(onChange).toHaveBeenCalledWith([
      { ...variables[0], name: 'user_full_name', maxLength: 0 },
      variables[1],
    ])
    expect(variables[0].name).toBe('var')
    expect(onEditingIndexChange).toHaveBeenCalledWith(null)
  })

  test('deletes immutably and removes an unsaved new variable when its dialog closes', () => {
    const onChange = mock(() => {})
    const onEditingIndexChange = mock(() => {})
    let tree = renderEditor({ variables, onChange, editingIndex: null, onEditingIndexChange })
    const actionButtons = findAll(tree, (node) => node.type === 'button' && node.props.size === 'icon')
    ;(actionButtons[3].props.onClick as (event: { stopPropagation(): void }) => void)({ stopPropagation() {} })
    expect(onChange).toHaveBeenCalledWith([variables[0]])
    expect(variables).toHaveLength(2)

    onChange.mockClear()
    tree = renderEditor({ variables, onChange, editingIndex: 1, onEditingIndexChange, isNewVariable: true })
    const dialog = findAll(tree, (node) => node.type === 'dialog')[0]
    ;(dialog.props.onOpenChange as (open: boolean) => void)(false)
    expect(onChange).toHaveBeenCalledWith([variables[0]])
    expect(onEditingIndexChange).toHaveBeenCalledWith(null)
  })
})
