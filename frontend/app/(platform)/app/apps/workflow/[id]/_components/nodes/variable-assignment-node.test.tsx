import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.n}` : key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Variable: element, Home: element, ArrowRight: element, Ban: element, Edit3: element, Plus: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { VariableAssignmentNode, getAssignmentOperationConfig } = await import('./variable-assignment-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected assignments with operation-specific values and handles', () => {
  const tree = VariableAssignmentNode({
    id: 'assign', selected: true,
    data: {
      type: 'variable_assignment', label: 'Update state', config: {},
      variableAssignmentConfig: { assignments: [
        { id: 'one', targetVariable: '{{conversation.name}}', operation: 'overwrite', variableRef: '{{input.name}}', variableRefNodeLabel: 'Input' },
        { id: 'two', targetVariable: 'status', targetVariableLabel: 'State', operation: 'set', constantValue: 'a-very-long-value' },
        { id: 'three', targetVariable: 'note', operation: 'clear' },
        { id: 'four', targetVariable: 'items', operation: 'append', variableRef: '{{input.item}}' },
      ] },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAssignment.itemCount:4')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'name')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'a-very-lon...')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAssignment.empty')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAssignment.moreAssignments:1')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses translated operation metadata and the default configuration prompt', () => {
  const operations = getAssignmentOperationConfig((key) => `translated:${key}`)
  const tree = VariableAssignmentNode({ id: 'assign', data: { type: 'variable_assignment', label: '', config: {} } }) as TreeNode

  expect(operations.overwrite.label).toBe('translated:nodesVariableAssignment.opOverwrite')
  expect(operations.clear.shortLabel).toBe('∅')
  expect(operations.append.description).toBe('translated:nodesVariableAssignment.opAppendDesc')
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAssignment.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesVariableAssignment.clickToConfigure')).toHaveLength(1)
})
