import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const updateEmail = mock(async () => ({}))
const sendTestEmail = mock(async () => ({}))
const toastSuccess = mock(() => {})

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api/admin/site-settings', () => ({ siteSettingsApi: { updateEmail, sendTestEmail } }))
mock.module('lucide-react', () => ({ Loader2: () => <span>loading</span> }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CardDescription: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CardHeader: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CardTitle: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, disabled }: { checked: boolean; onCheckedChange: (value: boolean) => void; disabled: boolean }) => (
    <input type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onCheckedChange(event.target.checked)} />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange, disabled }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void; disabled: boolean }>) => (
    <select value={value} disabled={disabled} onChange={(event) => onValueChange(event.target.value)}>{children}</select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) => children ? <span role="alert">{children}</span> : null,
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => field !== key)),
  getValidationSummaryEntries: (errors: Record<string, string>, inline: string[]) => Object.entries(errors).filter(([field]) => !inline.includes(field)),
  mapValidationErrors: (errors: Record<string, string>, paths: Record<string, string>) => Object.fromEntries(Object.entries(errors).map(([field, message]) => [paths[field] ?? field, message])),
  normalizeValidationErrors: (error: { errors?: Record<string, string> }) => error.errors ?? {},
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const { EmailSettingsTab } = await import('./email-settings')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const settings = {
  smtp_enabled: true,
  smtp_host: 'smtp.example.com',
  smtp_port: 587,
  smtp_encryption: 'tls' as const,
  smtp_username: 'user',
  smtp_password: 'secret',
  email_from_name: 'Clouisle',
  email_from_address: 'sender@example.com',
}
const renderers: ReactTestRenderer[] = []

afterEach(() => {
  updateEmail.mockReset()
  updateEmail.mockResolvedValue({})
  sendTestEmail.mockReset()
  sendTestEmail.mockResolvedValue({})
  toastSuccess.mockClear()
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(overrides: Partial<React.ComponentProps<typeof EmailSettingsTab>> = {}) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<EmailSettingsTab settings={settings} onSettingsChange={() => {}} canUpdate {...overrides} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function button(renderer: ReactTestRenderer, text: string) {
  return renderer.root.findAllByType('button').find((candidate) => candidate.findAll((node) => node.children.includes(text)).length > 0)!
}

function testEmailInput(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'email.testEmailPlaceholder')!
}

describe('email settings callbacks and errors', () => {
  test('forwards field callback values and applies the SMTP port fallback', () => {
    const onSettingsChange = mock(() => {})
    const renderer = render({ onSettingsChange })

    act(() => renderer.root.findByProps({ id: 'smtp-host' }).props.onChange({ target: { value: 'mail.example.com' } }))
    expect(onSettingsChange).toHaveBeenLastCalledWith({ ...settings, smtp_host: 'mail.example.com' })

    act(() => renderer.root.findByProps({ id: 'smtp-port' }).props.onChange({ target: { value: '' } }))
    expect(onSettingsChange).toHaveBeenLastCalledWith({ ...settings, smtp_port: 587 })

    act(() => renderer.root.findByType('select').props.onChange({ target: { value: 'ssl' } }))
    expect(onSettingsChange).toHaveBeenLastCalledWith({ ...settings, smtp_encryption: 'ssl' })

    act(() => renderer.root.findByProps({ type: 'checkbox' }).props.onChange({ target: { checked: false } }))
    expect(onSettingsChange).toHaveBeenLastCalledWith({ ...settings, smtp_enabled: false })
  })

  test('hides actions and disables settings callbacks without update permission', () => {
    const renderer = render({ canUpdate: false })

    expect(renderer.root.findAllByType('button')).toHaveLength(0)
    expect(renderer.root.findAllByType('input').every((input) => input.props.disabled)).toBe(true)
    expect(renderer.root.findByType('select').props.disabled).toBe(true)
  })

  test('validates required save fields, then reports a successful save', async () => {
    const invalid = render({ settings: { ...settings, smtp_host: ' ', email_from_address: '' } })

    await act(async () => button(invalid, 'save').props.onClick())
    expect(updateEmail).not.toHaveBeenCalled()
    expect(invalid.root.findAllByProps({ role: 'alert' }).map((node) => node.children[0])).toEqual(['required', 'required'])

    const valid = render()
    await act(async () => button(valid, 'save').props.onClick())
    expect(updateEmail).toHaveBeenCalledWith(settings)
    expect(toastSuccess).toHaveBeenCalledWith('saveSuccess')
  })

  test('maps save and test-email API errors and clears the test error on change', async () => {
    updateEmail.mockRejectedValueOnce({ errors: { 'settings.smtp_host': 'bad host', other: 'summary error' } })
    sendTestEmail.mockRejectedValueOnce({ errors: { email: 'invalid recipient' } })
    const consoleError = mock(() => {})
    const originalConsoleError = console.error
    console.error = consoleError
    const renderer = render()

    await act(async () => button(renderer, 'save').props.onClick())
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children[0])).toEqual(['summary error', 'bad host'])

    await act(async () => button(renderer, 'email.sendTest').props.onClick())
    expect(sendTestEmail).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' }).at(-1)!.children).toEqual(['testEmailRequired'])

    act(() => testEmailInput(renderer).props.onChange({ target: { value: 'person@example.com' } }))
    await act(async () => button(renderer, 'email.sendTest').props.onClick())
    expect(sendTestEmail).toHaveBeenCalledWith('person@example.com')
    expect(renderer.root.findAllByProps({ role: 'alert' }).at(-1)!.children).toEqual(['invalid recipient'])
    expect(consoleError).toHaveBeenCalledWith('Failed to save email settings:', expect.anything())
    expect(consoleError).toHaveBeenCalledWith('Failed to send test email:', expect.anything())
    console.error = originalConsoleError
  })

  test('sends a test email successfully', async () => {
    const renderer = render()
    act(() => testEmailInput(renderer).props.onChange({ target: { value: 'person@example.com' } }))

    await act(async () => button(renderer, 'email.sendTest').props.onClick())

    expect(sendTestEmail).toHaveBeenCalledWith('person@example.com')
    expect(toastSuccess).toHaveBeenCalledWith('testEmailSent')
  })
})
