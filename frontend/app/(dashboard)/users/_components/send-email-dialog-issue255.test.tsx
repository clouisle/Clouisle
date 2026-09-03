import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const sendEmail = mock(() => Promise.resolve({ sent_count: 2, skipped_count: 0 }))
const success = mock(() => {})
const warning = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))
mock.module('sonner', () => ({ toast: { success, warning } }))
mock.module('lucide-react', () => ({ Loader2: () => null }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { sendEmail } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  getValidationSummaryEntries: (errors: Record<string, string>, fields: string[]) =>
    fields.flatMap((field) => errors[field] ? [[field, errors[field]]] : []),
  normalizeValidationErrors: (error: { errors?: Record<string, string> }) => error.errors ?? {},
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))

const element = (tag: string) => {
  function Element({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
  return Element
}
mock.module('@/components/ui/dialog', () => ({
  Dialog: element('dialog'), DialogContent: element('section'), DialogDescription: element('p'),
  DialogFooter: element('footer'), DialogHeader: element('header'), DialogTitle: element('h2'),
}))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))

const { SendEmailDialog } = await import('./send-email-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []
const users = [
  { id: 'user-1', email: 'one@example.com' },
  { id: 'user-2', email: 'two@example.com' },
  { id: 'user-3', email: 'three@example.com' },
  { id: 'user-4', email: 'four@example.com' },
]

function render(overrides: Partial<React.ComponentProps<typeof SendEmailDialog>> = {}) {
  const onOpenChange = mock(() => {})
  const onSuccess = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<SendEmailDialog open users={users as never} onOpenChange={onOpenChange} onSuccess={onSuccess} {...overrides} />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onOpenChange, onSuccess }
}

const sendButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType('button').find((button) => button.children.includes('send'))!

beforeEach(() => {
  sendEmail.mockReset()
  sendEmail.mockResolvedValue({ sent_count: 2, skipped_count: 0 })
  success.mockClear()
  warning.mockClear()
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('SendEmailDialog issue #255 callbacks', () => {
  test('validates subject then content and clears each field error while editing', async () => {
    const { renderer } = render()

    await act(async () => sendButton(renderer).props.onClick())
    expect(renderer.root.findByProps({ id: 'subject' }).props['aria-invalid']).toBe(true)
    expect(sendEmail).not.toHaveBeenCalled()

    act(() => renderer.root.findByProps({ id: 'subject' }).props.onChange({ target: { value: 'Maintenance' } }))
    await act(async () => sendButton(renderer).props.onClick())
    expect(renderer.root.findByProps({ id: 'content' }).props['aria-invalid']).toBe(true)

    act(() => renderer.root.findByProps({ id: 'content' }).props.onChange({ target: { value: 'Tonight' } }))
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(0)
  })

  test('sends all recipients, reports success, closes, and invokes the success callback', async () => {
    const { renderer, onOpenChange, onSuccess } = render()
    act(() => {
      renderer.root.findByProps({ id: 'subject' }).props.onChange({ target: { value: 'Maintenance' } })
      renderer.root.findByProps({ id: 'content' }).props.onChange({ target: { value: 'Tonight' } })
    })

    await act(async () => sendButton(renderer).props.onClick())

    expect(sendEmail).toHaveBeenCalledWith(['user-1', 'user-2', 'user-3', 'user-4'], 'Maintenance', 'Tonight', { silent: true })
    expect(success).toHaveBeenCalledWith('emailSent:{"count":2}')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalled()
  })

  test('warns for partial delivery and displays normalized API field errors', async () => {
    const partial = render()
    act(() => {
      partial.renderer.root.findByProps({ id: 'subject' }).props.onChange({ target: { value: 'Notice' } })
      partial.renderer.root.findByProps({ id: 'content' }).props.onChange({ target: { value: 'Body' } })
    })
    sendEmail.mockResolvedValueOnce({ sent_count: 3, skipped_count: 1 })
    await act(async () => sendButton(partial.renderer).props.onClick())
    expect(warning).toHaveBeenCalledWith('emailSentPartial:{"sent":3,"skipped":1}')

    const failed = render()
    act(() => {
      failed.renderer.root.findByProps({ id: 'subject' }).props.onChange({ target: { value: 'Notice' } })
      failed.renderer.root.findByProps({ id: 'content' }).props.onChange({ target: { value: 'Body' } })
    })
    sendEmail.mockRejectedValueOnce({ errors: { subject: 'Subject rejected' } })
    await act(async () => sendButton(failed.renderer).props.onClick())
    expect(failed.renderer.root.findByProps({ id: 'subject' }).props['aria-invalid']).toBe(true)
    expect(JSON.stringify(failed.renderer.toJSON())).toContain('subject: Subject rejected')
  })

  test('shows the recipient preview and closes from cancel', () => {
    const { renderer, onOpenChange } = render()
    expect(JSON.stringify(renderer.toJSON())).toContain('one@example.com, two@example.com, three@example.com')
    expect(JSON.stringify(renderer.toJSON())).toContain('+1 more')

    act(() => renderer.root.findAllByType('button').find((button) => button.children.includes('cancel'))!.props.onClick())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
