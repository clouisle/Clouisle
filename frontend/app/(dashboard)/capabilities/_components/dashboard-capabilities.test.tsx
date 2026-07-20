import { afterEach, beforeAll, describe, expect, mock, spyOn, test } from 'bun:test'
import { Window } from 'happy-dom'
import React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLInputElement: window.HTMLInputElement,
  HTMLTextAreaElement: window.HTMLTextAreaElement,
  File: window.File,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const toastError = mock(() => {})
const toastSuccess = mock(() => {})
const toastInfo = mock(() => {})
const setSearchQuery = mock(() => {})
const routerPush = mock(() => {})

const adminToolsApiMock = {
  listPage: mock(async () => ({ items: [], total: 0, page: 1, pageSize: 10 })),
  getFilterOptions: mock(async () => ({ categories: [], creators: [], teams: [] })),
  create: mock(async (teamId: string, data: unknown) => ({ id: 'created', teamId, data })),
  update: mock(async () => ({})),
  getById: mock(async () => ({})),
  listMcpTools: mock(async () => ({ tools: [] })),
  listToolShares: mock(async () => ({ shares: [] })),
  shareTool: mock(async () => ({})),
  unshareTool: mock(async () => ({})),
  toggle: mock(async () => ({})),
  duplicate: mock(async () => ({})),
  delete: mock(async () => ({})),
  getConfig: mock(async () => ({})),
  createConfig: mock(async () => ({})),
  updateConfig: mock(async () => ({})),
}
const adminSkillsApiMock = {
  list: mock(async () => ({ items: [], total: 0, page: 1, pageSize: 10 })),
  getFilterOptions: mock(async () => ({ sources: [], creators: [], teams: [] })),
  previewZip: mock(async () => ({})),
  previewGit: mock(async () => ({})),
  install: mock(async () => ({ installed: [], updated: [], skipped: [], errors: [] })),
}
const teamsApiMock = {
  getTeams: mock(async () => ({ items: [], total: 0, page: 1, pageSize: 100 })),
}
const adminPackagesApiMock = { export: mock(async () => ({ blob: new Blob(), filename: 'tool.zip' })) }
const downloadBlob = mock(() => {})

mock.module('@/lib/api/admin', () => ({ adminToolsApi: adminToolsApiMock, adminSkillsApi: adminSkillsApiMock, teamsApi: teamsApiMock }))
mock.module('@/lib/api/packages', () => ({ adminPackagesApi: adminPackagesApiMock, downloadBlob }))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    `${namespace}.${key}${values ? JSON.stringify(values) : ''}`,
}))
mock.module('next/link', () => ({ default: ({ href, children, ...props }: React.ComponentProps<'a'>) => <a href={href} {...props}>{children}</a> }))
mock.module('next/image', () => ({ default: (props: React.ComponentProps<'img'>) => <img alt="" {...props} /> }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push: routerPush }) }))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess, info: toastInfo } }))
const Icon = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />
mock.module('lucide-react', () => ({
  Plus: Icon,
  Search: Icon,
  MoreHorizontal: Icon,
  Pencil: Icon,
  Trash2: Icon,
  ChevronLeft: Icon,
  ChevronRight: Icon,
  ChevronsLeft: Icon,
  ChevronsRight: Icon,
  ChevronDown: Icon,
  X: Icon,
  Copy: Icon,
  ToggleLeft: Icon,
  ToggleRight: Icon,
  Wrench: Icon,
  Code: Icon,
  Server: Icon,
  Globe: Icon,
  Plug: Icon,
  Share2: Icon,
  Zap: Icon,
  Clock3: Icon,
  Calculator: Icon,
  FolderOpen: Icon,
  Link: Icon,
  ChartColumn: Icon,
  Upload: Icon,
  Download: Icon,
  Play: Icon,
  AlertCircle: Icon,
  CheckCircle2: Icon,
  Eye: Icon,
  FileArchive: Icon,
  GitBranch: Icon,
  Loader2: Icon,
  PackageOpen: Icon,
  RefreshCw: Icon,
  Info: Icon,
  Terminal: Icon,
  Users: Icon
}))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => ['', setSearchQuery] }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/lib/constants', () => ({ SKILL_ZIP_MAX_UPLOAD_SIZE_BYTES: 1024 }))
mock.module('@/lib/api', () => {
  class ApiError extends Error {}
  return { ApiError, isPresetToolCategory: (category: string) => ['api', 'code', 'search'].includes(category) }
})

const passthrough = (tag: keyof React.JSX.IntrinsicElements = 'div') => {
  const Component = ({ children, ...props }: { children?: React.ReactNode } & Record<string, unknown>) =>
    React.createElement(tag, props, children)
  return Component
}

mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>, buttonVariants: () => '' }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: ({ onChange, ...props }: Omit<React.ComponentProps<'input'>, 'onChange'> & { onChange?: (value: number | '') => void }) => (
    <input {...props} onChange={(event) => onChange?.(event.currentTarget.value === '' ? '' : Number(event.currentTarget.value))} />
  ),
}))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: passthrough('label') }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough('span') }))
mock.module('@/components/ui/card', () => ({ Card: passthrough(), CardContent: passthrough(), CardDescription: passthrough(), CardTitle: passthrough() }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ message }: { message?: string }) => message ? <p>{message}</p> : null }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: (checked: boolean) => void }) => (
    <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange?.(event.currentTarget.checked)} />
  ),
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: (checked: boolean) => void }) => (
    <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange?.(event.currentTarget.checked)} />
  ),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open === false ? null : <div>{children}</div>,
  DialogContent: passthrough(), DialogDescription: passthrough('p'), DialogFooter: passthrough('footer'), DialogHeader: passthrough('header'), DialogTitle: passthrough('h2'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open === false ? null : <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
  AlertDialogContent: passthrough(), AlertDialogDescription: passthrough('p'), AlertDialogFooter: passthrough('footer'), AlertDialogHeader: passthrough('header'), AlertDialogTitle: passthrough('h2'),
}))

const SelectContext = React.createContext<(value: string) => void>(() => {})
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (value: string) => void }) => <SelectContext.Provider value={onValueChange || (() => {})}>{children}</SelectContext.Provider>,
  SelectContent: passthrough(),
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => {
    const onValueChange = React.useContext(SelectContext)
    return <button data-value={value} onClick={() => onValueChange(value)}>{children}</button>
  },
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: passthrough('span'),
}))
const TabsContext = React.createContext<(value: string) => void>(() => {})
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (value: string) => void }) => <TabsContext.Provider value={onValueChange || (() => {})}>{children}</TabsContext.Provider>,
  TabsContent: passthrough(), TabsList: passthrough(),
  TabsTrigger: ({ children, value }: { children: React.ReactNode; value: string }) => {
    const onValueChange = React.useContext(TabsContext)
    return <button data-value={value} onClick={() => onValueChange(value)}>{children}</button>
  },
}))
mock.module('@/components/ui/table', () => ({ Table: passthrough('table'), TableBody: passthrough('tbody'), TableCell: passthrough('td'), TableHead: passthrough('th'), TableHeader: passthrough('thead'), TableRow: passthrough('tr') }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: passthrough(), CollapsibleContent: passthrough(), CollapsibleTrigger: passthrough('button') }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: passthrough() }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: passthrough(), DropdownMenuContent: passthrough(), DropdownMenuItem: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>, DropdownMenuSeparator: passthrough(), DropdownMenuTrigger: passthrough('button') }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: passthrough(), TooltipContent: passthrough(),
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement; children?: React.ReactNode } & Record<string, unknown>) => render ? React.cloneElement(render, props) : <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: ({ title, onSelectionChange }: { title: string; onSelectionChange: (values: Set<string>) => void }) => <button onClick={() => onSelectionChange(new Set(['selected']))}>{title}</button> }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-category-input', () => ({ ToolCategoryInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <input value={value} onChange={(event) => onChange(event.currentTarget.value)} /> }))
mock.module('@/app/(platform)/app/capabilities/_components/http-tool-dialog', () => ({ HttpToolDialog: ({ open, onSave }: { open: boolean; onSave: (data: unknown) => Promise<void> }) => open ? <button onClick={() => onSave({ name: 'http' })}>mock-http-save</button> : null }))
mock.module('@/app/(platform)/app/capabilities/_components/mcp-tool-dialog', () => ({ McpToolDialog: ({ open, onSave }: { open: boolean; onSave: (data: unknown) => Promise<void> }) => open ? <button onClick={() => onSave({ name: 'mcp' })}>mock-mcp-save</button> : null }))
mock.module('./delete-tool-dialog', () => ({ DeleteToolDialog: ({ open }: { open: boolean }) => open ? <div>delete-dialog</div> : null }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-test-panel', () => ({ ToolTestPanel: ({ tool }: { tool: { name: string } | null }) => tool ? <div>test:{tool.name}</div> : null }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-config-dialog', () => ({ ToolConfigDialog: ({ open, onSave }: { open: boolean; onSave: (config: Record<string, string>) => Promise<void> }) => open ? <button onClick={() => onSave({ api_key: 'secret' })}>config-dialog</button> : null }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: ({ open }: { open: boolean }) => open ? <div>import-package</div> : null }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => { const next = { ...errors }; delete next[key]; return next },
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => !key.startsWith(prefix))),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: () => ({}), normalizeValidationErrors: (error: unknown) => { throw error }, formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const teamsPage = { items: [{ id: 'team-1', name: 'Core' }, { id: 'team-2', name: 'Docs' }], total: 2, page: 1, pageSize: 100 }
const tool = { id: 'tool-1', name: 'lookup', display_name: 'Lookup', description: 'Finds docs', category: 'api', type: 'builtin', is_enabled: true, team_id: 'team-1', team_name: 'Core', created_at: '2026-01-01', updated_at: '2026-01-01', icon: null }
const adminSkill = { id: 'skill-1', name: 'writer', display_name: 'Writer', description: 'Writes docs', category: 'code', version: '1.0.0', source_type: 'git', is_enabled: true, is_system: false, team_id: 'team-1', team_name: 'Core', created_at: '2026-01-01', updated_at: '2026-01-01' }

let HttpToolDialog: typeof import('./http-tool-dialog').HttpToolDialog
let McpToolDialog: typeof import('./mcp-tool-dialog').McpToolDialog
let ToolShareDialog: typeof import('./tool-share-dialog').ToolShareDialog
let ToolsClient: typeof import('./tools-client').ToolsClient
let AdminSkillsPanel: typeof import('./admin-skills-panel').AdminSkillsPanel

beforeAll(async () => {
  ;({ HttpToolDialog } = await import('./http-tool-dialog'))
  ;({ McpToolDialog } = await import('./mcp-tool-dialog'))
  ;({ ToolShareDialog } = await import('./tool-share-dialog'))
  ;({ ToolsClient } = await import('./tools-client'))
  ;({ AdminSkillsPanel } = await import('./admin-skills-panel'))
})

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
  mock.restore()
  toastError.mockClear(); toastSuccess.mockClear(); toastInfo.mockClear(); setSearchQuery.mockClear(); routerPush.mockClear(); downloadBlob.mockClear()
})

async function render(element: React.ReactElement) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  await act(async () => {
    root.render(element)
    await Promise.resolve(); await Promise.resolve()
  })
  return container
}
function click(button: HTMLButtonElement) { act(() => button.click()) }
function button(container: HTMLElement, label: string) {
  const found = [...container.querySelectorAll('button')].find((item) => item.textContent?.includes(label))
  if (!found) throw new Error(`Missing button ${label}: ${container.textContent}`)
  return found as HTMLButtonElement
}
function input(container: HTMLElement, placeholder: string) {
  const found = [...container.querySelectorAll('input')].find((item) => item.placeholder === placeholder)
  if (!found) throw new Error(`Missing input ${placeholder}: ${container.innerHTML}`)
  return found
}
function reactInputByPlaceholder(container: HTMLElement, placeholder: string) {
  const key = Object.keys(input(container, placeholder)).find((item) => item.startsWith('__reactProps$'))
  if (!key) throw new Error(`Missing React props for ${placeholder}`)
  return (input(container, placeholder) as unknown as Record<string, { onChange?: (event: { target: { value: string } }) => void }>)[key]
}
function reactEnter(container: HTMLElement, placeholder: string, value: string) {
  act(() => reactInputByPlaceholder(container, placeholder).onChange?.({ target: { value } }))
}

describe('dashboard capability dialogs', () => {
  test('HttpToolDialog resets create state and saves trimmed HTTP config', async () => {
    const onSave = mock(async () => {})
    const onOpenChange = mock(() => {})
    const container = await render(<HttpToolDialog open tool={null} onOpenChange={onOpenChange} onSave={onSave} />)

    reactEnter(container, 'tools.httpDialog.toolNamePlaceholder', ' lookup ')
    reactEnter(container, 'tools.displayNamePlaceholder', ' Lookup ')
    reactEnter(container, 'tools.httpDialog.urlPlaceholder', ' https://example.test ')
    await act(async () => button(container, 'common.create').click())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: ' lookup ', display_name: ' Lookup ', type: 'custom', custom_type: 'http',
      http_config: expect.objectContaining({ method: 'GET', url: ' https://example.test ', timeout: 30 }),
    }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('McpToolDialog fetches MCP tools for the current stdio command before saving', async () => {
    const listMcpTools = spyOn(adminToolsApiMock, 'listMcpTools').mockResolvedValue({ tools: [{ name: 'search', description: 'Search docs', input_schema: {} }] })
    const onSave = mock(async () => {})
    const container = await render(<McpToolDialog open tool={null} onOpenChange={mock(() => {})} onSave={onSave} />)

    reactEnter(container, 'tools.mcpDialog.serverNamePlaceholder', ' docs ')
    reactEnter(container, 'tools.displayNamePlaceholder', ' Docs MCP ')
    reactEnter(container, 'tools.mcpDialog.commandPlaceholder', ' npx ')
    await act(async () => button(container, 'tools.mcpDialog.fetchTools').click())

    expect(listMcpTools).toHaveBeenCalledWith(expect.objectContaining({ transport: 'stdio', command: ' npx ' }))
    expect(container.textContent).toContain('search')
    await act(async () => button(container, 'common.create').click())
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ name: ' docs ', display_name: ' Docs MCP ', mcp_config: expect.objectContaining({ command: ' npx ' }) }))
  })

  test('ToolShareDialog filters current and already shared teams, then shares the selected team', async () => {
    spyOn(adminToolsApiMock, 'listToolShares').mockResolvedValue({ shares: [{ id: 'share-1', tool_id: 'tool-1', shared_with_team_id: 'team-2', shared_with_team_name: 'Docs', permission: 'read_only' }] })
    const shareTool = spyOn(adminToolsApiMock, 'shareTool').mockResolvedValue({})
    const container = await render(<ToolShareDialog open tool={tool} availableTeams={[{ id: 'team-1', name: 'Core' }, { id: 'team-2', name: 'Docs' }, { id: 'team-3', name: 'Ops' }]} onOpenChange={mock(() => {})} />)

    expect(container.textContent).toContain('Ops')
    expect(container.textContent).not.toContain('Core')
    click(button(container, 'Ops'))
    await act(async () => button(container, 'tools.share.share').click())

    expect(shareTool).toHaveBeenCalledWith('tool-1', { team_id: 'team-3', permission: 'read_only' })
    expect(toastSuccess).toHaveBeenCalledWith('tools.share.shareSuccess')
  })
})

describe('dashboard capability clients', () => {
  test('ToolsClient loads teams, tools, and filter options for dashboard scope', async () => {
    const listPage = spyOn(adminToolsApiMock, 'listPage').mockResolvedValue({ items: [tool], total: 1, page: 1, pageSize: 10 })
    spyOn(adminToolsApiMock, 'getFilterOptions').mockResolvedValue({ categories: [{ value: 'api', label: 'API' }], creators: [], teams: [] })
    const getTeams = spyOn(teamsApiMock, 'getTeams').mockResolvedValue(teamsPage)
    const container = await render(<ToolsClient />)

    expect(getTeams).toHaveBeenCalledWith(1, 100)
    expect(listPage).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 10 }))
    expect(container.textContent).toContain('Lookup')
    expect(container.textContent).toContain('tools.pageInfo{"page":1,"total":1}')
  })

  test('ToolsClient opens create menu actions and saves an HTTP tool through the admin API', async () => {
    spyOn(teamsApiMock, 'getTeams').mockResolvedValue(teamsPage)
    spyOn(adminToolsApiMock, 'listPage').mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 10 })
    spyOn(adminToolsApiMock, 'getFilterOptions').mockResolvedValue({ categories: [], creators: [], teams: [] })
    const createTool = spyOn(adminToolsApiMock, 'create').mockResolvedValue(tool)
    const container = await render(<ToolsClient />)

    click(button(container, 'tools.createMenu.http'))
    await act(async () => button(container, 'mock-http-save').click())

    expect(createTool).toHaveBeenCalledWith('team-1', { name: 'http' })
    expect(toastSuccess).toHaveBeenCalledWith('tools.toolCreated')
  })

  test('ToolsClient applies and resets filters and changes page size', async () => {
    spyOn(teamsApiMock, 'getTeams').mockResolvedValue(teamsPage)
    const listPage = spyOn(adminToolsApiMock, 'listPage').mockResolvedValue({ items: [tool], total: 25, page: 1, pageSize: 10 })
    spyOn(adminToolsApiMock, 'getFilterOptions').mockResolvedValue({
      categories: [{ value: 'api', label: 'API' }], creators: [{ value: 'me', label: 'Me' }], teams: [{ value: 'team-1', label: 'Core' }, { value: 'team-2', label: 'Docs' }],
    })
    const container = await render(<ToolsClient />)

    click(button(container, 'tools.type'))
    await act(async () => await Promise.resolve())
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, type: ['selected'] }))
    click(button(container, 'common.reset'))
    expect(setSearchQuery).toHaveBeenCalledWith('')

    await act(async () => button(container, '20').click())
    expect(listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, pageSize: 20 }))
  })

  test('ToolsClient selects mutable tools and confirms bulk deletion', async () => {
    const customTool = { ...tool, id: 'custom-1', name: 'http_lookup', display_name: 'HTTP Lookup', type: 'custom' as const, custom_type: 'http' as const }
    spyOn(teamsApiMock, 'getTeams').mockResolvedValue(teamsPage)
    spyOn(adminToolsApiMock, 'listPage').mockResolvedValue({ items: [tool, customTool], total: 2, page: 1, pageSize: 10 })
    spyOn(adminToolsApiMock, 'getFilterOptions').mockResolvedValue({ categories: [], creators: [], teams: [] })
    const deleteTool = spyOn(adminToolsApiMock, 'delete').mockResolvedValue({})
    const container = await render(<ToolsClient />)

    const checkboxes = [...container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')]
    click(checkboxes[1] as unknown as HTMLButtonElement)
    expect(container.textContent).toContain('1 tools.toolsSelected')
    click([...container.querySelectorAll<HTMLButtonElement>('button.text-destructive')].at(-1)!)
    await act(async () => [...container.querySelectorAll('button')].filter((item) => item.textContent?.includes('common.delete')).at(-1)!.click())

    expect(deleteTool).toHaveBeenCalledWith('custom-1')
    expect(toastSuccess).toHaveBeenCalledWith('tools.bulkDeleted{"count":1}')
  })

  test('ToolsClient runs custom tool actions and builtin configuration callbacks', async () => {
    const customTool = { ...tool, id: 'custom-1', name: 'http_lookup', display_name: 'HTTP Lookup', type: 'custom' as const, custom_type: 'http' as const, is_enabled: false }
    const builtinTool = { ...tool, id: undefined, name: 'web_search', display_name: 'Web Search', requires_config: true }
    spyOn(teamsApiMock, 'getTeams').mockResolvedValue(teamsPage)
    spyOn(adminToolsApiMock, 'listPage').mockResolvedValue({ items: [customTool, builtinTool], total: 2, page: 1, pageSize: 10 })
    spyOn(adminToolsApiMock, 'getFilterOptions').mockResolvedValue({ categories: [], creators: [], teams: [] })
    const getById = spyOn(adminToolsApiMock, 'getById').mockResolvedValue(customTool)
    const duplicate = spyOn(adminToolsApiMock, 'duplicate').mockResolvedValue({})
    const toggle = spyOn(adminToolsApiMock, 'toggle').mockResolvedValue({})
    const exportTool = spyOn(adminPackagesApiMock, 'export').mockResolvedValue({ blob: new Blob(['tool']), filename: 'tool.zip' })
    const createConfig = spyOn(adminToolsApiMock, 'createConfig').mockResolvedValue({})
    spyOn(adminToolsApiMock, 'getConfig').mockRejectedValue({ response: { status: 404 } })
    const container = await render(<ToolsClient />)

    click(button(container, 'common.edit'))
    await act(async () => await Promise.resolve())
    expect(getById).toHaveBeenCalledWith('custom-1')
    expect(container.textContent).toContain('mock-http-save')
    click(button(container, 'tools.duplicate'))
    click(button(container, 'tools.enable'))
    await act(async () => button(container, 'packages.export').click())
    expect(duplicate).toHaveBeenCalledWith('custom-1')
    expect(toggle).toHaveBeenCalledWith('custom-1')
    expect(exportTool).toHaveBeenCalledWith('tool', 'custom-1')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'tool.zip')
    await act(async () => button(container, 'tools.share.title').click())
    expect(container.textContent).toContain('tools.share.description{"toolName":"HTTP Lookup"}')
    click(button(container, 'tools.runTest'))
    expect(container.textContent).toContain('test:http_lookup')

    const editButtons = [...container.querySelectorAll('button')].filter((item) => item.textContent?.includes('common.edit'))
    click(editButtons.at(-1) as HTMLButtonElement)
    await act(async () => button(container, 'config-dialog').click())
    expect(createConfig).toHaveBeenCalledWith('web_search', { api_key: 'secret' }, 'team-1')
    expect(toastSuccess).toHaveBeenCalledWith('tools.configSaved')
  })

  test('AdminSkillsPanel loads skills and installs selected git preview entries', async () => {
    const list = spyOn(adminSkillsApiMock, 'list').mockResolvedValue({ items: [adminSkill], total: 1, page: 1, pageSize: 10 })
    spyOn(adminSkillsApiMock, 'getFilterOptions').mockResolvedValue({ sources: [{ value: 'git', label: 'Git' }], creators: [], teams: [] })
    spyOn(teamsApiMock, 'getTeams').mockResolvedValue(teamsPage)
    const previewGit = spyOn(adminSkillsApiMock, 'previewGit').mockResolvedValue({
      session_id: 'preview-1', source_type: 'git', source_uri: null, source_ref: null, source_subdir: null,
      skills: [{ package_path: 'skills/writer', name: 'writer', display_name: 'Writer', description: 'Writes', version: '1.0.0', category: 'code', valid: true, errors: [], warnings: [], file_count: 2 }],
      invalid: [], warnings: [],
    })
    const install = spyOn(adminSkillsApiMock, 'install').mockResolvedValue({ installed: ['writer'], updated: [], skipped: [], errors: [] })
    const container = await render(<AdminSkillsPanel />)

    expect(list).toHaveBeenCalledWith(expect.objectContaining({ page: 1, pageSize: 10, include_system: true }))
    expect(container.textContent).toContain('Writer')
    click(button(container, 'platform.skills.import.open'))
    reactEnter(container, 'https://github.com/org/repo.git', ' https://github.com/acme/skills.git ')
    await act(async () => [...container.querySelectorAll('button')].filter((item) => item.textContent?.includes('platform.skills.import.scan')).at(-1)!.click())
    await act(async () => button(container, 'platform.skills.import.installSelected').click())

    expect(previewGit).toHaveBeenCalledWith({ team_id: null, repo_url: 'https://github.com/acme/skills.git', ref: null })
    expect(install).toHaveBeenCalledWith('preview-1', { items: [{ package_path: 'skills/writer', action: 'install' }], is_enabled: true })
    expect(toastSuccess).toHaveBeenCalledWith('platform.skills.import.installed')
  })
})
