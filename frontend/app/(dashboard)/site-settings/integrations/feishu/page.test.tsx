import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { FeishuConfig, Integration } from '@/lib/api/admin/integrations'

let isSuperuser = true
let permissions: Record<string, true> = {}
const feishu: FeishuConfig = { app_id: 'cli_1', app_secret_configured: true, department_ids: ['dept-a'], is_enabled: true }
const instances: Integration[] = [{
  id: 'feishu-1', name: 'feishu', display_name: 'Feishu', provider_type: 'feishu',
  icon_url: null, button_text: null, is_enabled: true,
  enabled_capabilities: ['directory_sync'], supported_capabilities: ['directory_sync', 'user_login', 'notification'],
  config: {}, attribute_mapping: {}, credentials_configured: [],
  login_config: { allow_signup: true, require_approval: false, default_role_id: null }, created_at: '', updated_at: '',
}]
let tabProps: { config: FeishuConfig; integration: Integration | null; canUpdate: boolean; canUpdateLogin: boolean; tab: string } | null = null
let knowledgeRenders = 0
let tabState = { value: '', onValueChange: (value: string) => { void value } }

mock.module('next/link', () => ({ default: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <a {...props}>{children}</a> }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: { is_superuser: isSuperuser, is_active: true } }) }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: (permission: string) => Boolean(permissions[permission]) }) }))
mock.module('@/lib/api/admin/integrations', () => ({
  integrationsApi: { getFeishuConfig: async () => feishu, list: async () => instances },
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ value, onValueChange, children }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) => {
    tabState = { value, onValueChange }
    return <div>{children}</div>
  },
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ value, children }: React.PropsWithChildren<{ value: string }>) => <button type="button" data-tab={value} onClick={() => tabState.onValueChange(value)}>{children}</button>,
  TabsContent: ({ value, children }: React.PropsWithChildren<{ value: string }>) => value === tabState.value ? <div data-panel={value}>{children}</div> : null,
}))
mock.module('../_components', () => ({
  FeishuIntegrationTab: (props: NonNullable<typeof tabProps>) => { tabProps = props; return <div data-config /> },
  FeishuKnowledgeSync: () => { knowledgeRenders += 1; return <div data-knowledge /> },
}))

const { default: FeishuIntegrationPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

beforeEach(() => {
  isSuperuser = true
  permissions = { 'admin:integrations:settings:update': true, 'admin:integrations:login:update': true }
  tabProps = null
  knowledgeRenders = 0
})
afterEach(() => {
  act(() => renderers.splice(0).forEach((renderer) => renderer.unmount()))
  mock.clearAllMocks()
})

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => { renderer = create(<FeishuIntegrationPage />) })
  renderers.push(renderer!)
  return renderer!
}

test('opens on the configuration tab with the loaded Feishu app configuration', async () => {
  await render()

  expect(tabProps?.config).toEqual(feishu)
  expect(tabProps?.integration?.id).toBe('feishu-1')
  expect(tabProps?.canUpdate).toBe(true)
  expect(tabProps?.canUpdateLogin).toBe(true)
  expect(knowledgeRenders).toBe(0)
})

test('exposes dedicated directory and notification tabs', async () => {
  const renderer = await render()
  await act(async () => renderer.root.findByProps({ 'data-tab': 'directory' }).props.onClick())
  expect(tabProps?.tab).toBe('directory')
  expect(renderer.root.findAllByProps({ 'data-config': true })).toHaveLength(1)
  await act(async () => renderer.root.findByProps({ 'data-tab': 'notification' }).props.onClick())
  expect(tabProps?.tab).toBe('notification')
  expect(renderer.root.findAllByProps({ 'data-config': true })).toHaveLength(1)
})

test('switches to the embedded knowledge sync panel for system superusers', async () => {
  const renderer = await render()
  await act(async () => renderer.root.findByProps({ 'data-tab': 'knowledge' }).props.onClick())

  expect(renderer.root.findAllByProps({ 'data-knowledge': true })).toHaveLength(1)
  expect(renderer.root.findAllByProps({ 'data-panel': 'configuration' })).toHaveLength(0)
  expect(renderer.root.findByProps({ href: '/site-settings/integrations' })).toBeDefined()
})

test('keeps the knowledge sync panel away from delegated administrators', async () => {
  isSuperuser = false
  permissions = { 'admin:integrations:settings:update': true }
  const renderer = await render()

  expect(renderer.root.findAllByProps({ 'data-tab': 'knowledge' })).toHaveLength(0)
  expect(renderer.root.findAllByProps({ 'data-knowledge': true })).toHaveLength(0)
  expect(tabProps?.canUpdateLogin).toBe(false)
})
