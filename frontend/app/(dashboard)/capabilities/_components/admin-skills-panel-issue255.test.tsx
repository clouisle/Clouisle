import { afterEach, beforeAll, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const toastError = mock(() => {})
let query = ''
const setQuery = mock((value: string) => { query = value })
function SelectMock({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange?: (value: string) => void }>) {
  return <div data-select-value={value} data-on-value-change={onValueChange}>{children}</div>
}

mock.module('next-intl', () => ({ useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}` }))
mock.module('next/link', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
const icon = () => null
mock.module('lucide-react', () => ({
  AlertCircle: icon, CheckCircle2: icon, ChevronLeft: icon, ChevronRight: icon,
  ChevronsLeft: icon, ChevronsRight: icon, Eye: icon, FileArchive: icon,
  GitBranch: icon, Loader2: icon, PackageOpen: icon, Plus: icon, RefreshCw: icon,
  Search: icon, X: icon,
}))
mock.module('sonner', () => ({ toast: { error: toastError, success: mock() } }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [query, setQuery] }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>, buttonVariants: () => '' }))
mock.module('@/components/ui/card', () => ({ Card: element('section'), CardContent: element('div'), CardDescription: element('p'), CardTitle: element('h2') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ onCheckedChange, ...props }: Record<string, unknown>) => <input type="checkbox" onChange={(event) => (onCheckedChange as (checked: boolean) => void)(event.target.checked)} {...props} /> }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: ({ title, onSelectionChange }: { title: string; onSelectionChange: (values: Set<string>) => void }) => <button onClick={() => onSelectionChange(new Set(['selected']))}>{title}</button> }))
mock.module('@/components/ui/dialog', () => ({ Dialog: element('div'), DialogContent: element('div'), DialogDescription: element('p'), DialogFooter: element('footer'), DialogHeader: element('header'), DialogTitle: element('h2') }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/select', () => ({
  Select: SelectMock,
  SelectContent: element('div'), SelectItem: element('div'), SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/table', () => ({ Table: element('table'), TableBody: element('tbody'), TableCell: element('td'), TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr') }))
mock.module('@/components/ui/tabs', () => ({ Tabs: element('div'), TabsContent: element('div'), TabsList: element('div'), TabsTrigger: element('button') }))

function element<T extends keyof React.JSX.IntrinsicElements>(type: T) {
  function MockElement({ children, ...props }: React.ComponentProps<T>) {
    return React.createElement(type, props, children)
  }
  return MockElement
}

let AdminSkillsPanel: typeof import('./admin-skills-panel').AdminSkillsPanel
let adminSkillsApi: typeof import('@/lib/api/admin').adminSkillsApi
let teamsApi: typeof import('@/lib/api/admin').teamsApi

beforeAll(async () => {
  ;({ AdminSkillsPanel } = await import('./admin-skills-panel'))
  ;({ adminSkillsApi, teamsApi } = await import('@/lib/api/admin'))
})

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []
const skill = { id: 'skill-1', name: 'one', display_name: 'One', description: '', version: '1', source_type: 'git' as const, is_enabled: true, team_id: null, team_name: null, created_by_name: null, icon: '' }
const preview = {
  session_id: 'session', source_type: 'git' as const, warnings: [], invalid: [],
  skills: [
    { package_path: 'a', name: 'same', display_name: 'A', description: '', version: '1', valid: true, conflict: false, errors: [], warnings: [], file_count: 1 },
    { package_path: 'b', name: 'same', display_name: 'B', description: '', version: '1', valid: true, conflict: true, errors: [], warnings: ['skill_duplicate_name_in_source'], file_count: 1 },
  ],
}

function text(value: React.ReactNode): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement(value)) return text(value.props.children)
  return ''
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => text(item.props.children).includes(label))!

async function render() {
  let renderer!: ReactTestRenderer
  await act(async () => { renderer = create(<AdminSkillsPanel />); await Promise.resolve(); await Promise.resolve() })
  renderers.push(renderer)
  return renderer
}

function successfulLoad(total = 25) {
  spyOn(teamsApi, 'getTeams').mockResolvedValue({ items: [{ id: 'team-1', name: 'Team One' }] })
  spyOn(adminSkillsApi, 'list').mockResolvedValue({ items: [skill], total, page: 1, page_size: 10, pages: 3 })
  spyOn(adminSkillsApi, 'getFilterOptions').mockResolvedValue({ sources: [{ value: 'git', count: 1 }], teams: [{ value: 'team-1', label: 'Team One', count: 1 }, { value: 'team-2', label: 'Team Two', count: 1 }], creators: [{ value: 'ada', label: 'Ada', count: 1 }] })
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  query = ''
  setQuery.mockClear()
  toastError.mockClear()
  mock.restore()
})

test('reports load failures and cleans up a pending request on unmount', async () => {
  spyOn(teamsApi, 'getTeams').mockRejectedValue(new Error('teams failed'))
  spyOn(adminSkillsApi, 'list').mockRejectedValue(new Error('skills failed'))
  spyOn(adminSkillsApi, 'getFilterOptions').mockResolvedValue({ sources: [], teams: [], creators: [] })
  const renderer = await render()
  expect(toastError).toHaveBeenCalledWith('teams failed')
  expect(toastError).toHaveBeenCalledWith('skills failed')

  let resolve!: (value: { items: typeof skill[]; total: number; page: number; page_size: number; pages: number }) => void
  spyOn(adminSkillsApi, 'list').mockReturnValue(new Promise((done) => { resolve = done }))
  act(() => { void button(renderer, 'platform.skills.refresh').props.onClick() })
  act(() => renderer.unmount())
  renderers.splice(renderers.indexOf(renderer), 1)
  resolve({ items: [], total: 0, page: 1, page_size: 10, pages: 1 })
  await Promise.resolve()
})

test('exercises filters, page size, pagination, and team selection callbacks', async () => {
  successfulLoad()
  const renderer = await render()
  act(() => renderer.root.findByProps({ 'data-select-value': '10' }).props['data-on-value-change']('20'))
  await act(async () => { await Promise.resolve() })
  expect(adminSkillsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 20 }))

  const paging = renderer.root.findAllByType('button').filter((item) => item.props.className === 'h-8 w-8')
  act(() => paging[2].props.onClick())
  await act(async () => { await Promise.resolve() })
  expect(adminSkillsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
  act(() => renderer.root.findAllByType('button').filter((item) => item.props.className === 'h-8 w-8')[0].props.onClick())
  await act(async () => { await Promise.resolve() })
  expect(adminSkillsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))

  act(() => renderer.root.findByProps({ 'data-select-value': 'system' }).props['data-on-value-change']('team-1'))
  expect(JSON.stringify(renderer.toJSON())).toContain('Team One')
  const filterButtons = renderer.root.findAllByType('button').filter((item) => ['common.status', 'platform.skills.source', 'common.team', 'common.createdBy'].includes(text(item.props.children)))
  for (const item of filterButtons) act(() => item.props.onClick())
  await act(async () => { await Promise.resolve() })
  expect(adminSkillsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: ['selected'], source_type: ['selected'], team_id: ['selected'], creator: ['selected'] }))
})

test('handles zip boundaries and preview API failures', async () => {
  successfulLoad(0)
  spyOn(adminSkillsApi, 'previewZip').mockRejectedValue(new Error('zip preview failed'))
  spyOn(adminSkillsApi, 'previewGit').mockRejectedValue('unknown')
  const renderer = await render()
  act(() => button(renderer, 'platform.skills.import.open').props.onClick())
  const fileInput = renderer.root.findAllByType('input').find((item) => item.props.type === 'file')!

  act(() => fileInput.props.onChange({ target: { files: [] } }))
  act(() => fileInput.props.onChange({ target: { files: [{ name: 'huge.zip', size: 51 * 1024 * 1024 }] } }))
  expect(toastError).toHaveBeenCalledWith('platform.skills.import.zipTooLarge')
  act(() => fileInput.props.onChange({ target: { files: [{ name: 'ok.zip', size: 1 }] } }))
  await act(async () => renderer.root.findAllByType('button').filter((item) => text(item.props.children).includes('platform.skills.import.scan'))[0].props.onClick())
  expect(toastError).toHaveBeenCalledWith('zip preview failed')

  act(() => renderer.root.findByProps({ placeholder: 'https://github.com/org/repo.git' }).props.onChange({ target: { value: 'repo' } }))
  await act(async () => renderer.root.findAllByType('button').filter((item) => text(item.props.children).includes('platform.skills.import.scan')).at(-1)!.props.onClick())
  expect(toastError).toHaveBeenCalledWith('Unknown error')
})

test('switches duplicate selection/action and reports rejected installation', async () => {
  successfulLoad(0)
  spyOn(adminSkillsApi, 'previewGit').mockResolvedValue(preview)
  const install = spyOn(adminSkillsApi, 'install').mockRejectedValue(new Error('install failed'))
  const renderer = await render()
  act(() => button(renderer, 'platform.skills.import.open').props.onClick())
  act(() => renderer.root.findByProps({ placeholder: 'https://github.com/org/repo.git' }).props.onChange({ target: { value: 'repo' } }))
  await act(async () => renderer.root.findAllByType('button').filter((item) => text(item.props.children).includes('platform.skills.import.scan')).at(-1)!.props.onClick())

  const checks = renderer.root.findAllByType('input').filter((item) => item.props.type === 'checkbox')
  act(() => checks[1].props.onChange({ target: { checked: true } }))
  act(() => renderer.root.findByProps({ 'data-select-value': 'update' }).props['data-on-value-change']('update'))
  await act(async () => button(renderer, 'platform.skills.import.installSelected').props.onClick())

  expect(install).toHaveBeenCalledWith('session', { items: [{ package_path: 'b', action: 'update' }], is_enabled: true })
  expect(toastError).toHaveBeenCalledWith('install failed')
  act(() => button(renderer, 'platform.skills.cancel').props.onClick())
})
