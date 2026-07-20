import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ FileText: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { TemplateNode, getDefaultTemplateConfig } = await import('./template-node')

type TreeNode = { props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('builds a localized default template configuration', () => {
  expect(getDefaultTemplateConfig((key) => `translated:${key}`)).toEqual({
    inputs: [], template: '', outputVariable: 'output',
    outputDescription: 'translated:nodesTemplate.outputDescription',
  })
})

test('renders selected custom template with input and output handles', () => {
  const tree = TemplateNode({
    id: 'template', selected: true,
    data: {
      type: 'template', label: 'Format response', config: {},
      templateConfig: {
        inputs: [{ id: 'name', name: 'name', value: '{{input.name}}' }],
        template: 'Hello {{ name }}', outputVariable: 'output', outputDescription: 'Formatted response',
      },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Format response')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('uses localized labels for the default node', () => {
  const tree = TemplateNode({ id: 'template', data: { type: 'template', label: '', config: {} } }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesTemplate.label')).toHaveLength(2)
})
