import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
const translate = Object.assign((key: string) => `memories.${key}`, { has: (key: string) => key.endsWith('.person') || key.endsWith('.knows') })
mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: component }))
mock.module('@/components/ui/separator', () => ({ Separator: component }))

const { GraphFilters } = await import('./graph-filters')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('labels filters and adds or removes entity and relation types', () => {
  const onEntityTypeFilterChange = mock(() => {})
  const onRelationTypeFilterChange = mock(() => {})
  const tree = GraphFilters({
    availableEntityTypes: ['person', 'custom'],
    availableRelationTypes: ['knows', 'related'],
    entityTypeFilter: ['person'],
    onEntityTypeFilterChange,
    relationTypeFilter: ['knows'],
    onRelationTypeFilterChange,
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'memories.entityTypes.person')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'custom')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'memories.relationTypes.knows')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'related')).toHaveLength(1)
  const checkboxes = findAll(tree, (node) => typeof node.props.onCheckedChange === 'function')
  expect(checkboxes.map((node) => node.props.checked)).toEqual([true, false, true, false])
  ;(checkboxes[0].props.onCheckedChange as (checked: boolean) => void)(false)
  ;(checkboxes[1].props.onCheckedChange as (checked: boolean) => void)(true)
  ;(checkboxes[2].props.onCheckedChange as (checked: boolean) => void)(false)
  ;(checkboxes[3].props.onCheckedChange as (checked: boolean) => void)(true)
  expect(onEntityTypeFilterChange).toHaveBeenNthCalledWith(1, [])
  expect(onEntityTypeFilterChange).toHaveBeenNthCalledWith(2, ['person', 'custom'])
  expect(onRelationTypeFilterChange).toHaveBeenNthCalledWith(1, [])
  expect(onRelationTypeFilterChange).toHaveBeenNthCalledWith(2, ['knows', 'related'])
})
