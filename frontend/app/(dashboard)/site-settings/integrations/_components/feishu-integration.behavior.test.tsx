import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const success = mock(() => {})
const error = mock(() => {})
const writeText = mock(async () => {})
globalThis.navigator = { clipboard: { writeText } } as never

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
  MessageSquareText: () => null,
  RefreshCw: () => null,
  Save: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} /> }))
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
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) => <div data-select-value={value} data-on-value-change={onValueChange}>{children}</div>,
  SelectTrigger: ({ children, ...props }: React.PropsWithChildren<React.ButtonHTMLAttributes<HTMLButtonElement>>) => <button {...props}>{children}</button>,
  SelectValue: ({ children, placeholder }: React.PropsWithChildren<{ placeholder?: string }>) => <span>{children || placeholder}</span>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <div data-select-item={value}>{children}</div>,
}))

import { integrationsApi, type FeishuConfig, type Integration } from '@/lib/api/admin/integrations'
import { ApiError } from '@/lib/api/client'
import { FeishuIntegrationTab } from './feishu-integration'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const config: FeishuConfig = { app_id: 'cli_1', app_secret_configured: true, department_ids: ['dept-a'], is_enabled: true }

const integration: Integration = {
  id: 'feishu-1', name: 'feishu', display_name: 'Feishu', provider_type: 'feishu',
  icon_url: null, button_text: null, is_enabled: true,
  enabled_capabilities: ['directory_sync'], supported_capabilities: ['directory_sync', 'user_login', 'notification'],
  config: {}, attribute_mapping: {}, credentials_configured: [],
  login_config: { allow_signup: true, require_approval: false, default_role_id: null }, created_at: '', updated_at: '',
}

const renderers: ReactTestRenderer[] = []

function render(props: { config?: FeishuConfig; integration?: Integration | null; canUpdate?: boolean; canUpdateLogin?: boolean } = {}) {
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
        canUpdateLogin={props.canUpdateLogin ?? true}
        onIntegrationChange={onIntegrationChange}
      />
    )
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onConfigChange, onIntegrationChange }
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => item.children.includes(label))!

const loginSwitch = (renderer: ReactTestRenderer) => renderer.root.findByProps({ 'aria-label': 'integrations.feishuLogin' })
const directorySwitch = (renderer: ReactTestRenderer) => renderer.root.findByProps({ 'aria-label': 'integrations.capabilities.directory_sync' })
const notificationSwitch = (renderer: ReactTestRenderer) => renderer.root.findByProps({ 'aria-label': 'integrations.capabilities.notification' })
const capabilitySave = (renderer: ReactTestRenderer) => renderer.root.findByProps({ 'data-testid': 'feishu-capability-save' })

beforeEach(() => {
  spyOn(integrationsApi, 'getFeishuTestRecipients').mockResolvedValue([])
  spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  success.mockClear()
  error.mockClear()
  translateCalls.length = 0
})

describe('FeishuIntegrationTab', () => {
  test('keeps directory scope read-only without settings update permission', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([
      { department_id: 'dept-a', name: 'Engineering', parent_department_id: null, children: [] },
    ])
    let renderer: ReactTestRenderer
    await act(async () => { renderer = create(<FeishuIntegrationTab config={config} onConfigChange={mock(() => {})} canUpdate={false} integration={integration} canUpdateLogin />) })
    renderers.push(renderer!)
    expect(renderer!.root.findByProps({ 'aria-label': 'Engineering' }).props.disabled).toBe(true)
    expect(renderer!.root.findAllByType('button').some((item) => item.children.includes('integrations.feishuSync'))).toBe(false)
  })

  test('reports account and team counts after a successful sync', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const syncFeishuContacts = spyOn(integrationsApi, 'syncFeishuContacts')
      .mockResolvedValue({ created: 3, updated: 1, skipped: 2, teams_created: 4 })
    const { renderer } = render()

    await act(async () => button(renderer, 'integrations.feishuSync').props.onClick())

    expect(syncFeishuContacts).toHaveBeenCalledTimes(1)
    expect(translateCalls).toContainEqual(['integrations.feishuSyncResult', { created: 3, updated: 1, skipped: 2, teams_created: 4 }])
    expect(success).toHaveBeenCalledWith('integrations.feishuSyncResult')
    expect(error).not.toHaveBeenCalled()
  })

  test('leaves backend-reported sync failures to the global error toast', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    spyOn(integrationsApi, 'syncFeishuContacts').mockRejectedValue(new ApiError(1002, 'Feishu API HTTP 400 (code 41050): no user authority error'))
    const { renderer } = render()

    await act(async () => button(renderer, 'integrations.feishuSync').props.onClick())

    expect(error).not.toHaveBeenCalled()
    expect(success).not.toHaveBeenCalled()
  })

  test('shows a localized fallback when the sync fails before the API answers', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    spyOn(integrationsApi, 'syncFeishuContacts').mockRejectedValue(new Error('Failed to fetch'))
    const { renderer } = render()

    await act(async () => button(renderer, 'integrations.feishuSync').props.onClick())

    expect(error).toHaveBeenCalledWith('integrations.feishuSyncFailed')
  })

  test('shows the Feishu company name returned by the department API', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([
      { department_id: '0', name: 'Acme Ltd.', parent_department_id: null, children: [] },
    ])
    const { renderer } = render()

    await act(async () => {})

    expect(renderer.root.findAllByType('span').some((item) => item.children.includes('Acme Ltd.'))).toBe(true)
    expect(renderer.root.findAllByType('span').some((item) => item.children.includes('integrations.feishuCompany'))).toBe(false)
  })

  test('skips the department request when directory sync is not enabled on the integration', async () => {
    const departments = spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const { renderer } = render({ integration: { ...integration, enabled_capabilities: ['user_login'] } })

    await act(async () => {})

    expect(departments).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'tree' })).toHaveLength(0)
  })

  test('skips the department request while the integration is disabled', async () => {
    const departments = spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    render({ config: { ...config, is_enabled: false } })

    await act(async () => {})

    expect(departments).not.toHaveBeenCalled()
  })

  test('shows the Feishu app redirect URL so it can be registered', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const { renderer } = render()

    const url = renderer.root.findByProps({ id: 'feishu-redirect-url' })
    expect(url.children.join('')).toMatch(/^https?:\/\/.+\/api\/v1\/sso\/callback\/feishu$/)

    await act(async () => renderer.root.findByProps({ 'aria-label': 'integrations.callbackUrl' }).props.onClick())

    expect(writeText).toHaveBeenCalledWith(url.children.join(''))
    writeText.mockClear()
  })

  test('opts Feishu into web login by saving the merged capability list', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const update = spyOn(integrationsApi, 'update').mockResolvedValue(integration)
    const { renderer, onIntegrationChange } = render()

    await act(async () => loginSwitch(renderer).props.onCheckedChange(true))
    await act(async () => capabilitySave(renderer).props.onClick())

    expect(update).toHaveBeenCalledWith('feishu-1', { enabled_capabilities: ['directory_sync', 'user_login'], button_text: null })
    expect(onIntegrationChange).toHaveBeenCalledWith(integration)
    expect(success).toHaveBeenCalledWith('saveSuccess')
    expect(error).not.toHaveBeenCalled()
  })

  test('drops only the login capability when Feishu sign-in is switched off', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const update = spyOn(integrationsApi, 'update').mockResolvedValue(integration)
    const { renderer } = render({ integration: { ...integration, enabled_capabilities: ['directory_sync', 'user_login'], button_text: 'Sign in with Feishu' } })

    expect(loginSwitch(renderer).props.checked).toBe(true)
    await act(async () => loginSwitch(renderer).props.onCheckedChange(false))
    await act(async () => capabilitySave(renderer).props.onClick())

    expect(update).toHaveBeenCalledWith('feishu-1', { enabled_capabilities: ['directory_sync'], button_text: 'Sign in with Feishu' })
  })

  test('turns directory sync off through its own capability switch', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const update = spyOn(integrationsApi, 'update').mockResolvedValue({ ...integration, enabled_capabilities: ['user_login'] })
    const { renderer } = render({ integration: { ...integration, enabled_capabilities: ['directory_sync', 'user_login'] } })

    expect(directorySwitch(renderer).props.checked).toBe(true)
    await act(async () => directorySwitch(renderer).props.onCheckedChange(false))
    await act(async () => capabilitySave(renderer).props.onClick())

    expect(update).toHaveBeenCalledWith('feishu-1', { enabled_capabilities: ['user_login'], button_text: null })
    expect(directorySwitch(renderer).props.disabled).toBe(false)
  })

  test('omits the login-domain button text when only directory sync is editable', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const update = spyOn(integrationsApi, 'update').mockResolvedValue({ ...integration, enabled_capabilities: [] })
    const { renderer } = render({ canUpdateLogin: false })

    await act(async () => directorySwitch(renderer).props.onCheckedChange(false))
    await act(async () => capabilitySave(renderer).props.onClick())

    expect(update).toHaveBeenCalledWith('feishu-1', { enabled_capabilities: [] })
  })

  test('leaves both capability switches read-only without their update permissions', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const update = spyOn(integrationsApi, 'update').mockResolvedValue(integration)
    const { renderer } = render({ canUpdateLogin: false })

    expect(directorySwitch(renderer).props.disabled).toBe(false)
    expect(loginSwitch(renderer).props.disabled).toBe(true)
    expect(renderer.root.findByProps({ id: 'feishu-button-text' }).props.disabled).toBe(true)
    expect(capabilitySave(renderer).props.disabled).toBe(true)
    await act(async () => capabilitySave(renderer).props.onClick())
    expect(update).not.toHaveBeenCalled()
  })

  test('keeps both capabilities disabled until the Feishu integration itself is enabled', async () => {
    spyOn(integrationsApi, 'getFeishuDepartments').mockResolvedValue([])
    const { renderer } = render({ config: { ...config, is_enabled: false } })

    expect(directorySwitch(renderer).props.disabled).toBe(true)
    expect(loginSwitch(renderer).props.disabled).toBe(true)
    expect(renderer.root.findAllByProps({ 'data-testid': 'feishu-capability-save' })).toHaveLength(0)
  })

  test('checks Feishu app authentication without requiring directory sync capability', async () => {
    const check = spyOn(integrationsApi, 'checkFeishuConnection').mockResolvedValue({ status: 'ok' })
    const { renderer } = render({ integration: { ...integration, enabled_capabilities: [] } })

    await act(async () => button(renderer, 'integrations.feishuConnectionCheck').props.onClick())

    expect(check).toHaveBeenCalledTimes(1)
    expect(success).toHaveBeenCalledWith('integrations.feishuConnectionCheckSuccess')
  })

  test('sends test messages only to explicitly selected linked users', async () => {
    const recipients = [
      { id: 'user-1', username: 'ada', email: 'ada@example.com' },
      { id: 'user-2', username: 'grace', email: 'grace@example.com' },
    ]
    spyOn(integrationsApi, 'getFeishuTestRecipients').mockResolvedValue(recipients)
    const send = spyOn(integrationsApi, 'sendFeishuTestMessage').mockResolvedValue({ status: 'sent' })
    const { renderer } = render({ integration: { ...integration, enabled_capabilities: ['notification'] } })
    await act(async () => {})
    const recipientTrigger = renderer.root.findByProps({ id: 'feishu-test-recipient-trigger' })
    const recipientSelect = recipientTrigger.parent
    await act(async () => recipientSelect.props['data-on-value-change']('user-2'))
    await act(async () => button(renderer, 'integrations.feishuTestSend').props.onClick())

    const selectedLabel = recipientTrigger.findByType('span').children.join('')
    const optionLabel = renderer.root.findByProps({ 'data-select-item': 'user-2' }).children.join('')
    expect(selectedLabel).toBe('grace')
    expect(optionLabel).toBe(selectedLabel)
    expect(send).toHaveBeenCalledWith('user-2', 'Clouisle Feishu test', 'This is a test message from Clouisle.')
    expect(success).toHaveBeenCalledWith('integrations.feishuTestSent')
  })
  test('allows an authorized admin to enable Feishu notifications', async () => {
    const { renderer, onIntegrationChange } = render()
    const update = spyOn(integrationsApi, 'update').mockResolvedValue({
      ...integration,
      enabled_capabilities: ['directory_sync', 'notification'],
    })
    expect(notificationSwitch(renderer).props.checked).toBe(false)
    await act(async () => notificationSwitch(renderer).props.onCheckedChange(true))
    expect(capabilitySave(renderer).props.disabled).toBe(false)
    await act(async () => capabilitySave(renderer).props.onClick())
    expect(update).toHaveBeenCalledWith('feishu-1', {
      enabled_capabilities: ['directory_sync', 'notification'],
      button_text: null,
    })
    expect(onIntegrationChange).toHaveBeenCalledWith(expect.objectContaining({
      enabled_capabilities: ['directory_sync', 'notification'],
    }))
  })
})


