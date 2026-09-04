import { afterEach, beforeAll, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const toastError = mock(() => {})
const toastSuccess = mock(() => {})
let query = ''
const setQuery = mock((value: string) => { query = value })

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    `${namespace}.${key}${values ? JSON.stringify(values) : ''}`,
}))
mock.module('next/link', () => ({
  default: ({ href, children, ...props }: React.ComponentProps<'a'>) => <a href={href} {...props}>{children}</a>,
}))
mock.module('lucide-react', () => ({
  AlertCircle: () => null,
  CheckCircle2: () => null,
  ChevronLeft: () => null,
  ChevronRight: () => null,
  ChevronsLeft: () => null,
  ChevronsRight: () => null,
  Eye: () => null,
  FileArchive: () => null,
  GitBranch: () => null,
  Loader2: () => null,
  PackageOpen: () => null,
  Plus: () => null,
  RefreshCw: () => null,
  Search: () => null,
  X: () => null,
}))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [query, setQuery] }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
  buttonVariants: () => 'button-link',
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <section>{children}</section>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ onCheckedChange, ...props }: Record<string, unknown>) => <input type="checkbox" onChange={(event) => (onCheckedChange as (checked: boolean) => void)(event.target.checked)} {...props} /> }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({
  DataTableFacetedFilter: ({ title, selectedValues, onSelectionChange }: { title: string; selectedValues: Set<string>; onSelectionChange: (values: Set<string>) => void }) => (
    <button data-selected={Array.from(selectedValues).join(',')} onClick={() => onSelectionChange(new Set(['enabled']))}>{title}</button>
  ),
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div role="dialog">{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, ...props }: React.ComponentProps<'td'>) => <td {...props}>{children}</td>,
  TableHead: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}))

let AdminSkillsPanel: typeof import('./admin-skills-panel').AdminSkillsPanel
let adminSkillsApi: typeof import('@/lib/api/admin').adminSkillsApi
let teamsApi: typeof import('@/lib/api/admin').teamsApi

beforeAll(async () => {
  ;({ AdminSkillsPanel } = await import('./admin-skills-panel'))
  ;({ adminSkillsApi, teamsApi } = await import('@/lib/api/admin'))
})

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

const skill = {
  id: 'skill-1', name: 'reporter', display_name: 'Reporter', description: 'Creates reports', version: '1.0.0',
  source_type: 'git' as const, is_enabled: false, team_id: null, team_name: null, created_by_name: null, icon: '',
}

const filters = {
  sources: [{ value: 'git', count: 1 }],
  teams: [{ value: 'team-1', label: 'Team One', count: 1 }],
  creators: [{ value: 'user-1', label: 'Ada', count: 1 }],
}

function text(value: React.ReactNode): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement(value)) return text(value.props.children)
  return ''
}

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<AdminSkillsPanel />)
    await Promise.resolve()
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => text(item.props.children).includes(label))!

function mockList(items = [skill]) {
  spyOn(teamsApi, 'getTeams').mockResolvedValue({ items: [{ id: 'team-1', name: 'Team One' }] })
  spyOn(adminSkillsApi, 'list').mockResolvedValue({ items, total: items.length, page: 1, page_size: 10, pages: 1 })
  spyOn(adminSkillsApi, 'getFilterOptions').mockResolvedValue(filters)
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  query = ''
  setQuery.mockClear()
  toastError.mockClear()
  toastSuccess.mockClear()
  mock.restore()
})

describe('AdminSkillsPanel', () => {
  test('loads skills and resets active filters', async () => {
    query = 'old'
    mockList()
    const renderer = await render()

    expect(JSON.stringify(renderer.toJSON())).toContain('Reporter')
    expect(adminSkillsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'old', include_system: true }))

    act(() => renderer.root.findByProps({ placeholder: 'platform.skills.searchPlaceholder' }).props.onChange({ target: { value: 'next' } }))
    expect(setQuery).toHaveBeenCalledWith('next')
    act(() => button(renderer, 'common.status').props.onClick())
    expect(adminSkillsApi.list).toHaveBeenLastCalledWith(expect.objectContaining({ status: ['enabled'] }))
    act(() => button(renderer, 'common.reset').props.onClick())
    expect(setQuery).toHaveBeenCalledWith('')
  })

  test('previews git packages and installs the selected non-conflicting skill', async () => {
    mockList([])
    const previewGit = spyOn(adminSkillsApi, 'previewGit').mockResolvedValue({
      session_id: 'session-1', source_type: 'git', warnings: [], invalid: [{ package_path: 'bad', name: '', display_name: '', description: '', errors: ['skill_package_invalid'], warnings: [] }],
      skills: [
        { package_path: 'skills/a', name: 'same', display_name: 'Alpha', description: 'A', version: '1', valid: true, conflict: false, errors: [], warnings: [], file_count: 1 },
        { package_path: 'skills/b', name: 'same', display_name: 'Beta', description: 'B', version: '1', valid: true, conflict: true, errors: [], warnings: ['skill_duplicate_name_in_source'], file_count: 1 },
      ],
    })
    const install = spyOn(adminSkillsApi, 'install').mockResolvedValue({ installed: ['same'], updated: [], skipped: [], errors: [] })
    const renderer = await render()

    act(() => button(renderer, 'platform.skills.import.open').props.onClick())
    act(() => renderer.root.findByProps({ placeholder: 'https://github.com/org/repo.git' }).props.onChange({ target: { value: ' https://github.com/acme/skills.git ' } }))
    act(() => renderer.root.findByProps({ placeholder: 'main' }).props.onChange({ target: { value: ' main ' } }))
    await act(async () => renderer.root.findAllByType('button').filter((item) => text(item.props.children).includes('platform.skills.import.scan')).at(-1)!.props.onClick())

    expect(previewGit).toHaveBeenCalledWith({ team_id: null, repo_url: 'https://github.com/acme/skills.git', ref: 'main' })
    expect(JSON.stringify(renderer.toJSON())).toContain('Alpha')
    expect(JSON.stringify(renderer.toJSON())).toContain('platform.skills.import.errors.invalidPackage')

    await act(async () => button(renderer, 'platform.skills.import.installSelected').props.onClick())

    expect(install).toHaveBeenCalledWith('session-1', { items: [{ package_path: 'skills/a', action: 'install' }], is_enabled: true })
    expect(toastSuccess).toHaveBeenCalledWith('platform.skills.import.installed')
  })

  test('rejects invalid zip uploads and reports install errors', async () => {
    mockList([])
    const install = spyOn(adminSkillsApi, 'install').mockResolvedValue({ installed: [], updated: [], skipped: [], errors: ['failed'] })
    spyOn(adminSkillsApi, 'previewZip').mockResolvedValue({
      session_id: 'zip-1', source_type: 'zip', warnings: [], invalid: [],
      skills: [{ package_path: 'skills/zip', name: 'zipper', display_name: 'Zipper', description: 'Zip', version: '1', valid: true, conflict: false, errors: [], warnings: [], file_count: 1 }],
    })
    const renderer = await render()

    act(() => button(renderer, 'platform.skills.import.open').props.onClick())
    const fileInput = renderer.root.findAllByType('input').find((item) => item.props.type === 'file')!
    act(() => fileInput.props.onChange({ target: { files: [{ name: 'skill.txt', size: 1 }] } }))
    expect(toastError).toHaveBeenCalledWith('platform.skills.import.zipRequired')

    act(() => fileInput.props.onChange({ target: { files: [{ name: 'skill.zip', size: 1 }] } }))
    await act(async () => renderer.root.findAllByType('button').filter((item) => text(item.props.children).includes('platform.skills.import.scan'))[0].props.onClick())
    await act(async () => button(renderer, 'platform.skills.import.installSelected').props.onClick())

    expect(install).toHaveBeenCalledWith('zip-1', { items: [{ package_path: 'skills/zip', action: 'install' }], is_enabled: true })
    expect(toastError).toHaveBeenCalledWith('failed')
  })
})
