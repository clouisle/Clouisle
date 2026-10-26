import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create as createRenderer, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { GlobalRegistrator } from '@happy-dom/global-registrator'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })
globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => `connections.${key}` }))
mock.module('lucide-react', () => ({
  ChevronDown: () => null,
  Loader2: () => null,
  Plus: () => null,
  RefreshCw: () => null,
  Trash2: () => null,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.ComponentProps<'span'>) => <span {...props}>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) => (children ? <span role="alert">{children}</span> : null),
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.ComponentProps<'input'>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange, disabled }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void; disabled?: boolean }>) => (
    <select value={value ?? ''} disabled={disabled} onChange={(event) => onValueChange(event.target.value)}>{children}</select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))

const connection = {
  id: 'c1',
  team_id: 'team-1',
  tool_id: 'tool-1',
  builtin_tool_key: null,
  scope: 'user' as const,
  name: 'Work account',
  account_label: 'work@example.com',
  status: 'active' as const,
  secret_fields: ['api_key'],
  secret_version: 1,
  is_default: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const listForTool = mock(async () => [connection])
const list = mock(async () => [connection])
const createForTool = mock(async () => connection)
const create = mock(async () => connection)
const listGrants = mock(async () => [])
const getOAuthStatus = mock(async () => ({
  connection_id: 'c1',
  provider_kind: 'mcp' as const,
  provider_configured: true,
  authorized: true,
  needs_reauth: false,
  status: 'active' as const,
  account_label: 'work@example.com',
  scopes: [],
  expires_at: null,
  client_id: null,
}))
const disconnectOAuth = mock(async () => ({ connection_id: 'c1', local_revoked: true, remote_revocation: 'revoked', needs_reauth: true }))
const startOAuth = mock(async () => ({
  authorization_url: 'https://auth.example.test/start',
  state: 'state',
  expires_at: '2026-01-01T00:05:00Z',
  provider_kind: 'mcp' as const,
  connection_id: 'c1',
}))
const update = mock(async () => connection)
const revoke = mock(async () => connection)

mock.module('@/lib/api/tool-connections', () => ({
  toolConnectionsApi: {
    listForTool,
    list,
    createForTool,
    create,
    listGrants,
    getOAuthStatus,
    startOAuth,
    disconnectOAuth,
    update,
    revoke,
    createGrant: mock(async () => ({})),
    revokeGrant: mock(async () => ({})),
    get: mock(async () => connection),
  },
}))

// Dynamic import is required so module mocks above apply before the picker loads.
const { ToolConnectionPicker, getToolConnectionBinding } = await import('./connection-picker')

const tool = {
  id: 'tool-1',
  name: 'ticktick',
  display_name: 'TickTick',
  identity_policy: 'personal_only' as const,
  connection_fields: [{ name: 'api_key', label: 'API key', required: true, secret: true }],
}

let renderer: ReactTestRenderer | undefined

beforeEach(() => {
  listForTool.mockClear()
  list.mockClear()
  createForTool.mockClear()
  create.mockClear()
  getOAuthStatus.mockClear()
  startOAuth.mockClear()
  disconnectOAuth.mockClear()
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
  mock.restore()
})

async function flush() {
  await act(async () => {})
}

function selects(): HTMLSelectElement[] {
  return Array.from(document.querySelectorAll('select'))
}

function button(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find((item) => item.textContent === text)
}

async function renderPicker(overrides: {
  tool?: typeof tool | null
  builtinToolKey?: string
  onChange?: (value: ReturnType<typeof getToolConnectionBinding>) => void
} = {}) {
  const onChange = overrides.onChange ?? mock()
  await act(async () => {
    renderer = createRenderer(
      <ToolConnectionPicker
        tool={overrides.tool === undefined ? tool : overrides.tool}
        builtinToolKey={overrides.builtinToolKey}
        teamId="team-1"
        value={getToolConnectionBinding(null)}
        onChange={onChange}
        entrypointType="agent"
        entrypointId="agent-1"
      />
    )
  })
  await flush()
  return onChange
}

describe('ToolConnectionPicker', () => {
  test('lists personal connections and emits an explicit personal binding', async () => {
    const onChange = await renderPicker()
    expect(listForTool).toHaveBeenCalledWith('tool-1', { teamId: 'team-1' })

    const connectionSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'c1')
    )!
    await act(async () => {
      connectionSelect.value = 'c1'
      connectionSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(onChange).toHaveBeenCalledWith({
      connection_mode: 'personal',
      connection_id: 'c1',
      grant_id: null,
    })
  })

  test('manages secret connections and starts OAuth from the manager', async () => {
    await renderPicker()
    await act(async () => button('connections.manage')!.click())
    await flush()
    expect(getOAuthStatus).toHaveBeenCalledWith('c1', 'team-1')

    const nameInput = renderer!.root.findByProps({ placeholder: 'connections.namePlaceholder' })
    const secretInput = renderer!.root.findByProps({ id: 'connection-secret-api_key' })
    await act(async () => nameInput.props.onChange({ target: { value: 'Personal' } }))
    await act(async () => secretInput.props.onChange({ target: { value: 'secret-value' } }))
    await act(async () => button('connections.create')!.click())
    await flush()
    expect(createForTool).toHaveBeenCalledWith('tool-1', expect.objectContaining({
      name: 'Personal',
      scope: 'user',
      config: { api_key: 'secret-value' },
    }))

    const authorize = button('connections.oauthConnect')
    expect(authorize).toBeTruthy()
    await act(async () => authorize!.click())
    await flush()
    expect(startOAuth).toHaveBeenCalledWith('c1', expect.objectContaining({ redirect_path: expect.any(String) }))

    const rotate = button('connections.oauthClientSecret')
    expect(rotate).toBeTruthy()
    await act(async () => rotate!.click())
    const clientSecret = renderer!.root.findByProps({ id: 'oauth-client-secret-c1' })
    await act(async () => clientSecret.props.onChange({ target: { value: 'rotated-secret' } }))
    await act(async () => button('connections.oauthSaveSecret')!.click())
    await flush()
    expect(startOAuth).toHaveBeenCalledWith('c1', expect.objectContaining({ client_secret: 'rotated-secret' }))

    await act(async () => button('connections.oauthDisconnect')!.click())
    await flush()
    expect(disconnectOAuth).toHaveBeenCalledWith('c1')
  })

  test('supports builtin tools through their stable key', async () => {
    await renderPicker({
      tool: { ...tool, id: undefined as unknown as string },
      builtinToolKey: 'web_search',
    })
    expect(list).toHaveBeenCalledWith('team-1', { builtinToolKey: 'web_search' })
    expect(listForTool).not.toHaveBeenCalled()

    await act(async () => button('connections.manage')!.click())
    await flush()
    const nameInput = renderer!.root.findByProps({ placeholder: 'connections.namePlaceholder' })
    const secretInput = renderer!.root.findByProps({ id: 'connection-secret-api_key' })
    await act(async () => nameInput.props.onChange({ target: { value: 'Search account' } }))
    await act(async () => secretInput.props.onChange({ target: { value: 'secret' } }))
    await act(async () => button('connections.create')!.click())
    await flush()
    expect(create).toHaveBeenCalledWith(expect.objectContaining({
      builtin_tool_key: 'web_search',
      name: 'Search account',
    }))
  })

  test('does not expose connection controls when the identity policy is none', async () => {
    await renderPicker({ tool: { ...tool, identity_policy: 'none' } })
    expect(listForTool).not.toHaveBeenCalled()
    expect(selects()).toHaveLength(0)
    expect(document.body.textContent).toContain('connections.identityNone')
  })
})
