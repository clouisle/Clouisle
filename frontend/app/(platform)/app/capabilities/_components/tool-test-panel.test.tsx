import React from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const toastSuccess = mock(() => {})
const toastError = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => <img alt={alt} src={src} />,
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
const listTools = mock(async () => ({ status: 'completed', operation: 'list:tools', execution_id: null, result: { items: [] }, pending_approval: null }))
mock.module('@/lib/api', () => ({ toolsApi: { test: mock(), getWebSearchEngines: mock(async () => ['tavily']) } }))
mock.module('@/lib/api/tool-mcp', () => ({ toolMcpApi: { listTools } }))
mock.module('@/components/tools/connection-picker', () => ({
  EMPTY_CONNECTION_BINDING: { connection_mode: null, connection_id: null },
  ToolConnectionPicker: () => <div data-connection-picker />,
}))
mock.module('@/components/tools/web-search-engine-select', () => ({
  WebSearchEngineSelect: ({ value, onValueChange }: { value: string; onValueChange: (value: string) => void }) => (
    <select aria-label="search-engine" value={value} onChange={(event) => onValueChange(event.target.value)}>
      <option value="auto">auto</option>
      <option value="tavily">tavily</option>
    </select>
  ),
}))
mock.module('@/lib/validation', () => ({
  normalizeValidationErrors: (error: { fields?: Record<string, string> }) => error.fields ?? {},
  clearValidationError: (errors: Record<string, string>, key: string) =>
    Object.fromEntries(Object.entries(errors).filter(([field]) => field !== key)),
  getValidationSummaryEntries: (errors: Record<string, string>, inlineFields: string[]) =>
    Object.entries(errors).filter(([field]) => !inlineFields.includes(field)),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const childrenOnly = ({ children }: React.PropsWithChildren) => <>{children}</>
mock.module('@/components/ui/sheet', () => ({
  Sheet: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <>{children}</> : null,
  SheetContent: childrenOnly,
  SheetDescription: childrenOnly,
  SheetHeader: childrenOnly,
  SheetTitle: childrenOnly,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<React.ButtonHTMLAttributes<HTMLButtonElement>>) =>
    <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren<React.LabelHTMLAttributes<HTMLLabelElement>>) =>
    <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) => children ? <span role="alert">{children}</span> : null,
}))
mock.module('@/components/ui/badge', () => ({ Badge: childrenOnly }))
mock.module('@/components/ui/card', () => ({ Card: childrenOnly, CardContent: childrenOnly }))
mock.module('@/components/ui/separator', () => ({ Separator: () => <hr /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) =>
    <select value={value} onChange={(event) => onValueChange(event.target.value)}>{children}</select>,
  SelectContent: childrenOnly,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) =>
    <option value={value}>{typeof children === 'string' ? children : value}</option>,
  SelectTrigger: childrenOnly,
  SelectValue: childrenOnly,
}))

const { ToolTestPanel } = await import('./tool-test-panel')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const baseTool = {
  id: 'tool-1',
  name: 'transform',
  display_name: 'Transform',
  description: 'Transform structured data',
  icon: '🧰',
  type: 'custom',
  category: 'other',
  parameters: [
    { name: 'query', type: 'string', required: true },
    { name: 'count', type: 'integer', required: false },
    { name: 'ratio', type: 'number', required: false },
    { name: 'enabled', type: 'boolean', required: false },
    { name: 'tags', type: 'array', required: false },
    { name: 'metadata', type: 'object', required: false },
    { name: 'mode', type: 'string', enum: ['fast', 'safe'], required: false },
  ],
  is_enabled: true,
  requires_config: false,
  config_fields: [],
} as const

const renderers: ReactTestRenderer[] = []
const consoleError = mock(() => {})
const originalConsoleError = console.error

beforeEach(() => {
  console.error = consoleError as never
  consoleError.mockClear()
  toastSuccess.mockClear()
  toastError.mockClear()
  listTools.mockClear()
  listTools.mockImplementation(async () => ({ status: 'completed', operation: 'list:tools', execution_id: null, result: { items: [] }, pending_approval: null }))
})

afterEach(() => {
  console.error = originalConsoleError
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(tool: unknown, api: { test: ReturnType<typeof mock> }) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(
      <ToolTestPanel tool={tool as never} open onOpenChange={() => {}} teamId="team-1" api={api as never} />,
    )
  })
  renderers.push(renderer!)
  return renderer!
}

function change(renderer: ReactTestRenderer, id: string, value: string) {
  act(() => renderer.root.findByProps({ id }).props.onChange({ target: { value } }))
}

function booleanSelect(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('select').find((select) =>
    select.findAllByType('option').some((option) => option.props.value === 'true'),
  )!
}

function runButton(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('button').find((button) =>
    button.children.some((child) => child === 'runTest' || child === 'testing'),
  )!
}

describe('tool test panel', () => {
  test('renders nothing at the null-tool boundary', () => {
    const api = { test: mock() }
    expect(render(null, api).toJSON()).toBeNull()
  })

  test('passes the chosen enabled engine when testing web search', async () => {
    const api = { test: mock(async () => ({ success: true, result: {} })) }
    const renderer = render({
      ...baseTool,
      type: 'builtin',
      name: 'web_search',
      parameters: [{ name: 'query', type: 'string', required: true }],
    }, api)

    change(renderer, 'query', 'weather')
    const engine = renderer.root.findByProps({ 'aria-label': 'search-engine' })
    expect(engine.props.value).toBe('auto')
    act(() => engine.props.onChange({ target: { value: 'tavily' } }))
    await act(async () => runButton(renderer).props.onClick())

    expect(api.test).toHaveBeenCalledWith(
      { name: 'web_search', arguments: { query: 'weather', search_engine: 'tavily' } },
      'team-1',
    )
  })

  test('converts regular and code-tool inputs before execution and shows loading and rich success output', async () => {
    let resolve!: (value: unknown) => void
    const pending = new Promise((next) => { resolve = next })
    const api = { test: mock(() => pending) }
    const renderer = render({ ...baseTool, type: 'code', icon: 'https://example.test/tool.png' }, api)

    expect(renderer.root.findByType('img').props.src).toBe('https://example.test/tool.png')
    change(renderer, 'query', 'hello')
    change(renderer, 'count', '12')
    change(renderer, 'ratio', '2.5')
    act(() => booleanSelect(renderer).props.onChange({ target: { value: 'true' } }))
    change(renderer, 'tags', '["a","b"]')
    change(renderer, 'metadata', '{not-json}')
    act(() => {
      const modeSelect = renderer.root.findAllByType('select').find((s) =>
        s.findAllByType('option').some((opt) => opt.props.value === 'safe'),
      )!
      modeSelect.props.onChange({ target: { value: 'safe' } })
    })
    let execution!: Promise<void>
    act(() => { execution = runButton(renderer).props.onClick() })
    expect(runButton(renderer).props.disabled).toBe(true)
    expect(JSON.stringify(renderer.toJSON())).toContain('testing')
    expect(api.test).toHaveBeenCalledWith({
      name: 'transform',
      arguments: {
        query: 'hello', count: 12, ratio: 2.5, enabled: true,
        tags: ['a', 'b'], metadata: '{not-json}', mode: 'safe',
      },
    }, 'team-1')

    resolve({
      name: 'transform', success: true, result: { ok: true }, logs: 'completed',
      artifacts: [{ path: '/workspace/report.json' }], duration_ms: 37,
    })
    await act(async () => execution)

    const output = JSON.stringify(renderer.toJSON())
    expect(output).toContain('success')
    expect(output).toContain('37')
    expect(output).toContain('completed')
    expect(output).toContain('/workspace/report.json')
  })

  test('renders execution failures and validation errors, then clears an edited field error', async () => {
    const api = {
      test: mock()
        .mockResolvedValueOnce({ name: 'transform', success: false, error: 'runtime exploded' })
        .mockRejectedValueOnce({ fields: { query: 'Query is required', __all__: 'Request rejected' } }),
    }
    const renderer = render(baseTool, api)

    await act(async () => runButton(renderer).props.onClick())
    expect(JSON.stringify(renderer.toJSON())).toContain('runtime exploded')
    expect(JSON.stringify(renderer.toJSON())).toContain('failed')

    await act(async () => runButton(renderer).props.onClick())
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(' '))).toEqual([
      'Query is required', 'Request rejected', 'Query is required',
    ])

    change(renderer, 'query', 'fixed')
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(' '))).toEqual([
      'Request rejected',
    ])
  })

  test('loads an MCP schema through the saved connection, parses values, and enforces selection boundaries', async () => {
    const api = {
      test: mock(async () => ({ name: 'mcp', success: true, result: 0, duration_ms: 0 })),
    }
    listTools.mockImplementation(async () => ({
      status: 'completed', operation: 'list:tools', execution_id: null, pending_approval: null,
      result: { items: [{
        name: 'lookup',
        title: null,
        description: 'Lookup records',
        parameters: {
          type: 'object',
          required: ['term'],
          properties: {
            term: { type: 'string', description: 'Lookup term' },
            limit: { type: 'integer' },
            filters: { type: 'object' },
            active: { type: 'boolean' },
            region: { type: 'string', enum: ['us', 'eu'] },
          },
        },
        output_schema: null,
        annotations: null,
        meta: null,
      }], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 1 },
    }))
    const renderer = render({
      ...baseTool,
      name: 'mcp',
      type: 'mcp',
      parameters: [],
    }, api)

    expect(runButton(renderer).props.disabled).toBe(true)
    await act(async () => {})
    expect(listTools).toHaveBeenCalledWith('tool-1', { teamId: 'team-1' })
    expect(runButton(renderer).props.disabled).toBe(false)
    expect(JSON.stringify(renderer.toJSON())).toContain('Lookup term')

    change(renderer, 'term', 'alpha')
    change(renderer, 'limit', '3')
    change(renderer, 'filters', '{"kind":"doc"}')
    act(() => booleanSelect(renderer).props.onChange({ target: { value: 'false' } }))
    act(() => {
      const regionSelect = renderer.root.findAllByType('select').find((s) =>
        s.findAllByType('option').some((opt) => opt.props.value === 'eu'),
      )!
      regionSelect.props.onChange({ target: { value: 'eu' } })
    })
    await act(async () => runButton(renderer).props.onClick())

    expect(api.test).toHaveBeenCalledWith({
      name: 'mcp',
      arguments: {
        term: 'alpha', limit: 3, filters: { kind: 'doc' }, active: false,
        region: 'eu', __tool_name__: 'lookup',
      },
    }, 'team-1')
    expect(JSON.stringify(renderer.toJSON())).toContain('0')
  })

  test('handles empty and failed saved MCP discovery without executing', async () => {
    listTools.mockImplementation(async () => ({
      status: 'completed', operation: 'list:tools', execution_id: null,
      result: { items: [], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 0 },
      pending_approval: null,
    }))
    const emptyApi = { test: mock() }
    const tool = {
      ...baseTool, name: 'mcp', type: 'mcp', parameters: [],
    }
    const empty = render(tool, emptyApi)
    await act(async () => {})
    expect(JSON.stringify(empty.toJSON())).toContain('mcpDialog.noToolsAvailable')
    expect(runButton(empty).props.disabled).toBe(true)

    listTools.mockImplementation(async () => { throw new Error('offline') })
    const failedApi = { test: mock() }
    const failed = render(tool, failedApi)
    await act(async () => {})
    expect(runButton(failed).props.disabled).toBe(true)
    expect(failedApi.test).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalledWith('testPanel.loadFailed')
  })

  test('handles parameter input enum and boolean select changes and empty selection', async () => {
    const tool = {
      ...baseTool,
      parameters: [
        { name: 'env', type: 'string', required: false, enum: ['staging', 'prod'] },
        { name: 'debug', type: 'boolean', required: false },
      ],
    }
    const api = { test: mock(async () => ({ success: true })) }
    const panel = render(tool as never, api)
    await act(async () => {})

    const selects = panel.root.findAllByType('select')
    act(() => {
      selects[0].props.onChange({ target: { value: 'staging' } })
      selects[1].props.onChange({ target: { value: 'true' } })
    })
    act(() => {
      selects[0].props.onChange({ target: { value: '__EMPTY__' } })
      selects[1].props.onChange({ target: { value: '__EMPTY__' } })
    })
    await act(async () => runButton(panel).props.onClick())
    expect(api.test).toHaveBeenCalled()
  })

  test('freezes a pending test request and resumes with the identical payload', async () => {
    const api = {
      test: mock()
        .mockResolvedValueOnce({
          name: 'transform', success: false, pending_approval: true, execution_id: 'exec-1',
        })
        .mockResolvedValueOnce({ name: 'transform', success: true, result: { ok: true } }),
    }
    const panel = render(baseTool, api)
    change(panel, 'query', 'hello')
    await act(async () => runButton(panel).props.onClick())

    expect(JSON.stringify(panel.toJSON())).toContain('testPanel.pendingApproval')
    expect(runButton(panel).props.disabled).toBe(true)

    const resume = panel.root.findAllByType('button').find((button) =>
      button.children.some((child) => child === 'testPanel.resume'),
    )!
    await act(async () => resume.props.onClick())

    expect(api.test).toHaveBeenLastCalledWith(
      { name: 'transform', arguments: { query: 'hello' }, execution_id: 'exec-1' },
      'team-1',
    )
    expect(api.test).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(panel.toJSON())).toContain('ok')
  })

  test('freezes pending saved MCP discovery and resumes the same page scope', async () => {
    listTools
      .mockResolvedValueOnce({
        status: 'pending_approval', operation: 'list:tools', execution_id: 'exec-2',
        result: null,
        pending_approval: { execution_id: 'exec-2', tool_name: 'mcp', status: 'awaiting_approval' },
      })
      .mockResolvedValueOnce({
        status: 'completed', operation: 'list:tools', execution_id: null, pending_approval: null,
        result: { items: [], pages_fetched: 1, truncated: false, truncation_reason: null, next_cursor: null, total_items: 0 },
      })
    const panel = render({ ...baseTool, name: 'mcp', type: 'mcp', parameters: [] }, { test: mock() })
    await act(async () => {})

    expect(JSON.stringify(panel.toJSON())).toContain('testPanel.pendingApproval')
    const resume = panel.root.findAllByType('button').find((button) =>
      button.children.some((child) => child === 'testPanel.resume'),
    )!
    await act(async () => resume.props.onClick())

    expect(listTools).toHaveBeenLastCalledWith('tool-1', {
      teamId: 'team-1', maxItems: 200, execution_id: 'exec-2',
    })
  })
})
