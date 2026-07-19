import { afterEach, beforeAll, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const toastError = mock(() => {})
const toastSuccess = mock(() => {})
const currentTeam = { id: 'team-1' }

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    `${namespace}.${key}${values ? JSON.stringify(values) : ''}`,
}))

mock.module('next/link', () => ({
  default: ({ href, children, ...props }: React.ComponentProps<'a'>) => <a href={href} {...props}>{children}</a>,
}))

mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/components/permission-guard', () => ({ PermissionGuard: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children, ...props }: React.ComponentProps<'div'>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: React.ComponentProps<'div'>) => <div {...props}>{children}</div>,
  CardDescription: ({ children, ...props }: React.ComponentProps<'div'>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: React.ComponentProps<'div'>) => <div {...props}>{children}</div>,
}))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: (props: React.ComponentProps<'input'>) => <input type="checkbox" {...props} /> }))
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
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children }: { children: React.ReactNode }) => <td>{children}</td>,
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

let SkillsPanel: typeof import('./skills-panel').SkillsPanel
let skillsApi: typeof import('@/lib/api').skillsApi

beforeAll(async () => {
  ;({ SkillsPanel } = await import('./skills-panel'))
  ;({ skillsApi } = await import('@/lib/api'))
})

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  toastError.mockClear()
  toastSuccess.mockClear()
})

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SkillsPanel />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

function text(value: React.ReactNode): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement(value)) return text(value.props.children)
  return ''
}

function button(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').find((item) => text(item.props.children).includes(label))!
}

const skill = {
  id: 'skill-1', name: 'summarize', display_name: 'Summarize', description: 'Makes summaries', category: 'code' as const,
  version: '1.2.0', source_type: 'git' as const, input_schema: {}, default_config: {}, is_enabled: false, is_system: false,
  import_warnings: [], created_at: '2026-01-01', updated_at: '2026-01-01', team_id: 'team-1',
}

describe('SkillsPanel', () => {
  test('shows the accessible empty boundary after loading skills for the current team', async () => {
    const list = spyOn(skillsApi, 'list').mockResolvedValue({ system: [], team: [] })

    const renderer = await render()

    expect(list).toHaveBeenCalledWith({ team_id: 'team-1', include_system: true })
    expect(JSON.stringify(renderer.toJSON())).toContain('platform.skills.noSkills')
    expect(JSON.stringify(renderer.toJSON())).toContain('platform.skills.noSkillsHint')
  })

  test('renders disabled skill metadata and opens import validation for an invalid archive', async () => {
    spyOn(skillsApi, 'list').mockResolvedValue({ system: [], team: [skill] })
    const renderer = await render()

    expect(JSON.stringify(renderer.toJSON())).toContain('Summarize')
    expect(JSON.stringify(renderer.toJSON())).toContain('platform.skills.disabled')
    expect(renderer.root.findByType('a').props.href).toBe('/app/capabilities/skills/skill-1')

    act(() => button(renderer, 'platform.skills.import.open').props.onClick())
    const fileInput = renderer.root.findAllByType('input').find((item) => item.props.type === 'file')!
    act(() => fileInput.props.onChange({ target: { files: [{ name: 'not-a-zip.txt', size: 1 }] } }))

    expect(toastError).toHaveBeenCalledWith('platform.skills.import.zipRequired')
  })

  test('previews a git source and installs its selected skill with the expected payload', async () => {
    spyOn(skillsApi, 'list').mockResolvedValue({ system: [], team: [] })
    const previewGit = spyOn(skillsApi, 'previewGit').mockResolvedValue({
      session_id: 'preview-1', source_type: 'git', skills: [{
        package_path: 'skills/reporter', name: 'reporter', display_name: 'Reporter', description: 'Creates reports', version: '1.0.0',
        category: 'data', valid: true, errors: [], warnings: [], file_count: 2,
      }], invalid: [], warnings: [],
    })
    const install = spyOn(skillsApi, 'install').mockResolvedValue({ installed: ['reporter'], updated: [], skipped: [], errors: [] })
    const renderer = await render()

    act(() => button(renderer, 'platform.skills.import.open').props.onClick())
    const gitUrl = renderer.root.findAllByType('input').find((item) => item.props.placeholder === 'https://github.com/org/repo.git')!
    const gitRef = renderer.root.findAllByType('input').find((item) => item.props.placeholder === 'main')!
    act(() => gitUrl.props.onChange({ target: { value: ' https://github.com/acme/skills.git ' } }))
    act(() => gitRef.props.onChange({ target: { value: ' release ' } }))
    await act(async () => renderer.root.findAllByType('button')
      .filter((item) => text(item.props.children).includes('platform.skills.import.scan')).at(-1)!.props.onClick())

    expect(previewGit).toHaveBeenCalledWith({ team_id: 'team-1', repo_url: 'https://github.com/acme/skills.git', ref: 'release' })
    expect(JSON.stringify(renderer.toJSON())).toContain('Reporter')

    await act(async () => button(renderer, 'platform.skills.import.installSelected').props.onClick())

    expect(install).toHaveBeenCalledWith('preview-1', { items: [{ package_path: 'skills/reporter', action: 'install' }], is_enabled: true })
    expect(toastSuccess).toHaveBeenCalledWith('platform.skills.import.installed')
  })
})
