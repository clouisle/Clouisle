import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create as createRenderer, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
const toastSuccess = mock(() => {})
const toastError = mock(() => {})

mock.module('sonner', () => ({
  toast: {
    success: toastSuccess,
    error: toastError,
  },
}))

mock.module('next-intl', () => ({
  useTranslations: (ns: string) => (key: string, values?: Record<string, unknown>) => {
    if (values) return `${ns}.${key}:${JSON.stringify(values)}`
    return `${ns}.${key}`
  },
}))

let currentTeam: { id: string; name: string; role: 'owner' | 'admin' | 'member' | 'viewer' } | null = { id: 'team-1', name: 'Team One', role: 'member' }

mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam }),
}))

mock.module('lucide-react', () => ({
  Check: () => null,
  ChevronDown: () => null,
  ExternalLink: () => null,
  KeyRound: () => null,
  Link2: () => null,
  Loader2: () => null,
  Plus: () => null,
  RefreshCw: () => null,
  Star: () => null,
  Trash2: () => null,
  X: () => null,
}))
mock.module('@/components/tools/tool-icons', () => ({
  renderToolIcon: () => <span data-testid="tool-icon" />,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.ComponentProps<'span'>) => <span {...props}>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
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
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({
    children,
    value,
    onValueChange,
  }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void }>) => (
    <select
      data-testid="tool-select"
      value={value ?? ''}
      onChange={(e) => onValueChange(e.target.value)}
    >
      {children}
    </select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectGroup: ({ children }: React.PropsWithChildren) => <optgroup>{children}</optgroup>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => (
    <option value={value}>{children}</option>
  ),
  SelectLabel: ({ children }: React.PropsWithChildren) => <label>{children}</label>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectValue: ({ children, placeholder }: React.PropsWithChildren<{ placeholder?: string }>) => (
    <span>{children || placeholder}</span>
  ),
}))

const mockConnections = [
  {
    id: 'conn-1',
    team_id: 'team-1',
    tool_id: 'tool-mcp-1',
    builtin_tool_key: null,
    scope: 'user' as const,
    name: 'My GitHub Account',
    account_label: 'yunhai@github.com',
    status: 'active' as const,
    secret_fields: ['github_token'],
    secret_version: 1,
    is_default: true,
    created_at: '2026-10-27T00:00:00Z',
    updated_at: '2026-10-27T00:00:00Z',
  },
  {
    id: 'conn-2',
    team_id: 'team-1',
    tool_id: null,
    builtin_tool_key: 'postgresql_query',
    scope: 'user' as const,
    name: 'Local DB',
    account_label: 'localhost:5432/app',
    status: 'reauth_required' as const,
    secret_fields: ['password'],
    secret_version: 1,
    is_default: false,
    created_at: '2026-10-27T00:00:00Z',
    updated_at: '2026-10-27T00:00:00Z',
  },
]

const mockToolsResponse = {
  builtin: [
    {
      id: 'tool-builtin-1',
      name: 'postgresql_query',
      display_name: 'PostgreSQL',
      type: 'builtin' as const,
      category: 'data',
      identity_policy: 'selectable' as const,
      connection_fields: [
        { name: 'host', label: 'Host', required: true, secret: false },
        { name: 'port', label: 'Port', required: true, secret: false, default: '5432' },
        { name: 'password', label: 'Password', required: true, secret: true },
        { name: 'ssl', label: 'SSL mode', required: false, secret: false, input_type: 'select', default: 'prefer', options: ['disable', 'prefer', 'require'] },
      ],
      is_enabled: true,
    },
  ],
  mcp: [
    {
      id: 'tool-mcp-1',
      name: 'github',
      display_name: 'GitHub',
      type: 'mcp' as const,
      category: 'api',
      identity_policy: 'personal_only' as const,
      connection_fields: [
        { name: 'github_token', label: 'GitHub Personal Access Token', required: true, secret: true },
      ],
      is_enabled: true,
    },
  ],
  custom: [
    {
      id: 'tool-custom-1',
      name: 'weather_api',
      display_name: 'Weather API',
      type: 'custom' as const,
      category: 'api',
      identity_policy: 'selectable' as const,
      connection_fields: [
        { name: 'api_key', label: 'API Key', required: true, secret: true },
      ],
      is_enabled: true,
    },
  ],
}

const listConnectionsMock = mock(() => Promise.resolve(mockConnections))
const getOAuthStatusMock = mock(() =>
  Promise.resolve({ provider_configured: true, needs_reauth: false, scopes: [], expires_at: null, client_id: 'client-1' })
)
const createForToolMock = mock(() => Promise.resolve({ id: 'conn-new' }))
const createMock = mock(() => Promise.resolve({ id: 'conn-builtin-new' }))
const updateMock = mock(() => Promise.resolve({ id: 'conn-1', is_default: true }))
const revokeMock = mock(() => Promise.resolve({ id: 'conn-1' }))
const startOAuthMock = mock(() => Promise.resolve({ authorization_url: 'https://oauth.example.test/start' }))
const disconnectOAuthMock = mock(() => Promise.resolve({ disconnected: true }))

mock.module('@/lib/api/tool-connections', () => ({
  toolConnectionsApi: {
    list: listConnectionsMock,
    getOAuthStatus: getOAuthStatusMock,
    createForTool: createForToolMock,
    create: createMock,
    update: updateMock,
    revoke: revokeMock,
    startOAuth: startOAuthMock,
    disconnectOAuth: disconnectOAuthMock,
  },
}))

mock.module('@/lib/api/tools', () => ({
  toolsApi: {
    list: mock(() => Promise.resolve(mockToolsResponse)),
  },
}))


let renderers: ReactTestRenderer[] = []

// Dynamic import required so mock.module calls above take effect before module evaluation.
const { UserToolConnections } = await import('./user-tool-connections')

beforeEach(() => {
  currentTeam = { id: 'team-1', name: 'Team One', role: 'member' }
  listConnectionsMock.mockClear()
  listConnectionsMock.mockImplementation(() => Promise.resolve(mockConnections))
  getOAuthStatusMock.mockClear()
  createForToolMock.mockClear()
  createMock.mockClear()
  updateMock.mockClear()
  revokeMock.mockClear()
  startOAuthMock.mockClear()
  disconnectOAuthMock.mockClear()
  toastSuccess.mockClear()
  toastError.mockClear()
})

afterEach(() => {
  for (const renderer of renderers) {
    act(() => renderer.unmount())
  }
  renderers = []
})

async function render() {
  let renderer!: ReactTestRenderer
  act(() => {
    renderer = createRenderer(<UserToolConnections />)
  })
  renderers.push(renderer)
  await act(async () => {})
  return renderer
}

function buttonText(node: { children?: unknown }): string {
  const parts = Array.isArray(node.children) ? node.children : []
  return parts
    .map((child) => {
      if (typeof child === 'string') return child
      if (child && typeof child === 'object' && 'children' in child) {
        return buttonText(child as { children?: unknown })
      }
      return ''
    })
    .join('')
}

describe('UserToolConnections', () => {
  test('renders team required hint when no active team', async () => {
    currentTeam = null
    const renderer = await render()
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('settings.connections.noTeam')
  })

  test('loads and displays connection list with tool names and badges', async () => {
    const renderer = await render()
    const text = JSON.stringify(renderer.toJSON())

    expect(listConnectionsMock).toHaveBeenCalledWith('team-1', expect.anything())
    // Shows tool display names
    expect(text).toContain('GitHub')
    expect(text).toContain('PostgreSQL')
    // Shows connection names
    expect(text).toContain('My GitHub Account')
    expect(text).toContain('Local DB')
    // Shows account labels
    expect(text).toContain('yunhai@github.com')
    // Shows default badge
    expect(text).toContain('settings.connections.defaultBadge')
    // Shows reauth required badge
    expect(text).toContain('settings.connections.reauthRequired')
  })

  test('hides management actions on team connections for non-admin members', async () => {
    const teamConnection = {
      ...mockConnections[0],
      id: 'conn-team',
      tool_id: null,
      builtin_tool_key: 'postgresql_query',
      scope: 'team' as const,
      name: 'Shared DB',
      is_default: false,
    }
    listConnectionsMock.mockImplementation(() => Promise.resolve([teamConnection]))
    const renderer = await render()

    expect(renderer.root.findAllByType('button').some((b) => b.props.title === 'tools.connections.revoke')).toBe(false)
    expect(
      renderer.root.findAllByType('button').some((b) =>
        buttonText(b).includes('settings.connections.setDefault')
      )
    ).toBe(false)
  })

  test('allows team owners and admins to manage team connections', async () => {
    currentTeam = { id: 'team-1', name: 'Team One', role: 'admin' }
    const teamConnection = {
      ...mockConnections[0],
      id: 'conn-team',
      tool_id: null,
      builtin_tool_key: 'postgresql_query',
      scope: 'team' as const,
      name: 'Shared DB',
      is_default: false,
    }
    listConnectionsMock.mockImplementation(() => Promise.resolve([teamConnection]))
    const renderer = await render()

    expect(renderer.root.findAllByType('button').some((b) => b.props.title === 'tools.connections.revoke')).toBe(true)
  })

  test('supports setting a connection as default', async () => {
    const renderer = await render()
    const buttons = renderer.root.findAllByType('button')
    const setDefaultBtn = buttons.find((b) =>
      buttonText(b).includes('settings.connections.setDefault')
    )
    expect(setDefaultBtn).toBeDefined()

    await act(async () => {
      setDefaultBtn!.props.onClick()
    })

    expect(updateMock).toHaveBeenCalledWith('conn-2', { is_default: true })
    expect(toastSuccess).toHaveBeenCalledWith('settings.connections.setDefaultSuccess')
  })

  test('supports revoking/deleting a connection', async () => {
    const renderer = await render()
    const buttons = renderer.root.findAllByType('button')
    const deleteBtn = buttons.find((b) => b.props.title === 'tools.connections.revoke')
    expect(deleteBtn).toBeDefined()

    await act(async () => {
      deleteBtn!.props.onClick()
    })

    expect(revokeMock).toHaveBeenCalledWith('conn-1')
    expect(toastSuccess).toHaveBeenCalledWith('settings.connections.revokeSuccess')
  })

  test('supports launching OAuth for reconnect', async () => {
    const openMock = mock(() => {})
    const originalOpen = globalThis.window.open
    globalThis.window.open = openMock as unknown as typeof window.open

    try {
      const renderer = await render()
      const buttons = renderer.root.findAllByType('button')
      const reconnectBtn = buttons.find((b) =>
        buttonText(b).includes('settings.connections.reconnect')
      )
      expect(reconnectBtn).toBeDefined()

      await act(async () => {
        reconnectBtn!.props.onClick()
      })

      expect(startOAuthMock).toHaveBeenCalledWith('conn-2', expect.anything())
      expect(openMock).toHaveBeenCalledWith('https://oauth.example.test/start', '_blank', 'noopener,noreferrer')
    } finally {
      globalThis.window.open = originalOpen
    }
  })

  test('supports quick-creating a connection for an MCP tool', async () => {
    const renderer = await render()

    // Click "添加连接"
    const addBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('settings.connections.add')
    )
    expect(addBtn).toBeDefined()

    await act(async () => {
      addBtn!.props.onClick()
    })

    // Now quick-create card is open
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('settings.connections.createTitle')

    // Select GitHub tool
    const select = renderer.root.findByProps({ 'data-testid': 'tool-select' })
    await act(async () => {
      select.props.onChange({ target: { value: 'tool-mcp-1' } })
    })

    // Form should now show connection fields
    const inputs = renderer.root.findAllByType('input')
    const tokenInput = inputs.find((i) => i.props.id === 'field-github_token')
    expect(tokenInput).toBeDefined()

    // Fill token
    await act(async () => {
      tokenInput!.props.onChange({ target: { value: 'ghp_secret_token_123' } })
    })

    // Click Create
    const createBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('tools.connections.create')
    )
    expect(createBtn).toBeDefined()

    await act(async () => {
      createBtn!.props.onClick()
    })

    expect(createForToolMock).toHaveBeenCalledWith('tool-mcp-1', {
      team_id: 'team-1',
      scope: 'user',
      name: 'GitHub',
      account_label: null,
      config: {
        github_token: 'ghp_secret_token_123',
      },
    })
    expect(toastSuccess).toHaveBeenCalledWith('settings.connections.createdSuccess')
  })

  test('validates required secret fields during creation', async () => {
    const renderer = await render()

    // Click "添加连接"
    const addBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('settings.connections.add')
    )
    await act(async () => {
      addBtn!.props.onClick()
    })

    // Select PostgreSQL
    const select = renderer.root.findByProps({ 'data-testid': 'tool-select' })
    await act(async () => {
      select.props.onChange({ target: { value: 'postgresql_query' } })
    })

    // Submit with empty required fields
    const createBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('tools.connections.create')
    )
    await act(async () => {
      createBtn!.props.onClick()
    })

    // Should display validation error
    const alert = renderer.root.findByProps({ role: 'alert' })
    expect(alert).toBeDefined()
    expect(createForToolMock).not.toHaveBeenCalled()
    expect(createMock).not.toHaveBeenCalled()
  })

  test('creates a builtin connection with its materialized definition id', async () => {
    const renderer = await render()
    const addBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('settings.connections.add')
    )
    await act(async () => {
      addBtn!.props.onClick()
    })

    const select = renderer.root.findByProps({ 'data-testid': 'tool-select' })
    await act(async () => {
      select.props.onChange({ target: { value: 'postgresql_query' } })
    })

    // Declared select fields (SSL mode) render as selects, not free text.
    expect(renderer.root.findAllByProps({ 'data-testid': 'tool-select' })).toHaveLength(2)

    const inputs = renderer.root.findAllByType('input')
    for (const [id, value] of [
      ['field-host', 'db.internal'],
      ['field-password', 'secret'],
    ] as const) {
      const field = inputs.find((item) => item.props.id === id)!
      await act(async () => {
        field.props.onChange({ target: { value } })
      })
    }

    const createBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('tools.connections.create')
    )
    await act(async () => {
      createBtn!.props.onClick()
    })

    expect(createForToolMock).toHaveBeenCalledWith(
      'tool-builtin-1',
      expect.objectContaining({
        team_id: 'team-1',
        scope: 'user',
        name: 'PostgreSQL',
        config: expect.objectContaining({ host: 'db.internal', password: 'secret', port: '5432' }),
      })
    )
  })

  test('opens the client secret form and authorizes with it', async () => {
    const openMock = mock(() => {})
    const originalOpen = globalThis.window.open
    globalThis.window.open = openMock as unknown as typeof window.open

    try {
      const renderer = await render()
      const secretToggle = renderer.root.findAllByType('button').find((b) =>
        buttonText(b).includes('tools.connections.oauthClientSecret')
      )!
      await act(async () => {
        secretToggle.props.onClick()
      })

      const secretInput = renderer.root.findAllByType('input').find(
        (item) => item.props.id === 'client-secret-conn-1'
      )!
      await act(async () => {
        secretInput.props.onChange({ target: { value: 'client-secret' } })
      })

      const saveBtn = renderer.root.findAllByType('button').find((b) =>
        buttonText(b).includes('tools.connections.oauthSaveSecret')
      )!
      await act(async () => {
        saveBtn.props.onClick()
      })

      expect(startOAuthMock).toHaveBeenCalledWith('conn-1', expect.objectContaining({
        client_secret: 'client-secret',
      }))
      expect(openMock).toHaveBeenCalled()
    } finally {
      globalThis.window.open = originalOpen
    }
  })

  test('disconnects an authorized external account', async () => {
    const renderer = await render()
    const disconnectBtn = renderer.root.findAllByType('button').find((b) =>
      buttonText(b).includes('tools.connections.oauthDisconnect')
    )!
    await act(async () => {
      disconnectBtn.props.onClick()
    })

    expect(disconnectOAuthMock).toHaveBeenCalledWith('conn-1')
    expect(toastSuccess).toHaveBeenCalled()
  })

  test('shows the empty state when the user has no connections', async () => {
    listConnectionsMock.mockImplementation(() => Promise.resolve([]))
    const renderer = await render()
    const text = JSON.stringify(renderer.toJSON())
    expect(text).toContain('settings.connections.emptyTitle')
    expect(text).toContain('settings.connections.emptyDescription')
  })

  test('reports a load failure without breaking the tab', async () => {
    listConnectionsMock.mockImplementation(() => Promise.reject(new Error('offline')))
    const renderer = await render()
    expect(toastError).toHaveBeenCalledWith('tools.connections.loadFailed')
    expect(JSON.stringify(renderer.toJSON())).toContain('settings.connections.description')
  })
})

