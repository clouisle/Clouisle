import { test, expect, mock } from 'bun:test'
import * as React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'
import { ConversationList } from './conversation-list'
import { NewChatDialog } from './new-chat-dialog'
import { ChatWindow } from './chat-window'
import { MessageCenterDialog } from './message-center-dialog'
import { type ImConversation, type ImMessage } from '@/lib/api'
import { stripMarkdown } from '@/lib/utils'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

function nodeText(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  const children = (node as { children?: unknown[] } | null)?.children
  return Array.isArray(children) ? children.map(nodeText).join('') : ''
}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'zh',
}))
const element = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
  <div {...props}>{children}</div>
)
mock.module('@/components/ui/dialog', () => ({
  Dialog: element,
  DialogContent: element,
  DialogHeader: element,
  DialogTitle: element,
}))
mock.module('streamdown', () => ({
  Streamdown: ({ children }: { children: React.ReactNode }) => <div data-testid="streamdown">{children}</div>,
}))
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam: { id: 'team-1', name: 'Team One' } }),
}))
mock.module('@/components/chat/authenticated-asset', () => ({
  useAuthenticatedAssetUrl: () => ({ src: '/blob-url', loading: false, error: false }),
  downloadAuthenticatedAsset: mock(async () => {}),
}))


mock.module('@/lib/api', () => ({
  imApi: {
    listConversations: mock(async () => []),
    getMessages: mock(async () => ({ messages: [], has_more: false })),
    sendMessage: mock(async () => ({
      id: 'msg-1',
      conversation_id: 'conv-1',
      seq: 1,
      content: 'hello',
      msg_type: 'text',
      created_at: '2026-11-04T00:00:00Z',
    })),
    markRead: mock(async () => ({ cleared: 0 })),
    createDirectConversation: mock(async () => null),
    listTeamCandidates: mock(async () => [
      { id: 'user-2', username: 'bob', full_name: 'Bob', role: 'member' },
    ]),
    searchMessages: mock(async () => [
      {
        message_id: 'msg-found-1',
        conversation_id: 'conv-user',
        seq: 5,
        content: 'I found what you asked',
        msg_type: 'text',
        conversation_type: 'direct',
        created_at: '2026-11-04T12:00:00Z',
        peer: { id: 'user-bob', username: 'bob', full_name: 'Bob Builder' },
      },
    ]),
    subscribeEvents: mock(() => () => {}),
  },
}))

test('renders conversation list and filters by search query', () => {
  const conversations: ImConversation[] = [
    {
      id: 'conv-sys',
      type: 'system',
      team_id: 'team-1',
      is_pinned: true,
      is_muted: false,
      last_read_seq: 0,
      latest_seq: 1,
      unread_count: 2,
      last_message_content: 'Notice message',
      last_message_at: '2026-11-04T12:00:00Z',
      created_at: '2026-11-04T10:00:00Z',
      updated_at: '2026-11-04T12:00:00Z',
    },
    {
      id: 'conv-user',
      type: 'direct',
      team_id: 'team-1',
      is_pinned: false,
      is_muted: false,
      last_read_seq: 5,
      latest_seq: 5,
      unread_count: 0,
      last_message_content: 'Hey Alice',
      last_message_at: '2026-11-04T11:00:00Z',
      peer: { id: 'user-bob', username: 'bob', full_name: 'Bob Builder' },
      created_at: '2026-11-04T09:00:00Z',
      updated_at: '2026-11-04T11:00:00Z',
    },
  ]

  let selectedConv: ImConversation | null = null
  let renderer!: ReactTestRenderer

  act(() => {
    renderer = create(
      <ConversationList
        conversations={conversations}
        selectedId="conv-sys"
        onSelect={(c) => {
          selectedConv = c
        }}
        onNewChat={() => {}}
        search=""
        onSearchChange={() => {}}
      />
    )
  })

  expect(renderer.root.findAllByType('button').length).toBe(3) // 1个新对话按钮 + 2个会话按钮

  // 点击单聊会话
  const buttons = renderer.root.findAllByType('button')
  act(() => {
    buttons[2].props.onClick()
  })

  expect(selectedConv?.id).toBe('conv-user')
})

test('renders new chat dialog and lists candidates', async () => {
  let selectedUser = ''
  let renderer!: ReactTestRenderer

  await act(async () => {
    renderer = create(
      <NewChatDialog
        open={true}
        onOpenChange={() => {}}
        teamId="team-1"
        onSelectUser={(uid) => {
          selectedUser = uid
        }}
      />
    )
    await Promise.resolve()
  })

  const userButtons = renderer.root.findAllByType('button')
  expect(userButtons.length).toBeGreaterThan(0)

  act(() => {
    userButtons[0].props.onClick()
  })
  expect(selectedUser).toBe('user-2')
})

test('ChatWindow ignores Enter key during Chinese IME composition', async () => {
  const conv: ImConversation = {
    id: 'conv-direct',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 1,
    latest_seq: 1,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  const textarea = renderer.root.findByType('textarea')
  act(() => {
    textarea.props.onChange({ target: { value: 'nihao' } })
  })

  const preventDefault = mock()
  const { imApi } = await import('@/lib/api')
  const sendMessage = imApi.sendMessage as unknown as { mockClear: () => void; mock: { calls: unknown[] } }
  sendMessage.mockClear()

  // 1. 在 compositionstart 激活期间按 Enter：应当忽略，不发送
  act(() => {
    textarea.props.onCompositionStart()
  })
  act(() => {
    textarea.props.onKeyDown({
      key: 'Enter',
      shiftKey: false,
      keyCode: 229,
      nativeEvent: { isComposing: true },
      preventDefault,
    })
  })
  expect(preventDefault).not.toHaveBeenCalled()
  expect(imApi.sendMessage).not.toHaveBeenCalled()

  // 2. compositionend 结束后按 Enter：正常发送
  act(() => {
    textarea.props.onCompositionEnd()
  })
  act(() => {
    textarea.props.onKeyDown({
      key: 'Enter',
      shiftKey: false,
      keyCode: 13,
      nativeEvent: { isComposing: false },
      preventDefault,
    })
  })
  expect(preventDefault).toHaveBeenCalledTimes(1)
})

test('stripMarkdown removes markdown syntax markers cleanly', () => {
  expect(stripMarkdown('**文档索引成功** 知识库 **111** 中的文件已处理完成')).toBe(
    '文档索引成功 知识库 111 中的文件已处理完成'
  )
  expect(stripMarkdown('# 标题\n\n- 列表项1\n- 列表项2\n> [链接](https://example.com)')).toBe(
    '标题 列表项1 列表项2 链接'
  )
  expect(stripMarkdown('```python\nprint(1)\n``` 普通文本 `inline_code`')).toBe(
    '普通文本 inline_code'
  )
  expect(stripMarkdown(null)).toBe('')
})

test('ConversationList strips markdown in last_message_content subtitle', () => {
  const convs: ImConversation[] = [
    {
      id: 'conv-notif',
      type: 'system',
      team_id: 'team-1',
      is_pinned: true,
      is_muted: false,
      last_read_seq: 1,
      latest_seq: 1,
      unread_count: 0,
      last_message_content: '**文档索引成功** 知识库 **111** 中的文件',
      last_message_at: '2026-11-04T12:00:00Z',
      created_at: '2026-11-04T10:00:00Z',
      updated_at: '2026-11-04T12:00:00Z',
    },
  ]

  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(
      <ConversationList
        conversations={convs}
        selectedId="conv-notif"
        onSelect={() => {}}
        onNewChat={() => {}}
        search=""
        onSearchChange={() => {}}
      />
    )
  })

  const p = renderer.root.findByType('p')
  expect(p.children.join('')).toBe('文档索引成功 知识库 111 中的文件')
  expect(p.children.join('')).not.toContain('**')
})

test('ChatWindow renders date divider when messages span across different days', async () => {
  const conv: ImConversation = {
    id: 'conv-span-days',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 2,
    latest_seq: 2,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-05T00:00:00Z',
  }

  const { imApi } = await import('@/lib/api')
  imApi.getMessages = mock(async () => ({
    messages: [
      {
        id: 'msg-day-1',
        conversation_id: 'conv-span-days',
        seq: 1,
        content: 'Yesterday message',
        msg_type: 'text',
        status: 'normal',
        created_at: '2026-11-04T10:00:00Z',
      },
      {
        id: 'msg-day-2',
        conversation_id: 'conv-span-days',
        seq: 2,
        content: 'Today message',
        msg_type: 'text',
        status: 'normal',
        created_at: '2026-11-05T10:00:00Z',
      },
    ],
    has_more: false,
  }))

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  const dividers = renderer.root.findAll(
    (node) => node.props['data-testid'] === 'im-date-divider'
  )
  expect(dividers.length).toBe(2) // 第一天一个分割线，跨天后第二天一个分割线

  const earliestNotice = renderer.root.findAll(
    (node) => node.props.children === 'earliestMessageNotice'
  )
  expect(earliestNotice.length).toBe(1)
})

test('MessageCenterDialog renders and mounts correctly when open', async () => {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(
      <MessageCenterDialog
        open={true}
        onOpenChange={() => {}}
        currentUserId="user-alice"
      />
    )
    await Promise.resolve()
  })

  expect(renderer.root).toBeTruthy()
})

test('ChatWindow renders unread divider before first unread message', async () => {
  const convWithUnread: ImConversation = {
    id: 'conv-with-unread',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 1, // 已读到 seq 1
    latest_seq: 3,    // 最新到 seq 3
    unread_count: 2,  // 有 2 条未读 (seq 2, 3)
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }

  const { imApi } = await import('@/lib/api')
  imApi.getMessages = mock(async () => ({
    messages: [
      {
        id: 'msg-read-1',
        conversation_id: 'conv-with-unread',
        seq: 1,
        content: 'Read message',
        msg_type: 'text',
        status: 'normal',
        created_at: '2026-11-04T10:00:00Z',
      },
      {
        id: 'msg-unread-2',
        conversation_id: 'conv-with-unread',
        seq: 2,
        content: 'Unread message 1',
        msg_type: 'text',
        status: 'normal',
        created_at: '2026-11-04T10:05:00Z',
      },
      {
        id: 'msg-unread-3',
        conversation_id: 'conv-with-unread',
        seq: 3,
        content: 'Unread message 2',
        msg_type: 'text',
        status: 'normal',
        created_at: '2026-11-04T10:10:00Z',
      },
    ],
    has_more: false,
  }))

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={convWithUnread} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  // 检查是否渲染了未读分割线
  const unreadDividers = renderer.root.findAll(
    (node) => node.props.id === 'im-unread-divider'
  )
  expect(unreadDividers.length).toBe(1)
})

test('ChatWindow preserves textarea focus and enabled state while sending', async () => {
  const conv: ImConversation = {
    id: 'conv-focus',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 1,
    latest_seq: 1,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  const textarea = renderer.root.findByType('textarea')
  expect(textarea.props.disabled).toBe(false)

  act(() => {
    textarea.props.onChange({ target: { value: 'New message to send' } })
  })

  const preventDefault = mock()
  await act(async () => {
    await textarea.props.onKeyDown({
      key: 'Enter',
      shiftKey: false,
      keyCode: 13,
      nativeEvent: { isComposing: false },
      preventDefault,
    })
  })

  expect(preventDefault).toHaveBeenCalledTimes(1)
  expect(textarea.props.disabled).toBe(false)
})

test('ChatWindow splits text, image and file into ordered separate messages', async () => {
  const conv: ImConversation = {
    id: 'conv-split',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 0,
    latest_seq: 0,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }

  const { imApi } = await import('@/lib/api')
  const sent: Array<Record<string, unknown>> = []
  imApi.uploadAttachment = mock(async (_convId: string, file: File) => ({
    asset_id: `asset-${file.name}`,
    filename: file.name,
    size: 10,
    content_type: file.type,
    url: `/api/v1/upload/files/${file.name}`,
  }))
  imApi.sendMessage = mock(async (_convId: string, payload: Record<string, unknown>) => {
    sent.push(payload)
    return {
      id: `msg-${String(payload.client_msg_id)}`,
      conversation_id: conv.id,
      seq: sent.length,
      msg_type: payload.msg_type ?? 'text',
      content: payload.content,
      status: 'normal',
      created_at: '2026-11-04T00:00:00Z',
      attachment: payload.asset_id
        ? {
            asset_id: payload.asset_id,
            filename: 'f',
            size: 10,
            content_type: 'image/png',
            url: '/x',
          }
        : null,
    }
  })

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  const textarea = renderer.root.findByType('textarea')
  act(() => {
    textarea.props.onChange({ target: { value: 'hello' } })
  })

  const fileInputs = renderer.root.findAll(
    (node) => node.type === 'input' && node.props.type === 'file'
  )
  expect(fileInputs.length).toBe(1)

  await act(async () => {
    fileInputs[0].props.onChange({
      target: {
        files: [
          new File(['x'], 'a.png', { type: 'image/png' }),
          new File(['y'], 'b.pdf', { type: 'application/pdf' }),
        ],
        value: '',
      },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  const sendButton = renderer.root.findAll(
    (node) => node.type === 'button' && node.props.children === 'send'
  )[0]
  await act(async () => {
    await sendButton.props.onClick()
  })

  expect(sent.length).toBe(3)
  expect(sent[0]).toMatchObject({ content: 'hello', msg_type: 'text' })
  expect(sent[1]).toMatchObject({ content: '', msg_type: 'file', asset_id: 'asset-a.png' })
  expect(sent[2]).toMatchObject({ content: '', msg_type: 'file', asset_id: 'asset-b.pdf' })
  expect(String(sent[0].client_msg_id).endsWith('-text')).toBe(true)
  expect(String(sent[1].client_msg_id).endsWith('-asset-a.')).toBe(true)
  expect(String(sent[2].client_msg_id).endsWith('-asset-b.')).toBe(true)
})

test('ChatWindow retries a failed draft with stable client message ids', async () => {
  const conv: ImConversation = {
    id: 'conv-retry',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 0,
    latest_seq: 0,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }

  const { imApi } = await import('@/lib/api')
  const imageIds: string[] = []
  let failImage = true
  imApi.uploadAttachment = mock(async (_convId: string, file: File) => ({
    asset_id: 'asset-retry-image',
    filename: file.name,
    size: 10,
    content_type: file.type,
    url: `/api/v1/upload/files/${file.name}`,
  }))
  imApi.sendMessage = mock(async (_convId: string, payload: Record<string, unknown>) => {
    if (payload.msg_type === 'file' && payload.content === '') {
      imageIds.push(String(payload.client_msg_id))
      if (failImage) {
        failImage = false
        throw new Error('network down')
      }
    }
    return {
      id: `msg-${String(payload.client_msg_id)}`,
      conversation_id: conv.id,
      seq: 1,
      msg_type: payload.msg_type ?? 'text',
      content: payload.content,
      status: 'normal',
      created_at: '2026-11-04T00:00:00Z',
      attachment: null,
    }
  })

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  const textarea = renderer.root.findByType('textarea')
  act(() => {
    textarea.props.onChange({ target: { value: 'draft' } })
  })
  const imageInput = renderer.root.findAll(
    (node) => node.type === 'input' && node.props.type === 'file'
  )[0]
  await act(async () => {
    imageInput.props.onChange({
      target: { files: [new File(['x'], 'a.png', { type: 'image/png' })], value: '' },
    })
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  const sendButton = () =>
    renderer.root.findAll(
      (node) => node.type === 'button' && node.props.children === 'send'
    )[0]

  await act(async () => {
    await sendButton().props.onClick()
  })
  await act(async () => {
    await sendButton().props.onClick()
  })

  expect(imageIds.length).toBe(2)
  expect(imageIds[0]).toBe(imageIds[1])
})

test('ChatWindow keeps a live SSE message that arrives during the initial history load', async () => {
  const conv: ImConversation = {
    id: 'conv-live-merge',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 0,
    latest_seq: 2,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }

  const { imApi } = await import('@/lib/api')
  type MessagePage = { messages: ImMessage[]; has_more: boolean }
  let resolveLoad!: (value: MessagePage) => void
  const loadPromise = new Promise<MessagePage>((resolve) => {
    resolveLoad = resolve
  })
  imApi.getMessages = mock(async () => loadPromise)

  const loaded: ImMessage[] = [
    {
      id: 'msg-loaded-1',
      conversation_id: conv.id,
      seq: 1,
      content: 'loaded one',
      msg_type: 'text',
      status: 'normal',
      created_at: '2026-11-04T10:00:00Z',
    },
    {
      id: 'msg-loaded-2',
      conversation_id: conv.id,
      seq: 2,
      content: 'loaded two',
      msg_type: 'text',
      status: 'normal',
      created_at: '2026-11-04T10:01:00Z',
    },
  ]
  const live: ImMessage = {
    id: 'msg-live-3',
    conversation_id: conv.id,
    seq: 3,
    content: 'live message',
    msg_type: 'text',
    status: 'normal',
    created_at: '2026-11-04T10:02:00Z',
  }

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
  })

  // SSE 在历史请求返回前到达
  await act(async () => {
    renderer.update(
      <ChatWindow conversation={conv} currentUserId="user-alice" incomingMessage={live} />
    )
  })

  await act(async () => {
    resolveLoad({ messages: loaded, has_more: false })
    await loadPromise
  })

  const liveBubbles = renderer.root.findAll(
    (node) =>
      node.props['data-testid'] === 'streamdown' && node.props.children === 'live message'
  )
  expect(liveBubbles.length).toBe(1)
  expect(
    renderer.root.findAll((node) => node.props.id === 'im-msg-msg-loaded-2').length
  ).toBe(1)
})

test('ChatWindow discards a stale history response after switching conversations', async () => {
  const convA: ImConversation = {
    id: 'conv-stale-a',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 0,
    latest_seq: 0,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-04T00:00:00Z',
  }
  const convB: ImConversation = {
    ...convA,
    id: 'conv-stale-b',
    peer: { id: 'user-carol', username: 'carol', full_name: 'Carol' },
  }

  const { imApi } = await import('@/lib/api')
  type MessagePage = { messages: ImMessage[]; has_more: boolean }
  let resolveA!: (value: MessagePage) => void
  const pendingA = new Promise<MessagePage>((resolve) => {
    resolveA = resolve
  })
  const currentMessage: ImMessage = {
    id: 'msg-current-b',
    conversation_id: convB.id,
    seq: 1,
    content: 'current B message',
    msg_type: 'text',
    status: 'normal',
    created_at: '2026-11-04T11:00:00Z',
  }
  imApi.getMessages = mock(async (id: string) => {
    if (id === convA.id) return pendingA
    return { messages: [currentMessage], has_more: false }
  })

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={convA} currentUserId="user-alice" />)
  })

  await act(async () => {
    renderer.update(<ChatWindow conversation={convB} currentUserId="user-alice" />)
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  // 旧会话的请求此时才返回（带 has_more），应当被完全丢弃
  await act(async () => {
    resolveA({
      messages: [
        {
          id: 'msg-stale-a',
          conversation_id: convA.id,
          seq: 4,
          content: 'stale A message',
          msg_type: 'text',
          status: 'normal',
          created_at: '2026-11-04T10:00:00Z',
        },
      ],
      has_more: true,
    })
    await pendingA
  })

  expect(
    renderer.root.findAll((node) => node.props.children === 'stale A message').length
  ).toBe(0)
  expect(
    renderer.root.findAll(
      (node) =>
        node.props['data-testid'] === 'streamdown' &&
        node.props.children === 'current B message'
    ).length
  ).toBe(1)
  // 过期响应的 has_more 不得覆盖当前会话
  expect(JSON.stringify(renderer.toJSON())).not.toContain('loadEarlierMessages')
})

test('ConversationList highlights search matches and keeps the unread badge', () => {
  const convs: ImConversation[] = [
    {
      id: 'conv-bob',
      type: 'direct',
      team_id: 'team-1',
      is_pinned: false,
      is_muted: false,
      last_read_seq: 1,
      latest_seq: 5,
      unread_count: 4,
      last_message_content: 'hello there',
      last_message_at: '2026-11-04T12:00:00Z',
      peer: { id: 'user-bob', username: 'bobbity', full_name: 'Bob Builder' },
      created_at: '2026-11-04T10:00:00Z',
      updated_at: '2026-11-04T12:00:00Z',
    },
  ]
  let selected: ImConversation | null = null
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(
      <ConversationList
        teamId="team-1"
        conversations={convs}
        selectedId={null}
        onSelect={(conv) => {
          selected = conv
        }}
        onNewChat={() => {}}
        search="bob"
        onSearchChange={() => {}}
      />
    )
  })

  expect(JSON.stringify(renderer.toJSON())).toContain('"4"')
  expect(nodeText(renderer.root)).toContain('Bob')

  act(() => {
    renderer.root
      .findAll((node) => node.type === 'button' && node.props.onClick)
      .at(-1)!
      .props.onClick()
  })
  expect(selected?.id).toBe('conv-bob')
})

test('ConversationList shows the search-specific empty state', async () => {
  const { imApi } = await import('@/lib/api')
  imApi.searchMessages = mock(async () => [])
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(
      <ConversationList
        teamId="team-1"
        conversations={[]}
        selectedId={null}
        onSelect={() => {}}
        onNewChat={() => {}}
        search="nothing-matches"
        onSearchChange={() => {}}
      />
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 300))
  })
  expect(
    renderer.root.findAll((node) => String(node.props.children) === 'noSearchResults').length
  ).toBe(1)
})

test('ConversationList renders message search results and selects them', async () => {
  const { imApi } = await import('@/lib/api')
  imApi.searchMessages = mock(async () => [
    {
      message_id: 'msg-found-1',
      conversation_id: 'conv-user',
      seq: 5,
      content: 'I found what you asked',
      msg_type: 'text',
      conversation_type: 'direct',
      created_at: '2026-11-04T12:00:00Z',
      peer: { id: 'user-bob', username: 'bob', full_name: 'Bob Builder' },
    },
  ])
  let picked: { conversation_id: string; seq: number } | null = null
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = create(
      <ConversationList
        teamId="team-1"
        conversations={[]}
        selectedId={null}
        onSelect={() => {}}
        onSelectSearchResult={(result) => {
          picked = { conversation_id: result.conversation_id, seq: result.seq }
        }}
        onNewChat={() => {}}
        search="found"
        onSearchChange={() => {}}
      />
    )
  })

  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 300))
  })

  const resultButton = renderer.root
    .findAll((node) => node.type === 'button' && node.props.onClick)
    .find((node) => nodeText(node).includes('I found what you asked'))
  expect(resultButton).toBeDefined()
  act(() => {
    resultButton!.props.onClick()
  })
  expect(picked).toEqual({ conversation_id: 'conv-user', seq: 5 })
})

test('ChatWindow renders attachments without a filename caption and downloads files', async () => {
  const conv: ImConversation = {
    id: 'conv-files',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 2,
    latest_seq: 2,
    unread_count: 0,
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T00:00:00Z',
    updated_at: '2026-11-05T00:00:00Z',
  }
  const { imApi } = await import('@/lib/api')
  imApi.getMessages = mock(async () => ({
    messages: [
      {
        id: 'msg-image',
        conversation_id: conv.id,
        seq: 1,
        msg_type: 'file',
        content: '',
        status: 'normal',
        created_at: '2026-11-05T09:00:00Z',
        attachment: {
          asset_id: 'asset-image',
          filename: 'photo.png',
          size: 2048,
          content_type: 'image/png',
          url: '/api/v1/upload/files/im/2026/11/photo.png',
        },
      },
      {
        id: 'msg-pdf',
        conversation_id: conv.id,
        seq: 2,
        msg_type: 'file',
        content: '',
        status: 'normal',
        created_at: '2026-11-05T09:01:00Z',
        attachment: {
          asset_id: 'asset-pdf',
          filename: 'report.pdf',
          size: 4096,
          content_type: 'application/pdf',
          url: '/api/v1/upload/files/im/2026/11/report.pdf',
        },
      },
    ],
    has_more: false,
  }))

  const { downloadAuthenticatedAsset } = await import('@/components/chat/authenticated-asset')
  const download = downloadAuthenticatedAsset as unknown as {
    mockClear: () => void
    mock: { calls: unknown[][] }
  }
  download.mockClear()

  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ChatWindow conversation={conv} currentUserId="user-alice" />)
    await Promise.resolve()
  })

  const images = renderer.root.findAllByType('img')
  expect(images.length).toBe(1)
  expect(images[0].props.src).toBe('/blob-url')
  const caption = renderer.root.findAll((node) => node.props.children === 'photo.png')
  expect(caption.length).toBe(0)
  expect(renderer.root.findAll((node) => node.props.children === 'report.pdf').length).toBeGreaterThan(0)

  act(() => {
    renderer.root
      .findAll((node) => node.type === 'button' && node.props.title === 'download')
      .at(-1)!
      .props.onClick()
  })
  expect(download.mock.calls.at(-1)).toEqual([
    '/api/v1/upload/files/im/2026/11/report.pdf',
    'report.pdf',
  ])
})

test('MessageCenterDialog loads conversations, applies live events and search jumps', async () => {
  const { imApi } = await import('@/lib/api')
  const systemConv: ImConversation = {
    id: 'conv-system',
    type: 'system',
    team_id: 'team-1',
    is_pinned: true,
    is_muted: false,
    last_read_seq: 3,
    latest_seq: 3,
    unread_count: 0,
    last_message_content: 'welcome',
    last_message_at: '2026-11-05T08:00:00Z',
    created_at: '2026-11-04T10:00:00Z',
    updated_at: '2026-11-05T08:00:00Z',
  }
  const directConv: ImConversation = {
    id: 'conv-direct-live',
    type: 'direct',
    team_id: 'team-1',
    is_pinned: false,
    is_muted: false,
    last_read_seq: 2,
    latest_seq: 4,
    unread_count: 2,
    last_message_content: 'older message',
    last_message_at: '2026-11-05T07:00:00Z',
    peer: { id: 'user-bob', username: 'bob', full_name: 'Bob' },
    created_at: '2026-11-04T10:00:00Z',
    updated_at: '2026-11-05T07:00:00Z',
  }

  imApi.listConversations = mock(async () => [systemConv, directConv])
  imApi.getMessages = mock(async () => ({ messages: [], has_more: false }))
  imApi.markRead = mock(async () => ({ cleared: 0 }))
  imApi.createDirectConversation = mock(async () => directConv)
  let handlers: {
    onNewMessage: (msg: Record<string, unknown>) => void
    onConversationRead: (data: { conversation_id: string; last_read_seq: number }) => void
  } | null = null
  imApi.subscribeEvents = mock((next: typeof handlers) => {
    handlers = next
    return () => {}
  })

  let unreadUpdates = 0
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(
      <MessageCenterDialog
        open
        onOpenChange={() => {}}
        currentUserId="user-alice"
        onUnreadUpdated={() => {
          unreadUpdates += 1
        }}
      />
    )
    await Promise.resolve()
    await Promise.resolve()
  })

  // 系统通知会话默认选中
  expect(nodeText(renderer.root)).toContain('systemNotifications')
  expect(imApi.listConversations).toHaveBeenCalledWith('team-1')

  // 非当前会话的实时消息：更新预览、未读数并触发回调
  act(() => {
    handlers!.onNewMessage({
      id: 'live-1',
      conversation_id: directConv.id,
      seq: 5,
      content: 'live text',
      msg_type: 'text',
      created_at: '2026-11-05T09:00:00Z',
    })
  })
  expect(nodeText(renderer.root)).toContain('live text')
  expect(unreadUpdates).toBeGreaterThan(0)

  // 已读事件按游标重算未读
  act(() => {
    handlers!.onConversationRead({ conversation_id: directConv.id, last_read_seq: 5 })
  })

  // 点击会话切换
  const directRow = renderer.root
    .findAll((node) => node.type === 'button' && /bob/i.test(nodeText(node)))
    .at(-1)
  act(() => {
    directRow!.props.onClick()
  })

  // 搜索结果：已在列表中 → 选中并跳到指定 seq
  const conversationList = renderer.root.findByType(ConversationList)
  act(() => {
    conversationList.props.onSelectSearchResult({
      message_id: 'msg-jump',
      conversation_id: directConv.id,
      seq: 3,
      content: 'found it',
      msg_type: 'text',
      conversation_type: 'direct',
      created_at: '2026-11-05T06:00:00Z',
    })
  })
  await act(async () => {
    await Promise.resolve()
  })
  expect(imApi.getMessages).toHaveBeenCalledWith(directConv.id, {
    around_seq: 3,
    limit: 40,
  })

  // 新建会话后刷新列表
  const newChat = renderer.root.findByType(NewChatDialog)
  await act(async () => {
    await newChat.props.onSelectUser('user-2')
  })
  expect(imApi.createDirectConversation).toHaveBeenCalledWith('team-1', 'user-2')
})
