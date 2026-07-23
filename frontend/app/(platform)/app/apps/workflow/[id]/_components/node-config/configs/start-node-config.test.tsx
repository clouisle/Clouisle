import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
mock.module('react', () => ({ default: {} }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Pencil: component, Trash2: component }))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/label', () => ({ Label: component }))
mock.module('../constants', () => ({
  systemParameters: [{ id: 'sys_user_id', name: 'sys_user_id', valueType: 'String' }],
  parameterTypeConfig: { text: { icon: component, valueType: 'string' } },
}))

const { StartNodeConfig } = await import('./start-node-config')
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

 test('shows system and empty input states and adds a parameter', () => {
  const onAddParameter = mock(() => {})
  const tree = StartNodeConfig({ parameters: [], onAddParameter, onEditParameter: mock(() => {}), onRemoveParameter: mock(() => {}) }) as TreeNode
  expect(findAll(tree, (node) => text(node) === 'Ssys_user_id')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'String')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configStart.noParameters')).toHaveLength(1)
  const add = findAll(tree, (node) => node.type === component && node.props.size === 'sm')[0]
  ;(add.props.onClick as () => void)()
  expect(onAddParameter).toHaveBeenCalledTimes(1)
})

test('edits and removes named, required, and fallback-type parameters', () => {
  const onEditParameter = mock(() => {}), onRemoveParameter = mock(() => {})
  const named = { id: 'name', name: 'Name', type: 'text' as const, required: true }
  const unnamed = { id: 'other', name: '', type: 'unknown' as 'text', required: false }
  const tree = StartNodeConfig({ parameters: [named, unnamed], onAddParameter: mock(() => {}), onEditParameter, onRemoveParameter }) as TreeNode
  expect(findAll(tree, (node) => node.props.children === 'Name')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.unnamed')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.required')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'string')).toHaveLength(2)

  const rows = findAll(tree, (node) => node.type === 'div' && String(node.props.className).includes('cursor-pointer'))
  ;(rows[0].props.onClick as () => void)()
  expect(onEditParameter).toHaveBeenCalledWith(named)

  const actions = findAll(tree, (node) => node.type === component && node.props.size === 'icon')
  const stopPropagation = mock(() => {})
  ;(actions[0].props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation })
  expect(onEditParameter).toHaveBeenLastCalledWith(named)
  ;(actions[1].props.onClick as (event: { stopPropagation: () => void }) => void)({ stopPropagation })
  expect(onRemoveParameter).toHaveBeenCalledWith('name')
  expect(stopPropagation).toHaveBeenCalledTimes(2)
})
