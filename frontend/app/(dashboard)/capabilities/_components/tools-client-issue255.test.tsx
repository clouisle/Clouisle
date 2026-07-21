import { afterEach, beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLInputElement: window.HTMLInputElement,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const api = {
  listPage: mock(async () => page()),
  getFilterOptions: mock(async () => filters),
  getById: mock(async () => tools[1]),
  create: mock(async () => undefined),
  update: mock(async () => undefined),
  toggle: mock(async () => undefined),
  duplicate: mock(async () => undefined),
  delete: mock(async () => undefined),
  getConfig: mock(async () => ({})),
  updateConfig: mock(async () => undefined),
  createConfig: mock(async () => undefined),
}
const teamsApi = { getTeams: mock(async () => ({ items: teams })) }
const packagesApi = { export: mock(async () => ({ blob: new Blob(['x']), filename: 'tool.zip' })) }
const downloadBlob = mock()
const push = mock()
const success = mock()
const errorToast = mock()
const consoleError = mock()
let permissions = new Set(['admin:capability:create', 'admin:capability:read', 'admin:capability:update', 'admin:capability:delete', 'admin:capability:execute'])
let search = ''

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    `${namespace}.${key}${values ? `:${JSON.stringify(values)}` : ''}`,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { success, error: errorToast } }))
mock.module('@/hooks/use-url-search-state', () => ({
  useUrlSearchState: () => {
    const [, rerender] = React.useState(0)
    return [search, (value: string) => { search = value; rerender((n) => n + 1) }] as const
  },
}))
mock.module('@/lib/api', () => ({
  isPresetToolCategory: (value: string) => ['search', 'web'].includes(value),
}))
mock.module('@/lib/api/admin', () => ({ adminToolsApi: api, teamsApi }))
mock.module('@/lib/api/packages', () => ({ adminPackagesApi: packagesApi, downloadBlob }))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
  PermissionGuard: ({ permission, children }: { permission: string; children: React.ReactNode }) =>
    permissions.has(permission) ? <>{children}</> : null,
}))
function NextImage(props: React.ImgHTMLAttributes<HTMLImageElement>) { return <img alt={props.alt ?? ''} {...props} /> }
mock.module('next/image', () => ({ default: NextImage }))
const Icon = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />
mock.module('lucide-react', () => ({
  Plus: Icon, Search: Icon, MoreHorizontal: Icon, Pencil: Icon, Trash2: Icon, ChevronLeft: Icon, ChevronRight: Icon,
  ChevronsLeft: Icon, ChevronsRight: Icon, ChevronDown: Icon, X: Icon, Copy: Icon, ToggleLeft: Icon, ToggleRight: Icon,
  Wrench: Icon, Code: Icon, Server: Icon, Globe: Icon, Plug: Icon, Share2: Icon, Zap: Icon, Clock3: Icon,
  Calculator: Icon, FolderOpen: Icon, Link: Icon, ChartColumn: Icon, Upload: Icon, Download: Icon, Play: Icon,
}))

function element(Tag = 'div') {
  function MockElement({ children, render, ...props }: React.HTMLAttributes<HTMLElement> & { render?: React.ReactNode }) {
    return React.createElement(Tag, props, render ?? children)
  }
  return MockElement
}
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: ({ onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} onInput={onChange} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange }: { checked?: boolean; onCheckedChange?: () => void }) =>
    <input type="checkbox" checked={checked} onChange={onCheckedChange} />,
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (v: string) => void }) => <div>{children}<button onClick={() => onValueChange('20')}>select-20</button></div>,
  SelectContent: element(), SelectItem: element(), SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element(), DropdownMenuContent: element(), DropdownMenuItem: element('button'), DropdownMenuSeparator: element('hr'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, options, onSelectionChange }: { title: string; options: { value: string; label: string }[]; onSelectionChange: (v: Set<string>) => void }) =>
    <div data-filter={title}>{options.map((option) => <button key={option.value} onClick={() => onSelectionChange(new Set([option.value]))}>{title}:{option.value}</button>)}</div>,
}))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element(), TooltipContent: element(), TooltipTrigger: element('button') }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <div data-dialog="bulk">{children}</div> : null,
  AlertDialogAction: element('button'), AlertDialogCancel: element('button'), AlertDialogContent: element(), AlertDialogDescription: element(), AlertDialogFooter: element(), AlertDialogHeader: element(), AlertDialogTitle: element(),
}))

function dialogMock(name: string) {
  function MockDialog({ open, onSave, onSuccess, onImported, onOpenChange, onSelectedTeamChange, tool }: {
    open: boolean; onSave?: (data: Record<string, unknown>) => Promise<void>; onSuccess?: () => void; onImported?: () => void; onOpenChange: (v: boolean) => void; onSelectedTeamChange?: (v: string | null) => void; tool?: { id?: string } | null
  }) {
    return <div data-dialog={name} data-open={String(open)} data-tool={tool?.id ?? ''}>
      <button onClick={() => onOpenChange(false)}>{name}-close</button>
      {onSave && <button onClick={() => void onSave({ name: 'saved' }).catch(() => undefined)}>{name}-save</button>}
      {onSuccess && <button onClick={onSuccess}>{name}-success</button>}
      {onImported && <button onClick={onImported}>{name}-imported</button>}
      {onSelectedTeamChange && <button onClick={() => onSelectedTeamChange(null)}>{name}-clear-team</button>}
    </div>
  }
  return MockDialog
}
mock.module('@/app/(platform)/app/capabilities/_components/http-tool-dialog', () => ({ HttpToolDialog: dialogMock('http') }))
mock.module('@/app/(platform)/app/capabilities/_components/mcp-tool-dialog', () => ({ McpToolDialog: dialogMock('mcp') }))
mock.module('./delete-tool-dialog', () => ({ DeleteToolDialog: dialogMock('delete') }))
mock.module('./tool-share-dialog', () => ({ ToolShareDialog: dialogMock('share') }))
mock.module('@/components/packages/import-package-dialog', () => ({ ImportPackageDialog: dialogMock('import') }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-config-dialog', () => ({
  ToolConfigDialog: ({ open, onSave }: { open: boolean; onSave: (v: Record<string, string>) => Promise<void> }) => <div data-dialog="config" data-open={String(open)}><button onClick={() => void onSave({ token: 'secret' }).catch(() => undefined)}>config-save</button></div>,
}))
mock.module('@/app/(platform)/app/capabilities/_components/tool-test-panel', () => ({
  ToolTestPanel: ({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) => <div data-dialog="test" data-open={String(open)}><button onClick={() => onOpenChange(false)}>test-close</button></div>,
}))

type Tool = {
  id?: string; name: string; display_name: string; description: string; type: 'builtin' | 'custom' | 'mcp'; category: string; is_enabled: boolean; requires_config: boolean; custom_type?: 'http' | 'code'; team_id?: string; owner_team_name?: string; created_by_name?: string; icon?: string
}
const teams = [{ id: 'team-1', name: 'Alpha' }, { id: 'team-2', name: 'Beta' }]
const tools: Tool[] = [
  { name: 'clock', display_name: 'Clock', description: '', type: 'builtin', category: 'search', is_enabled: true, requires_config: true, team_id: 'team-1', icon: 'https://icon.test/x.png' },
  { id: 'http-1', name: 'http', display_name: 'HTTP', description: '', type: 'custom', custom_type: 'http', category: 'Other', is_enabled: true, requires_config: false, owner_team_name: 'Owner', created_by_name: 'Ada', icon: 'H' },
  { id: 'mcp-1', name: 'mcp', display_name: 'MCP', description: '', type: 'mcp', category: 'web', is_enabled: false, requires_config: false },
]
const filters = { categories: [{ value: 'search', label: 'Search' }, { value: 'Other', label: 'Other' }], creators: [{ value: 'ada', label: 'Ada' }], teams: [{ value: 'team-1', label: 'Alpha' }, { value: 'team-2', label: 'Beta' }] }
const page = () => ({ items: tools, total: 25, page: 1, page_size: 10 })

let ToolsClient: typeof import('./tools-client').ToolsClient
const roots: Root[] = []
beforeAll(async () => { ({ ToolsClient } = await import('./tools-client')) })
beforeEach(() => {
  search = ''
  permissions = new Set(['admin:capability:create', 'admin:capability:read', 'admin:capability:update', 'admin:capability:delete', 'admin:capability:execute'])
  for (const fn of [...Object.values(api), teamsApi.getTeams, packagesApi.export, downloadBlob, push, success, errorToast, consoleError]) fn.mockClear()
  api.listPage.mockImplementation(async () => page())
  api.getFilterOptions.mockImplementation(async () => filters)
  teamsApi.getTeams.mockImplementation(async () => ({ items: teams }))
  api.getById.mockImplementation(async () => tools[1])
  packagesApi.export.mockImplementation(async () => ({ blob: new Blob(['x']), filename: 'tool.zip' }))
  console.error = consoleError
})
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

async function render() {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  await act(async () => { root.render(<ToolsClient />); await tick() })
  return container
}
const tick = () => new Promise((resolve) => setTimeout(resolve, 0))
async function click(container: HTMLElement, text: string, occurrence = 0) {
  const matches = [...container.querySelectorAll('button')].filter((node) => node.textContent?.includes(text))
  await act(async () => { matches[occurrence]!.click(); await tick() })
}
function enter(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, value)
  input.dispatchEvent(new window.Event('input', { bubbles: true }))
}

describe('ToolsClient issue #255 coverage', () => {
  it('loads rows, translates categories, displays metadata, and sends every filter', async () => {
    const container = await render()
    expect(container.textContent).toContain('Clock')
    expect(container.textContent).toContain('tools.categories.search')
    expect(container.textContent).toContain('Other')
    expect(container.textContent).toContain('Owner')
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://icon.test/x.png')

    const input = container.querySelector('input[placeholder="tools.searchPlaceholder"]')!
    await act(async () => { enter(input, 'needle'); await tick() })
    for (const value of ['builtin', 'search', 'enabled', 'team-1', 'ada']) await click(container, `:${value}`)
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'needle', type: ['builtin'], category: ['search'], status: ['enabled'], team_id: ['team-1'], creator: ['ada'], page: 1 }))

    await click(container, 'common.reset')
    expect(search).toBe('')
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ search: undefined, type: undefined, category: undefined, status: undefined, team_id: undefined, creator: undefined }))
  })

  it('selects eligible tools, clears selection, and bulk deletes success and failure', async () => {
    const container = await render()
    const checks = container.querySelectorAll('input[type="checkbox"]')
    await act(async () => { (checks[0] as HTMLInputElement).click(); await tick() })
    expect(container.textContent).toContain('2 tools.toolsSelected')
    const bulkButton = [...container.querySelectorAll('button')].find((button) => button.className.includes('text-destructive'))!
    await act(async () => { bulkButton.click(); await tick() })
    await act(async () => { ([...container.querySelectorAll('[data-dialog="bulk"] button')].at(-1) as HTMLButtonElement).click(); await tick() })
    expect(api.delete).toHaveBeenCalledTimes(2)
    expect(success).toHaveBeenCalledWith('tools.bulkDeleted:{"count":2}')

    await act(async () => { (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click(); await tick() })
    api.delete.mockImplementationOnce(async () => { throw new Error('delete failed') })
    const failingBulkButton = [...container.querySelectorAll('button')].find((button) => button.className.includes('text-destructive'))!
    await act(async () => { failingBulkButton.click(); await tick() })
    await act(async () => { ([...container.querySelectorAll('[data-dialog="bulk"] button')].at(-1) as HTMLButtonElement).click(); await tick() })
    expect(container.querySelector('[data-dialog="bulk"]')).toBeNull()

    await act(async () => { (container.querySelectorAll('input[type="checkbox"]')[1] as HTMLInputElement).click(); await tick() })
    expect(container.textContent).not.toContain('tools.toolsSelected')
  })

  it('opens create dialogs, routes code creation, saves HTTP and MCP creations, and propagates save failures', async () => {
    const container = await render()
    await click(container, 'tools.createMenu.http')
    expect(container.querySelector('[data-dialog="http"]')?.getAttribute('data-open')).toBe('true')
    await click(container, 'http-save')
    expect(api.create).toHaveBeenCalledWith('team-1', { name: 'saved' })
    expect(success).toHaveBeenCalledWith('tools.toolCreated')

    await click(container, 'tools.createMenu.mcp')
    api.create.mockImplementationOnce(async () => { throw new Error('save failed') })
    await click(container, 'mcp-save')
    expect(consoleError).toHaveBeenCalledWith('Failed to save tool:', expect.any(Error))

    await click(container, 'tools.createMenu.code')
    expect(push).toHaveBeenCalledWith('/capabilities/code?teamId=team-1')
  })

  it('edits HTTP, MCP, code, inferred and unknown custom tools, including detail failure', async () => {
    const container = await render()
    api.getById.mockImplementationOnce(async () => tools[1])
    await click(container, 'common.edit', 1)
    expect(container.querySelector('[data-dialog="http"]')?.getAttribute('data-tool')).toBe('http-1')
    await click(container, 'http-save')
    expect(api.update).toHaveBeenCalledWith('http-1', { name: 'saved' })

    api.getById.mockImplementationOnce(async () => tools[2])
    await click(container, 'common.edit', 2)
    expect(container.querySelector('[data-dialog="mcp"]')?.getAttribute('data-tool')).toBe('mcp-1')

    api.getById.mockImplementationOnce(async () => ({ ...tools[1], custom_type: 'code' }))
    await click(container, 'common.edit', 1)
    expect(push).toHaveBeenCalledWith('/capabilities/code?id=http-1')

    api.getById.mockImplementationOnce(async () => ({ ...tools[1], custom_type: undefined, http_config: { url: 'x' } }))
    await click(container, 'common.edit', 1)
    api.getById.mockImplementationOnce(async () => ({ ...tools[1], custom_type: undefined, code_config: { code: 'x' } }))
    await click(container, 'common.edit', 1)
    api.getById.mockImplementationOnce(async () => ({ ...tools[1], custom_type: undefined }))
    await click(container, 'common.edit', 1)
    expect(errorToast).toHaveBeenCalledWith('tools.error.unknownToolType')
    api.getById.mockImplementationOnce(async () => { throw new Error('detail failed') })
    await click(container, 'common.edit', 1)
    expect(consoleError).toHaveBeenCalledWith('Failed to load tool detail:', expect.any(Error))
  })

  it('configures builtins with update/create paths and handles non-404 and save failures', async () => {
    const container = await render()
    await click(container, 'common.edit')
    await click(container, 'config-save')
    expect(api.updateConfig).toHaveBeenCalledWith('clock', { token: 'secret' }, 'team-1')

    await click(container, 'common.edit')
    api.getConfig.mockImplementationOnce(async () => { throw { response: { status: 404 } } })
    await click(container, 'config-save')
    expect(api.createConfig).toHaveBeenCalledWith('clock', { token: 'secret' }, 'team-1')

    await click(container, 'common.edit')
    api.getConfig.mockImplementationOnce(async () => { throw new Error('server') })
    await click(container, 'config-save')
    expect(consoleError).toHaveBeenCalledWith('Failed to save config:', expect.any(Error))
  })

  it('runs action callbacks, dialogs, toggles, duplicate, export and their API failure branches', async () => {
    const container = await render()
    await click(container, 'tools.runTest')
    expect(container.querySelector('[data-dialog="test"]')?.getAttribute('data-open')).toBe('true')
    await click(container, 'test-close')

    await click(container, 'tools.disable')
    expect(api.toggle).toHaveBeenCalledWith('http-1')
    expect(success).toHaveBeenCalledWith('tools.toolDisabled')
    api.toggle.mockImplementationOnce(async () => { throw new Error('toggle') })
    await click(container, 'tools.enable')

    await click(container, 'tools.duplicate')
    expect(api.duplicate).toHaveBeenCalledWith('http-1')
    api.duplicate.mockImplementationOnce(async () => { throw new Error('duplicate') })
    await click(container, 'tools.duplicate')

    await click(container, 'packages.export')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'tool.zip')
    packagesApi.export.mockImplementationOnce(async () => { throw new Error('export') })
    await click(container, 'packages.export')

    await click(container, 'tools.share.title')
    expect(container.querySelector('[data-dialog="share"]')?.getAttribute('data-open')).toBe('true')
    await click(container, 'share-success')
    await click(container, 'common.delete', 1)
    expect(container.querySelector('[data-dialog="delete"]')?.getAttribute('data-open')).toBe('true')
    await click(container, 'delete-success')
    await click(container, 'packages.import')
    expect(container.querySelector('[data-dialog="import"]')?.getAttribute('data-open')).toBe('true')
    await click(container, 'import-imported')
  })

  it('enforces permissions and survives initial API failures and empty results', async () => {
    permissions = new Set()
    api.listPage.mockImplementationOnce(async () => { throw new Error('list') })
    api.getFilterOptions.mockImplementationOnce(async () => { throw new Error('filters') })
    teamsApi.getTeams.mockImplementationOnce(async () => { throw new Error('teams') })
    const failed = await render()
    expect(failed.textContent).toContain('tools.noTools')
    expect(failed.textContent).not.toContain('tools.createTool')
    expect(failed.textContent).not.toContain('packages.import')
    expect(failed.textContent).not.toContain('tools.runTest')

    permissions = new Set(['admin:capability:execute'])
    const executeOnly = await render()
    expect(executeOnly.textContent).toContain('tools.runTest')
    expect(executeOnly.textContent).not.toContain('common.edit')
    expect(executeOnly.textContent).not.toContain('common.delete')
  })

  it('changes pagination and page size', async () => {
    const container = await render()
    await click(container, 'select-20')
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 20, page: 1 }))
    const pagination = [...container.querySelectorAll('button')].filter((button) => button.className.includes('h-8 w-8') && button.querySelector('svg'))
    await act(async () => { pagination.at(-2)!.click(); await tick() })
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    await act(async () => { pagination.at(-1)!.click(); await tick() })
    expect(api.listPage).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  })
})
