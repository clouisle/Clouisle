import { expect, mock, test } from 'bun:test'

const EmailSettingsTab = {}
const WebhookSettingsTab = {}
const AutoNotificationsSettingsTab = {}

mock.module('./email-settings', () => ({ EmailSettingsTab }))
mock.module('./webhook-settings', () => ({ WebhookSettingsTab }))
mock.module('./auto-notifications-settings', () => ({ AutoNotificationsSettingsTab }))

const components = await import('./index')

test('re-exports the notification settings tabs', () => {
  expect(components).toMatchObject({
    EmailSettingsTab,
    WebhookSettingsTab,
    AutoNotificationsSettingsTab,
  })
})
