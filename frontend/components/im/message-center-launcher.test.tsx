import { expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'
import { MessageCenterLauncher } from './message-center-launcher'

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
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam: { id: 'team-1', name: 'Team' } }),
}))
mock.module('@/lib/api', () => ({
  authApi: {
    getCurrentUser: mock(async () => ({ id: 'user-alice', username: 'alice' })),
  },
  imApi: {
    getUnreadCount: mock(async () => ({ total: 7 })),
    listConversations: mock(async () => []),
    getMessages: mock(async () => ({ messages: [], has_more: false })),
    sendMessage: mock(async () => ({})),
    markRead: mock(async () => ({ cleared: 0 })),
    searchMessages: mock(async () => []),
    listTeamCandidates: mock(async () => []),
    subscribeEvents: mock(() => () => {}),
    createDirectConversation: mock(async () => null),
  },
}))

test('launcher waits for the user, shows unread count and opens the dialog', async () => {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<MessageCenterLauncher />)
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  const buttons = () =>
    renderer.root.findAll(
      (node) => node.type === 'button' && node.props['aria-label'] === 'title'
    )
  expect(buttons().length).toBe(1)
  expect(JSON.stringify(renderer.toJSON())).toContain('"7"')

  await act(async () => {
    buttons()[0].props.onClick()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  // Dialog mounted -> backend list call happens
  const { imApi } = await import('@/lib/api')
  expect(imApi.listConversations).toHaveBeenCalled()
})
