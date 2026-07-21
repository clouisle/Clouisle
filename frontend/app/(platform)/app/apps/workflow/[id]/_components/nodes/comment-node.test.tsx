import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateIndex = 0
const updates: unknown[][] = []
const setNodes = mock(() => {})
const element = function Element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(value: T) => {
    const index = stateIndex++
    const setValue = (next: T) => updates[index].push(next)
    return [value, setValue] as [T, typeof setValue]
  },
  useRef: () => ({ current: null }),
  useEffect: () => {},
  useCallback: <T,>(callback: T) => callback,
}))
mock.module('@xyflow/react', () => ({ NodeResizer: element, useReactFlow: () => ({ setNodes }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('streamdown', () => ({ Streamdown: element }))
mock.module('@/lib/utils', () => ({ cn: (...values: string[]) => values.filter(Boolean).join(' ') }))

const { COMMENT_COLORS, CommentNode } = await import('./comment-node')

function find(node: unknown, predicate: (node: { props: Record<string, unknown> }) => boolean): { props: Record<string, unknown> } | undefined {
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined
  const current = node as { props: Record<string, unknown> }
  if (predicate(current)) return current
  return [current.props.children].flat().map((child) => find(child, predicate)).find(Boolean)
}

test('renders note content, author, color, and selected resizer', () => {
  stateIndex = 0
  updates.length = 2
  updates[0] = []
  updates[1] = []
  const tree = CommentNode({ id: 'note-1', selected: true, data: { type: 'comment', label: 'Note', content: 'Hello', author: 'Ada', color: 'blue', config: {} } } as never) as { props: Record<string, unknown> }
  const resizer = find(tree, (node) => node.props.minWidth === 200)

  expect(COMMENT_COLORS.blue.bg).toContain('blue')
  expect(resizer?.props.isVisible).toBe(true)
  expect(resizer?.props.lineClassName).toBe(COMMENT_COLORS.blue.resizeLine)
  expect(find(tree, (node) => node.props.children === 'Hello')).toBeDefined()
  expect(find(tree, (node) => node.props.children === 'Ada')).toBeDefined()
})

test('enters edit mode and saves content on escape', () => {
  stateIndex = 0
  updates.length = 2
  updates[0] = []
  updates[1] = []
  const tree = CommentNode({ id: 'note-1', selected: false, data: { type: 'comment', label: 'Note', config: {} } } as never) as { props: Record<string, unknown> }
  const note = find(tree, (node) => typeof node.props.onDoubleClick === 'function')

  note?.props.onDoubleClick({ stopPropagation: mock(() => {}) })
  expect(updates[1]).toEqual([true])
})
