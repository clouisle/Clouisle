import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Bottom: 'bottom' } }))
mock.module('lucide-react', () => ({ Play: element }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { StartNode } = await import('./start-node')

function find(node: unknown, predicate: (node: { props: Record<string, unknown> }) => boolean): { props: Record<string, unknown> } | undefined {
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined
  const current = node as { props: Record<string, unknown> }
  if (predicate(current)) return current
  return [current.props.children].flat().map((child) => find(child, predicate)).find(Boolean)
}

test('renders the selected start node with its output handle', () => {
  const tree = StartNode({ selected: true } as never) as { props: Record<string, unknown> }
  const handle = find(tree, (node) => node.props.type === 'source')

  expect(tree.props.className).toContain('ring-2')
  expect(handle?.props.position).toBe('bottom')
  expect(find(tree, (node) => node.props.children === 'nodesStart.label')).toBeDefined()
})

test('renders without a selection ring by default', () => {
  const tree = StartNode({ selected: false } as never) as { props: Record<string, unknown> }

  expect(tree.props.className).not.toContain('ring-2')
})
