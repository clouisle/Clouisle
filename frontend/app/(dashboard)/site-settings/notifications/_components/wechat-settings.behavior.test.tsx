import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const success = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ ExternalLink: () => null, Loader2: () => null }))

mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean }) => (
    <input aria-label="wechat-enabled" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" {...props} />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children, ...props }: React.HTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))

import { siteSettingsApi, type WeChatSettings } from '@/lib/api/admin/site-settings'
import { WeChatSettingsTab } from './wechat-settings'

const settings: WeChatSettings = {
  wechat_enabled: true,
  wechat_notification_type: 'webhook',
  wechat_webhook_url: 'https://qyapi.weixin.qq.test/cgi-bin/webhook/send?key=test',
  wechat_corp_id: '',
  wechat_agent_id: '',
  wechat_secret: '',
}

const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function render(overrides: Partial<React.ComponentProps<typeof WeChatSettingsTab>> = {}) {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<WeChatSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate {...overrides} />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onSettingsChange }
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => item.children.includes(label))!

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  success.mockClear()
})

describe('WeChatSettingsTab', () => {
  test('updates webhook fields and sends valid save and test requests', async () => {
    const updateWeChat = spyOn(siteSettingsApi, 'updateWeChat').mockResolvedValue({})
    const sendTestWeChat = spyOn(siteSettingsApi, 'sendTestWeChat').mockResolvedValue()
    const { renderer, onSettingsChange } = render()

    act(() => renderer.root.findByProps({ id: 'wechat-webhook-url' }).props.onChange({ target: { value: 'https://qyapi.weixin.qq.test/cgi-bin/webhook/send?key=next' } }))
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, wechat_webhook_url: 'https://qyapi.weixin.qq.test/cgi-bin/webhook/send?key=next' })

    await act(async () => button(renderer, 'wechat.sendTest').props.onClick())
    await act(async () => button(renderer, 'save').props.onClick())

    expect(sendTestWeChat).toHaveBeenCalled()
    expect(updateWeChat).toHaveBeenCalledWith(settings)
    expect(success).toHaveBeenCalledWith('wechat.testSent')
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('validates required webhook and app credentials', async () => {
    const updateWeChat = spyOn(siteSettingsApi, 'updateWeChat')
    const { renderer } = render({ settings: { ...settings, wechat_webhook_url: '' } })

    await act(async () => button(renderer, 'save').props.onClick())
    expect(updateWeChat).not.toHaveBeenCalled()
    expect(renderer.root.findByProps({ id: 'wechat-webhook-url' }).props['aria-invalid']).toBe(true)

    act(() => renderer.root.findByProps({ value: 'webhook' }).props.onValueChange('app'))
    const appSettings = { ...settings, wechat_notification_type: 'app' as const }
    const app = render({ settings: appSettings })
    await act(async () => button(app.renderer, 'save').props.onClick())
    expect(app.renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(3)
  })

  test('hides update actions and disables controls for read-only viewers', () => {
    const { renderer } = render({ canUpdate: false })

    expect(renderer.root.findByProps({ 'aria-label': 'wechat-enabled' }).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ id: 'wechat-webhook-url' }).props.disabled).toBe(true)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('save'))).toBe(false)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('wechat.sendTest'))).toBe(false)
  })
})
