import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react', () => ({ useRef: () => ({ current: [] }) }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ GitBranch: element, Home: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { ConditionNode, getConditionOperatorLabels, getConditionOperatorShortLabels } = await import('./condition-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('returns translated condition operator labels', () => {
  const t = (key: string) => `translated:${key}`

  expect(getConditionOperatorLabels(t).equals).toBe('translated:nodesCondition.operatorEquals')
  expect(getConditionOperatorShortLabels(t).is_empty).toBe('translated:nodesCondition.shortIsEmpty')
  expect(getConditionOperatorShortLabels(t).greater_or_equal).toBe('≥')
})

test('renders selected conditional branches, values, and branch-specific handles', () => {
  const tree = ConditionNode({
    id: 'condition', selected: true,
    data: {
      type: 'condition', label: 'Router', config: {},
      branches: [
        { id: 'if', type: 'if', name: 'IF', logicOperator: 'and', conditions: [
          { id: 'rule-1', variable: '{{input.status}}', variableSource: 'Input', operator: 'equals', value: 'open' },
          { id: 'rule-2', variable: '{{input.priority}}', operator: 'equals', value: 'high' },
        ] },
        { id: 'else', type: 'else', name: 'ELSE', logicOperator: 'and', conditions: [] },
      ],
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'status')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'IF')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'open')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source').map((node) => node.props.id)).toEqual(['if', 'else'])
})

test('uses default branches and configuration prompt when no branches are configured', () => {
  const tree = ConditionNode({ id: 'condition', data: { type: 'condition', label: '', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesCondition.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesCondition.clickToConfigure')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'source').map((node) => node.props.id)).toEqual(['if', 'else'])
})

test('positions a branch that follows an else branch', () => {
  const tree = ConditionNode({
    id: 'condition',
    data: {
      type: 'condition', label: 'Router', config: {},
      branches: [
        { id: 'else', type: 'else', name: 'ELSE', logicOperator: 'and', conditions: [] },
        { id: 'if', type: 'if', name: 'IF', logicOperator: 'and', conditions: [] },
      ],
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.type === 'source').map((node) => node.props.id)).toEqual(['else', 'if'])
})
