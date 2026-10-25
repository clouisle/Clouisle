import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const success = mock(() => {})
const error = mock(() => {})

const translateCalls: Array<[string, Record<string, unknown> | undefined]> = []
const translate = (key: string, values?: Record<string, unknown>) => {
  translateCalls.push([key, values])
  return key
}

mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('lucide-react', () => ({
  Check: () => null,
  ChevronDown: () => null,
  ChevronRight: () => null,
  Copy: () => null,
  Loader2: () => null,
  RefreshCw: () => null,
  Save: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ onCheckedChange, checked, ...props }: { onCheckedChange?: (value: boolean) => void; checked?: boolean }) => (
    <input
      type="checkbox"
      checked={Boolean(checked)}
      onChange={(event) => onCheckedChange?.(event.target.checked)}
      {...props}
    />
  ),
}))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: React.PropsWithChildren) => <div>{children}</div> }))
mock.module('@/components/ui/switch', () => ({ Switch: (props: { checked: boolean; onCheckedChange: (checked: boolean) => void; disabled?: boolean; 'aria-label': string }) => <button {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren) => <div data-testid="select-control" {...props}>{children}</div>,
  SelectTrigger: ({ children, ...props }: React.PropsWithChildren) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren<{ value: string }>) => <div>{children}</div>,
}))

import { integrationsApi, type FeishuAgentChatConfig, type FeishuConfig, type Integration } from '@/lib/api/admin/integrations'
import { FeishuIntegrationTab } from './feishu-integration'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const config: FeishuConfig = {
  app_id: 'cli_1',
  app_secret_configured: true,
  department_ids: [],
  is_enabled: true,
}

const agentChatConfig: FeishuAgentChatConfig = {
  connection_mode: 'callback',
  event_verification_token_configured: true,
  event_encrypt_key_configured: false,
  is_enabled: true,
  capability_enabled: true,
  receiver_status: { state: 'callback', managed: false },
}


const integration: Integration = {
  id: 'feishu-1',
  name: 'feishu',
  display_name: 'Feishu',
  provider_type: 'feishu',
  icon_url: null,
  button_text: null,
  is_enabled: true,
  enabled_capabilities: ['agent_chat'],
  supported_capabilities: ['directory_sync', 'user_login', 'notification', 'agent_chat'],
  config: {},
  attribute_mapping: {},
  credentials_configured: [],
  login_config: { allow_signup: true, require_approval: false, default_role_id: null },
  created_at: '',
  updated_at: '',
}

const renderers: ReactTestRenderer[] = []

function render(props: {
  canUpdate?: boolean
  integration?: Integration | null
  config?: FeishuConfig
} = {}) {
  const onConfigChange = mock(() => {})
  const onIntegrationChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(
      <FeishuIntegrationTab
        config={props.config ?? config}
        onConfigChange={onConfigChange}
        canUpdate={props.canUpdate ?? true}
        integration={props.integration === undefined ? integration : props.integration}
        canUpdateLogin
        onIntegrationChange={onIntegrationChange}
        tab="agentChat"
      />
    )
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onConfigChange, onIntegrationChange }
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root.findByProps({ 'data-testid': 'feishu-agent-chat-save' })

beforeEach(() => {
  spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
  spyOn(integrationsApi, 'getFeishuAgentChatConfig').mockResolvedValue(agentChatConfig)
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  success.mockClear()
  error.mockClear()
  translateCalls.length = 0
})

describe('FeishuIntegrationTab agent chat tab', () => {

  test('shows the event callback URL that must be registered with Feishu', async () => {
    const { renderer } = render()

    await act(async () => {})

    const code = renderer.root.findByProps({ id: 'feishu-agent-chat-callback-url' })
    expect(String(code.children[0])).toContain('/api/v1/integrations/feishu/callback')
  })


  test('sends a freshly typed secret only when it changed', async () => {
    const update = spyOn(integrationsApi, 'updateFeishuAgentChatConfig').mockResolvedValue(agentChatConfig)
    const { renderer } = render()

    await act(async () => {})
    await act(async () => {
      renderer.root.findByProps({ id: 'feishu-agent-chat-encrypt-key' })
        .props.onChange({ target: { value: 'new-encrypt-key' } })
    })

    await act(async () => saveButton(renderer).props.onClick())

    expect(update).toHaveBeenCalledWith({
      connection_mode: 'callback',
      event_encrypt_key: 'new-encrypt-key',
    })
  })

  test('shows the configured-secret placeholder only for stored secrets', async () => {
    const { renderer } = render()

    await act(async () => {})

    expect(renderer.root.findByProps({ id: 'feishu-agent-chat-verification-token' }).props.placeholder)
      .toBe('integrations.feishuSecretConfigured')
    expect(renderer.root.findByProps({ id: 'feishu-agent-chat-encrypt-key' }).props.placeholder)
      .toBe('')
  })

  test('keeps the save button disabled until something changes', async () => {
    const { renderer } = render()

    await act(async () => {})

    expect(saveButton(renderer).props.disabled).toBe(true)
  })

  test('reports a failed save with the localized fallback', async () => {
    spyOn(integrationsApi, 'updateFeishuAgentChatConfig').mockRejectedValue(new Error('offline'))
    const { renderer } = render()

    await act(async () => {})
    await act(async () => {
      renderer.root.findByProps({ id: 'feishu-agent-chat-encrypt-key' })
        .props.onChange({ target: { value: 'new-encrypt-key' } })
    })
    await act(async () => saveButton(renderer).props.onClick())

    expect(error).toHaveBeenCalledWith('integrations.feishuAgentChatSaveFailed')
    expect(success).not.toHaveBeenCalled()
  })

  test('explains that the capability must be enabled before configuring the channel', async () => {
    const { renderer } = render({
      integration: { ...integration, enabled_capabilities: ['directory_sync'] },
    })

    await act(async () => {})

    expect(translateCalls).toContainEqual(['integrations.feishuAgentChatDisabledHint', undefined])
    expect(renderer.root.findAllByProps({ 'data-testid': 'feishu-agent-chat-save' })).toHaveLength(0)
  })

  test('does not load agent chat settings without the app credentials', async () => {
    const configRequest = spyOn(integrationsApi, 'getFeishuAgentChatConfig').mockResolvedValue(agentChatConfig)
    render({ config: { ...config, app_secret_configured: false } })

    await act(async () => {})

    expect(configRequest).not.toHaveBeenCalled()
    expect(translateCalls).toContainEqual(['integrations.feishuAgentChatUnavailable', undefined])
  })

  test('keeps channel settings read-only without update permission', async () => {
    const { renderer } = render({ canUpdate: false })

    await act(async () => {})

    expect(renderer.root.findByProps({ 'data-testid': 'select-control' }).props.disabled).toBe(true)
    expect(renderer.root.findAllByProps({ 'data-testid': 'feishu-agent-chat-save' })).toHaveLength(0)
  })

  test('saves a mode-only change without sending hidden callback secrets', async () => {
    const update = spyOn(integrationsApi, 'updateFeishuAgentChatConfig').mockResolvedValue({
      ...agentChatConfig,
      connection_mode: 'long_connection',
    })
    const { renderer } = render()
    await act(async () => {})
    act(() => renderer.root.findByProps({ id: 'feishu-agent-chat-encrypt-key' })
      .props.onChange({ target: { value: 'unsaved-callback-key' } }))
    act(() => renderer.root.findByProps({ 'data-testid': 'select-control' })
      .props.onValueChange('long_connection'))

    expect(renderer.root.findAllByProps({ id: 'feishu-agent-chat-callback-url' })).toHaveLength(0)
    expect(renderer.root.findAllByProps({ id: 'feishu-agent-chat-encrypt-key' })).toHaveLength(0)
    expect(renderer.root.findAllByProps({ id: 'feishu-agent-chat-verification-token' })).toHaveLength(0)
    expect(saveButton(renderer).props.disabled).toBe(false)
    const trigger = renderer.root.findByProps({ id: 'feishu-agent-chat-connection-mode' })
    expect(trigger.findByType('span').children).toEqual(['integrations.feishuAgentChatLongConnectionMode'])

    await act(async () => saveButton(renderer).props.onClick())
    expect(update).toHaveBeenCalledWith({ connection_mode: 'long_connection' })
    expect(saveButton(renderer).props.disabled).toBe(true)
  })

  test('loads saved long connection mode and can switch back to callbacks', async () => {
    spyOn(integrationsApi, 'getFeishuAgentChatConfig').mockResolvedValue({
      ...agentChatConfig,
      connection_mode: 'long_connection',
    })
    const { renderer } = render()
    await act(async () => {})
    expect(renderer.root.findByProps({ 'data-testid': 'select-control' }).props.value).toBe('long_connection')
    expect(renderer.root.findAllByProps({ id: 'feishu-agent-chat-callback-url' })).toHaveLength(0)
    expect(saveButton(renderer).props.disabled).toBe(true)
    act(() => renderer.root.findByProps({ 'data-testid': 'select-control' }).props.onValueChange('callback'))
    expect(renderer.root.findByProps({ id: 'feishu-agent-chat-encrypt-key' }).props.type).toBe('password')
    expect(saveButton(renderer).props.disabled).toBe(false)
  })

  test('offers the agent chat capability switch on the configuration tab', () => {
    let renderer: ReactTestRenderer
    act(() => {
      renderer = create(
        <FeishuIntegrationTab
          config={config}
          onConfigChange={mock(() => {})}
          canUpdate
          integration={integration}
          canUpdateLogin
          onIntegrationChange={mock(() => {})}
          tab="configuration"
        />
      )
    })
    const root = renderer!.root
    renderers.push(renderer!)

    expect(root.findByProps({ 'aria-label': 'integrations.feishuAgentChat' }).props.checked).toBe(true)
  })
})

test('shows the managed receiver connection state instead of a manual start command', async () => {
  spyOn(integrationsApi, 'getFeishuAgentChatConfig').mockResolvedValue({
    ...agentChatConfig, connection_mode: 'long_connection',
    receiver_status: { state: 'connected', managed: true },
  })
  const { renderer } = render()
  await act(async () => {})
  expect(renderer.root.findByProps({ role: 'status' }).children.join('')).toContain('integrations.feishuReceiverStates.connected')
  expect(renderer.root.findAllByProps({ id: 'feishu-agent-chat-callback-url' })).toHaveLength(0)
})
