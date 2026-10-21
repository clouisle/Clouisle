import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { Integration } from '@/lib/api/integrations'

let canUpdate = true
const instance: Integration = {
  id: 'wechat-1', name: 'wechat', provider_type: 'wechat', display_name: 'WeChat iLink',
  icon_url: null, button_text: null, is_enabled: true,
  enabled_capabilities: ['agent_chat'], supported_capabilities: ['agent_chat', 'knowledge_collection'],
  config: {}, credentials_configured: [], attribute_mapping: {},
  login_config: { allow_signup: false, require_approval: false, default_role_id: null },
  created_at: '', updated_at: '',
}
const list = mock(async () => [instance])
const update = mock(async (_id: string, data: { enabled_capabilities: string[] }) => ({ ...instance, enabled_capabilities: data.enabled_capabilities }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/link', () => ({ default: ({ children, ...props }: React.PropsWithChildren) => <a {...props}>{children}</a> }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => canUpdate }) }))
mock.module('@/lib/api/admin/integrations', () => ({ integrationsApi: { list, update } }))
mock.module('@/components/ui/card', () => ({ Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>, CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div> }))
mock.module('@/components/ui/switch', () => ({ Switch: (props: Record<string, unknown>) => <button {...props} /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.PropsWithChildren) => <button {...props}>{children}</button> }))
const { default: WeChatIntegrationPage } = await import('./page')
const renderers: ReactTestRenderer[] = []

async function render() {
  let renderer!: ReactTestRenderer
  await act(async () => { renderer = create(<WeChatIntegrationPage />) })
  renderers.push(renderer)
  return renderer
}
beforeEach(() => { canUpdate = true; mock.clearAllMocks() })
afterEach(() => { for (const renderer of renderers.splice(0)) act(() => renderer.unmount()) })

test('feature changes preserve the other selection and never send a master toggle', async () => {
  const renderer = await render()
  const agent = () => renderer.root.findByProps({ 'aria-label': 'integrations.capabilities.agent_chat' })
  const collection = () => renderer.root.findByProps({ 'aria-label': 'integrations.capabilities.knowledge_collection' })
  expect(agent().props.checked).toBe(true)
  expect(collection().props.checked).toBe(false)
  await act(async () => collection().props.onCheckedChange(true))
  const save = renderer.root.findAllByType('button').find(node => node.props.onClick && node.children.includes('save'))!
  await act(async () => save.props.onClick())
  expect(update).toHaveBeenCalledWith('wechat-1', { enabled_capabilities: ['agent_chat', 'knowledge_collection'] })
  expect(agent().props.checked).toBe(true)
  expect(collection().props.checked).toBe(true)
})

test('read-only viewers cannot mutate feature selection', async () => {
  canUpdate = false
  const renderer = await render()
  const control = renderer.root.findByProps({ 'aria-label': 'integrations.capabilities.knowledge_collection' })
  expect(control.props.disabled).toBe(true)
  await act(async () => control.props.onCheckedChange(true))
  expect(control.props.checked).toBe(false)
  expect(update).not.toHaveBeenCalled()
})
