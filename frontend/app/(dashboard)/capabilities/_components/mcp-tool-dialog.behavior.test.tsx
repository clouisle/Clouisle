import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const toastError = mock(() => {})
const toastInfo = mock(() => {})
const toastSuccess = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    `${namespace}.${key}${values ? JSON.stringify(values) : ''}`,
}))
mock.module('sonner', () => ({ toast: { error: toastError, info: toastInfo, success: toastSuccess } }))
mock.module('lucide-react', () => ({
  CheckCircle2: () => null,
  Globe: () => null,
  Info: () => null,
  Loader2: () => null,
  Plus: () => null,
  RefreshCw: () => null,
  Terminal: () => null,
  Trash2: () => null,
}))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/card', () => ({ Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section> }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div role="dialog">{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} {...props} /> }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  TabsContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement } & Record<string, unknown>) =>
    render ? React.cloneElement(render, { ...props, ...(children !== undefined ? { children } : {}) }) : <button {...props}>{children}</button>,
}))

import { adminToolsApi } from '@/lib/api/admin'
import { McpToolDialog } from './mcp-tool-dialog'

const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function text(value: React.ReactNode): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement(value)) return text(value.props.children)
  return ''
}

function render(props: Partial<React.ComponentProps<typeof McpToolDialog>> = {}) {
  const onOpenChange = mock(() => {})
  const onSave = mock(async () => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<McpToolDialog open onOpenChange={onOpenChange} onSave={onSave} {...props} />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onOpenChange, onSave }
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => text(item.props.children).includes(label))!
const input = (renderer: ReactTestRenderer, props: Record<string, unknown>) => renderer.root.findAllByType('input').find((item) => Object.entries(props).every(([key, value]) => item.props[key] === value))!

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  toastError.mockClear()
  toastInfo.mockClear()
  toastSuccess.mockClear()
})

describe('McpToolDialog', () => {
  test('validates required stdio fields, loads tools, and saves a created server', async () => {
    const listMcpTools = spyOn(adminToolsApi, 'listMcpTools').mockResolvedValue({ tools: [{ name: 'search', description: 'Searches' }] })
    const { renderer, onSave, onOpenChange } = render()

    await act(async () => button(renderer, 'common.create').props.onClick())
    expect(renderer.root.findAllByProps({ role: 'alert' }).length).toBeGreaterThan(0)

    act(() => input(renderer, { id: 'name' }).props.onChange({ target: { value: 'mcp_search' } }))
    act(() => input(renderer, { id: 'displayName' }).props.onChange({ target: { value: 'MCP Search' } }))
    act(() => input(renderer, { id: 'icon' }).props.onChange({ target: { value: '🔎' } }))
    act(() => input(renderer, { id: 'command' }).props.onChange({ target: { value: 'npx' } }))
    act(() => input(renderer, { placeholder: 'tools.mcpDialog.argumentPlaceholder{"index":1}' }).props.onChange({ target: { value: '-y' } }))
    const envInputs = renderer.root.findAllByType('input').filter((item) => item.props.placeholder === 'tools.mcpDialog.headerKeyPlaceholder' || item.props.placeholder === 'tools.mcpDialog.headerValuePlaceholder')
    act(() => envInputs[0]!.props.onChange({ target: { value: 'NODE_ENV' } }))
    act(() => envInputs[1]!.props.onChange({ target: { value: 'test' } }))

    await act(async () => button(renderer, 'tools.mcpDialog.fetchTools').props.onClick())
    await act(async () => button(renderer, 'common.create').props.onClick())

    expect(listMcpTools).toHaveBeenCalledWith({ transport: 'stdio', command: 'npx', args: ['-y'], env: { NODE_ENV: 'test' } })
    expect(toastSuccess).toHaveBeenCalledWith('tools.mcpDialog.toolsLoaded{"count":1}')
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'mcp_search',
      display_name: 'MCP Search',
      description: '- search: Searches',
      icon: '🔎',
      type: 'mcp',
      mcp_config: { transport: 'stdio', command: 'npx', args: ['-y'], env: { NODE_ENV: 'test' } },
    }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('uses HTTP transport headers and reports empty tool discovery', async () => {
    const listMcpTools = spyOn(adminToolsApi, 'listMcpTools').mockResolvedValue({ tools: [] })
    const { renderer, onSave } = render()

    act(() => renderer.root.findByProps({ value: 'stdio' }).props.onValueChange('http'))
    act(() => input(renderer, { id: 'name' }).props.onChange({ target: { value: 'mcp_http' } }))
    act(() => input(renderer, { id: 'displayName' }).props.onChange({ target: { value: 'HTTP MCP' } }))
    act(() => input(renderer, { id: 'http-url' }).props.onChange({ target: { value: 'https://mcp.example.test' } }))
    const headerInputs = renderer.root.findAllByType('input').filter((item) => item.props.placeholder === 'tools.mcpDialog.headerNamePlaceholder' || item.props.placeholder === 'tools.mcpDialog.headerValuePlaceholder')
    act(() => headerInputs.at(-2)!.props.onChange({ target: { value: 'Authorization' } }))
    act(() => headerInputs.at(-1)!.props.onChange({ target: { value: 'Bearer token' } }))

    await act(async () => button(renderer, 'tools.mcpDialog.fetchTools').props.onClick())
    await act(async () => button(renderer, 'common.create').props.onClick())

    expect(listMcpTools).toHaveBeenCalledWith({ transport: 'http', url: 'https://mcp.example.test', headers: { Authorization: 'Bearer token' } })
    expect(toastInfo).toHaveBeenCalledWith('tools.mcpDialog.noToolsFound')
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ mcp_config: { transport: 'http', url: 'https://mcp.example.test', headers: { Authorization: 'Bearer token' } } }))
  })

  test('hydrates an existing SSE tool and keeps the name immutable', async () => {
    const onSave = mock(async () => {})
    const { renderer } = render({
      onSave,
      tool: {
        name: 'existing', display_name: 'Existing MCP', description: '', type: 'mcp', category: 'other', parameters: [], is_enabled: false,
        requires_config: false, config_fields: [], mcp_config: { transport: 'sse', url: 'https://mcp.example.test/sse', headers: { 'X-Test': '1' } },
      },
    })

    expect(input(renderer, { id: 'name' }).props.disabled).toBe(true)
    act(() => input(renderer, { id: 'displayName' }).props.onChange({ target: { value: 'Existing Updated' } }))
    await act(async () => button(renderer, 'common.save').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'existing',
      display_name: 'Existing Updated',
      is_enabled: false,
      mcp_config: { transport: 'sse', url: 'https://mcp.example.test/sse', headers: { 'X-Test': '1' } },
    }))
  })
})
