import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const success = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ Loader2: () => null }))

mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean }) => (
    <input aria-label="webhook-enabled" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" {...props} />
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

import { siteSettingsApi, type WebhookSettings } from '@/lib/api/admin/site-settings'
import { WebhookSettingsTab } from './webhook-settings'

const settings: WebhookSettings = {
  webhook_enabled: true,
  webhook_url: 'https://example.com/webhook',
  webhook_method: 'POST',
  webhook_headers: { Authorization: 'Bearer test' },
  webhook_body_template: '{"title":"{{title}}"}',
  webhook_secret: 'secret',
}

const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function render(overrides: Partial<React.ComponentProps<typeof WebhookSettingsTab>> = {}) {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<WebhookSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate {...overrides} />)
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

describe('WebhookSettingsTab', () => {
  test('updates endpoint fields and saves or sends tests', async () => {
    const updateWebhook = spyOn(siteSettingsApi, 'updateWebhook').mockResolvedValue({})
    const sendTestWebhook = spyOn(siteSettingsApi, 'sendTestWebhook').mockResolvedValue()
    const { renderer, onSettingsChange } = render()

    act(() => renderer.root.findByProps({ id: 'webhook-url' }).props.onChange({ target: { value: 'https://example.com/next' } }))
    act(() => renderer.root.findByProps({ value: 'POST' }).props.onValueChange('GET'))
    act(() => renderer.root.findByProps({ id: 'webhook-headers' }).props.onChange({ target: { value: '{"X-Test":"1"}' } }))
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, webhook_url: 'https://example.com/next' })
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, webhook_method: 'GET' })
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, webhook_headers: { 'X-Test': '1' } })

    await act(async () => button(renderer, 'webhook.sendTest').props.onClick())
    await act(async () => button(renderer, 'save').props.onClick())
    expect(sendTestWebhook).toHaveBeenCalled()
    expect(updateWebhook).toHaveBeenCalledWith(settings)
    expect(success).toHaveBeenCalledWith('webhook.testSent')
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('validates required URL and invalid header JSON', async () => {
    const updateWebhook = spyOn(siteSettingsApi, 'updateWebhook')
    const { renderer } = render({ settings: { ...settings, webhook_url: '' } })

    act(() => renderer.root.findByProps({ id: 'webhook-headers' }).props.onChange({ target: { value: '{bad' } }))
    await act(async () => button(renderer, 'save').props.onClick())

    expect(updateWebhook).not.toHaveBeenCalled()
    expect(renderer.root.findByProps({ id: 'webhook-url' }).props['aria-invalid']).toBe(true)
    expect(renderer.root.findByProps({ id: 'webhook-headers' }).props['aria-invalid']).toBe(true)
  })

  test('hides update actions and disables controls for read-only viewers', () => {
    const { renderer } = render({ canUpdate: false })

    expect(renderer.root.findByProps({ 'aria-label': 'webhook-enabled' }).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ id: 'webhook-url' }).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ id: 'webhook-headers' }).props.disabled).toBe(true)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('save'))).toBe(false)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('webhook.sendTest'))).toBe(false)
  })
})
