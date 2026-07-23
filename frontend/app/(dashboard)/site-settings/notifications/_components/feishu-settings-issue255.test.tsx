import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const success = mock(() => {})
const normalizeValidationErrors = mock((error: unknown) => error as Record<string, string>)
const mapValidationErrors = mock((errors: Record<string, string>) =>
  Object.fromEntries(Object.entries(errors).map(([key, value]) => [key.replace('settings.', ''), value]))
)

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ ExternalLink: () => null, Loader2: () => null }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => {
    const next = { ...errors }
    delete next[key]
    return next
  },
  getValidationSummaryEntries: (errors: Record<string, string>, inline: string[]) =>
    Object.entries(errors).filter(([key]) => !inline.includes(key)),
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
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
  Switch: ({ onCheckedChange, ...props }: { onCheckedChange: (checked: boolean) => void }) =>
    <input type="checkbox" onChange={(event) => onCheckedChange(event.target.checked)} {...props} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))

import { siteSettingsApi, type FeishuSettings } from '@/lib/api/admin/site-settings'
import { FeishuSettingsTab } from './feishu-settings'

const settings: FeishuSettings = {
  feishu_enabled: true,
  feishu_notification_type: 'webhook',
  feishu_webhook_url: 'https://open.feishu.test/hook',
  feishu_secret: '',
  feishu_app_id: '',
  feishu_app_secret: '',
}
const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function render() {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<FeishuSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate />) })
  renderers.push(renderer!)
  return { renderer: renderer!, onSettingsChange }
}

const button = (renderer: ReactTestRenderer, label: string) =>
  renderer.root.findAllByType('button').find((item) => item.children.includes(label))!

beforeEach(() => {
  success.mockClear()
  normalizeValidationErrors.mockClear()
  mapValidationErrors.mockClear()
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
})

describe('FeishuSettingsTab Issue #255 callbacks and errors', () => {
  test('maps a rejected save field error and clears it when the field changes', async () => {
    const error = { 'settings.feishu_webhook_url': 'invalid webhook' }
    spyOn(siteSettingsApi, 'updateFeishu').mockRejectedValue(error)
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})
    const { renderer, onSettingsChange } = render()

    await act(async () => button(renderer, 'save').props.onClick())
    expect(renderer.root.findByProps({ id: 'feishu-webhook-url' }).props['aria-invalid']).toBe(true)
    expect(normalizeValidationErrors).toHaveBeenCalledWith(error)
    expect(consoleError).toHaveBeenCalledWith('Failed to save feishu settings:', error)

    act(() => renderer.root.findByProps({ id: 'feishu-webhook-url' }).props.onChange({ target: { value: 'https://open.feishu.test/next' } }))
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, feishu_webhook_url: 'https://open.feishu.test/next' })
    expect(renderer.root.findByProps({ id: 'feishu-webhook-url' }).props['aria-invalid']).toBe(false)
    expect(success).not.toHaveBeenCalled()
  })

  test('handles a rejected test send and restores the send button', async () => {
    const error = { feishu_webhook_url: 'provider rejected webhook' }
    spyOn(siteSettingsApi, 'sendTestFeishu').mockRejectedValue(error)
    const consoleError = spyOn(console, 'error').mockImplementation(() => {})
    const { renderer } = render()

    await act(async () => button(renderer, 'feishu.sendTest').props.onClick())

    expect(renderer.root.findByProps({ id: 'feishu-webhook-url' }).props['aria-invalid']).toBe(true)
    expect(button(renderer, 'feishu.sendTest').props.disabled).toBe(false)
    expect(consoleError).toHaveBeenCalledWith('Failed to send test feishu:', error)
    expect(success).not.toHaveBeenCalled()
  })
})
