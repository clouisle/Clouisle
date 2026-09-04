import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

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
    <input aria-label="slack-enabled" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" {...props} />
  ),
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))

import { siteSettingsApi, type SlackSettings } from '@/lib/api/admin/site-settings'
import { SlackSettingsTab } from './slack-settings'

const settings: SlackSettings = {
  slack_enabled: true,
  slack_webhook_url: 'https://hooks.slack.test/services/test',
}

const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function render(overrides: Partial<React.ComponentProps<typeof SlackSettingsTab>> = {}) {
  const onSettingsChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<SlackSettingsTab settings={settings} onSettingsChange={onSettingsChange} canUpdate {...overrides} />)
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

describe('SlackSettingsTab', () => {
  test('updates webhook fields and sends valid save and test requests', async () => {
    const updateSlack = spyOn(siteSettingsApi, 'updateSlack').mockResolvedValue({})
    const sendTestSlack = spyOn(siteSettingsApi, 'sendTestSlack').mockResolvedValue()
    const { renderer, onSettingsChange } = render()

    act(() => renderer.root.findByProps({ id: 'slack-webhook-url' }).props.onChange({ target: { value: 'https://hooks.slack.test/services/next' } }))
    expect(onSettingsChange).toHaveBeenCalledWith({ ...settings, slack_webhook_url: 'https://hooks.slack.test/services/next' })

    await act(async () => button(renderer, 'slack.sendTest').props.onClick())
    await act(async () => button(renderer, 'save').props.onClick())

    expect(sendTestSlack).toHaveBeenCalled()
    expect(updateSlack).toHaveBeenCalledWith(settings)
    expect(success).toHaveBeenCalledWith('slack.testSent')
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('validates required webhook before saving', async () => {
    const updateSlack = spyOn(siteSettingsApi, 'updateSlack')
    const { renderer } = render({ settings: { ...settings, slack_webhook_url: '' } })

    await act(async () => button(renderer, 'save').props.onClick())

    expect(updateSlack).not.toHaveBeenCalled()
    expect(renderer.root.findByProps({ id: 'slack-webhook-url' }).props['aria-invalid']).toBe(true)
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(1)
  })

  test('hides update actions and disables controls for read-only viewers', () => {
    const { renderer } = render({ canUpdate: false })

    expect(renderer.root.findByProps({ 'aria-label': 'slack-enabled' }).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ id: 'slack-webhook-url' }).props.disabled).toBe(true)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('save'))).toBe(false)
    expect(renderer.root.findAllByType('button').some((item) => item.children.includes('slack.sendTest'))).toBe(false)
  })
})
