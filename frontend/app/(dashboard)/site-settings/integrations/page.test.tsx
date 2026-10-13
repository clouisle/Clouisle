import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getEmail = mock(() => Promise.resolve({ smtp_enabled: true }))
const getWebhook = mock(() => Promise.resolve({ webhook_enabled: true }))
const getFeishuConfig = mock(() => Promise.resolve({ app_id: 'app', app_secret_configured: true, department_ids: ['dept-1'] }))
const updateEmail = mock(() => Promise.resolve({}))
const sendTestEmail = mock(() => Promise.resolve())
const updateWebhook = mock(() => Promise.resolve({}))
const sendTestWebhook = mock(() => Promise.resolve())
const updateFeishuConfig = mock(() => Promise.resolve({ app_id: 'app', app_secret_configured: true }))
const getFeishuDepartments = mock(() => Promise.resolve([]))
const updateFeishuDepartmentScope = mock(() => Promise.resolve({ department_ids: ['dept-1'] }))
const syncFeishuContacts = mock(() => Promise.resolve({ created: 0, updated: 0, skipped: 0, teams_created: 0 }))
let canUpdate = true
let feishuProps: { config: { app_id: string; app_secret_configured: boolean; department_ids: string[] }; canUpdate: boolean } | null = null

mock.module('sonner', () => ({ toast: { error: mock(() => undefined) } }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/button', () => ({ Button: ({ children, onClick }: React.PropsWithChildren<{ onClick?: () => void }>) => <button onClick={onClick}>{children}</button> }))
mock.module('@/components/ui/switch', () => ({ Switch: (props: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean; 'aria-label': string }) => <button aria-label={props['aria-label']} data-checked={props.checked} checked={props.checked} disabled={props.disabled} onClick={() => { if (!props.disabled) props.onCheckedChange(!props.checked) }} /> }))
mock.module('@/components/ui/dialog', () => ({ Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div role="dialog">{children}</div> : null, DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>, DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>, DialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>, DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2> }))
mock.module('@/lib/api/admin/site-settings', () => ({ siteSettingsApi: { getEmail, getWebhook, getFeishuConfig, updateEmail, sendTestEmail, updateWebhook, sendTestWebhook, updateFeishuConfig, getFeishuDepartments, updateFeishuDepartmentScope, syncFeishuContacts } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => canUpdate }) }))
mock.module('./_components', () => ({
  EmailSettingsTab: ({ canUpdate: editable }: { canUpdate: boolean }) => <div data-email-editable={String(editable)} />,
  WebhookSettingsTab: ({ canUpdate: editable }: { canUpdate: boolean }) => <div data-webhook-editable={String(editable)} />,
  FeishuIntegrationTab: (props: typeof feishuProps) => {
    feishuProps = props
    return <div data-feishu-ready={String(Boolean(props?.config.app_secret_configured))} />
  },
}))

const { default: SiteSettingsIntegrationsPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsIntegrationsPage />)
  })
  return renderer!
}

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
  feishuProps = null
})

test('opens configuration by clicking the integration card', async () => {
  const renderer = await render()
  expect(getEmail).toHaveBeenCalledTimes(1)
  expect(getWebhook).toHaveBeenCalledTimes(1)
  expect(getFeishuConfig).toHaveBeenCalledTimes(1)
  expect(renderer.root.findAllByProps({ role: 'dialog' })).toHaveLength(0)
  const cards = renderer.root.findAllByProps({ role: 'button' }).filter(card => card.props.tabIndex === 0)
  expect(cards).toHaveLength(3)
  act(() => cards[2].props.onClick())
  expect(feishuProps?.config).toEqual({ app_id: 'app', app_secret_configured: true, department_ids: ['dept-1'] })
  expect(renderer.root.findByProps({ 'data-feishu-ready': 'true' })).toBeDefined()
  act(() => renderer.unmount())
})
test('persists email and webhook toggle changes without opening their cards', async () => {
  const renderer = await render()
  const emailSwitch = renderer.root.findByProps({ 'aria-label': 'email.smtpEnabled' })
  const webhookSwitch = renderer.root.findByProps({ 'aria-label': 'webhook.enabled' })
  await act(async () => emailSwitch.props.onCheckedChange(false))
  expect(renderer.root.findAllByProps({ role: 'dialog' })).toHaveLength(0)
  await act(async () => webhookSwitch.props.onCheckedChange(false))
  expect(renderer.root.findAllByProps({ role: 'dialog' })).toHaveLength(0)
  expect(updateEmail).toHaveBeenCalledWith({ smtp_enabled: false })
  expect(updateWebhook).toHaveBeenCalledWith({ webhook_enabled: false })
  act(() => renderer.unmount())
})



test('renders read-only integration switches as disabled', async () => {
  canUpdate = false
  const renderer = await render()
  expect(renderer.root.findByProps({ 'aria-label': 'email.smtpEnabled' }).props.disabled).toBe(true)
  expect(renderer.root.findByProps({ 'aria-label': 'webhook.enabled' }).props.disabled).toBe(true)
  expect(renderer.root.findAllByProps({ role: 'dialog' })).toHaveLength(0)
  act(() => renderer.unmount())
})
