import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { GlobalRegistrator } from '@happy-dom/global-registrator'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const push = mock(() => {})
mock.module('next/navigation', () => ({
  useRouter: () => ({ push, replace: () => {}, back: () => {}, refresh: () => {} }),
  usePathname: () => '/app/capabilities',
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))
mock.module('next-intl', () => ({ useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}` }))
mock.module('lucide-react', () => ({
  AlertCircle: () => null, ChevronDown: () => null, Loader2: () => null,
  Plus: () => null, RefreshCw: () => null, Trash2: () => null,
}))
mock.module('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: React.ComponentProps<'span'>) => <span {...props}>{children}</span>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open = true }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <footer>{children}</footer>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: React.PropsWithChildren) => <div>{children}</div> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void }>) => (
    <select value={value ?? ''} onChange={(event) => onValueChange(event.target.value)}>{children}</select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  TabsContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <span role="alert">{children}</span> : null }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
const getCapabilities = mock(async () => ({
  status: 'completed', operation: 'list:capabilities', execution_id: null, pending_approval: null,
  result: { resources: true, resources_subscribe: true, resource_templates: true, prompts: true, server_name: 'Docs', server_version: '1.0' },
}))
const listResources = mock(async () => ({
  status: 'completed', operation: 'list:resources', execution_id: null, pending_approval: null,
  result: { items: [{ uri: 'doc://a', name: 'Doc', title: 'Doc', description: null, mime_type: 'text/plain', size: 4, annotations: null, meta: null }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 1 },
}))
const listResourceTemplates = mock(async () => ({
  status: 'completed', operation: 'list:resource-templates', execution_id: null, pending_approval: null,
  result: { items: [], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 0 },
}))
const listPrompts = mock(async () => ({
  status: 'completed', operation: 'list:prompts', execution_id: null, pending_approval: null,
  result: { items: [], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 0 },
}))
const readResource = mock(async () => ({
  status: 'completed', operation: 'read:resource', execution_id: null, pending_approval: null,
  result: [{ uri: 'doc://a', mime_type: 'text/plain', text: 'resource body', blob: null, meta: null }],
}))
let subscribeCallbacks: { onOpened: (event: Record<string, unknown>) => void; onUpdated: (event: Record<string, unknown>) => void; onClosed: (reason: string) => void } | null = null
const subscribeResource = mock((_toolId: string, _params: Record<string, unknown>, callbacks: NonNullable<typeof subscribeCallbacks>) => {
  subscribeCallbacks = callbacks
  return () => {}
})
const getPrompt = mock(async () => ({
  status: 'completed', operation: 'prompt:test', execution_id: null, pending_approval: null,
  result: { messages: [], description: null, meta: null },
}))
mock.module('@/lib/api/tool-mcp', () => ({
  toolMcpApi: { getCapabilities, listResources, listResourceTemplates, listPrompts, readResource, getPrompt, subscribeResource },
}))
const getAgents = mock(async () => ({ items: [{ id: 'agent-1', name: 'Assistant' }], total: 1, page: 1, page_size: 100, total_pages: 1 }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents } }))

// Dynamic import applies the module mocks before the browser loads.
const { McpToolBrowser } = await import('./mcp-tool-browser')

let renderer: ReactTestRenderer | undefined
afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
  mock.restore()
})

async function flush() {
  await act(async () => {})
}

function button(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find((item) => item.textContent?.includes(text))
}

async function render() {
  window.localStorage.setItem('access_token', 'test-token')
  await act(async () => {
    renderer = create(
      <McpToolBrowser
        tool={{ id: 'tool-1', name: 'docs', display_name: 'Docs', identity_policy: 'none', connection_fields: [] } as never}
        teamId="team-1"
        open
        onOpenChange={() => {}}
      />
    )
  })
  await flush()
}

describe('McpToolBrowser', () => {
  test('reads a resource and copies the untrusted preview into a one-use chat draft', async () => {
    await render()
    expect(getCapabilities).toHaveBeenCalledWith('tool-1', expect.objectContaining({ teamId: 'team-1' }))
    await flush()

    await act(async () => button('Doc')!.click())
    await flush()
    expect(readResource).toHaveBeenCalledWith('tool-1', 'team-1', 'doc://a', expect.anything())
    expect(document.body.textContent).toContain('resource body')

    await act(async () => button('tools.mcpBrowser.monitor.start')!.click())
    expect(subscribeResource).toHaveBeenCalledWith('tool-1', expect.objectContaining({ uri: 'doc://a' }), expect.anything())
    await act(async () => {
      subscribeCallbacks?.onOpened({
        subscription_id: 's1', tool_id: 'tool-1', team_id: 'team-1', uri: 'doc://a',
        connection_id: null, connection_scope: 'team', account_label: 'Docs team', expires_at: '2026-01-01T00:05:00Z',
      })
    })
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.open')
    await act(async () => {
      subscribeCallbacks?.onUpdated({ subscription_id: 's1', uri: 'doc://a', sequence: 1, received_at: 'now' })
    })
    expect(readResource).toHaveBeenCalledTimes(2)
    await act(async () => subscribeCallbacks?.onClosed('ttl_expired'))
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.closed')

    await act(async () => button('mcpBrowser.apply')!.click())
    await flush()
    expect(getAgents).toHaveBeenCalled()
    const agentSelect = Array.from(document.querySelectorAll('select')).at(-1)!
    await act(async () => {
      agentSelect.value = 'agent-1'
      agentSelect.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await act(async () => button('mcpBrowser.openChat')!.click())
    const draftKey = Object.keys(window.sessionStorage).find((key) => key.includes('team-1:agent-1'))
    expect(draftKey).toBeTruthy()
    expect(JSON.parse(window.sessionStorage.getItem(draftKey!)!).text).toContain('Untrusted external context')
    expect(push).toHaveBeenCalledWith('/chat/agent-1?draft=1&team=team-1')
  })
})
