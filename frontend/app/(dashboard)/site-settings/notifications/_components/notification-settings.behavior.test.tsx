import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const success = mock(() => {})
const translate = Object.assign((key: string) => key, { has: () => true })

mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ Loader2: () => null }))

function element(tag: keyof React.JSX.IntrinsicElements) {
  function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
  return MockElement
}

mock.module('@/components/ui/card', () => ({
  Card: element('section'), CardContent: element('div'), CardDescription: element('p'),
  CardHeader: element('header'), CardTitle: element('h2'),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('span') }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) =>
    <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} {...props} />,
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: () => void }) =>
    <input type="checkbox" checked={checked} onChange={onCheckedChange} {...props} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: element('div'), SelectContent: element('div'), SelectItem: element('div'),
  SelectTrigger: element('button'), SelectValue: element('span'),
}))

import { ApiError } from '@/lib/api/client'
import { siteSettingsApi, type WebhookSettings } from '@/lib/api/admin/site-settings'
import { AutoNotificationsSettingsTab } from './auto-notifications-settings'
import { WebhookSettingsTab } from './webhook-settings'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []
const enabledChannels = {
  email: true, dingtalk: false, wechat: false, feishu: false, webhook: true, slack: false,
}
const webhookSettings: WebhookSettings = {
  webhook_enabled: true,
  webhook_url: 'https://hooks.example.test/notify',
  webhook_method: 'POST',
  webhook_headers: { Authorization: 'Bearer test' },
  webhook_body_template: '{"title":"{{title}}"}',
  webhook_secret: 'secret',
}

async function renderAuto(canUpdate = true) {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<AutoNotificationsSettingsTab enabledChannels={enabledChannels} canUpdate={canUpdate} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function renderWebhook(settings: WebhookSettings = webhookSettings) {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<WebhookSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onSettingsChange }
}

const button = (renderer: ReactTestRenderer, label: string) =>
  renderer.root.findAllByType('button').find((node) => node.children.includes(label))!

beforeEach(() => {
  success.mockClear()
  spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
})

describe('AutoNotificationsSettingsTab', () => {
  test('loads config, exposes only enabled providers, and saves user changes', async () => {
    spyOn(siteSettingsApi, 'getAutoNotifications').mockResolvedValue({
      channels: ['email'], enabled_types: ['team.member_added'],
    })
    const update = spyOn(siteSettingsApi, 'updateAutoNotifications').mockResolvedValue({
      channels: ['email', 'webhook'], enabled_types: [],
    })
    const renderer = await renderAuto()

    expect(renderer.root.findByProps({ id: 'global-email' }).props.checked).toBe(true)
    expect(renderer.root.findAllByProps({ id: 'global-dingtalk' })).toHaveLength(0)

    act(() => renderer.root.findByProps({ id: 'global-webhook' }).props.onCheckedChange())
    const firstType = renderer.root.findAll((node) => node.props.checked === true && node.props.onCheckedChange && !node.props.id)[0]
    act(() => firstType.props.onCheckedChange(false))
    await act(async () => button(renderer, 'save').props.onClick())

    expect(update).toHaveBeenCalledWith({ channels: ['email', 'webhook'], enabled_types: [] })
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('finishes loading after an API failure and maps save validation errors', async () => {
    spyOn(siteSettingsApi, 'getAutoNotifications').mockRejectedValue(new Error('offline'))
    const renderer = await renderAuto()
    expect(renderer.root.findByProps({ children: 'autoNotifications.title' })).toBeDefined()

    spyOn(siteSettingsApi, 'updateAutoNotifications').mockRejectedValue(new ApiError(1001, 'invalid', {
      errors: { channels: ['Choose a channel'] },
    }))
    await act(async () => button(renderer, 'save').props.onClick())

    expect(renderer.root.findAllByProps({ children: 'Choose a channel' }).length).toBeGreaterThan(0)
    expect(success).not.toHaveBeenCalled()
  })
})

describe('WebhookSettingsTab', () => {
  test('validates locally before crossing the provider boundary', async () => {
    const update = spyOn(siteSettingsApi, 'updateWebhook')
    const sendTest = spyOn(siteSettingsApi, 'sendTestWebhook')
    const { renderer } = renderWebhook({ ...webhookSettings, webhook_url: '' })

    await act(async () => button(renderer, 'save').props.onClick())
    await act(async () => button(renderer, 'webhook.sendTest').props.onClick())

    expect(update).not.toHaveBeenCalled()
    expect(sendTest).not.toHaveBeenCalled()
    expect(renderer.root.findByProps({ id: 'webhook-url' }).props['aria-invalid']).toBe(true)
  })

  test('saves settings and tests the provider only through mocked API methods', async () => {
    const update = spyOn(siteSettingsApi, 'updateWebhook').mockResolvedValue({})
    const sendTest = spyOn(siteSettingsApi, 'sendTestWebhook').mockResolvedValue()
    const { renderer } = renderWebhook()

    await act(async () => button(renderer, 'save').props.onClick())
    await act(async () => button(renderer, 'webhook.sendTest').props.onClick())

    expect(update).toHaveBeenCalledWith(webhookSettings)
    expect(sendTest).toHaveBeenCalledTimes(1)
    expect(success).toHaveBeenCalledWith('saveSuccess')
    expect(success).toHaveBeenCalledWith('webhook.testSent')
  })

  test('surfaces provider validation failures without reporting success', async () => {
    spyOn(siteSettingsApi, 'updateWebhook').mockRejectedValue(new ApiError(1001, 'invalid', {
      errors: { 'settings.webhook_url': ['URL is rejected'] },
    }))
    const { renderer } = renderWebhook()

    await act(async () => button(renderer, 'save').props.onClick())

    expect(renderer.root.findByProps({ children: 'URL is rejected' })).toBeDefined()
    expect(renderer.root.findByProps({ id: 'webhook-url' }).props['aria-invalid']).toBe(true)
    expect(success).not.toHaveBeenCalled()
  })
})
