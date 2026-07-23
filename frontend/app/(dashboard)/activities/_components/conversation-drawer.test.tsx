import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const convertBackendMessages = mock(() => [
  { id: 'chat-1', role: 'user', content: 'Hello' },
  { id: 'chat-2', role: 'assistant', content: 'Hi' },
])
const canPerform = mock(() => true)

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({ useMemo: <T,>(factory: () => T) => factory() }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({
  type: tag,
  props: { ...props, children },
})
mock.module('lucide-react', () => ({ Loader2: element('loader'), Trash2: element('trash') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/sheet', () => ({
  Sheet: element('sheet'),
  SheetContent: element('sheet-content'),
}))
mock.module('@/components/chat', () => ({ Message: element('message') }))
mock.module('@/components/chat/conversation-drawer-header', () => ({
  ConversationDrawerHeader: element('drawer-header'),
}))
mock.module('@/lib/utils/message-converter', () => ({ convertBackendMessages }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform }) }))

const { ConversationDrawer } = await import('./conversation-drawer')

type Tree = { type: unknown; props: Record<string, unknown> }
type Props = Parameters<typeof ConversationDrawer>[0]

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function findAll(node: ReactNode, type: unknown): Tree[] {
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const tree = resolved as Tree
  const children = tree.props.children
  return [
    ...(tree.type === type ? [tree] : []),
    ...(Array.isArray(children) ? children : [children]).flatMap((child) =>
      findAll(child as ReactNode, type),
    ),
  ]
}

const conversation = {
  id: 'conversation-1',
  title: 'Support chat',
  created_at: '2026-07-19T10:00:00Z',
  variables: { topic: 'billing' },
  agent_name: 'Helper',
  agent_icon: '/agent.png',
  user_name: 'Ada',
  messages: [
    { id: 'backend-1', token_usage: { prompt: 10, completion: 5 } },
    { id: 'backend-2', token_usage: null },
  ],
} as unknown as NonNullable<Props['conversation']>

beforeEach(() => {
  convertBackendMessages.mockClear()
  canPerform.mockReset()
  canPerform.mockReturnValue(true)
})

describe('ConversationDrawer', () => {
  test('propagates open changes and shows only the loading state', () => {
    const onOpenChange = mock()
    const tree = ConversationDrawer({
      conversation: null,
      isLoading: true,
      open: true,
      onOpenChange,
    })
    const sheet = findAll(tree, 'sheet')[0]

    expect(sheet.props.open).toBe(true)
    ;(sheet.props.onOpenChange as (open: boolean) => void)(false)
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(findAll(tree, 'loader')).toHaveLength(1)
    expect(findAll(tree, 'drawer-header')).toHaveLength(0)
  })

  test('renders converted messages, token totals, and an authorized delete action', () => {
    const onDelete = mock()
    const tree = ConversationDrawer({
      conversation,
      isLoading: false,
      open: true,
      onOpenChange: mock(),
      onDelete,
    })

    expect(canPerform).toHaveBeenCalledWith('conversation:delete')
    expect(convertBackendMessages).toHaveBeenCalledWith(conversation.messages)
    const header = findAll(tree, 'drawer-header')[0]
    expect(header.props).toMatchObject({
      title: 'Support chat',
      totalTokens: 15,
      userName: 'Ada',
    })
    expect(findAll(tree, 'message').map((item) => item.props.message)).toEqual(
      convertBackendMessages.mock.results[0].value,
    )

    const deleteButton = findAll(header.props.action as ReactNode, 'button')[0]
    expect(deleteButton.props['aria-label']).toBe('delete')
    ;(deleteButton.props.onClick as () => void)()
    expect(onDelete).toHaveBeenCalledWith('conversation-1')
  })

  test('renders no content without data and hides deletion without permission', () => {
    const emptyTree = ConversationDrawer({
      conversation: null,
      isLoading: false,
      open: false,
      onOpenChange: mock(),
    })
    expect(findAll(emptyTree, 'drawer-header')).toHaveLength(0)
    expect(findAll(emptyTree, 'message')).toHaveLength(0)

    canPerform.mockReturnValue(false)
    const populatedTree = ConversationDrawer({
      conversation,
      isLoading: false,
      open: true,
      onOpenChange: mock(),
      onDelete: mock(),
    })
    const header = findAll(populatedTree, 'drawer-header')[0]
    expect(header).toBeDefined()
    expect(header.props.action).toBeNull()
  })
})
