import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type TreeNode = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): TreeNode => ({ type, props })
const NodeResizer = function NodeResizer() {}
const Streamdown = function Streamdown() {}
const setNodes = mock(() => {})
const setContent = mock(() => {})
const setIsEditing = mock(() => {})
let states: unknown[] = []
let effects: (() => void)[] = []
let refCurrent: Props | null = null

mock.module('react', () => ({
  useState: (initial: unknown) => [states.length ? states.shift() : initial, states.length ? setContent : setIsEditing],
  useRef: () => ({ current: refCurrent }),
  useEffect: (effect: () => void) => effects.push(effect),
  useCallback: (callback: unknown) => callback,
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@xyflow/react', () => ({ NodeResizer, useReactFlow: () => ({ setNodes }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('streamdown', () => ({ Streamdown }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { CommentNode } = await import('./comment-node')

function descendants(value: unknown): TreeNode[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as TreeNode
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  return text((value as TreeNode).props.children)
}

function render(data: Props = {}, selected = false) {
  effects = []
  return CommentNode({ id: 'comment-1', selected, data: { type: 'comment', label: 'Comment', config: {}, ...data } } as never) as TreeNode
}

beforeEach(() => {
  states = []
  effects = []
  refCurrent = null
  setNodes.mockClear()
  setContent.mockClear()
  setIsEditing.mockClear()
})

test('reflects selection, resize, color, content, and author presentation', () => {
  let tree = render()
  let nodes = descendants(tree)
  let resizer = nodes.find(node => node.type === NodeResizer)!
  let card = nodes.find(node => typeof node.props.onDoubleClick === 'function')!

  expect(resizer.props).toMatchObject({ minWidth: 200, minHeight: 120, isVisible: false, lineClassName: '!border-amber-300' })
  expect(resizer.props.handleClassName).toContain('!bg-amber-400')
  expect(card.props.className).toContain('border-amber-200')
  expect(card.props.style).toEqual({ minWidth: 200, minHeight: 120 })
  expect(text(tree)).toContain('nodesComment.doubleClickToEdit')

  states = ['**Release note**', false]
  tree = render({ content: '**Release note**', author: 'Ada', color: 'blue' }, true)
  nodes = descendants(tree)
  resizer = nodes.find(node => node.type === NodeResizer)!
  card = nodes.find(node => typeof node.props.onDoubleClick === 'function')!

  expect(resizer.props).toMatchObject({ isVisible: true, lineClassName: '!border-blue-300' })
  expect(card.props.className).toContain('border-blue-400')
  expect(nodes.find(node => node.type === Streamdown)!.props.children).toBe('**Release note**')
  expect(text(tree)).toContain('Ada')
})

test('enters edit mode, focuses the textarea, and updates draft content', () => {
  const stopPropagation = mock(() => {})
  let tree = render({ content: 'Draft' })
  descendants(tree).find(node => typeof node.props.onDoubleClick === 'function')!.props.onDoubleClick!({ stopPropagation })

  expect(stopPropagation).toHaveBeenCalled()
  expect(setIsEditing).toHaveBeenCalledWith(true)

  const focus = mock(() => {})
  const setSelectionRange = mock(() => {})
  refCurrent = { focus, setSelectionRange }
  states = ['Draft', true]
  tree = render({ content: 'Draft' })
  effects.forEach(effect => effect())
  const textarea = descendants(tree).find(node => node.type === 'textarea')!

  expect(focus).toHaveBeenCalled()
  expect(setSelectionRange).toHaveBeenCalledWith(5, 5)
  expect(textarea.props).toMatchObject({ value: 'Draft', placeholder: 'nodesComment.placeholder' })
  textarea.props.onChange!({ target: { value: 'Updated draft' } })
  expect(setContent).toHaveBeenCalledWith('Updated draft')
})

test('syncs external content and saves edits on Escape or blur', () => {
  states = ['Local draft', true]
  const tree = render({ content: 'Server draft' })
  effects[0]()
  expect(setContent).toHaveBeenCalledWith('Server draft')

  const textarea = descendants(tree).find(node => node.type === 'textarea')!
  textarea.props.onKeyDown!({ key: 'Enter' })
  expect(setNodes).not.toHaveBeenCalled()

  textarea.props.onKeyDown!({ key: 'Escape' })
  expect(setNodes).toHaveBeenCalledTimes(1)
  const updateNodes = setNodes.mock.calls[0][0] as (nodes: Props[]) => Props[]
  const untouched = { id: 'other', data: { content: 'Other' } }
  expect(updateNodes([{ id: 'comment-1', data: { author: 'Ada' } }, untouched])).toEqual([
    { id: 'comment-1', data: { author: 'Ada', content: 'Local draft' } },
    untouched,
  ])
  expect(setIsEditing).toHaveBeenCalledWith(false)

  textarea.props.onBlur!()
  expect(setNodes).toHaveBeenCalledTimes(2)
})
