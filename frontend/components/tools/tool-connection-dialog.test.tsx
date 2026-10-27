import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import React from 'react'
import { act, create as createRenderer, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { Tool } from '@/lib/api'
import type { ToolConnection } from '@/lib/api/tool-connections'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })
globalThis.IS_REACT_ACT_ENVIRONMENT = true

// Translation infrastructure is not under test; keys are rendered verbatim so
// assertions can point at the exact message the dialog decided to show.
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}|${Object.values(values).join(',')}` : `${namespace}.${key}`,
}))

const listForTool = mock(async (): Promise<ToolConnection[]> => [])
const list = mock(async (): Promise<ToolConnection[]> => [])
const createForTool = mock(async (): Promise<ToolConnection> => connection)
const create = mock(async (): Promise<ToolConnection> => connection)
const getOAuthStatus = mock(async () => ({
  connection_id: 'connection-1',
  provider_kind: null,
  provider_configured: false,
  authorized: false,
  needs_reauth: false,
  status: 'active' as const,
  account_label: null,
  scopes: [],
  expires_at: null,
  client_id: null,
}))
const update = mock(async () => connection)
const revoke = mock(async (): Promise<ToolConnection> => connection)
const startOAuth = mock(async () => ({
  authorization_url: 'https://auth.example.test/start',
  state: 'state',
  expires_at: '2026-01-01T00:05:00Z',
  provider_kind: 'mcp' as const,
  connection_id: 'connection-1',
}))
const disconnectOAuth = mock(async () => ({
  connection_id: 'connection-1',
  local_revoked: true,
  remote_revocation: 'revoked' as const,
  needs_reauth: true,
}))

mock.module('@/lib/api/tool-connections', () => ({
  toolConnectionsApi: {
    listForTool,
    list,
    createForTool,
    create,
    getOAuthStatus,
    update,
    revoke,
    startOAuth,
    disconnectOAuth,
    get: mock(async () => connection),
  },
}))

// A static import cannot work here: module mocks must be registered before the
// dialog and its manager bind to the network module they import.
const { ToolConnectionDialog } = await import('./tool-connection-dialog')

const connection: ToolConnection = {
  id: 'connection-1',
  team_id: 'team-1',
  tool_id: 'tool-1',
  builtin_tool_key: null,
  scope: 'user',
  name: 'Work account',
  account_label: 'work@example.com',
  status: 'active',
  secret_fields: ['api_key'],
  secret_version: 1,
  is_default: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-1',
    name: 'ticktick',
    display_name: 'TickTick',
    description: 'Task manager',
    type: 'builtin',
    category: 'productivity',
    visibility: 'team',
    parameters: [],
    is_enabled: true,
    requires_config: false,
    config_fields: [],
    identity_policy: 'personal_only',
    connection_fields: [{ name: 'api_key', label: 'API key', required: true, secret: true }],
    ...overrides,
  }
}

let renderer: ReactTestRenderer | undefined
let onChanged = mock()

beforeEach(() => {
  for (const fn of [
    listForTool,
    list,
    createForTool,
    create,
    getOAuthStatus,
    update,
    revoke,
    startOAuth,
    disconnectOAuth,
  ]) {
    fn.mockClear()
  }
  listForTool.mockImplementation(async () => [])
  list.mockImplementation(async () => [])
  createForTool.mockImplementation(async () => connection)
  create.mockImplementation(async () => connection)
  getOAuthStatus.mockImplementation(async () => ({
    connection_id: 'connection-1',
    provider_kind: null,
    provider_configured: false,
    authorized: false,
    needs_reauth: false,
    status: 'active' as const,
    account_label: null,
    scopes: [],
    expires_at: null,
    client_id: null,
  }))
  update.mockImplementation(async () => connection)
  revoke.mockImplementation(async () => connection)
  onChanged = mock()
})

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
  document.body.replaceChildren()
})

async function flush() {
  await act(async () => {})
  await act(async () => {})
  await act(async () => {})
}

async function renderDialog(
  overrides: Partial<React.ComponentProps<typeof ToolConnectionDialog>> = {}
) {
  const props: React.ComponentProps<typeof ToolConnectionDialog> = {
    tool: makeTool(),
    teamId: 'team-1',
    open: true,
    onOpenChange: () => {},
    onChanged,
    ...overrides,
  }
  await act(async () => {
    renderer = createRenderer(<ToolConnectionDialog {...props} />)
  })
  await flush()
}

function pageText(): string {
  return document.body.textContent ?? ''
}

function buttonByText(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find((node) => node.textContent === text)
}

async function clickElement(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  await flush()
}

async function clickButton(text: string) {
  const target = buttonByText(text)
  expect(target).toBeTruthy()
  await clickElement(target!)
}

const nameInput = { placeholder: 'tools.connections.namePlaceholder' }
const secretInput = { id: 'connection-secret-api_key' }

function inputProps(match: Record<string, string>): Record<string, unknown> {
  return renderer!.root.findByProps(match).props
}

function inputValue(match: Record<string, string>): string {
  return inputProps(match).value as string
}

async function changeInput(match: Record<string, string>, value: string) {
  const onChange = inputProps(match).onChange as (event: { target: { value: string } }) => void
  expect(typeof onChange).toBe('function')
  await act(async () => {
    onChange({ target: { value } })
  })
}

async function fillCreateForm(name: string, secret?: string) {
  await changeInput(nameInput, name)
  if (secret !== undefined) await changeInput(secretInput, secret)
}

function alertText(): string | null {
  return document.querySelector('[role="alert"]')?.textContent ?? null
}

describe('ToolConnectionDialog', () => {
  test('renders nothing when no tool is selected', async () => {
    await renderDialog({ tool: null })

    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(pageText()).toBe('')
    expect(listForTool).not.toHaveBeenCalled()
  })

  test('does not mount the connection manager while the dialog is closed', async () => {
    await renderDialog({ open: false })

    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(pageText()).toBe('')
    expect(listForTool).not.toHaveBeenCalled()
  })

  test('forwards a close request to the dialog owner', async () => {
    const onOpenChange = mock()
    await renderDialog({ onOpenChange })

    await clickButton('Close')

    expect(onOpenChange).toHaveBeenCalled()
    expect(onOpenChange.mock.calls[0][0]).toBe(false)
  })

  test('shows a custom tool emoji icon in the dialog title', async () => {
    await renderDialog({ tool: makeTool({ icon: '🦊', type: 'custom', custom_type: 'http' }) })

    expect(pageText()).toContain('🦊')
    expect(pageText()).toContain('platform.tools.configDialog.title|TickTick')
  })

  test('refuses to manage connections when the tool has no resolved identity definition', async () => {
    await renderDialog({ tool: makeTool({ identity_policy: undefined }) })

    expect(pageText()).toContain('platform.tools.connectionDialog.definitionUnavailable')
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(listForTool).not.toHaveBeenCalled()
  })

  test('reports an unusable definition when identity is none but the tool still needs configuration', async () => {
    await renderDialog({
      tool: makeTool({ identity_policy: 'none', requires_config: true }),
    })

    expect(pageText()).toContain('platform.tools.connectionDialog.definitionUnavailable')
    expect(pageText()).not.toContain('platform.tools.connectionDialog.notRequired')
    expect(listForTool).not.toHaveBeenCalled()
  })

  test('states explicitly that a tool with none identity needs no connection', async () => {
    await renderDialog({
      tool: makeTool({ identity_policy: 'none', requires_config: false }),
    })

    expect(pageText()).toContain('platform.tools.connectionDialog.notRequired')
    expect(listForTool).not.toHaveBeenCalled()
  })

  test('requires a team context instead of exposing team-scoped connection management', async () => {
    await renderDialog({ teamId: undefined })

    expect(pageText()).toContain('platform.tools.connectionDialog.teamRequired')
    expect(listForTool).not.toHaveBeenCalled()
    expect(buttonByText('tools.connections.create')).toBeUndefined()
  })

  test('reports an unusable definition for a custom tool that has no service identity', async () => {
    await renderDialog({
      tool: makeTool({ id: undefined, type: 'custom', custom_type: 'http' }),
    })

    expect(pageText()).toContain('platform.tools.connectionDialog.definitionUnavailable')
    expect(listForTool).not.toHaveBeenCalled()
  })

  test('requires a connection name before calling the save endpoint', async () => {
    await renderDialog()

    await clickButton('tools.connections.create')

    expect(alertText()).toBe('tools.connections.nameRequired')
    expect(createForTool).not.toHaveBeenCalled()
    expect(onChanged).not.toHaveBeenCalled()
  })

  test('requires every required secret field and names the missing ones', async () => {
    await renderDialog()

    await fillCreateForm('Work account')
    await clickButton('tools.connections.create')

    expect(alertText()).toBe('tools.connections.secretRequired|API key')
    expect(createForTool).not.toHaveBeenCalled()
    expect(onChanged).not.toHaveBeenCalled()
  })

  test('saves a personal connection once validation passes and refreshes the tool', async () => {
    await renderDialog()

    await fillCreateForm('Work account', 'super-secret')
    await clickButton('tools.connections.create')

    expect(createForTool).toHaveBeenCalledTimes(1)
    expect(createForTool).toHaveBeenCalledWith('tool-1', {
      team_id: 'team-1',
      scope: 'user',
      name: 'Work account',
      account_label: null,
      config: { api_key: 'super-secret' },
    })
    expect(onChanged).toHaveBeenCalledTimes(1)
    // The form is reset and the list is reloaded after a successful save.
    expect(inputValue(nameInput)).toBe('')
    expect(inputValue(secretInput)).toBe('')
    expect(listForTool).toHaveBeenCalledTimes(2)
    expect(alertText()).toBeNull()
  })

  test('keeps the form usable and shows the failure when saving is rejected', async () => {
    createForTool.mockImplementationOnce(async () => {
      throw new Error('403 forbidden')
    })
    await renderDialog()

    await fillCreateForm('Work account', 'super-secret')
    await clickButton('tools.connections.create')

    expect(alertText()).toBe('tools.connections.createFailed')
    expect(onChanged).not.toHaveBeenCalled()
    expect(inputValue(nameInput)).toBe('Work account')
    expect(inputValue(secretInput)).toBe('super-secret')
    expect(buttonByText('tools.connections.create')!.disabled).toBe(false)
  })

  test('surfaces a denied connection list without blocking new saves', async () => {
    listForTool.mockImplementationOnce(async () => {
      throw new Error('403 forbidden')
    })
    await renderDialog()

    expect(alertText()).toBe('tools.connections.loadFailed')

    await fillCreateForm('Work account', 'super-secret')
    await clickButton('tools.connections.create')

    expect(createForTool).toHaveBeenCalledTimes(1)
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  test('keeps personal_only tools limited to personal scope', async () => {
    await renderDialog({ tool: makeTool({ identity_policy: 'personal_only' }) })

    expect(document.querySelector('[aria-haspopup="listbox"]')).toBeNull()

    await fillCreateForm('Work account', 'super-secret')
    await clickButton('tools.connections.create')

    expect(createForTool).toHaveBeenCalledWith(
      'tool-1',
      expect.objectContaining({ scope: 'user' })
    )
  })

  test('keeps team_only tools limited to team scope', async () => {
    await renderDialog({ tool: makeTool({ identity_policy: 'team_only' }) })

    expect(document.querySelector('[aria-haspopup="listbox"]')).toBeNull()

    await fillCreateForm('Team account', 'shared-secret')
    await clickButton('tools.connections.create')

    expect(createForTool).toHaveBeenCalledWith(
      'tool-1',
      expect.objectContaining({ scope: 'team' })
    )
  })

  test('offers a scope choice for selectable tools and defaults to the caller personal scope', async () => {
    await renderDialog({ tool: makeTool({ identity_policy: 'selectable' }) })

    expect(document.querySelector('[aria-haspopup="listbox"]')).not.toBeNull()

    await fillCreateForm('Work account', 'super-secret')
    await clickButton('tools.connections.create')

    expect(createForTool).toHaveBeenCalledWith(
      'tool-1',
      expect.objectContaining({ scope: 'user' })
    )
  })

  test('creates builtin connections by builtin key when the tool has no service id', async () => {
    await renderDialog({ tool: makeTool({ id: undefined }) })

    expect(list).toHaveBeenCalledWith('team-1', { builtinToolKey: 'ticktick' })

    await fillCreateForm('Work account')
    await clickButton('tools.connections.create')

    expect(createForTool).not.toHaveBeenCalled()
    expect(create).toHaveBeenCalledWith({
      team_id: 'team-1',
      scope: 'user',
      name: 'Work account',
      account_label: null,
      config: {},
      builtin_tool_key: 'ticktick',
    })
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  test('lists existing connections with their scope and lets the owner pick a default', async () => {
    listForTool.mockImplementation(async () => [connection])
    await renderDialog()

    expect(pageText()).toContain('work@example.com')
    expect(pageText()).toContain('tools.connections.scopeOptions.user')
    expect(buttonByText('tools.connections.setDefault')).toBeTruthy()
    expect(document.querySelector('button[title="tools.connections.revoke"]')).not.toBeNull()

    await clickButton('tools.connections.setDefault')

    expect(update).toHaveBeenCalledWith('connection-1', { is_default: true })
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(listForTool).toHaveBeenCalledTimes(2)
  })

  test('revokes a connection and reloads the list', async () => {
    listForTool.mockImplementation(async () => [connection])
    await renderDialog()

    await clickElement(document.querySelector('button[title="tools.connections.revoke"]')!)

    expect(revoke).toHaveBeenCalledWith('connection-1')
    expect(onChanged).toHaveBeenCalledTimes(1)
    expect(listForTool).toHaveBeenCalledTimes(2)
  })
})
