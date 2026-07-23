import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${Object.values(values).join('/')}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' }, NodeResizeControl: element }))
mock.module('lucide-react', () => ({ Infinity: element, LogOut: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { LoopNode, LoopStartNode, LoopExitNode, defaultLoopConfig } = await import('./loop-node')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

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

test('renders selected loop dimensions, limits, output, and handles', () => {
  const tree = LoopNode({
    id: 'loop', selected: true, width: 640, height: 360,
    data: { type: 'loop', label: 'Retry tasks', config: {}, loopConfig: { ...defaultLoopConfig, maxIterations: 20, outputVariable: 'items' } },
  }) as TreeNode

  expect(tree.props.style).toEqual({ width: 640, height: 360 })
  expect(tree.props.className).toContain('border-primary')
  expect(findAll(tree, (node) => node.props.children === 'Retry tasks')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesLoop.maxIterations:20')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node) === 'items[]').length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.type === element && node.props.minWidth === 400)).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.style).toEqual({ top: '50%' })
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.id).toBe('done')
})

test('uses default loop sizing and labels', () => {
  const tree = LoopNode({ id: 'loop', data: { type: 'loop', label: '', config: {} } }) as TreeNode

  expect(defaultLoopConfig).toEqual({ maxIterations: 10, indexVariable: 'index', loopVariables: [], exitConditions: [], exitLogicOperator: 'and', outputVariable: 'results' })
  expect(tree.props.style).toEqual({ width: 500, height: 280 })
  expect(findAll(tree, (node) => node.props.children === 'nodesLoop.label')).toHaveLength(1)
})

test('renders loop start variables with truncation and defaults', () => {
  const configured = LoopStartNode({
    id: 'start', selected: true,
    data: { type: 'loop_start', label: '', parentLoopId: 'loop', config: {}, loopConfig: {
      ...defaultLoopConfig, indexVariable: 'position', loopVariables: [
        { id: 'one', name: 'total', type: 'number', defaultValue: '0' },
        { id: 'two', name: 'done', type: 'boolean', defaultValue: 'false' },
      ],
    } },
  }) as TreeNode
  const fallback = LoopStartNode({ id: 'start', data: { type: 'loop_start', label: '', parentLoopId: 'loop', config: {}, loopConfig: { ...defaultLoopConfig, indexVariable: '' } } }) as TreeNode

  expect(findAll(configured, (node) => node.props.children === 'position, total...')).toHaveLength(1)
  expect(findAll(configured, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(configured, (node) => node.props.type === 'source')[0].props.position).toBe('right')
  expect(findAll(fallback, (node) => node.props.children === 'index')).toHaveLength(1)
})

test('renders selected loop exit with localized label and input handle', () => {
  const tree = LoopExitNode({ id: 'exit', selected: true, data: { type: 'loop_exit', label: '', parentLoopId: 'loop', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'nodesCommon.exitLoop')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
})
