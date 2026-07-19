import { expect, mock, test } from 'bun:test'

const EmailSettingsTab = {}
const DingTalkSettingsTab = {}
const WeChatSettingsTab = {}
const FeishuSettingsTab = {}
const WebhookSettingsTab = {}
const SlackSettingsTab = {}
const AutoNotificationsSettingsTab = {}

mock.module('./email-settings', () => ({ EmailSettingsTab }))
mock.module('./dingtalk-settings', () => ({ DingTalkSettingsTab }))
mock.module('./wechat-settings', () => ({ WeChatSettingsTab }))
mock.module('./feishu-settings', () => ({ FeishuSettingsTab }))
mock.module('./webhook-settings', () => ({ WebhookSettingsTab }))
mock.module('./slack-settings', () => ({ SlackSettingsTab }))
mock.module('./auto-notifications-settings', () => ({ AutoNotificationsSettingsTab }))

const components = await import('./index')

test('re-exports the notification settings tabs', () => {
  expect(components).toMatchObject({
    EmailSettingsTab,
    DingTalkSettingsTab,
    WeChatSettingsTab,
    FeishuSettingsTab,
    WebhookSettingsTab,
    SlackSettingsTab,
    AutoNotificationsSettingsTab,
  })
})
