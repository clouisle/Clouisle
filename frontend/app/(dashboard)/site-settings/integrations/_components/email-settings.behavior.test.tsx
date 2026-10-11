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
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean }) => (
    <input aria-label="smtp-enabled" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" {...props} />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children, ...props }: React.HTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))

import { siteSettingsApi, type EmailSettings } from '@/lib/api/admin/site-settings'
import { EmailSettingsTab } from './email-settings'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const settings: EmailSettings = {
  smtp_enabled: true,
  smtp_host: 'smtp.example.com',
  smtp_port: 587,
  smtp_encryption: 'tls',
  smtp_username: 'mailer',
  smtp_password: 'secret',
  email_from_name: 'Clouisle',
  email_from_address: 'noreply@example.com',
}

const renderers: ReactTestRenderer[] = []

function render(overrides: Partial<React.ComponentProps<typeof EmailSettingsTab>> = {}) {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<EmailSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate {...overrides} />)
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

describe('EmailSettingsTab', () => {
  test('exposes labelled SMTP fields and reports setting edits through its callback', () => {
    const { renderer, onSettingsChange } = render()
    const host = renderer.root.findByProps({ id: 'smtp-host' })

    expect(host.props).toMatchObject({ value: 'smtp.example.com', disabled: false, 'aria-invalid': false })
    act(() => host.props.onChange({ target: { value: 'mail.acme.test' } }))

    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, smtp_host: 'mail.acme.test' })
  })

  test('blocks invalid SMTP saves and identifies the invalid fields accessibly', async () => {
    const updateEmail = spyOn(siteSettingsApi, 'updateEmail')
    const { renderer } = render({ settings: { ...settings, smtp_host: '', email_from_address: '' } })

    await act(async () => button(renderer, 'save').props.onClick())

    expect(updateEmail).not.toHaveBeenCalled()
    expect(renderer.root.findByProps({ id: 'smtp-host' }).props['aria-invalid']).toBe(true)
    expect(renderer.root.findByProps({ id: 'from-address' }).props['aria-invalid']).toBe(true)
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(2)
  })

  test('sends test emails and saves valid settings with their expected API payloads', async () => {
    const sendTestEmail = spyOn(siteSettingsApi, 'sendTestEmail').mockResolvedValue()
    const updateEmail = spyOn(siteSettingsApi, 'updateEmail').mockResolvedValue({})
    const { renderer } = render()
    const testEmail = renderer.root.findByProps({ placeholder: 'email.testEmailPlaceholder' })

    act(() => testEmail.props.onChange({ target: { value: 'admin@acme.test' } }))
    await act(async () => button(renderer, 'email.sendTest').props.onClick())
    await act(async () => button(renderer, 'save').props.onClick())

    expect(sendTestEmail).toHaveBeenCalledWith('admin@acme.test')
    expect(updateEmail).toHaveBeenCalledWith(settings)
    expect(success).toHaveBeenCalledWith('testEmailSent')
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('hides update actions and disables settings fields for read-only viewers', () => {
    const { renderer } = render({ canUpdate: false })

    expect(renderer.root.findByProps({ id: 'smtp-host' }).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ 'aria-label': 'smtp-enabled' }).props.disabled).toBe(true)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('save'))).toBe(false)
    expect(renderer.root.findAllByProps({ placeholder: 'email.testEmailPlaceholder' })).toHaveLength(0)
  })
})
