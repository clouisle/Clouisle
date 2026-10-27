import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create as createRenderer, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import type { ToolConnectionBinding } from './connection-picker'

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
    getOAuthStatus,
    startOAuth,
    disconnectOAuth,
    update,
    revoke,
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
  update.mockClear()
  revoke.mockClear()
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

async function choose(select: HTMLSelectElement, value: string) {
  await act(async () => {
    select.value = value
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

async function renderPicker(overrides: {
  tool?: typeof tool | null
  builtinToolKey?: string
  value?: ToolConnectionBinding
  onChange?: (value: ToolConnectionBinding) => void
  disabled?: boolean
} = {}) {
  const onChange = overrides.onChange ?? mock()
  await act(async () => {
    renderer = createRenderer(
      <ToolConnectionPicker
        tool={overrides.tool === undefined ? tool : overrides.tool}
        builtinToolKey={overrides.builtinToolKey}
        teamId="team-1"
        value={overrides.value ?? getToolConnectionBinding(null)}
        onChange={onChange}
        disabled={overrides.disabled}
      />
    )
  })
  await flush()
  return onChange
}

function optionValues(select: HTMLSelectElement): string[] {
  return Array.from(select.options).map((option) => option.value)
}

function alertText(): string | null {
  return document.querySelector('[role="alert"]')?.textContent ?? null
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
    })
  })

  test('defaults personal tools to automatic current-user selection without warnings', async () => {
    await renderPicker()

    const connectionSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === '__automatic__')
    )!
    expect(connectionSelect.value).toBe('__automatic__')
    expect(document.body.textContent).not.toContain('connections.selectionRequired')
    expect(document.body.textContent).not.toContain('connections.noConnectionsForMode')
  })

  test('defaults selectable tools to automatic personal without forcing a scope', async () => {
    await renderPicker({ tool: { ...tool, identity_policy: 'selectable' } })

    const scopeSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'team')
    )!
    expect(scopeSelect.value).toBe('personal')
    const connectionSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === '__automatic__')
    )!
    expect(connectionSelect.value).toBe('__automatic__')
    expect(document.body.textContent).not.toContain('connections.selectionRequired')
  })

  test('keeps a fixed connection and clears it when automatic is selected', async () => {
    const onChange = await renderPicker({
      value: getToolConnectionBinding({ connection_mode: 'personal', connection_id: 'c1' }),
    })

    expect(document.body.textContent).toContain('work@example.com')
    const connectionSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'c1')
    )!
    expect(connectionSelect.value).toBe('c1')

    await choose(connectionSelect, '__automatic__')
    expect(onChange).toHaveBeenCalledWith({ connection_mode: 'personal', connection_id: null })
  })

  test('can switch a missing fixed personal account back to automatic', async () => {
    listForTool.mockImplementationOnce(async () => [])
    const onChange = await renderPicker({
      value: getToolConnectionBinding({ connection_mode: 'personal', connection_id: 'removed' }),
    })
    const connectionSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === '__automatic__')
    )!
    expect(connectionSelect.disabled).toBe(false)
    await choose(connectionSelect, '__automatic__')
    expect(onChange).toHaveBeenCalledWith({ connection_mode: 'personal', connection_id: null })
  })

  test('emits team bindings for selectable tools', async () => {
    listForTool.mockImplementationOnce(async () => [
      connection,
      { ...connection, id: 'c2', scope: 'team', name: 'Team account', account_label: 'team@example.com', is_default: false },
    ])
    const onChange = await renderPicker({
      tool: { ...tool, identity_policy: 'selectable' },
      value: getToolConnectionBinding({ connection_mode: 'team', connection_id: null }),
    })

    const connectionSelect = selects().find((item) =>
      Array.from(item.options).some((option) => option.value === 'c2')
    )!
    await choose(connectionSelect, 'c2')
    expect(onChange).toHaveBeenCalledWith({ connection_mode: 'team', connection_id: 'c2' })
  })

  test('submits only the selected endpoint mode and includes visible defaults', async () => {
    await act(async () => {
      renderer = createRenderer(<ToolConnectionPicker tool={{ ...tool, connection_fields: [
        { name: 'url', label: 'URL', required: false, secret: true, input_mode: 'url' },
        { name: 'host', label: 'Host', required: false, secret: false, input_mode: 'host' },
        { name: 'port', label: 'Port', required: false, secret: false, input_mode: 'host', input_type: 'number', default: '5432' },
        { name: 'timeout', label: 'Timeout', required: false, secret: false, input_type: 'number', default: '15' },
      ] }} teamId="team-1" value={getToolConnectionBinding(null)} onChange={mock()} />)
    })
    await flush()
    await act(async () => button('connections.manage')!.click())
    expect(document.getElementById('connection-secret-url')).toBeNull()
    expect((document.getElementById('connection-secret-port') as HTMLInputElement).value).toBe('5432')
    await act(async () => renderer!.root.findByProps({ placeholder: 'connections.namePlaceholder' }).props.onChange({ target: { value: 'Database' } }))
    await act(async () => renderer!.root.findByProps({ id: 'connection-secret-host' }).props.onChange({ target: { value: 'db.internal' } }))
    await act(async () => button('connections.inputModes.url')!.click())
    expect(document.getElementById('connection-secret-host')).toBeNull()
    await act(async () => renderer!.root.findByProps({ id: 'connection-secret-url' }).props.onChange({ target: { value: 'postgresql://db.example/app' } }))
    await act(async () => button('connections.create')!.click())
    await flush()
    expect(createForTool).toHaveBeenCalledWith('tool-1', expect.objectContaining({
      config: { url: 'postgresql://db.example/app', timeout: '15' },
    }))
  })
  test('manages secret connections and starts OAuth from the manager', async () => {
    await renderPicker()
    await act(async () => button('connections.manage')!.click())
    await flush()
    expect(getOAuthStatus).toHaveBeenCalledWith('c1', 'team-1')
    expect(document.body.textContent).toContain('work@example.com')
    expect(document.body.textContent).toContain('connections.oauthAuthorized')
    expect(document.body.textContent).not.toContain('api_key')

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

  test('surfaces a connection load failure and recovers on refresh', async () => {
    listForTool.mockImplementationOnce(async () => {
      throw new Error('offline')
    })
    await renderPicker()
    expect(document.body.textContent).toContain('connections.loadFailed')

    const refresh = document.querySelector('button[title="connections.refresh"]') as HTMLButtonElement
    expect(refresh.disabled).toBe(false)
    await act(async () => refresh.click())
    await flush()
    await flush()

    expect(listForTool).toHaveBeenCalledTimes(2)
    expect(document.body.textContent).not.toContain('connections.loadFailed')
    expect(optionValues(selects()[0])).toContain('c1')
  })

  test('labels default and non-active connections in the options', async () => {
    listForTool.mockImplementationOnce(async () => [
      { ...connection, id: 'c1', is_default: true, status: 'active' as const },
      {
        ...connection,
        id: 'c2',
        name: 'Legacy key',
        account_label: null,
        is_default: false,
        status: 'reauth_required' as const,
      },
    ])
    await renderPicker()

    const options = Array.from(selects()[0].options)
    expect(options.find((option) => option.value === 'c1')!.textContent)
      .toBe('work@example.com · connections.defaultBadge')
    expect(options.find((option) => option.value === 'c2')!.textContent)
      .toBe('Legacy key · connections.status.reauth_required')
  })

  test('never offers team-scoped connections to a personal-only tool', async () => {
    listForTool.mockImplementationOnce(async () => [
      connection,
      { ...connection, id: 'team-conn', scope: 'team' as const, account_label: null },
    ])
    await renderPicker()

    expect(optionValues(selects()[0])).toEqual(['__automatic__', 'c1'])
  })

  test('disables team selection and explains the empty team pool', async () => {
    listForTool.mockImplementationOnce(async () => [{ ...connection, scope: 'user' as const }])
    await renderPicker({ tool: { ...tool, identity_policy: 'team_only' } })

    expect(selects()).toHaveLength(1)
    expect(optionValues(selects()[0])).toEqual([])
    expect(selects()[0].disabled).toBe(true)
    expect(document.body.textContent).toContain('connections.noConnectionsForMode')
    expect(document.body.textContent).not.toContain('connections.loadFailed')
  })

  test('shows only team and site connections when a selectable tool binds to team', async () => {
    listForTool.mockImplementationOnce(async () => [
      connection,
      { ...connection, id: 'c2', scope: 'team' as const, account_label: 'team@example.com' },
      { ...connection, id: 'c3', scope: 'site' as const, account_label: 'site@example.com' },
    ])
    await renderPicker({
      tool: { ...tool, identity_policy: 'selectable' },
      value: getToolConnectionBinding({ connection_mode: 'team', connection_id: null }),
    })

    const connectionOptions = selects().find((item) => optionValues(item).includes('c2'))!
    expect(optionValues(connectionOptions)).toEqual(['c2', 'c3'])
    expect(connectionOptions.disabled).toBe(false)
  })

  test('switching a selectable tool to team scope clears the bound account', async () => {
    const onChange = await renderPicker({
      tool: { ...tool, identity_policy: 'selectable' },
      value: getToolConnectionBinding({ connection_mode: 'personal', connection_id: 'c1' }),
    })
    const modeSelect = selects().find((item) => optionValues(item).includes('personal'))!
    await choose(modeSelect, 'team')
    expect(onChange).toHaveBeenCalledWith({ connection_mode: 'team', connection_id: null })
  })

  test('offers only user and team scopes when creating a connection', async () => {
    await renderPicker({ tool: { ...tool, identity_policy: 'selectable' } })
    await act(async () => button('connections.manage')!.click())
    await flush()

    const scopeSelect = selects().find((item) => optionValues(item).includes('user'))!
    expect(optionValues(scopeSelect)).toEqual(['user', 'team'])
    expect(scopeSelect.value).toBe('user')
  })

  test('does not offer a scope choice for personal-only tools', async () => {
    await renderPicker()
    await act(async () => button('connections.manage')!.click())
    await flush()

    expect(selects().some((item) => optionValues(item).includes('user'))).toBe(false)
  })

  test('creates a team-scoped connection from the selected scope and account label', async () => {
    await renderPicker({ tool: { ...tool, identity_policy: 'selectable' } })
    await act(async () => button('connections.manage')!.click())
    await flush()

    const scopeSelect = selects().find((item) => optionValues(item).includes('user'))!
    await choose(scopeSelect, 'team')
    await act(async () => renderer!.root.findByProps({ placeholder: 'connections.namePlaceholder' })
      .props.onChange({ target: { value: 'Team key' } }))
    await act(async () => renderer!.root.findByProps({ placeholder: 'connections.accountLabelPlaceholder' })
      .props.onChange({ target: { value: 'ops@example.com' } }))
    await act(async () => renderer!.root.findByProps({ id: 'connection-secret-api_key' })
      .props.onChange({ target: { value: 'team-secret' } }))
    await act(async () => button('connections.create')!.click())
    await flush()

    expect(createForTool).toHaveBeenCalledWith('tool-1', expect.objectContaining({
      team_id: 'team-1',
      scope: 'team',
      name: 'Team key',
      account_label: 'ops@example.com',
      config: { api_key: 'team-secret' },
    }))
  })

  test('rejects manager submissions without a name or required secret', async () => {
    await renderPicker()
    await act(async () => button('connections.manage')!.click())
    await flush()

    await act(async () => button('connections.create')!.click())
    expect(alertText()).toBe('connections.nameRequired')
    expect(createForTool).not.toHaveBeenCalled()

    await act(async () => renderer!.root.findByProps({ placeholder: 'connections.namePlaceholder' })
      .props.onChange({ target: { value: 'Personal' } }))
    await act(async () => button('connections.create')!.click())
    expect(alertText()).toBe('connections.secretRequired')
    expect(createForTool).not.toHaveBeenCalled()
  })

  test('reports create failures and keeps the entered secret for retry', async () => {
    createForTool.mockImplementationOnce(async () => {
      throw new Error('rejected')
    })
    await renderPicker()
    await act(async () => button('connections.manage')!.click())
    await flush()
    await act(async () => renderer!.root.findByProps({ placeholder: 'connections.namePlaceholder' })
      .props.onChange({ target: { value: 'Personal' } }))
    await act(async () => renderer!.root.findByProps({ id: 'connection-secret-api_key' })
      .props.onChange({ target: { value: 'secret-value' } }))
    await act(async () => button('connections.create')!.click())
    await flush()

    expect(alertText()).toBe('connections.createFailed')
    expect(renderer!.root.findByProps({ id: 'connection-secret-api_key' }).props.value).toBe('secret-value')
  })

  test('reports set-default failures without dropping the connection list', async () => {
    const twoConnections = async () => [
      connection,
      { ...connection, id: 'c2', account_label: 'second@example.com', is_default: false },
    ]
    listForTool.mockImplementationOnce(twoConnections)
    await renderPicker()
    listForTool.mockImplementationOnce(twoConnections)
    await act(async () => button('connections.manage')!.click())
    await flush()

    update.mockImplementationOnce(async () => {
      throw new Error('forbidden')
    })
    await act(async () => button('connections.setDefault')!.click())
    await flush()

    expect(update).toHaveBeenCalledWith('c2', { is_default: true })
    expect(alertText()).toBe('connections.updateFailed')
    expect(document.body.textContent).toContain('second@example.com')
  })

  test('reports revoke failures', async () => {
    revoke.mockImplementationOnce(async () => {
      throw new Error('forbidden')
    })
    await renderPicker()
    await act(async () => button('connections.manage')!.click())
    await flush()

    const revokeButton = document.querySelector('button[title="connections.revoke"]') as HTMLButtonElement
    await act(async () => revokeButton.click())
    await flush()

    expect(revoke).toHaveBeenCalledWith('c1')
    expect(alertText()).toBe('connections.revokeFailed')
  })

  test('reports manager load failures instead of pretending the team has no connections', async () => {
    listForTool.mockImplementationOnce(async () => [connection])
    await renderPicker()
    listForTool.mockImplementationOnce(async () => {
      throw new Error('offline')
    })
    await act(async () => button('connections.manage')!.click())
    await flush()
    await flush()

    expect(alertText()).toBe('connections.loadFailed')
    expect(document.body.textContent).toContain('connections.empty')
  })

  test('surfaces OAuth failures without opening a window', async () => {
    startOAuth.mockImplementationOnce(async () => {
      throw new Error('denied')
    })
    const originalOpen = window.open
    const openSpy = mock(() => null)
    window.open = openSpy as unknown as typeof window.open
    try {
      await renderPicker()
      await act(async () => button('connections.manage')!.click())
      await flush()
      await act(async () => button('connections.oauthConnect')!.click())
      await flush()

      expect(alertText()).toBe('connections.oauthFailed')
      expect(openSpy).not.toHaveBeenCalled()
    } finally {
      window.open = originalOpen
    }
  })

  test('prompts reauthorization and opens the authorization URL', async () => {
    getOAuthStatus.mockImplementationOnce(async () => ({
      connection_id: 'c1',
      provider_kind: 'mcp' as const,
      provider_configured: true,
      authorized: false,
      needs_reauth: true,
      status: 'reauth_required' as const,
      account_label: 'work@example.com',
      scopes: [],
      expires_at: null,
      client_id: null,
    }))
    const originalOpen = window.open
    const openSpy = mock(() => null)
    window.open = openSpy as unknown as typeof window.open
    try {
      await renderPicker()
      await act(async () => button('connections.manage')!.click())
      await flush()

      expect(document.body.textContent).toContain('connections.oauthNeedsReauth')
      await act(async () => button('connections.oauthReconnect')!.click())
      await flush()

      expect(startOAuth).toHaveBeenCalledWith('c1', { redirect_path: '/' })
      expect(openSpy).toHaveBeenCalledWith(
        'https://auth.example.test/start',
        '_blank',
        'noopener,noreferrer'
      )
    } finally {
      window.open = originalOpen
    }
  })

  test('locks every control while the binding is disabled', async () => {
    await renderPicker({ disabled: true })

    const manage = button('connections.manage')!
    expect(manage.disabled).toBe(true)
    expect((document.querySelector('button[title="connections.refresh"]') as HTMLButtonElement).disabled).toBe(true)
    expect(selects()[0].disabled).toBe(true)
    await act(async () => manage.click())
    expect(document.body.textContent).not.toContain('connections.manageTitle')
  })
})
