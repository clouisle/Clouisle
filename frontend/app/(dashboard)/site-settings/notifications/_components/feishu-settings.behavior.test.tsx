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
    <input aria-label="feishu-enabled" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" {...props} />
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

import { siteSettingsApi, type FeishuSettings } from '@/lib/api/admin/site-settings'
import { FeishuSettingsTab } from './feishu-settings'

const settings: FeishuSettings = {
  feishu_enabled: true,
  feishu_notification_type: 'webhook',
  feishu_webhook_url: 'https://oapi.feishu.test/robot/send?access_token=test',
  feishu_secret: 'test-secret',
  feishu_app_id: '',
  feishu_app_secret: '',
}

const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function render(overrides: Partial<React.ComponentProps<typeof FeishuSettingsTab>> = {}) {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<FeishuSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate {...overrides} />)
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

describe('FeishuSettingsTab', () => {
  test('updates webhook fields and sends valid save and test requests', async () => {
    const updateFeishu = spyOn(siteSettingsApi, 'updateFeishu').mockResolvedValue({})
    const sendTestFeishu = spyOn(siteSettingsApi, 'sendTestFeishu').mockResolvedValue()
    const { renderer, onSettingsChange } = render()

    act(() => renderer.root.findByProps({ id: 'feishu-webhook-url' }).props.onChange({ target: { value: 'https://oapi.feishu.test/robot/send?access_token=next' } }))
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, feishu_webhook_url: 'https://oapi.feishu.test/robot/send?access_token=next' })

    await act(async () => button(renderer, 'feishu.sendTest').props.onClick())
    await act(async () => button(renderer, 'save').props.onClick())

    expect(sendTestFeishu).toHaveBeenCalled()
    expect(updateFeishu).toHaveBeenCalledWith(settings)
    expect(success).toHaveBeenCalledWith('feishu.testSent')
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('validates required webhook and app credentials', async () => {
    const updateFeishu = spyOn(siteSettingsApi, 'updateFeishu')
    const { renderer } = render({ settings: { ...settings, feishu_webhook_url: '' } })

    await act(async () => button(renderer, 'save').props.onClick())
    expect(updateFeishu).not.toHaveBeenCalled()
    expect(renderer.root.findByProps({ id: 'feishu-webhook-url' }).props['aria-invalid']).toBe(true)

    act(() => renderer.root.findByProps({ value: 'webhook' }).props.onValueChange('app'))
    const appSettings = { ...settings, feishu_notification_type: 'app' as const }
    const app = render({ settings: appSettings })
    await act(async () => button(app.renderer, 'save').props.onClick())
    expect(app.renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(2)
  })

  test('hides update actions and disables controls for read-only viewers', () => {
    const { renderer } = render({ canUpdate: false })

    expect(renderer.root.findByProps({ 'aria-label': 'feishu-enabled' }).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ id: 'feishu-webhook-url' }).props.disabled).toBe(true)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('save'))).toBe(false)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('feishu.sendTest'))).toBe(false)
  })
})
