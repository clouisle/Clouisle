import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getEmail = mock(() => Promise.resolve({ smtp_enabled: true }))
const getDingTalk = mock(() => Promise.resolve({ dingtalk_enabled: false }))
const getWeChat = mock(() => Promise.resolve({ wechat_enabled: true }))
const getFeishu = mock(() => Promise.resolve({ feishu_enabled: false }))
const getWebhook = mock(() => Promise.resolve({ webhook_enabled: true }))
const getSlack = mock(() => Promise.resolve({ slack_enabled: false }))
let canUpdate = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  Mail: () => null,
  MessageSquare: () => null,
  Globe: () => null,
  Hash: () => null,
  Bell: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { getEmail, getDingTalk, getWeChat, getFeishu, getWebhook, getSlack },
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))
mock.module('./_components', () => ({
  AutoNotificationsSettingsTab: (props: Record<string, unknown>) => (
    <div data-auto={JSON.stringify(props)} />
  ),
  EmailSettingsTab: () => null,
  DingTalkSettingsTab: () => null,
  WeChatSettingsTab: () => null,
  FeishuSettingsTab: () => null,
  WebhookSettingsTab: () => null,
  SlackSettingsTab: () => null,
}))

const { default: SiteSettingsNotificationsPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsNotificationsPage />)
  })
  return renderer!
}

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
})

test('passes loaded enabled channels to automatic notification settings', async () => {
  const renderer = await render()
  const auto = renderer.root.findAll((node) => typeof node.props['data-auto'] === 'string')[0]
  const props = JSON.parse(auto.props['data-auto'])

  expect(props.enabledChannels).toEqual({
    email: true,
    dingtalk: false,
    wechat: true,
    feishu: false,
    webhook: true,
    slack: false,
  })
  expect(getSlack).toHaveBeenCalledTimes(1)
  act(() => renderer.unmount())
})

test('passes read-only permission to automatic notification settings', async () => {
  canUpdate = false
  const renderer = await render()
  const auto = renderer.root.findAll((node) => typeof node.props['data-auto'] === 'string')[0]

  expect(JSON.parse(auto.props['data-auto']).canUpdate).toBe(false)
  act(() => renderer.unmount())
})
