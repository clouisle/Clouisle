import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const setOpen = mock(() => {})

mock.module('react', () => ({
  useState: (value: unknown) => [value, setOpen],
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, ChevronDown: component, ChevronRight: component }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/input', () => ({ Input: component }))
mock.module('@/components/ui/select', () => ({ Select: component, SelectContent: component, SelectItem: component, SelectTrigger: component, SelectValue: component }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { TypeSpecEditor } = await import('./type-spec-editor')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function expand(node: unknown): unknown {
  if (!node || typeof node !== 'object' || !('props' in node)) return node
  const current = node as TreeNode
  return typeof current.type === 'function' && current.type !== component ? expand(current.type(current.props)) : current
}

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  const expanded = expand(node)
  if (!expanded || typeof expanded !== 'object' || !('props' in expanded)) return []
  const current = expanded as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('selects kinds and edits nested array items', () => {
  const onChange = mock(() => {})
  const tree = TypeSpecEditor({ value: { kind: 'array', item: { kind: 'string' } }, onChange }) as TreeNode
  const selects = findAll(tree, (node) => node.type === component && node.props.onValueChange)

  expect(selects).toHaveLength(2)
  ;(selects[0].props.onValueChange as (value: string) => void)('number')
  expect(onChange).toHaveBeenCalledWith({ kind: 'number' })
  ;(selects[1].props.onValueChange as (value: string) => void)('boolean')
  expect(onChange).toHaveBeenCalledWith({ kind: 'array', item: { kind: 'boolean' } })
  expect(findAll(tree, (node) => node.props.children === 'configCode.itemType')).toHaveLength(1)
})

test('adds, renames, updates, and removes object fields', () => {
  const onChange = mock(() => {})
  const tree = TypeSpecEditor({ value: { kind: 'object', fields: { field: { kind: 'string' }, field2: { kind: 'number' } } }, onChange, lockKind: true }) as TreeNode
  const buttons = findAll(tree, (node) => node.type === component && node.props.onClick)
  const inputs = findAll(tree, (node) => node.type === component && node.props.onBlur)
  const selects = findAll(tree, (node) => node.type === component && node.props.onValueChange)
  const toggle = findAll(tree, (node) => node.type === 'button' && node.props.onClick)[0]

  ;(toggle.props.onClick as () => void)()
  expect(setOpen).toHaveBeenCalled()
  ;(buttons[0].props.onClick as () => void)()
  expect(onChange).toHaveBeenCalledWith({ kind: 'object', fields: { field: { kind: 'string' }, field2: { kind: 'number' }, field3: { kind: 'string' } } })

  ;(inputs[0].props.onBlur as (event: { target: { value: string } }) => void)({ target: { value: 'renamed' } })
  expect(onChange).toHaveBeenCalledWith({ kind: 'object', fields: { renamed: { kind: 'string' }, field2: { kind: 'number' } } })
  ;(selects[0].props.onValueChange as (value: string) => void)('boolean')
  expect(onChange).toHaveBeenCalledWith({ kind: 'object', fields: { field: { kind: 'boolean' }, field2: { kind: 'number' } } })
  ;(buttons[1].props.onClick as () => void)()
  expect(onChange).toHaveBeenCalledWith({ kind: 'object', fields: { field2: { kind: 'number' } } })
})

test('defaults to any and clears the final object field', () => {
  const defaultTree = TypeSpecEditor({ value: undefined, onChange: () => {} }) as TreeNode
  expect(findAll(defaultTree, (node) => node.type === component && node.props.onValueChange && node.props.value === 'any').length).toBeGreaterThan(0)

  const onChange = mock(() => {})
  const objectTree = TypeSpecEditor({ value: { kind: 'object', fields: { only: { kind: 'string' } } }, onChange, lockKind: true }) as TreeNode
  const remove = findAll(objectTree, (node) => node.type === component && node.props.className?.toString().includes('text-destructive'))[0]
  ;(remove.props.onClick as () => void)()
  expect(onChange).toHaveBeenCalledWith({ kind: 'object', fields: undefined })
})
