import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { Integration, IntegrationType } from '@/lib/api/integrations'

const builtin = (provider_type: 'email' | 'webhook' | 'feishu'): Integration => ({
  id: provider_type, name: provider_type, display_name: provider_type, provider_type,
  icon_url: null, button_text: null, is_enabled: true,
  enabled_capabilities: [provider_type === 'feishu' ? 'directory_sync' : 'notification'],
  supported_capabilities: provider_type === 'feishu' ? ['directory_sync', 'user_login'] : ['notification'],
  config: {}, attribute_mapping: {}, credentials_configured: [],
  login_config: { allow_signup: true, require_approval: false, default_role_id: null }, created_at: '', updated_at: '',
})
const login: Integration = { ...builtin('email'), id: 'login-1', name: 'company', display_name: 'Company Login', provider_type: 'oidc', enabled_capabilities: ['user_login'], supported_capabilities: ['user_login'] }
const catalog: IntegrationType[] = [
  { provider_type: 'oidc', display_name: 'OpenID Connect', supported_capabilities: ['user_login'], singleton: false },
  { provider_type: 'feishu', display_name: 'Feishu', supported_capabilities: ['directory_sync', 'user_login'], singleton: true },
]
const list = mock(async () => [builtin('email'), builtin('webhook'), builtin('feishu'), login])
const types = mock(async () => catalog)
const getEmail = mock(async () => ({ smtp_enabled: true }))
const getWebhook = mock(async () => ({ webhook_enabled: true }))
const feishu = { app_id: 'app', app_secret_configured: true, department_ids: ['dept-1'], is_enabled: true }
const getFeishuConfig = mock(async () => feishu)
const updateEmail = mock(async () => ({ smtp_enabled: false }))
const updateWebhook = mock(async () => ({ webhook_enabled: false }))
const updateFeishuConfig = mock(async () => ({ ...feishu, is_enabled: false }))
const update = mock(async () => login)
const remove = mock(async () => undefined)
const testConnection = mock(async () => ({ status: 'success', message: 'Connected' }))
const toastSuccess = mock(() => undefined)
const toastError = mock(() => undefined)
let permissions: Record<string, true> = {}
let dialogProps: { open: boolean; provider: Integration | null; types: IntegrationType[]; onClose: (success?: boolean) => void } | null = null
let feishuProps: { config: typeof feishu; canUpdate: boolean; integration: Integration | null; canUpdateLogin: boolean } | null = null

mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.PropsWithChildren) => <section {...props}>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/switch', () => ({ Switch: (props: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean; 'aria-label': string }) => <button {...props} /> }))
mock.module('@/components/ui/dialog', () => ({ Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div role="dialog">{children}</div> : null, DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>, DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>, DialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>, DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2> }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div role="alertdialog">{children}</div> : null,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren) => <button {...props}>{children}</button>,
}))
mock.module('@/lib/api/admin/integrations', () => ({ integrationsApi: { list, types, getEmail, getWebhook, getFeishuConfig, updateEmail, updateWebhook, updateFeishuConfig, update, delete: remove, testConnection } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: (permission: string) => Boolean(permissions[permission]) }) }))
mock.module('./_components', () => ({
  EmailSettingsTab: ({ canUpdate }: { canUpdate: boolean }) => <div data-email-editable={String(canUpdate)} />,
  WebhookSettingsTab: ({ canUpdate }: { canUpdate: boolean }) => <div data-webhook-editable={String(canUpdate)} />,
  FeishuIntegrationTab: (props: NonNullable<typeof feishuProps>) => { feishuProps = props; return <div data-feishu-ready={String(props.config.app_secret_configured)} /> },
}))
mock.module('./_components/login-integration-dialog', () => ({ LoginIntegrationDialog: (props: NonNullable<typeof dialogProps>) => { dialogProps = props; return props.open ? <div data-login-editor={props.provider?.id || 'new'} /> : null } }))

const { default: SiteSettingsIntegrationsPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []
async function render() {
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<SiteSettingsIntegrationsPage />) })
  renderers.push(renderer!)
  return renderer!
}
beforeEach(() => {
  permissions = { 'admin:integrations:login:read': true, 'admin:integrations:settings:read': true, 'admin:integrations:login:update': true, 'admin:integrations:settings:update': true }
  dialogProps = null
  feishuProps = null
})
afterEach(() => {
  act(() => renderers.splice(0).forEach((renderer) => renderer.unmount()))
  mock.clearAllMocks()
})

test('lists login integrations alongside builtins and opens existing configuration forms', async () => {
  const renderer = await render()
  expect(renderer.root.findAllByType('section').filter((node) => node.props['data-integration-id'])).toHaveLength(4)
  const feishuCard = renderer.root.findByProps({ 'data-integration-id': 'feishu' })
  expect(feishuCard.findAllByType('span').map((badge) => badge.children.join(''))).toEqual([
    'integrations.capabilities.directory_sync: integrations.enabled',
    'integrations.capabilities.user_login: integrations.disabled',
  ])
  act(() => feishuCard.findAllByProps({ 'aria-label': 'integrations.feishu', type: 'button' }).find((node) => node.props.onClick)?.props.onClick())
  expect(feishuProps?.config).toEqual(feishu)
  expect(feishuProps?.integration).toEqual(builtin('feishu'))
  expect(feishuProps?.canUpdateLogin).toBe(true)
  expect(renderer.root.findByProps({ 'data-feishu-ready': 'true' })).toBeDefined()
  expect(dialogProps?.open).toBe(false)
  act(() => renderer.root.findByProps({ 'aria-label': 'Company Login', type: 'button' }).props.onClick())
  expect(dialogProps?.provider).toEqual(login)
})

test('persists builtin and login toggles through their separate contracts', async () => {
  const renderer = await render()
  await act(async () => renderer.root.findByProps({ 'aria-label': 'email.smtpEnabled' }).props.onCheckedChange(false))
  await act(async () => renderer.root.findByProps({ 'aria-label': 'webhook.enabled' }).props.onCheckedChange(false))
  await act(async () => renderer.root.findAllByProps({ 'aria-label': 'integrations.feishu' }).find((node) => node.props.onCheckedChange)?.props.onCheckedChange(false))
  await act(async () => renderer.root.findByProps({ 'aria-label': 'Company Login: enabled' }).props.onCheckedChange(false))
  expect(updateEmail).toHaveBeenCalledWith({ smtp_enabled: false })
  expect(updateWebhook).toHaveBeenCalledWith({ webhook_enabled: false })
  expect(updateFeishuConfig).toHaveBeenCalledWith({ is_enabled: false })
  expect(update).toHaveBeenCalledWith('login-1', { is_enabled: false })
  expect(renderer.root.findAllByProps({ role: 'dialog' })).toHaveLength(0)
})

test('opens creation, tests a login connection, and deletes after confirmation', async () => {
  const renderer = await render()
  act(() => renderer.root.findAllByType('button').find((node) => node.children.includes('addProvider'))?.props.onClick())
  expect(dialogProps?.open).toBe(true)
  expect(dialogProps?.provider).toBeNull()
  expect(dialogProps?.types.map((type) => type.provider_type)).toEqual(['oidc'])
  await act(async () => renderer.root.findAllByType('button').find((node) => node.children.includes('testConnection'))?.props.onClick())
  expect(testConnection).toHaveBeenCalledWith('login-1')
  expect(toastSuccess).toHaveBeenCalledWith('Connected')
  act(() => renderer.root.findByProps({ 'aria-label': 'deleteProvider: Company Login' }).props.onClick())
  expect(remove).not.toHaveBeenCalled()
  await act(async () => renderer.root.findAllByType('button').find((node) => node.children.includes('delete'))?.props.onClick())
  expect(remove).toHaveBeenCalledWith('login-1')
  expect(renderer.root.findAllByProps({ 'data-integration-id': 'login-1' })).toHaveLength(0)
})

test('login-only readers never request builtin config or display builtin instances', async () => {
  permissions = { 'admin:integrations:login:read': true }
  const renderer = await render()
  expect(getEmail).not.toHaveBeenCalled()
  expect(getWebhook).not.toHaveBeenCalled()
  expect(getFeishuConfig).not.toHaveBeenCalled()
  expect(renderer.root.findAllByType('section').filter((node) => node.props['data-integration-id'])).toHaveLength(1)
  expect(renderer.root.findByProps({ 'aria-label': 'Company Login: enabled' }).props.disabled).toBe(true)
  await act(async () => renderer.root.findByProps({ 'aria-label': 'Company Login: enabled' }).props.onCheckedChange(false))
  expect(update).not.toHaveBeenCalled()
})

test('builtin-only readers keep login instances and login edit privilege isolated', async () => {
  permissions = { 'admin:integrations:settings:read': true, 'admin:integrations:login:update': true }
  const renderer = await render()
  expect(renderer.root.findAllByProps({ 'data-integration-id': 'login-1' })).toHaveLength(0)
  expect(renderer.root.findByProps({ 'aria-label': 'email.smtpEnabled' }).props.disabled).toBe(true)
  expect(dialogProps).toBeNull()
})
