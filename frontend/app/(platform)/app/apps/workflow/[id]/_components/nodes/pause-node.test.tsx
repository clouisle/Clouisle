import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.count}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ CirclePause: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { PauseNode } = await import('./pause-node')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected variable pause with count and handles', () => {
  const tree = PauseNode({
    selected: true,
    data: {
      type: 'pause', label: 'Budget review', config: {},
      pauseConfig: {
        mode: 'variables', title: '', inputVariables: [
          { id: 'price', name: 'price', type: 'number', required: true, defaultValue: '' },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-amber-500')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Budget review')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesPause.variableCount:1')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses the approval summary and localized fallback label', () => {
  const tree = PauseNode({
    data: { type: 'pause', label: '', config: {}, pauseConfig: { mode: 'approval', title: '', inputVariables: [] } },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesPause.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesPause.approval')).toHaveLength(1)
})
