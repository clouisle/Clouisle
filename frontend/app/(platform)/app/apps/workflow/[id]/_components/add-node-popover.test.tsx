import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}
const setAdjustedPosition = mock(() => {})
const popover = {
  getBoundingClientRect: () => ({ width: 100, height: 200 }),
  contains: () => false,
}

Object.defineProperty(globalThis, 'window', { value: { innerWidth: 150, innerHeight: 300 }, configurable: true })
Object.defineProperty(globalThis, 'document', { value: {
  addEventListener: (_type: string, listener: (event: { key?: string, target?: object }) => void) => listener({ key: 'Escape', target: {} }),
  removeEventListener: () => {},
}, configurable: true })
Object.defineProperty(globalThis, 'setTimeout', { value: (callback: () => void) => { callback(); return 1 }, configurable: true })
Object.defineProperty(globalThis, 'clearTimeout', { value: () => {}, configurable: true })

mock.module('react', () => ({
  useRef: () => ({ current: popover }),
  useState: (value: unknown) => [value, setAdjustedPosition],
  useEffect: (effect: () => void | (() => void)) => effect()?.(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Bot: element, GitBranch: element, Workflow: element, Wrench: element, Code: element, X: element, RefreshCw: element, Infinity: element, LogOut: element, FileText: element, Combine: element, Variable: element, Braces: element, Link: element, Tags: element, MessageSquareText: element, Sparkles: element, Database: element, Images: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { AddNodePopover } = await import('./add-node-popover')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function render(container?: 'iteration' | 'loop') {
  const onSelect = mock(() => {})
  const onClose = mock(() => {})
  const tree = AddNodePopover({
    position: { x: 120, y: 240 }, sourceNodeId: 'source', sourceHandleId: 'branch',
    isInsideIteration: container === 'iteration', isInsideLoop: container === 'loop', onSelect, onClose,
  }) as TreeNode
  return { tree, onSelect, onClose }
}

test('renders normal categories and forwards node selection context', () => {
  const { tree, onSelect, onClose } = render()

  expect(tree.props.style).toEqual({ left: 120, top: 240, transform: 'translate(8px, -50%)' })
  expect(setAdjustedPosition).toHaveBeenCalledWith({ x: 16, y: 184 })
  for (const category of ['model', 'logic', 'transform', 'extension']) {
    expect(findAll(tree, (node) => node.props.children === `nodeCategories.${category}`)).toHaveLength(1)
  }
  for (const type of ['llm', 'media_generation', 'condition', 'question_classifier', 'iteration', 'loop', 'code', 'template', 'file_to_url', 'variable_aggregator', 'variable_assignment', 'parameter_extractor', 'sub_workflow', 'agent', 'tool', 'knowledge_retrieval', 'answer']) {
    expect(findAll(tree, (node) => node.props.children === `nodeLabels.${type}`)).toHaveLength(1)
  }

  const llm = findAll(tree, (node) => node.props.children === 'nodeLabels.llm')[0]
  ;(findAll(tree, (node) => node.type === 'button' && findAll(node, (child) => child === llm).length > 0)[0].props.onClick as () => void)()
  expect(onSelect).toHaveBeenCalledWith('llm', 'source', 'branch')

  expect(onClose).toHaveBeenCalledTimes(2)
  const close = findAll(tree, (node) => node.type === 'button' && node.props.className?.toString().includes('absolute'))[0]
  ;(close.props.onClick as () => void)()
  expect(onClose).toHaveBeenCalledTimes(3)
})

test('uses container-specific exit nodes', () => {
  const iteration = render('iteration').tree
  const loop = render('loop').tree

  expect(findAll(iteration, (node) => node.props.children === 'nodeLabels.iteration_exit')).toHaveLength(1)
  expect(findAll(iteration, (node) => node.props.children === 'nodeLabels.iteration')).toHaveLength(0)
  expect(findAll(loop, (node) => node.props.children === 'nodeLabels.loop_exit')).toHaveLength(1)
  expect(findAll(loop, (node) => node.props.children === 'nodeLabels.loop')).toHaveLength(0)
})
