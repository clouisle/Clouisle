import { beforeAll, beforeEach, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from 'react-test-renderer'

import type { DingTalkSettings } from '@/lib/api/admin/site-settings'

const updateDingTalk = mock(async () => ({}))
const sendTestDingTalk = mock(async () => ({}))
const success = mock(() => undefined)

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({
  ExternalLink: 'mock-external-link',
  Loader2: 'mock-loader',
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { updateDingTalk, sendTestDingTalk },
}))

for (const [path, exports] of [
  ['@/components/ui/card', ['Card', 'CardContent', 'CardDescription', 'CardHeader', 'CardTitle']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
] as const) {
  mock.module(path, () => Object.fromEntries(exports.map((name) => [name, `mock-${name.toLowerCase()}`])))
}
mock.module('@/components/ui/input', () => ({ Input: 'mock-input' }))
mock.module('@/components/ui/label', () => ({ Label: 'mock-label' }))
mock.module('@/components/ui/button', () => ({ Button: 'mock-button' }))
mock.module('@/components/ui/switch', () => ({ Switch: 'mock-switch' }))
mock.module('@/components/ui/field', () => ({ FieldError: 'mock-field-error' }))

let DingTalkSettingsTab: typeof import('./dingtalk-settings').DingTalkSettingsTab

const settings: DingTalkSettings = {
  dingtalk_enabled: true,
  dingtalk_notification_type: 'webhook',
  dingtalk_webhook_url: 'https://example.test/hook',
  dingtalk_secret: 'secret',
  dingtalk_app_key: 'app-key',
  dingtalk_app_secret: 'app-secret',
  dingtalk_agent_id: 'agent-id',
}

function renderTab(onSettingsChange: (value: DingTalkSettings) => void): ReactTestRenderer {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(createElement(DingTalkSettingsTab, { settings, onSettingsChange, canUpdate: true }))
  })
  return renderer!
}

function findElements(renderer: ReactTestRenderer, type: string): ReactTestInstance[] {
  return renderer.root.findAll((node) => node.type === type)
}

beforeAll(async () => {
  ({ DingTalkSettingsTab } = await import('./dingtalk-settings'))
})

beforeEach(() => {
  updateDingTalk.mockClear()
  sendTestDingTalk.mockClear()
  success.mockClear()
})

describe('DingTalkSettingsTab callbacks', () => {
  test('reports switch, select, and input changes', () => {
    const onSettingsChange = mock(() => undefined)
    const tree = renderTab(onSettingsChange)

    findElements(tree, 'mock-switch')[0].props.onCheckedChange(false)
    const select = findElements(tree, 'mock-select')[0]
    select.props.onValueChange('')
    select.props.onValueChange('app')
    findElements(tree, 'mock-input')[0].props.onChange({ target: { value: 'https://new.test/hook' } })

    expect(onSettingsChange.mock.calls).toEqual([
      [{ ...settings, dingtalk_enabled: false }],
      [{ ...settings, dingtalk_notification_type: 'app' }],
      [{ ...settings, dingtalk_webhook_url: 'https://new.test/hook' }],
    ])
  })

  test('saves settings and sends a test notification', async () => {
    const tree = renderTab(() => undefined)
    const buttons = findElements(tree, 'mock-button')

    await act(async () => buttons[0].props.onClick())
    await act(async () => buttons[1].props.onClick())

    expect(sendTestDingTalk).toHaveBeenCalledTimes(1)
    expect(updateDingTalk).toHaveBeenCalledWith(settings)
    expect(success.mock.calls).toEqual([['dingtalk.testSent'], ['saveSuccess']])
  })
})
