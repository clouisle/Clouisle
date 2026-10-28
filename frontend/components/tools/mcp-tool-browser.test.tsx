import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { ApiError } from '@/lib/api/client'

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
  DialogContent: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
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
const TabsContext = React.createContext<{ value: string; onValueChange: (value: string) => void }>({
  value: '',
  onValueChange: () => {},
})
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void }>) => (
    <TabsContext.Provider value={{ value: value ?? '', onValueChange }}>{children}</TabsContext.Provider>
  ),
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: ({ children, value, disabled }: React.PropsWithChildren<{ value: string; disabled?: boolean }>) => {
    const tabs = React.useContext(TabsContext)
    return (
      <button type="button" data-tab={value} disabled={disabled} onClick={() => tabs.onValueChange(value)}>
        {children}
      </button>
    )
  },
  TabsContent: ({ children, value }: React.PropsWithChildren<{ value: string }>) => {
    const tabs = React.useContext(TabsContext)
    return tabs.value === value ? <div>{children}</div> : null
  },
}))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <span role="alert">{children}</span> : null }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))

const CAPABILITIES = {
  status: 'completed', operation: 'list:capabilities', execution_id: null, pending_approval: null,
  result: { resources: true, resources_subscribe: true, resource_templates: true, prompts: true, server_name: 'Docs', server_version: '1.0' },
}
const RESOURCES = {
  status: 'completed', operation: 'list:resources', execution_id: null, pending_approval: null,
  result: { items: [{ uri: 'doc://a', name: 'Doc', title: 'Doc', description: null, mime_type: 'text/plain', size: 4, annotations: null, meta: null }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 1 },
}
const TEMPLATES = {
  status: 'completed', operation: 'list:resource-templates', execution_id: null, pending_approval: null,
  result: { items: [], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 0 },
}
const PROMPTS = {
  status: 'completed', operation: 'list:prompts', execution_id: null, pending_approval: null,
  result: { items: [], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 0 },
}
const RESOURCE_BODY = {
  status: 'completed', operation: 'read:resource', execution_id: null, pending_approval: null,
  result: [
    { uri: 'doc://a', mime_type: 'text/plain', text: 'resource body', blob: null, meta: null },
    { uri: 'doc://a', mime_type: null, text: null, blob: null, meta: null },
  ],
}

type ApiOutcome = Record<string, unknown>
const getCapabilities = mock(async (): Promise<ApiOutcome> => CAPABILITIES)
const listResources = mock(async (): Promise<ApiOutcome> => RESOURCES)
const listResourceTemplates = mock(async (): Promise<ApiOutcome> => TEMPLATES)
const listPrompts = mock(async (): Promise<ApiOutcome> => PROMPTS)
const readResource = mock(async (): Promise<ApiOutcome> => RESOURCE_BODY)
let subscribeCallbacks: {
  onOpened: (event: Record<string, unknown>) => void
  onUpdated: (event: Record<string, unknown>) => void
  onClosed: (reason: string) => void
  onPendingApproval: (executionId: string) => void
} | null = null
const unsubscribeResource = mock(() => {})
const subscribeResource = mock((_toolId: string, _params: Record<string, unknown>, callbacks: NonNullable<typeof subscribeCallbacks>) => {
  subscribeCallbacks = callbacks
  return unsubscribeResource
})
const getPrompt = mock(async (): Promise<ApiOutcome> => ({
  status: 'completed', operation: 'prompt:test', execution_id: null, pending_approval: null,
  result: { messages: [], description: null, meta: null },
}))
mock.module('@/lib/api/tool-mcp', () => ({
  toolMcpApi: { getCapabilities, listResources, listResourceTemplates, listPrompts, readResource, getPrompt, subscribeResource },
}))
const getAgents = mock(async () => ({ items: [{ id: 'agent-1', name: 'Assistant' }], total: 1, page: 1, page_size: 100, total_pages: 1 }))
mock.module('@/lib/api/agents', () => ({ agentsApi: { getAgents } }))

// Test-only dynamic import: mock.module registrations above must be installed
// before this component (and its transitive UI imports) are evaluated.
const { McpToolBrowser } = await import('./mcp-tool-browser')

let renderer: ReactTestRenderer | undefined
afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
})

beforeEach(() => {
  for (const api of [getCapabilities, listResources, listResourceTemplates, listPrompts, readResource, getPrompt, subscribeResource, getAgents, unsubscribeResource, push]) {
    api.mockClear()
  }
  getCapabilities.mockImplementation(async () => CAPABILITIES)
  listResources.mockImplementation(async () => RESOURCES)
  listResourceTemplates.mockImplementation(async () => TEMPLATES)
  listPrompts.mockImplementation(async () => PROMPTS)
  readResource.mockImplementation(async () => RESOURCE_BODY)
  getPrompt.mockImplementation(async () => ({
    status: 'completed', operation: 'prompt:test', execution_id: null, pending_approval: null,
    result: { messages: [], description: null, meta: null },
  }))
  subscribeResource.mockImplementation((_toolId, _params, callbacks) => {
    subscribeCallbacks = callbacks
    return unsubscribeResource
  })
  getAgents.mockImplementation(async () => ({ items: [{ id: 'agent-1', name: 'Assistant' }], total: 1, page: 1, page_size: 100, total_pages: 1 }))
  subscribeCallbacks = null
  window.localStorage.clear()
  window.sessionStorage.clear()
})

async function flush() {
  await act(async () => {})
}

function buttons(text: string): HTMLButtonElement[] {
  return Array.from(document.querySelectorAll('button')).filter((item) => item.textContent?.includes(text))
}

function button(text: string): HTMLButtonElement | undefined {
  return buttons(text)[0]
}

async function click(text: string, index = 0) {
  await act(async () => buttons(text)[index]!.click())
  await flush()
}

async function select(element: HTMLSelectElement, value: string) {
  await act(async () => {
    element.value = value
    element.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await flush()
}

async function render(options: { open?: boolean; toolId?: string; onOpenChange?: (open: boolean) => void } = {}) {
  window.localStorage.setItem('access_token', 'test-token')
  await act(async () => {
    renderer = create(
      <McpToolBrowser
        tool={{ id: options.toolId ?? 'tool-1', name: 'docs', display_name: 'Docs', identity_policy: 'none', connection_fields: [] } as never}
        teamId="team-1"
        open={options.open ?? true}
        onOpenChange={options.onOpenChange ?? (() => {})}
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
    expect(JSON.parse(window.sessionStorage.getItem(draftKey!)!).text).toContain('tools.mcpBrowser.draftResourceNotice')
    expect(push).toHaveBeenCalledWith('/chat/agent-1?draft=1&team=team-1')
  })

  test('gates tabs and monitoring on advertised capabilities', async () => {
    getCapabilities.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'list:capabilities', execution_id: null, pending_approval: null,
      result: { resources: true, resources_subscribe: false, resource_templates: false, prompts: false, server_name: null, server_version: null },
    }))
    await render()

    expect(document.body.textContent).toContain('tools.mcpBrowser.serverUnknown')
    expect(button('tools.mcpBrowser.tabs.resources')!.disabled).toBe(false)
    expect(button('tools.mcpBrowser.tabs.templates')!.disabled).toBe(true)
    expect(button('tools.mcpBrowser.tabs.prompts')!.disabled).toBe(true)
    expect(button('tools.mcpBrowser.monitor.start')).toBeUndefined()
    expect(document.body.textContent).toContain('Doc')
  })

  test('does not request unsupported capabilities and selects a supported tab', async () => {
    getCapabilities.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'list:capabilities', execution_id: null, pending_approval: null,
      result: { resources: false, resources_subscribe: false, resource_templates: false, prompts: true, server_name: 'Prompts only', server_version: null },
    }))
    await render()

    expect(listResources).not.toHaveBeenCalled()
    expect(listResourceTemplates).not.toHaveBeenCalled()
    expect(listPrompts).toHaveBeenCalledTimes(1)
    expect(button('tools.mcpBrowser.tabs.resources')!.disabled).toBe(true)
    expect(button('tools.mcpBrowser.tabs.prompts')!.disabled).toBe(false)
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.resources.empty')
  })

  test('shows an honest unsupported state when no browsing capability exists', async () => {
    getCapabilities.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'list:capabilities', execution_id: null, pending_approval: null,
      result: { resources: false, resources_subscribe: false, resource_templates: false, prompts: false, server_name: 'Empty', server_version: null },
    }))
    await render()

    expect(listResources).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('tools.mcpBrowser.unsupported.resources')
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.resources.empty')
  })

  test('resets the active tab when the server changes', async () => {
    await render()
    await click('tools.mcpBrowser.tabs.templates')
    expect(listResourceTemplates).toHaveBeenCalledTimes(1)

    await act(async () => {
      renderer!.update(
        <McpToolBrowser
          tool={{ id: 'tool-2', name: 'other', display_name: 'Other', identity_policy: 'none', connection_fields: [] } as never}
          teamId="team-1"
          open
          onOpenChange={() => {}}
        />
      )
    })
    await flush()

    expect(getCapabilities).toHaveBeenLastCalledWith('tool-2', expect.anything())
    expect(listResources).toHaveBeenLastCalledWith('tool-2', expect.anything())
    expect(listResourceTemplates).toHaveBeenCalledTimes(1)
    expect(button('Doc')).toBeTruthy()
  })

  test('shows truncation notices for partial lists and previews', async () => {
    listResources.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'list:resources', execution_id: null, pending_approval: null,
      result: {
        items: [{ uri: 'doc://a', name: 'Doc', title: 'Doc', description: null, mime_type: 'text/plain', size: 4, annotations: null, meta: null }],
        pages_fetched: 1, truncated: true, truncation_reason: 'max_items', next_cursor: null, total_items: 3,
      },
    }))
    readResource.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'read:resource', execution_id: null, pending_approval: null,
      result: [{ uri: 'doc://a', mime_type: 'text/plain', text: 'x'.repeat(6001), blob: null, meta: null }],
    }))
    await render()

    expect(document.body.textContent).toContain('tools.mcpBrowser.truncated.list')
    await click('Doc')
    expect(document.body.textContent).toContain('tools.mcpBrowser.previewTruncated')
  })

  test('shows the localized API error and legacy policy guidance', async () => {
    getCapabilities.mockRejectedValueOnce(new ApiError(6510, 'This tool needs a caller confirmation policy.'))
    await render()

    expect(document.body.textContent).toContain('This tool needs a caller confirmation policy.')
    expect(document.body.textContent).toContain('tools.mcpBrowser.policyGuidance')
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.loadFailed')
  })

  test('closes with Escape and stops an active monitor', async () => {
    const onOpenChange = mock(() => {})
    await render({ onOpenChange })
    await click('tools.mcpBrowser.monitor.start')
    const dialog = renderer!.root.findAll(
      (node) => node.props.className === 'sm:max-w-4xl max-h-[90vh] overflow-y-auto'
    )[0]
    expect(dialog).toBeTruthy()

    await act(async () => {
      dialog.props.onKeyDownCapture({ key: 'Escape', preventDefault() {}, stopPropagation() {} })
    })

    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(unsubscribeResource).toHaveBeenCalledTimes(1)

    await click('tools.mcpBrowser.close')
    expect(onOpenChange).toHaveBeenCalledTimes(2)
  })


  test('shows loading, reports discovery failure, and recovers on refresh', async () => {
    const capabilitiesRequest = Promise.withResolvers<ApiOutcome>()
    getCapabilities.mockImplementationOnce(() => capabilitiesRequest.promise)
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

    expect(document.body.textContent).toContain('tools.mcpBrowser.loading')
    expect(button('tools.mcpBrowser.tabs.resources')!.disabled).toBe(true)
    await act(async () => capabilitiesRequest.resolve(CAPABILITIES))
    await flush()
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.loading')
    expect(document.body.textContent).toContain('tools.mcpBrowser.serverInfo')

    getCapabilities.mockRejectedValueOnce(new Error('offline'))
    await click('tools.mcpBrowser.refresh')
    expect(document.body.textContent).toContain('tools.mcpBrowser.loadFailed')
    expect(button('tools.mcpBrowser.tabs.resources')!.disabled).toBe(true)

    await click('tools.mcpBrowser.refresh')
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.loadFailed')
    expect(document.body.textContent).toContain('tools.mcpBrowser.serverInfo')
    expect(button('tools.mcpBrowser.tabs.prompts')!.disabled).toBe(false)
  })

  test('reports a failed resource listing without claiming the list is empty', async () => {
    listResources.mockRejectedValueOnce(new Error('listing offline'))
    await render()

    expect(document.body.textContent).toContain('tools.mcpBrowser.loadFailed')
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.resources.empty')
  })

  test('retries capability discovery that awaits approval', async () => {
    getCapabilities.mockImplementationOnce(async () => ({
      status: 'pending_approval', operation: 'list:capabilities', execution_id: 'exec-capabilities',
      pending_approval: null, result: null,
    }))
    await render()
    expect(document.body.textContent).toContain('tools.mcpBrowser.pendingApproval')
    expect(listResources).not.toHaveBeenCalled()

    getCapabilities.mockImplementationOnce(async () => CAPABILITIES)
    await click('tools.mcpBrowser.retryApproval')
    expect(getCapabilities).toHaveBeenLastCalledWith('tool-1', expect.objectContaining({ execution_id: 'exec-capabilities' }))
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.pendingApproval')
    expect(document.body.textContent).toContain('Doc')
  })

  test('retries a resource listing that awaits approval', async () => {
    listResources.mockImplementationOnce(async () => ({
      status: 'pending_approval', operation: 'list:resources', execution_id: null,
      pending_approval: { execution_id: 'exec-list', tool_name: 'list_resources', status: 'awaiting_approval' },
      result: null,
    }))
    await render()
    expect(document.body.textContent).toContain('tools.mcpBrowser.pendingApproval')

    await click('tools.mcpBrowser.retryApproval')
    expect(listResources).toHaveBeenLastCalledWith('tool-1', expect.objectContaining({ execution_id: 'exec-list' }))
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.pendingApproval')
    expect(document.body.textContent).toContain('Doc')
  })

  test('paginates resources and expands templates into an editable URI', async () => {
    listResources
      .mockImplementationOnce(async () => ({
        status: 'completed', operation: 'list:resources', execution_id: null, pending_approval: null,
        result: {
          items: [
            { uri: 'doc://a', name: 'Doc', title: 'Doc', description: null, mime_type: 'text/plain', size: 4, annotations: null, meta: null },
            { uri: 'doc://b', name: 'Second', title: null, description: 'Second doc', mime_type: null, size: null, annotations: null, meta: null },
          ],
          pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: 'cursor-r', total_items: 3,
        },
      }))
      .mockImplementationOnce(async () => ({
        status: 'completed', operation: 'list:resources', execution_id: null, pending_approval: null,
        result: { items: [{ uri: 'doc://c', name: null, title: null, description: null, mime_type: null, size: null, annotations: null, meta: null }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 3 },
      }))
    listResourceTemplates
      .mockImplementationOnce(async () => ({
        status: 'completed', operation: 'list:resource-templates', execution_id: null, pending_approval: null,
        result: { items: [{ uri_template: 'doc://{id}', name: null, title: null, description: null, mime_type: null, annotations: null, meta: null }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: 'cursor-t', total_items: 2 },
      }))
      .mockImplementationOnce(async () => ({
        status: 'completed', operation: 'list:resource-templates', execution_id: null, pending_approval: null,
        result: { items: [{ uri_template: 'doc://second/{id}', name: null, title: 'Second template', description: null, mime_type: null, annotations: null, meta: null }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 2 },
      }))
    await render()

    expect(button('Second')).toBeTruthy()
    expect(button('doc://c')).toBeUndefined()
    await click('tools.mcpBrowser.loadMore')
    expect(listResources).toHaveBeenLastCalledWith('tool-1', expect.objectContaining({ cursor: 'cursor-r' }))
    expect(button('doc://c')).toBeTruthy()
    expect(button('Doc')).toBeTruthy()

    await click('tools.mcpBrowser.tabs.templates')
    expect(document.body.textContent).toContain('doc://{id}')
    await click('tools.mcpBrowser.loadMore')
    expect(listResourceTemplates).toHaveBeenLastCalledWith('tool-1', expect.objectContaining({ cursor: 'cursor-t' }))
    expect(document.body.textContent).toContain('Second template')
    await click('tools.mcpBrowser.templates.expand', 0)
    const uriInput = renderer!.root.findByProps({ value: 'doc://{id}' })
    expect((document.querySelector('input') as HTMLInputElement).value).toBe('doc://{id}')
    expect(document.body.textContent).toContain('tools.mcpBrowser.templates.unexpanded')
    expect(button('tools.mcpBrowser.templates.read')!.disabled).toBe(true)
    await act(async () => uriInput.props.onChange({ target: { value: '   ' } }))
    await flush()
    expect(button('tools.mcpBrowser.templates.read')!.disabled).toBe(true)
    await act(async () => uriInput.props.onChange({ target: { value: 'doc://edited' } }))
    await flush()
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.templates.unexpanded')
    await click('tools.mcpBrowser.templates.read')
    expect(readResource).toHaveBeenLastCalledWith('tool-1', 'team-1', 'doc://edited', expect.anything())
  })

  test('selects prompts, requires mandatory arguments, and previews message content', async () => {
    listPrompts.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'list:prompts', execution_id: null, pending_approval: null,
      result: {
        items: [
          {
            name: 'summarize', title: null, description: 'Summarize a topic',
            arguments: [
              { name: 'topic', description: 'Topic name', required: true },
              { name: 'style', description: null, required: false },
            ],
            meta: null,
          },
          { name: 'translate', title: 'Translate', description: null, arguments: [], meta: null },
        ],
        pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: 'cursor-p', total_items: 3,
      },
    })).mockImplementationOnce(async () => ({
      status: 'completed', operation: 'list:prompts', execution_id: null, pending_approval: null,
      result: { items: [{ name: 'rewrite', title: 'Rewrite', description: null, arguments: [], meta: null }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 3 },
    }))
    getPrompt.mockImplementationOnce(async () => ({
      status: 'completed', operation: 'prompt:summarize', execution_id: null, pending_approval: null,
      result: {
        messages: [
          { role: 'user', content: { text: 'hello world' } },
          { role: 'assistant', content: { type: 'text', data: 'from data' } },
          { role: 'system', content: { type: 'image' } },
        ],
        description: null,
        meta: null,
      },
    }))
    await render()
    await click('tools.mcpBrowser.tabs.prompts')

    expect(document.body.textContent).toContain('summarize')
    await click('tools.mcpBrowser.loadMore')
    expect(listPrompts).toHaveBeenLastCalledWith('tool-1', expect.objectContaining({ cursor: 'cursor-p' }))
    expect(document.body.textContent).toContain('Rewrite')

    await click('tools.mcpBrowser.prompts.use', 0)
    const promptInputs = Array.from(document.querySelectorAll('input'))
    expect(promptInputs).toHaveLength(2)
    expect(button('tools.mcpBrowser.prompts.get')!.disabled).toBe(true)
    const topicInput = renderer!.root.findByProps({ placeholder: 'Topic name' })
    await act(async () => topicInput.props.onChange({ target: { value: 'agents' } }))
    await flush()
    expect(button('tools.mcpBrowser.prompts.get')!.disabled).toBe(false)

    await click('tools.mcpBrowser.prompts.get')
    expect(getPrompt).toHaveBeenCalledWith('tool-1', 'team-1', 'summarize', { topic: 'agents' }, expect.anything())
    expect(document.body.textContent).toContain('hello world')
    expect(document.body.textContent).toContain('from data')
    expect(document.body.textContent).toContain('user')
    expect(document.body.textContent).toContain('assistant')
    expect(document.body.textContent).toContain('system')
    expect(document.body.textContent).toContain('tools.mcpBrowser.untrustedPrompt')
    expect(document.body.textContent).not.toContain('Untrusted external context from MCP prompt')

    await click('tools.mcpBrowser.apply')
    await select(Array.from(document.querySelectorAll('select')).at(-1)!, 'agent-1')
    await click('tools.mcpBrowser.openChat')
    const promptDraftKey = Object.keys(window.sessionStorage).find((key) => key.includes('team-1:agent-1'))
    expect(promptDraftKey).toBeTruthy()
    const promptDraft = JSON.parse(window.sessionStorage.getItem(promptDraftKey!)!).text as string
    expect(promptDraft).toContain('tools.mcpBrowser.draftPromptNotice')
    expect(promptDraft).toContain('[user] hello world')
    expect(promptDraft).toContain('[assistant] from data')
    expect(push).toHaveBeenCalledWith('/chat/agent-1?draft=1&team=team-1')

    await click('tools.mcpBrowser.prompts.use', 1)
    expect(document.querySelectorAll('input')).toHaveLength(0)
    expect(button('tools.mcpBrowser.prompts.get')!.disabled).toBe(false)
    expect(document.body.textContent).not.toContain('hello world')

    getPrompt.mockImplementationOnce(async () => ({
      status: 'pending_approval', operation: 'prompt:translate', execution_id: null,
      pending_approval: { execution_id: 'exec-prompt', tool_name: 'get_prompt', status: 'awaiting_approval' },
      result: null,
    }))
    await click('tools.mcpBrowser.prompts.get')
    expect(document.body.textContent).toContain('tools.mcpBrowser.pendingApproval')
    expect(button('tools.mcpBrowser.apply')!.disabled).toBe(true)
  })

  test('surfaces pending and binary resource previews without offering an empty draft', async () => {
    readResource
      .mockImplementationOnce(async () => ({
        status: 'pending_approval', operation: 'read:resource', execution_id: null,
        pending_approval: { execution_id: 'exec-read', tool_name: 'read_resource', status: 'awaiting_approval' },
        result: null,
      }))
      .mockImplementationOnce(async () => ({
        status: 'completed', operation: 'read:resource', execution_id: null, pending_approval: null,
        result: [{ uri: 'doc://a', mime_type: null, text: null, blob: 'AAAA', meta: null }],
      }))
    await render()

    await click('Doc')
    expect(document.body.textContent).toContain('tools.mcpBrowser.pendingApproval')
    expect(button('tools.mcpBrowser.apply')!.disabled).toBe(true)

    await click('Doc')
    expect(document.body.textContent).toContain('tools.mcpBrowser.binaryResource')
    expect(button('tools.mcpBrowser.apply')!.disabled).toBe(true)

    readResource.mockRejectedValueOnce(new Error('broken resource'))
    await click('Doc')
    expect(document.body.textContent).toContain('tools.mcpBrowser.loadFailed')
  })

  test('manages the subscription monitor lifecycle across pending, stop, and reconnect states', async () => {
    await render()

    await click('tools.mcpBrowser.monitor.start')
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.connecting')
    await click('tools.mcpBrowser.monitor.stop')
    expect(unsubscribeResource).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).not.toContain('tools.mcpBrowser.monitor.connecting')

    await click('tools.mcpBrowser.monitor.start')
    await act(async () => subscribeCallbacks?.onPendingApproval('exec-monitor'))
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.pending')
    await click('tools.mcpBrowser.monitor.retry')
    expect(subscribeResource).toHaveBeenLastCalledWith('tool-1', expect.objectContaining({ uri: 'doc://a', execution_id: 'exec-monitor' }), expect.anything())

    await act(async () => {
      subscribeCallbacks?.onOpened({
        subscription_id: 's2', tool_id: 'tool-1', team_id: 'team-1', uri: 'doc://a',
        connection_id: null, connection_scope: '', account_label: null, expires_at: '2026-01-01T00:05:00Z',
      })
    })
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.open')
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.updates')
    await act(async () => subscribeCallbacks?.onClosed('token_revoked'))
    expect(document.body.textContent).toContain('tools.mcpBrowser.monitor.closed')
    await click('tools.mcpBrowser.monitor.reconnect')
    expect(subscribeResource).toHaveBeenCalledTimes(4)
    expect(subscribeResource.mock.calls.at(-1)![1].execution_id).toBeUndefined()
  })

  test('shows the empty agent state and blocks applying the draft', async () => {
    getAgents.mockRejectedValueOnce(new Error('agents offline'))
    await render()
    await click('Doc')
    expect(button('tools.mcpBrowser.apply')).toBeTruthy()

    await click('tools.mcpBrowser.apply')
    expect(document.body.textContent).toContain('tools.mcpBrowser.noAgents')
    expect(button('tools.mcpBrowser.openChat')!.disabled).toBe(true)
  })

  test('blocks applying a draft when no credential is available', async () => {
    await render()
    await click('Doc')
    await click('tools.mcpBrowser.apply')

    window.localStorage.removeItem('access_token')
    const agentSelect = Array.from(document.querySelectorAll('select')).at(-1)!
    expect(agentSelect.options).toHaveLength(1)
    await select(agentSelect, 'agent-1')
    await click('tools.mcpBrowser.openChat')
    expect(document.body.textContent).toContain('tools.mcpBrowser.draftUnavailable')
    expect(push).not.toHaveBeenCalled()
    expect(Object.keys(window.sessionStorage).some((key) => key.includes('team-1:agent-1'))).toBe(false)
  })
})
