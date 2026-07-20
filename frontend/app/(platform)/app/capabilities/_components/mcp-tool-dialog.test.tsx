import React from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const listMcpTools = mock(async () => ({ tools: [] as Array<{ name: string; description?: string; parameters: Record<string, unknown> }> }))
const toastInfo = mock(() => undefined)
const toastSuccess = mock(() => undefined)

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { info: toastInfo, success: toastSuccess } }))
mock.module('@/lib/api/tools', () => ({ toolsApi: { listMcpTools } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => field !== key)),
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => !field.startsWith(prefix))),
  normalizeValidationErrors: (error: unknown) => error as Record<string, string>,
  mapValidationErrors: (errors: Record<string, string>, paths: Record<string, string>) => Object.fromEntries(Object.entries(errors).map(([field, message]) => [paths[field] ?? field, message])),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const children = ({ children }: React.PropsWithChildren) => <>{children}</>
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children: content }: React.PropsWithChildren<{ open?: boolean }>) => open ? <>{content}</> : null,
  DialogContent: children, DialogDescription: children, DialogFooter: children, DialogHeader: children, DialogTitle: children,
}))
mock.module('@/components/ui/button', () => ({ Button: ({ children: content, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{content}</button> }))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children: content, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{content}</label> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children: content }: React.PropsWithChildren) => content ? <span role="alert">{content}</span> : null }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, id }: { checked: boolean; onCheckedChange: (checked: boolean) => void; id?: string }) =>
    <input id={id} type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children: content, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void }>) =>
    <select data-team value={value} onChange={(event) => onValueChange(event.target.value)}>{content}</select>,
  SelectContent: children,
  SelectItem: ({ children: content, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{content}</option>,
  SelectTrigger: children,
  SelectValue: children,
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children: content, value, onValueChange }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void }>) =>
    <section data-tabs={value} onChange={(event: React.ChangeEvent<HTMLElement>) => onValueChange((event.target as HTMLElement).dataset.value!)}>{content}</section>,
  TabsList: children,
  TabsTrigger: ({ children: content, value }: React.PropsWithChildren<{ value: string }>) => <i data-value={value}>{content}</i>,
  TabsContent: ({ children: content, value }: React.PropsWithChildren<{ value: string }>) => <div data-tab-content={value}>{content}</div>,
}))
mock.module('@/components/ui/badge', () => ({ Badge: children }))
mock.module('@/components/ui/card', () => ({ Card: children }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: children }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: ({ onChange }: { onChange: (value: string) => void }) => <button data-image onClick={() => onChange('https://images.test/icon.png')} /> }))
mock.module('./tool-category-input', () => ({
  ToolCategoryInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <select data-category value={value} onChange={(event) => onChange(event.target.value)}><option value="api">api</option><option value="data">data</option></select>,
}))

const { McpToolDialog } = await import('./mcp-tool-dialog')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []
let onSave = mock(async (data: unknown) => { void data })
let onOpenChange = mock((open: boolean) => { void open })

beforeEach(() => {
  onSave = mock(async (data: unknown) => { void data })
  onOpenChange = mock((open: boolean) => { void open })
  listMcpTools.mockReset()
  listMcpTools.mockImplementation(async () => ({ tools: [] }))
  toastInfo.mockClear()
  toastSuccess.mockClear()
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(props: Partial<React.ComponentProps<typeof McpToolDialog>> = {}) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<McpToolDialog open onSave={onSave} onOpenChange={onOpenChange} {...props} />) })
  renderers.push(renderer!)
  return renderer!
}

function input(renderer: ReactTestRenderer, id: string) {
  return renderer.root.findAllByProps({ id }).find((node) => node.type === 'input')!
}

function change(node: ReturnType<typeof input>, value: string) {
  act(() => node.props.onChange({ target: { value } }))
}

function values(renderer: ReactTestRenderer, placeholder: string) {
  return renderer.root.findAllByProps({ placeholder }).filter((node) => node.type === 'input')
}

function button(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').find((node) => node.children.includes(label))!
}

function errors(renderer: ReactTestRenderer) {
  return renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(''))
}

function transport(renderer: ReactTestRenderer, value: 'stdio' | 'sse' | 'http') {
  act(() => renderer.root.findAll((node) => node.type === 'section' && node.props['data-tabs'])[0].props.onChange({ target: { dataset: { value } } }))
}

async function click(node: ReturnType<typeof button>) {
  await act(async () => node.props.onClick())
}

function fillIdentity(renderer: ReactTestRenderer) {
  change(input(renderer, 'name'), 'weather_server')
  change(input(renderer, 'displayName'), 'Weather server')
}

describe('MCP tool dialog', () => {
  test('validates create fields, clears corrected errors, and guards disabled actions', async () => {
    const renderer = render()
    const fetch = button(renderer, 'mcpDialog.fetchTools')
    expect(fetch.props.disabled).toBe(true)
    expect(renderer.root.findAllByType('button').filter((node) => node.props.size === 'icon').every((node) => node.props.disabled)).toBe(true)

    await click(button(renderer, 'create'))
    expect(onSave).not.toHaveBeenCalled()
    expect(errors(renderer)).toEqual(expect.arrayContaining(['error.nameRequired', 'form.displayNameRequired', 'mcpDialog.commandRequired']))

    change(input(renderer, 'name'), '1 invalid')
    change(input(renderer, 'displayName'), 'Weather')
    change(input(renderer, 'command'), 'bunx')
    expect(input(renderer, 'name').props['aria-invalid']).toBe(false)
    await click(button(renderer, 'create'))
    expect(errors(renderer)).toContain('error.invalidName')

    transport(renderer, 'http')
    await click(button(renderer, 'create'))
    expect(errors(renderer)).toContain('mcpDialog.urlRequired')
  })

  test('loads tools and submits filtered stdio arguments, environment, team, and display settings', async () => {
    const selectedTeam = mock((id: string | null) => { void id })
    listMcpTools.mockImplementation(async () => ({ tools: [
      { name: 'forecast', description: 'Gets forecast', parameters: {} },
      { name: 'alerts', description: undefined, parameters: {} },
    ] }))
    const renderer = render({ teams: [{ id: 'team-1', name: 'Platform' }], selectedTeamId: 'team-1', onSelectedTeamChange: selectedTeam })
    fillIdentity(renderer)
    change(input(renderer, 'command'), 'bunx')
    change(values(renderer, 'mcpDialog.argumentPlaceholder')[0], '--yes')
    act(() => button(renderer, 'mcpDialog.addArg').props.onClick())
    change(values(renderer, 'mcpDialog.headerKeyPlaceholder')[0], 'TOKEN')
    change(values(renderer, 'mcpDialog.headerValuePlaceholder')[0], 'fake-secret')
    act(() => renderer.root.findByProps({ 'data-category': true }).props.onChange({ target: { value: 'data' } }))
    act(() => input(renderer, 'enabled').props.onChange({ target: { checked: false } }))
    act(() => renderer.root.findByProps({ 'data-image': true }).props.onClick())
    act(() => renderer.root.findByProps({ 'data-team': true }).props.onChange({ target: { value: 'team-1' } }))

    await click(button(renderer, 'mcpDialog.fetchTools'))
    expect(listMcpTools).toHaveBeenCalledWith({ transport: 'stdio', command: 'bunx', args: ['--yes'], env: { TOKEN: 'fake-secret' } })
    expect(toastSuccess).toHaveBeenCalledWith('mcpDialog.toolsLoaded')
    expect(renderer.root.findAll((node) => node.children.includes('forecast')).length).toBeGreaterThan(0)

    await click(button(renderer, 'create'))
    expect(selectedTeam).toHaveBeenCalledWith('team-1')
    expect(onSave).toHaveBeenCalledWith({
      name: 'weather_server', display_name: 'Weather server',
      description: '- forecast: Gets forecast\n- alerts: No description',
      icon: 'https://images.test/icon.png', category: 'data', is_enabled: false, type: 'mcp',
      mcp_config: { transport: 'stdio', command: 'bunx', args: ['--yes'], env: { TOKEN: 'fake-secret' } },
    })
  })

  test('prefills edit HTTP configuration, keeps identity immutable, and submits headers without exposing real secrets', async () => {
    const renderer = render({ tool: {
      id: 'tool-1', name: 'existing_server', display_name: 'Existing server', description: 'Old', icon: '', category: 'api', is_enabled: true,
      type: 'mcp', mcp_config: { transport: 'http', url: 'https://mcp.test/rpc', headers: { Authorization: 'Bearer fake-token' } },
    } as React.ComponentProps<typeof McpToolDialog>['tool'] })

    expect(input(renderer, 'name').props).toMatchObject({ value: 'existing_server', disabled: true })
    expect(input(renderer, 'http-url').props.value).toBe('https://mcp.test/rpc')
    expect(values(renderer, 'mcpDialog.headerNamePlaceholder').some((node) => node.props.value === 'Authorization')).toBe(true)
    expect(values(renderer, 'mcpDialog.headerValuePlaceholder').some((node) => node.props.value === 'Bearer fake-token' && node.props.type === 'password')).toBe(true)
    expect(button(renderer, 'mcpDialog.fetchTools').props.disabled).toBe(false)

    change(input(renderer, 'displayName'), 'Renamed server')
    await click(button(renderer, 'save'))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'existing_server', display_name: 'Renamed server',
      mcp_config: { transport: 'http', url: 'https://mcp.test/rpc', headers: { Authorization: 'Bearer fake-token' } },
    }))
  })

  test('maps server field failures, clears configuration errors, and retries tool loading after a generic failure', async () => {
    const failure = new Error('offline')
    listMcpTools.mockRejectedValueOnce({ 'mcp_config.command': 'Command rejected' })
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ tools: [] })
    const consoleError = mock(() => undefined)
    const originalConsoleError = console.error
    console.error = consoleError
    const renderer = render()
    change(input(renderer, 'command'), 'runner')

    await click(button(renderer, 'mcpDialog.fetchTools'))
    expect(errors(renderer)).toContain('Command rejected')
    change(input(renderer, 'command'), 'runner-fixed')
    expect(errors(renderer)).not.toContain('Command rejected')

    await click(button(renderer, 'mcpDialog.fetchTools'))
    expect(consoleError).toHaveBeenCalledWith('Failed to fetch MCP tools:', failure)
    await click(button(renderer, 'mcpDialog.fetchTools'))
    expect(listMcpTools).toHaveBeenCalledTimes(3)
    expect(toastInfo).toHaveBeenCalledWith('mcpDialog.noToolsFound')
    console.error = originalConsoleError
  })

  test('maps save field failures, propagates a generic failure, then permits retry and cancel', async () => {
    onSave.mockRejectedValueOnce({ display_name: 'Already used', 'mcp_config.env': 'Invalid environment' })
      .mockRejectedValueOnce(new Error('save unavailable'))
      .mockResolvedValueOnce(undefined)
    const renderer = render()
    fillIdentity(renderer)
    change(input(renderer, 'command'), 'runner')

    await click(button(renderer, 'create'))
    expect(errors(renderer)).toEqual(expect.arrayContaining(['Already used', 'Invalid environment']))
    change(input(renderer, 'displayName'), 'Unique server')
    change(values(renderer, 'mcpDialog.headerKeyPlaceholder')[0], 'KEY')
    expect(errors(renderer)).not.toEqual(expect.arrayContaining(['Already used', 'Invalid environment']))

    await expect(click(button(renderer, 'create'))).rejects.toThrow('save unavailable')
    await click(button(renderer, 'create'))
    expect(onSave).toHaveBeenCalledTimes(3)
    act(() => button(renderer, 'cancel').props.onClick())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
