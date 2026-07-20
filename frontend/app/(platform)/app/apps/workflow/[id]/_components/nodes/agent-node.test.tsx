import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Bot: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { AgentNode } = await import('./agent-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected configured agent with input and output handles', () => {
  const tree = AgentNode({
    id: 'agent', selected: true,
    data: {
      type: 'agent', label: 'Research assistant', config: {},
      agentConfig: {
        agentId: 'agent-1', agentName: 'Researcher', inputVariable: '{{input.query}}', outputVariable: 'result',
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Research assistant')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Researcher')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses localized labels and warning without a selected agent', () => {
  const tree = AgentNode({ id: 'agent', data: { type: 'agent', label: '', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesAgent.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesAgent.notSelected')).toHaveLength(1)
})
