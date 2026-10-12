import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getEmail = mock(() => Promise.resolve({ smtp_enabled: true }))
const getWebhook = mock(() => Promise.resolve({ webhook_enabled: true }))
const getFeishuConfig = mock(() => Promise.resolve({ app_id: 'app', app_secret_configured: true, department_ids: ['dept-1'] }))
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
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/lib/api/admin/site-settings', () => ({ siteSettingsApi: { getEmail, getWebhook, getFeishuConfig } }))
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

test('loads Feishu config and renders its configured integration card', async () => {
  const renderer = await render()
  expect(getEmail).toHaveBeenCalledTimes(1)
  expect(getWebhook).toHaveBeenCalledTimes(1)
  expect(getFeishuConfig).toHaveBeenCalledTimes(1)
  expect(feishuProps?.config).toEqual({ app_id: 'app', app_secret_configured: true, department_ids: ['dept-1'] })
  expect(renderer.root.findByProps({ 'data-feishu-ready': 'true' })).toBeDefined()
  act(() => renderer.unmount())
})

test('passes read-only permission to Feishu and other integration forms', async () => {
  canUpdate = false
  const renderer = await render()
  expect(feishuProps?.canUpdate).toBe(false)
  expect(renderer.root.findByProps({ 'data-email-editable': 'false' })).toBeDefined()
  expect(renderer.root.findByProps({ 'data-webhook-editable': 'false' })).toBeDefined()
  act(() => renderer.unmount())
})
