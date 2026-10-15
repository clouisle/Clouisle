import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

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
import { siteSettingsApi } from '@/lib/api/admin/site-settings'
import { AutoNotificationsSettingsTab } from './auto-notifications-settings'
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

async function renderAuto(canUpdate = true) {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<AutoNotificationsSettingsTab canUpdate={canUpdate} />)
  })
  renderers.push(renderer!)
  return renderer!
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
  test('loads config, exposes only supported providers, and saves user changes', async () => {
    spyOn(siteSettingsApi, 'getAutoNotifications').mockResolvedValue({
      channels: ['email', 'dingtalk', 'wechat', 'feishu', 'slack'],
      enabled_types: ['team.member_added'],
    })
    const update = spyOn(siteSettingsApi, 'updateAutoNotifications').mockResolvedValue({
      channels: ['email', 'webhook', 'feishu'], enabled_types: [],
    })
    const renderer = await renderAuto()

    expect(renderer.root.findByProps({ id: 'global-email' }).props.checked).toBe(true)
    expect(renderer.root.findByProps({ id: 'global-webhook' }).props.checked).toBe(false)
    expect(renderer.root.findAll((node) => typeof node.props.id === 'string' && node.props.id.startsWith('global-')).map((node) => node.props.id)).toEqual(['global-email', 'global-email', 'global-webhook', 'global-webhook', 'global-feishu', 'global-feishu'])

    act(() => renderer.root.findByProps({ id: 'global-webhook' }).props.onCheckedChange())
    const firstType = renderer.root.findAll((node) => node.props.checked === true && node.props.onCheckedChange && !node.props.id)[0]
    act(() => firstType.props.onCheckedChange(false))
    await act(async () => button(renderer, 'save').props.onClick())

    expect(update).toHaveBeenCalledWith({ channels: ['email', 'feishu', 'webhook'], enabled_types: [] })
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

