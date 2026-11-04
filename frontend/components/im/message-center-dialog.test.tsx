import { test, expect, mock } from 'bun:test'
import * as React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'
import { ConversationList } from './conversation-list'
import { NewChatDialog } from './new-chat-dialog'
import { ChatWindow } from './chat-window'
import { type ImConversation } from '@/lib/api'
import { stripMarkdown } from '@/lib/utils'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

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

  // 查找带有 border-border 的日期分割线容器
  const dividers = renderer.root.findAll(
    (node) => node.props.className?.includes('relative flex items-center justify-center my-4')
  )
  expect(dividers.length).toBe(2) // 第一天一个分割线，跨天后第二天一个分割线

  const earliestNotice = renderer.root.findAll(
    (node) => node.props.children === 'earliestMessageNotice'
  )
  expect(earliestNotice.length).toBe(1)
})
