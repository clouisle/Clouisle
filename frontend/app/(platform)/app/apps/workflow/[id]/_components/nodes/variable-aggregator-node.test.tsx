import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.n}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Combine: element, Home: element, Braces: element, List: element, Link: element, Merge: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { VariableAggregatorNode, getAggregationModeConfig } = await import('./variable-aggregator-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected object aggregation with mapped variables and handles', () => {
  const tree = VariableAggregatorNode({
    id: 'aggregate', selected: true,
    data: {
      type: 'variable_aggregator', label: 'Build payload', config: {},
      variableAggregatorConfig: {
        mode: 'object', outputVariable: 'result',
        variables: [
          { id: 'one', sourceVariable: '{{first.name}}', sourceNodeLabel: 'First', targetKey: 'name' },
          { id: 'two', sourceVariable: '{{second.age}}', sourceNodeLabel: 'Second', targetKey: 'age' },
          { id: 'three', sourceVariable: 'plain', targetKey: 'raw' },
          { id: 'four', sourceVariable: '{{fourth.hidden}}', targetKey: 'hidden' },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'name')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'plain')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'hidden')).toHaveLength(0)
  expect(findAll(tree, (node) => node.props.children === 'nodesCommon.unknown')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAggregator.moreVariables:1')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses localized mode metadata and the default configuration prompt', () => {
  const t = (key: string) => `translated:${key}`
  const modes = getAggregationModeConfig(t)
  const tree = VariableAggregatorNode({ id: 'aggregate', data: { type: 'variable_aggregator', label: '', config: {} } }) as TreeNode

  expect(modes.array.label).toBe('translated:nodesVariableAggregator.modeArray')
  expect(modes.concat.outputType).toBe('String')
  expect(modes.merge.description).toBe('translated:nodesVariableAggregator.modeMergeDesc')
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAggregator.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAggregator.modeObject')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAggregator.clickToConfigure')).toHaveLength(1)
})
