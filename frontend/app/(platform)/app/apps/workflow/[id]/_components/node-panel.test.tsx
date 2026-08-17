import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Bot: element, CirclePause: element, GitBranch: element, Workflow: element, Wrench: element, Code: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { NodePanel } = await import('./node-panel')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders available workflow nodes and invokes each add action', () => {
  const onAddNode = mock(() => {})
  const tree = NodePanel({ onAddNode }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodePanel.addNode')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodePanel.dragOrClickToAdd')).toHaveLength(1)
  for (const type of ['llm', 'condition', 'pause', 'sub_workflow', 'tool', 'code']) {
    expect(findAll(tree, (node) => node.props.children === `nodeLabels.${type}`)).toHaveLength(1)
    expect(findAll(tree, (node) => node.props.children === `nodeDescriptions.${type}`)).toHaveLength(1)
  }

  const options = findAll(tree, (node) => node.type === 'button')
  expect(options).toHaveLength(6)
  options.forEach((option) => (option.props.onClick as () => void)())
  expect(onAddNode.mock.calls).toEqual([
    ['llm'], ['condition'], ['pause'], ['sub_workflow'], ['tool'], ['code'],
  ])
})
