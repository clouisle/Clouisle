import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Home: element, Zap: element, ArrowLeft: element, Plus: element }))
mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { StartNodeSelector } = await import('./start-node-selector')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

test('renders start options and invokes selection and cancellation actions', () => {
  const onSelect = mock(() => {})
  const onCancel = mock(() => {})
  const tree = StartNodeSelector({ onSelect, onCancel }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'startNodes.selectTitle')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'startNodes.selectDescription')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'startNodes.userInput.title')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'startNodes.userInput.description')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'startNodes.trigger.title')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'startNodes.trigger.description')).toHaveLength(1)

  const options = findAll(tree, (node) => node.type === 'button')
  expect(options).toHaveLength(2)
  ;(options[0].props.onClick as () => void)()
  ;(options[1].props.onClick as () => void)()
  expect(onSelect.mock.calls).toEqual([['user_input'], ['trigger']])

  const back = findAll(tree, (node) => node.type === element && node.props.variant === 'ghost')[0]
  ;(back.props.onClick as () => void)()
  expect(onCancel).toHaveBeenCalledTimes(1)
})
