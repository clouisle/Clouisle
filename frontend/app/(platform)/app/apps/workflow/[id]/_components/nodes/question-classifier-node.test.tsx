import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Tags: element, Sparkles: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { QuestionClassifierNode } = await import('./question-classifier-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders selected model and category-specific output handles', () => {
  const tree = QuestionClassifierNode({
    id: 'classifier', selected: true,
    data: {
      type: 'question_classifier', label: 'Route question', config: {},
      questionClassifierConfig: {
        sourceVariable: '{{input.question}}', modelId: 'model-1', modelName: 'Classifier Pro',
        categories: [
          { id: 'support', name: 'Support', description: 'Support questions' },
          { id: 'other', name: '', description: 'Everything else' },
        ],
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Route question')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Classifier Pro')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'Support')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesCommon.unnamed')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source').map((node) => node.props.id)).toEqual(['support', 'other'])
  expect(findAll(tree, (node) => node.props.type === 'source').map((node) => node.props.style)).toEqual([{ top: 66 }, { top: 94 }])
})

test('uses default labels, model warning, prompt, and output handle without categories', () => {
  const tree = QuestionClassifierNode({ id: 'classifier', data: { type: 'question_classifier', label: '', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesQuestionClassifier.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesCommon.modelNotSelected')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesQuestionClassifier.clickToAdd')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'source')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.id).toBeUndefined()
})
