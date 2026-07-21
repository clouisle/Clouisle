import React from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { renderToString } from 'react-dom/server'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const toolsApi = {
  listToolShares: mock(async () => ({ shares: [] })),
  shareTool: mock(async () => undefined),
  unshareTool: mock(async () => undefined),
  listMcpTools: mock(async () => ({ tools: [] })),
  test: mock(async () => ({ success: true, result: { ok: true } })),
}

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string, values?: Record<string, unknown>) => `${key}${values ? `:${Object.values(values).join(',')}` : ''}`,
    { has: () => true }
  ),
}))

mock.module('next/image', () => ({
  default: ({ alt = '', src = '' }: { alt?: string; src?: string }) => <img alt={alt} src={src} />,
}))

mock.module('sonner', () => ({ toast: { success: mock(), error: mock() } }))
mock.module('@/lib/api', () => ({ toolsApi }))
mock.module('@/lib/api/tools', () => ({}))

const passthrough = (tag: keyof React.JSX.IntrinsicElements = 'div') => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  return Component
}

mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  DialogContent: passthrough(),
  DialogDescription: passthrough('p'),
  DialogFooter: passthrough(),
  DialogHeader: passthrough(),
  DialogTitle: passthrough('h2'),
}))
mock.module('@/components/ui/sheet', () => ({
  Sheet: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  SheetContent: passthrough(),
  SheetDescription: passthrough('p'),
  SheetHeader: passthrough(),
  SheetTitle: passthrough('h2'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  AlertDialogAction: passthrough('button'),
  AlertDialogCancel: passthrough('button'),
  AlertDialogContent: passthrough(),
  AlertDialogDescription: passthrough('p'),
  AlertDialogFooter: passthrough(),
  AlertDialogHeader: passthrough(),
  AlertDialogTitle: passthrough('h2'),
}))
mock.module('@/components/ui/select', () => ({
  Select: passthrough(),
  SelectContent: passthrough(),
  SelectItem: passthrough(),
  SelectTrigger: passthrough('button'),
  SelectValue: passthrough('span'),
}))
mock.module('@/components/ui/button', () => ({ Button: passthrough('button') }))
mock.module('@/components/ui/input', () => ({ Input: passthrough('input') }))
mock.module('@/components/ui/label', () => ({ Label: passthrough('label') }))
mock.module('@/components/ui/field', () => ({ FieldError: passthrough('p') }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough('span') }))
mock.module('@/components/ui/card', () => ({ Card: passthrough(), CardContent: passthrough() }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: passthrough() }))
mock.module('@/components/ui/separator', () => ({ Separator: () => <hr /> }))
mock.module('lucide-react', () => ({
  Eye: passthrough('svg'),
  EyeOff: passthrough('svg'),
  ExternalLink: passthrough('svg'),
  Loader2: passthrough('svg'),
}))

import { HttpToolDialog } from './http-tool-dialog'
import { McpToolDialog } from './mcp-tool-dialog'
import { ApiError } from '@/lib/api/client'
import { ToolConfigDialog } from './tool-config-dialog'
import { ToolShareDialog } from './tool-share-dialog'
import { ToolTestPanel } from './tool-test-panel'

const baseTool = {
  id: 'tool-1',
  name: 'web_search',
  display_name: 'Web Search',
  description: 'Search the web',
  icon: '🔎',
  type: 'builtin',
  enabled: true,
  parameters: [],
  config_fields: ['TAVILY_API_KEY'],
  is_owned: true,
  team_id: 'team-1',
}

const httpTool = {
  ...baseTool,
  name: 'call_api',
  display_name: 'Call API',
  type: 'http',
  endpoint: 'https://example.com/api',
  method: 'POST',
  headers: { Authorization: 'Bearer token' },
}

const mcpTool = {
  ...baseTool,
  name: 'mcp_search',
  display_name: 'MCP Search',
  type: 'mcp',
  mcp_config: { server_url: 'https://mcp.example.com' },
}

const renderers: ReactTestRenderer[] = []

function nodeText(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join('')
  if (!node || typeof node !== 'object') return ''
  return nodeText((node as { children?: unknown }).children)
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true

beforeEach(() => {
  Object.values(toolsApi).forEach((fn) => fn.mockClear())
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

describe('platform capability component smoke coverage', () => {
  test('renders config dialog fields from tool config metadata', () => {
    const html = renderToString(
      <ToolConfigDialog
        tool={baseTool as never}
        open
        onOpenChange={() => undefined}
        onSave={async () => undefined}
        savedConfig={{ TAVILY_API_KEY: 'saved-key' }}
      />
    )

    expect(html).toContain('configDialog.title:Web Search')
    expect(html).toContain('TAVILY_API_KEY')
    expect(html).toContain('tvly-xxxxxxxxxx')
  })

  test('validates, reveals, saves, and reports config dialog API errors', async () => {
    const onSave = mock(async () => undefined)
    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(
        <ToolConfigDialog
          tool={baseTool as never}
          open
          onOpenChange={() => undefined}
          onSave={onSave}
          savedConfig={{ TAVILY_API_KEY: 'saved-key' }}
        />
      )
    })
    renderers.push(renderer!)

    await act(async () => renderer!.root.findAllByType('button').at(-1)!.props.onClick())
    expect(onSave).toHaveBeenCalledWith({ TAVILY_API_KEY: 'saved-key' })

    const input = renderer!.root.findByProps({ id: 'TAVILY_API_KEY' })
    act(() => input.props.onChange({ target: { value: '' } }))
    await act(async () => renderer!.root.findAllByType('button').at(-1)!.props.onClick())
    expect(renderer!.root.findByProps({ id: 'TAVILY_API_KEY' }).props['aria-invalid']).toBe(true)

    act(() => renderer!.root.findAllByType('button').find((button) => button.props.type === 'button')!.props.onClick())
    expect(renderer!.root.findByProps({ id: 'TAVILY_API_KEY' }).props.type).toBe('text')

    act(() => renderer!.root.findByProps({ id: 'TAVILY_API_KEY' }).props.onChange({ target: { value: 'new-key' } }))
    onSave.mockRejectedValueOnce(new ApiError(1001, 'invalid', { errors: { TAVILY_API_KEY: 'bad key' } }))
    await act(async () => renderer!.root.findAllByType('button').at(-1)!.props.onClick())
    expect(renderer!.root.findAllByType('p').map((node) => node.children.join(''))).toContain('bad key')
  })

  test('renders HTTP tool dialog in edit mode', () => {
    const html = renderToString(
      <HttpToolDialog
        tool={httpTool as never}
        open
        onOpenChange={() => undefined}
        onSave={async () => undefined}
        teams={[{ id: 'team-1', name: 'Core Team' }]}
        selectedTeamId="team-1"
      />
    )

    expect(html).toContain('httpDialog.editTitle')
    expect(html).toContain('form.name')
    expect(html).toContain('httpDialog.url')
  })

  test('renders MCP tool dialog server configuration', () => {
    const html = renderToString(
      <McpToolDialog
        tool={mcpTool as never}
        open
        onOpenChange={() => undefined}
        onSave={async () => undefined}
        teams={[{ id: 'team-1', name: 'Core Team' }]}
        selectedTeamId="team-1"
      />
    )

    expect(html).toContain('mcpDialog.editTitle')
    expect(html).toContain('mcpDialog.stdioMode')
    expect(html).toContain('mcpDialog.fetchTools')
  })

  test('renders share dialog and filters the current team', () => {
    const html = renderToString(
      <ToolShareDialog
        tool={baseTool as never}
        open
        onOpenChange={() => undefined}
        currentTeamId="team-1"
        availableTeams={[
          { id: 'team-1', name: 'Current Team', role: 'owner' },
          { id: 'team-2', name: 'Partner Team', role: 'member' },
        ] as never}
      />
    )

    expect(html).toContain('title')
    expect(html).toContain('Partner Team')
    expect(html).not.toContain('Current Team')
  })

  test('validates, shares, and unshares tools', async () => {
    const share = {
      id: 'share-1', shared_with_team_id: 'team-2', shared_with_team_name: 'Partner Team',
      permission: 'read_execute', shared_by_name: 'Ada',
    }
    toolsApi.listToolShares.mockResolvedValue({ shares: [share] })
    toolsApi.shareTool.mockResolvedValue(share)
    toolsApi.unshareTool.mockResolvedValue(undefined)
    const onSuccess = mock(() => undefined)
    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(
        <ToolShareDialog
          tool={baseTool as never}
          open
          onOpenChange={() => undefined}
          currentTeamId="team-1"
          availableTeams={[
            { id: 'team-1', name: 'Current Team', role: 'owner' },
            { id: 'team-2', name: 'Partner Team', role: 'member' },
            { id: 'team-3', name: 'Review Team', role: 'member' },
          ] as never}
          onSuccess={onSuccess}
        />
      )
    })
    renderers.push(renderer!)

    await act(async () => Promise.resolve())
    const shareButton = () => renderer!.root.findAllByType('button').find((button) => nodeText(button).includes('shareButton'))!
    await act(async () => shareButton().props.onClick())
    expect(renderer!.root.findAllByType('p').map((node) => node.children.join(''))).toContain('selectTeam')

    const selects = renderer!.root.findAll((node) => node.props.onValueChange)
    const teamSelect = selects.find((node) => node.props.value === undefined)!
    const permissionSelect = selects.find((node) => node.props.value === 'read_only')!
    act(() => {
      teamSelect.props.onValueChange('team-3')
      permissionSelect.props.onValueChange('read_execute')
    })
    await act(async () => shareButton().props.onClick())
    expect(toolsApi.shareTool).toHaveBeenCalledWith('tool-1', { team_id: 'team-3', permission: 'read_execute' })
    expect(onSuccess).toHaveBeenCalledTimes(1)

    act(() => renderer!.root.findAllByType('button').find((button) => button.props.className?.includes('text-destructive'))!.props.onClick())
    await act(async () => renderer!.root.findAllByType('button').find((button) => nodeText(button).includes('unshareButton'))!.props.onClick())
    expect(toolsApi.unshareTool).toHaveBeenCalledWith('tool-1', 'team-2')
    expect(onSuccess).toHaveBeenCalledTimes(2)
  })

  test('renders test panel parameter inputs for non-MCP tools', () => {
    const html = renderToString(
      <ToolTestPanel
        tool={{
          ...baseTool,
          parameters: [
            { name: 'query', type: 'string', required: true, description: 'Search query' },
            { name: 'limit', type: 'integer', required: false, default: 5 },
          ],
        } as never}
        open
        onOpenChange={() => undefined}
        api={toolsApi as never}
      />
    )

    expect(html).toContain('Search query')
    expect(html).toContain('query')
    expect(html).toContain('limit')
    expect(html).toContain('runTest')
  })

  test('runs tool tests with typed parameters and validation recovery', async () => {
    toolsApi.test
      .mockRejectedValueOnce(new ApiError(1001, 'invalid', { errors: { query: 'required' } }))
      .mockResolvedValueOnce({ success: true, result: { ok: true }, duration_ms: 25, logs: ['done'] })
    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(
        <ToolTestPanel
          tool={{
            ...baseTool,
            parameters: [
              { name: 'query', type: 'string', required: true, description: 'Search query' },
              { name: 'limit', type: 'integer', required: false, default: 5 },
              { name: 'enabled', type: 'boolean', required: false },
              { name: 'tags', type: 'array', required: false },
              { name: 'payload', type: 'object', required: false },
            ],
          } as never}
          open
          onOpenChange={() => undefined}
          api={toolsApi as never}
          teamId="team-1"
        />
      )
    })
    renderers.push(renderer!)

    await act(async () => renderer!.root.findAllByType('button').find((button) => nodeText(button).includes('runTest'))!.props.onClick())
    expect(renderer!.root.findAllByType('p').map((node) => node.children.join(''))).toContain('required')

    act(() => renderer!.root.findByProps({ id: 'query' }).props.onChange({ target: { value: 'cats' } }))
    act(() => renderer!.root.findByProps({ id: 'limit' }).props.onChange({ target: { value: '3' } }))
    act(() => renderer!.root.findByProps({ id: 'tags' }).props.onChange({ target: { value: '["a"]' } }))
    act(() => renderer!.root.findByProps({ id: 'payload' }).props.onChange({ target: { value: '{"x":1}' } }))
    act(() => renderer!.root.findAll((node) => node.props.onValueChange && node.props.value === '__empty__')[0].props.onValueChange('true'))
    await act(async () => renderer!.root.findAllByType('button').find((button) => nodeText(button).includes('runTest'))!.props.onClick())

    expect(toolsApi.test).toHaveBeenLastCalledWith({
      name: 'web_search',
      arguments: { query: 'cats', limit: 3, enabled: true, tags: ['a'], payload: { x: 1 } },
    }, 'team-1')
    expect(nodeText(renderer!.toJSON())).toContain('done')
  })
})
