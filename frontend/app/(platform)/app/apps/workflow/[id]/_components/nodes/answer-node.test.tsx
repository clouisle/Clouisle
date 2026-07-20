import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.n}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ MessageSquareText: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { AnswerNode } = await import('./answer-node')

function findAll(node: unknown, predicate: (node: { props: Record<string, unknown> }) => boolean): Array<{ props: Record<string, unknown> }> {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as { props: Record<string, unknown> }
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected answer outputs, limits the list, and exposes both handles', () => {
  const tree = AnswerNode({
    selected: true,
    data: {
      type: 'answer', label: 'Answer', config: {},
      answerConfig: { outputs: [
        { id: '1', sourceVariable: '{{writer.first}}' },
        { id: '2', sourceVariable: '{{writer.second}}', sourceVariableName: 'Named' },
        { id: '3', sourceVariable: '{{writer.third}}' },
        { id: '4', sourceVariable: '{{writer.fourth}}' },
        { id: '5', sourceVariable: '{{writer.fifth}}' },
      ] },
    },
  }) as { props: Record<string, unknown> }

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'first')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Named')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'fifth')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.children === 'nodesAnswer.outputCount:1')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('renders the configuration prompt for an answer node without outputs', () => {
  const tree = AnswerNode({ id: 'answer', data: { type: 'answer', label: '', config: {} } }) as { props: Record<string, unknown> }

  expect(findAll(tree, (node) => node.props.children === 'nodesAnswer.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesAnswer.clickToConfigure')).toHaveLength(1)
})
