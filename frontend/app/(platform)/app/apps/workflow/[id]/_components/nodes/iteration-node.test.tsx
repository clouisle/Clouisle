import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, NodeResizeControl: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ RefreshCw: element, LogOut: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { IterationNode, IterationStartNode, IterationExitNode } = await import('./iteration-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}

test('renders selected parallel iteration with configured dimensions and completion handle', () => {
  const tree = IterationNode({
    id: 'iteration', selected: true, width: 640, height: 360,
    data: {
      type: 'iteration', label: 'Each item', config: {},
      iterationConfig: {
        iteratorVariable: '{{input.items}}', iteratorType: 'array', itemVariable: 'item', indexVariable: 'index',
        keyVariable: 'key', valueVariable: 'value', parallel: true, maxParallel: 3, outputVariable: 'processed',
      },
    },
  }) as TreeNode

  expect(tree.props.style).toEqual({ width: 640, height: 360 })
  expect(tree.props.className).toContain('border-primary')
  expect(findAll(tree, (node) => Array.isArray(node.props.children) && node.props.children.join('') === 'processed[]')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node.props.children) === 'nodesIteration.parallel ×3')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.id).toBe('done')
})

test('renders default container and array/object iteration endpoints', () => {
  const container = IterationNode({ id: 'iteration', data: { type: 'iteration', label: '', config: {} } }) as TreeNode
  const arrayStart = IterationStartNode({ id: 'start', data: { type: 'iteration_start', label: '', parentIterationId: 'iteration', config: {} } }) as TreeNode
  const objectStart = IterationStartNode({
    id: 'start', selected: true,
    data: { type: 'iteration_start', label: '', parentIterationId: 'iteration', config: {}, iterationConfig: {
      iteratorVariable: '', iteratorType: 'object', itemVariable: 'item', indexVariable: 'index', keyVariable: 'field', valueVariable: 'content', parallel: false, outputVariable: 'results',
    } },
  }) as TreeNode
  const exit = IterationExitNode({ id: 'exit', selected: false, data: { type: 'iteration_exit', label: '', parentIterationId: 'iteration', config: {} } }) as TreeNode

  expect(container.props.style).toEqual({ width: 500, height: 280 })
  expect(findAll(container, (node) => Array.isArray(node.props.children) && node.props.children.join('') === 'results[]')).toHaveLength(1)
  expect(findAll(arrayStart, (node) => text(node.props.children) === 'item, index').length).toBeGreaterThan(0)
  expect(findAll(objectStart, (node) => text(node.props.children) === 'field, content').length).toBeGreaterThan(0)
  expect(findAll(exit, (node) => node.props.children === 'nodesCommon.exitLoop')).toHaveLength(1)
  expect(findAll(exit, (node) => node.props.type === 'target')[0].props.position).toBe('left')
})
