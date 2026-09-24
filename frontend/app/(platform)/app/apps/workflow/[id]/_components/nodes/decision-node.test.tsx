import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown> = {}) => ({ type, props })
const Handle = (props: Record<string, unknown>) => jsx('handle', props)

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@xyflow/react', () => ({ Handle, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ GitBranch: 'git-branch' }))
mock.module('next-intl', () => ({ useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}` }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { DecisionNode } = await import('./decision-node')

type TreeNode = { type?: unknown; props: Record<string, unknown> }

function findAll(value: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(value)) return value.flatMap((child) => findAll(child, predicate))
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as TreeNode
  return [
    ...(predicate(node) ? [node] : []),
    ...findAll(node.props.children, predicate),
  ]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join(' ')
  if (value && typeof value === 'object' && 'props' in value) {
    return text((value as TreeNode).props.children)
  }
  return ''
}

test('shows configured decision details and one output handle per branch', () => {
  const tree = DecisionNode({
    selected: true,
    data: {
      label: 'Route request',
      decisionConfig: {
        modelName: 'Jev 1.13',
        stateTemplate: '  {{start.query}}  ',
        questionId: 'route',
        questionType: 'choice',
        instructions: '  Choose a route  ',
        options: ['support', 'billing'],
        defaultHandle: 'review',
      },
    },
  }) as TreeNode

  expect(text(tree)).toContain('Route request')
  expect(text(tree)).toContain('Jev 1.13')
  expect(text(tree)).toContain('{{start.query}}')
  expect(text(tree)).toContain('Choose a route')
  expect(findAll(tree, (node) => node.type === Handle).map((node) => node.props.id)).toEqual([
    undefined,
    'support',
    'billing',
    'review',
  ])
  expect(findAll(tree, (node) => node.type === 'div').some(
    (node) => String(node.props.className).includes('border-primary'),
  )).toBe(true)
})

test('renders fallback labels and default branches when configuration is absent', () => {
  const tree = DecisionNode({ data: {} }) as TreeNode

  expect(text(tree)).toContain('workflow.nodesDecision.label')
  expect(text(tree)).toContain('workflow.nodesCommon.modelNotSelected')
  expect(findAll(tree, (node) => node.type === Handle).map((node) => node.props.id)).toEqual([
    undefined,
    'yes',
    'no',
    'default',
  ])
})
