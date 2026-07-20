import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Bot: element, Sparkles: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { LLMNode } = await import('./llm-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected configured model with handles', () => {
  const tree = LLMNode({
    id: 'llm', selected: true,
    data: {
      type: 'llm', label: 'Draft answer', config: {},
      llmConfig: { modelId: 'model-1', modelName: 'Claude Fable 5' },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Draft answer')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Claude Fable 5')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses default label and warns without a model', () => {
  const tree = LLMNode({ id: 'llm', data: { type: 'llm', label: '', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'LLM')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesCommon.modelNotSelected')).toHaveLength(1)
})
