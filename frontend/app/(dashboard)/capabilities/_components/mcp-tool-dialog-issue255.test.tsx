import { beforeEach, describe, expect, it, mock } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateValues: unknown[] = []
let stateIndex = 0
const updates: unknown[][] = []
const effects: Array<() => void> = []
const listMcpTools = mock(() => Promise.resolve({ tools: [] as Array<{ name: string; description?: string }> }))
const toastInfo = mock(() => {})
const toastSuccess = mock(() => {})
let mappedErrors: Record<string, string> = {}

function element() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    const setState = (value: T | ((previous: T) => T)) => {
      const previous = (stateValues[index] ?? initial) as T
      updates[index].push(typeof value === 'function' ? (value as (previous: T) => T)(previous) : value)
    }
    return [stateValues[index] ?? initial, setState] as const
  },
  useEffect: (effect: () => void) => effects.push(effect),
  useCallback: <T,>(callback: T) => callback,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  Loader2: element, Plus: element, Trash2: element, Info: element, Terminal: element,
  Globe: element, RefreshCw: element, CheckCircle2: element,
}))
mock.module('sonner', () => ({ toast: { info: toastInfo, success: toastSuccess } }))
mock.module('@/lib/api/admin', () => ({ adminToolsApi: { listMcpTools } }))
mock.module('@/lib/api/tools', () => ({}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => field !== key)),
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => !field.startsWith(prefix))),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: () => mappedErrors,
  normalizeValidationErrors: (error: unknown) => error,
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/components/ui/dialog', () => ({ Dialog: element, DialogContent: element, DialogDescription: element, DialogFooter: element, DialogHeader: element, DialogTitle: element }))
mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/input', () => ({ Input: element }))
mock.module('@/components/ui/label', () => ({ Label: element }))
mock.module('@/components/ui/switch', () => ({ Switch: element }))
mock.module('@/components/ui/tabs', () => ({ Tabs: element, TabsList: element, TabsTrigger: element, TabsContent: element }))
mock.module('@/components/ui/badge', () => ({ Badge: element }))
mock.module('@/components/ui/card', () => ({ Card: element }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: element }))
mock.module('@/components/ui/field', () => ({ FieldError: element }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element, TooltipContent: element, TooltipTrigger: element }))

const { McpToolDialog } = await import('./mcp-tool-dialog')
type Node = { type: unknown; props: Record<string, unknown> }

function render(values: unknown[] = [], props: Record<string, unknown> = {}) {
  stateValues = values
  stateIndex = 0
  updates.length = 15
  for (let index = 0; index < 15; index++) updates[index] = []
  effects.length = 0
  return McpToolDialog({ open: true, onOpenChange: mock(() => {}), onSave: mock(() => Promise.resolve()), ...props }) as Node
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return [((node as Node).props.children)].flat(Infinity).map(text).join('')
}

function all(node: unknown, predicate: (node: Node) => boolean): Node[] {
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as Node
  return [...(predicate(current) ? [current] : []), ...[current.props.children].flat(Infinity).flatMap((child) => all(child, predicate))]
}

const byText = (tree: Node, value: string) => all(tree, (node) => typeof node.props.onClick === 'function' && text(node).includes(value))[0]
const byId = (tree: Node, id: string) => all(tree, (node) => node.props.id === id)[0]

beforeEach(() => {
  listMcpTools.mockClear()
  toastInfo.mockClear()
  toastSuccess.mockClear()
  mappedErrors = {}
})

describe('McpToolDialog', () => {
  it('initializes create and editing forms, including both transport configurations', () => {
    render()
    effects.forEach((effect) => effect())
    expect(updates[0]).toContain('')
    expect(updates[5]).toContain('stdio')
    expect(updates[11]).toContainEqual([])
    expect(updates[13]).toContain(false)

    const stdioTool = {
      name: 'server', display_name: 'Server', icon: 'S', is_enabled: false,
      mcp_config: { transport: 'stdio', command: 'bunx', args: ['pkg'], env: { TOKEN: 123 } },
    }
    render([], { tool: stdioTool })
    effects[0]()
    expect(updates[6]).toContain('bunx')
    expect(updates[7]).toContainEqual(['pkg'])
    expect(updates[8]).toContainEqual([{ key: 'TOKEN', value: '123' }])
    expect(updates[9]).toContain('')
    expect(updates[13]).toContain(true)

    const httpTool = {
      name: 'remote', display_name: 'Remote', is_enabled: true,
      mcp_config: { transport: 'http', url: 'https://mcp.test', headers: { Authorization: 42 } },
    }
    render([], { tool: httpTool })
    effects[0]()
    expect(updates[5]).toContain('http')
    expect(updates[9]).toContain('https://mcp.test')
    expect(updates[10]).toContainEqual([{ key: 'Authorization', value: '42' }])
    expect(updates[6]).toContain('')
  })

  it('validates required fields before fetching or saving', async () => {
    const save = mock(() => Promise.resolve())
    const tree = render([], { onSave: save })

    await byText(tree, 'mcpDialog.fetchTools').props.onClick!()
    expect(updates[4]).toContainEqual({ command: 'mcpDialog.commandRequired' })
    expect(listMcpTools).not.toHaveBeenCalled()

    await byText(tree, 'create').props.onClick!()
    expect(updates[4]).toContainEqual({
      name: 'error.nameRequired', displayName: 'form.displayNameRequired', command: 'mcpDialog.commandRequired',
    })
    expect(save).not.toHaveBeenCalled()
  })

  it('builds stdio config, fetches tools, and saves their descriptions', async () => {
    const tools = [{ name: 'search', description: 'Find things' }, { name: 'plain' }]
    listMcpTools.mockResolvedValueOnce({ tools })
    const save = mock(() => Promise.resolve())
    const close = mock(() => {})
    const values = ['mcp_server', 'MCP Server', 'M', false, {}, 'stdio', 'bunx', ['pkg', ' '], [{ key: 'TOKEN', value: 'secret' }, { key: ' ', value: 'ignored' }], '', [{ key: '', value: '' }], tools, false, true, false]
    const tree = render(values, { onSave: save, onOpenChange: close })

    await byText(tree, 'mcpDialog.fetchTools').props.onClick!()
    expect(listMcpTools).toHaveBeenCalledWith({ transport: 'stdio', command: 'bunx', args: ['pkg'], env: { TOKEN: 'secret' } })
    expect(updates[11]).toContainEqual(tools)
    expect(updates[13]).toContain(true)
    expect(updates[12]).toEqual([true, false])
    expect(toastSuccess).toHaveBeenCalledWith('mcpDialog.toolsLoaded')

    await byText(tree, 'create').props.onClick!()
    expect(save).toHaveBeenCalledWith(expect.objectContaining({
      name: 'mcp_server', display_name: 'MCP Server', description: '- search: Find things\n- plain: No description',
      icon: 'M', is_enabled: false, type: 'mcp',
      mcp_config: { transport: 'stdio', command: 'bunx', args: ['pkg'], env: { TOKEN: 'secret' } },
    }))
    expect(close).toHaveBeenCalledWith(false)
    expect(updates[14]).toEqual([true, false])
  })

  it('builds remote config, handles empty results, and uses the fallback description', async () => {
    listMcpTools.mockResolvedValueOnce({ tools: [] })
    const save = mock(() => Promise.resolve())
    const values = ['remote', 'Remote MCP', '', true, {}, 'sse', '', [''], [{ key: '', value: '' }], 'https://mcp.test/sse', [{ key: 'Authorization', value: 'Bearer fake' }, { key: ' ', value: 'skip' }], [], false, false, false]
    const tree = render(values, { onSave: save })

    await byText(tree, 'mcpDialog.fetchTools').props.onClick!()
    expect(listMcpTools).toHaveBeenCalledWith({ transport: 'sse', url: 'https://mcp.test/sse', headers: { Authorization: 'Bearer fake' } })
    expect(toastInfo).toHaveBeenCalledWith('mcpDialog.noToolsFound')

    await byText(tree, 'create').props.onClick!()
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ description: 'MCP Server: Remote MCP' }))
  })

  it('maps fetch and save validation failures while rethrowing unknown save errors', async () => {
    const consoleError = mock(() => {})
    const originalError = console.error
    console.error = consoleError
    mappedErrors = { command: 'bad command' }
    listMcpTools.mockRejectedValueOnce(new Error('offline'))
    const fetchTree = render(['n', 'N', '', true, {}, 'stdio', 'bunx'])
    await byText(fetchTree, 'mcpDialog.fetchTools').props.onClick!()
    expect(updates[4]).toContainEqual({ command: 'bad command' })
    expect(updates[11]).toContainEqual([])
    expect(updates[13]).toContain(false)
    expect(consoleError).toHaveBeenCalled()
    console.error = originalError

    const saveError = new Error('invalid')
    const save = mock(() => Promise.reject(saveError))
    const saveTree = render(['n', 'N', '', true, {}, 'stdio', 'bunx'], { onSave: save })
    await byText(saveTree, 'create').props.onClick!()
    expect(updates[4]).toContainEqual({ command: 'bad command' })

    mappedErrors = {}
    const unknownTree = render(['n', 'N', '', true, {}, 'stdio', 'bunx'], { onSave: save })
    expect(byText(unknownTree, 'create').props.onClick!()).rejects.toBe(saveError)
  })

  it('updates transport fields and dynamic argument, environment, and header rows', () => {
    const values = ['name', 'Display', '', true, { name: 'bad', args: 'bad', 'args.0': 'bad', env: 'bad', 'env.0': 'bad', headers: 'bad', 'headers.0': 'bad' }, 'stdio', 'bunx', ['one', 'two'], [{ key: 'A', value: '1' }, { key: 'B', value: '2' }], '', [{ key: 'H1', value: 'v1' }, { key: 'H2', value: 'v2' }], [], false, false, false]
    const tree = render(values)

    byId(tree, 'name').props.onChange!({ target: { value: 'next' } })
    expect(updates[0]).toContain('next')
    expect(updates[4]).toContainEqual(expect.not.objectContaining({ name: expect.anything() }))

    const argumentInputs = all(tree, (node) => String(node.props.placeholder).startsWith('mcpDialog.argumentPlaceholder'))
    argumentInputs[0].props.onChange!({ target: { value: 'changed' } })
    expect(updates[7]).toContainEqual(['changed', 'two'])
    expect(updates[4]).toContainEqual(expect.not.objectContaining({ args: expect.anything(), 'args.0': expect.anything() }))
    byText(tree, 'mcpDialog.addArg').props.onClick!()
    expect(updates[7]).toContainEqual(['one', 'two', ''])

    const envInputs = all(tree, (node) => node.props.placeholder === 'mcpDialog.headerKeyPlaceholder')
    envInputs[0].props.onChange!({ target: { value: 'TOKEN' } })
    expect(updates[8]).toContainEqual([{ key: 'TOKEN', value: '1' }, { key: 'B', value: '2' }])
    byText(tree, 'mcpDialog.addEnvVar').props.onClick!()
    expect(updates[8]).toContainEqual([...values[8] as object[], { key: '', value: '' }])

    const headerInputs = all(tree, (node) => node.props.placeholder === 'mcpDialog.headerNamePlaceholder')
    headerInputs[0].props.onChange!({ target: { value: 'X-Test' } })
    expect(updates[10]).toContainEqual([{ key: 'X-Test', value: 'v1' }, { key: 'H2', value: 'v2' }])
    byText(tree, 'mcpDialog.addHeader').props.onClick!()
    expect(updates[10]).toContainEqual([...values[10] as object[], { key: '', value: '' }])

    const trashButtons = all(tree, (node) => node.props.size === 'icon' && typeof node.props.onClick === 'function')
    trashButtons[0].props.onClick!()
    trashButtons[2].props.onClick!()
    trashButtons[4].props.onClick!()
    expect(updates[7]).toContainEqual(['two'])
    expect(updates[8]).toContainEqual([{ key: 'B', value: '2' }])
    expect(updates[10]).toContainEqual([{ key: 'H2', value: 'v2' }])
  })

  it('validates remote URLs and forwards cancel', async () => {
    const close = mock(() => {})
    const tree = render(['name', 'Display', '', true, {}, 'http'], { onOpenChange: close })
    await byText(tree, 'mcpDialog.fetchTools').props.onClick!()
    expect(updates[4]).toContainEqual({ url: 'mcpDialog.urlRequired' })
    await byText(tree, 'create').props.onClick!()
    expect(updates[4]).toContainEqual({ url: 'mcpDialog.urlRequired' })
    byText(tree, 'cancel').props.onClick!()
    expect(close).toHaveBeenCalledWith(false)
  })
})
