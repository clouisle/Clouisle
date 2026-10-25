import { beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

type PageArgs = { page?: number; pageSize?: number; search?: string; keyword?: string; teamId?: string }
const getAgents = mock((...args: [PageArgs?]) => { void args; return Promise.resolve({ items: [] as AppRecord[], total: 0, page: 1, page_size: 20 }) })
const getWorkflows = mock((...args: [PageArgs?]) => { void args; return Promise.resolve({ items: [] as AppRecord[], total: 0, page: 1, page_size: 20 }) })
const deleteAgent = mock(() => Promise.resolve({}))
const deleteWorkflow = mock(() => Promise.resolve({}))
const duplicateAgent = mock(() => Promise.resolve({}))
const duplicateWorkflow = mock(() => Promise.resolve({}))
const publishAgent = mock(() => Promise.resolve({}))
const unpublishAgent = mock(() => Promise.resolve({}))
const publishWorkflow = mock(() => Promise.resolve({}))
const unpublishWorkflow = mock(() => Promise.resolve({}))
const exportPackage = mock(() => Promise.resolve({ blob: new Blob(['package']), filename: 'app.zip' }))
const downloadBlob = mock(() => undefined)
const replace = mock(() => undefined)
const push = mock(() => undefined)
const requireTeam = mock(() => undefined)
const canPerform = mock(() => false)
const success = mock(() => undefined)

let currentTeam: { id: string; role: string } | null = { id: 'team-1', role: 'member' }
let user: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
let search = ''
let intersectionCallback: ((entries: IntersectionObserverEntry[]) => void) | null = null

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: { name?: string }) => values?.name ? `${key} ${values.name}` : key,
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  useSearchParams: () => new URLSearchParams(search),
}))
mock.module('next/link', () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a>,
}))
mock.module('next/image', () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-require-team', () => ({ useRequireTeam: requireTeam }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user }) }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: <T,>(value: T) => value }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform }) }))
mock.module('@/lib/api/agents', () => ({
  agentsApi: { getAgents, deleteAgent, duplicateAgent, publishAgent, unpublishAgent },
}))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: { getWorkflows, deleteWorkflow, duplicateWorkflow, publishWorkflow, unpublishWorkflow },
}))
mock.module('@/lib/api/packages', () => ({ packagesApi: { export: exportPackage }, downloadBlob }))
mock.module('lucide-react', () => ({
  AppWindow: () => null,
  Plus: () => null,
  Sparkles: () => null,
  GitBranch: () => null,
  MoreHorizontal: () => null,
  Trash2: () => null,
  Copy: () => null,
  Send: () => null,
  FileEdit: () => null,
  MessageSquare: () => null,
  Loader2: () => null,
  Upload: () => null,
  Download: () => null,
}))

const Box = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/card', () => ({ Card: Box, CardContent: Box, CardDescription: Box, CardTitle: Box }))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: Box,
  DropdownMenuContent: Box,
  DropdownMenuItem: ({ children, ...props }: React.HTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ render }: { render: (props: Record<string, unknown>) => React.ReactNode }) => render({}),
}))
mock.module('@/components/ui/badge', () => ({ Badge: Box }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, onValueChange }: React.PropsWithChildren<{ onValueChange: (value: string) => void }>) => <div data-testid="tabs" data-change={onValueChange}>{children}</div>,
  TabsList: Box,
  TabsTrigger: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <button value={value}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: Box,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogContent: Box,
  AlertDialogDescription: Box,
  AlertDialogFooter: Box,
  AlertDialogHeader: Box,
  AlertDialogTitle: Box,
}))
mock.module('./_components/app-create-dialog', () => ({
  AppCreateDialog: (props: { open: boolean; initialType: string; onOpenChange: (open: boolean) => void; onSuccess: () => void }) => (
    <section data-testid="create-dialog" data-open={props.open} data-type={props.initialType}>
      <button onClick={() => props.onOpenChange(true)}>open-create</button>
      <button onClick={props.onSuccess}>create-success</button>
    </section>
  ),
}))
mock.module('@/components/packages/import-package-dialog', () => ({
  ImportPackageDialog: (props: { open: boolean; teamId: string; expectedResourceType?: string; onOpenChange: (open: boolean) => void; onImported: () => void }) => (
    <section data-testid="import-dialog" data-open={props.open} data-team={props.teamId} data-type={props.expectedResourceType ?? 'all'}>
      <button onClick={() => props.onOpenChange(true)}>open-import</button>
      <button onClick={props.onImported}>import-success</button>
    </section>
  ),
}))

const { default: AppsPage } = await import('./page')

type AppRecord = Record<string, unknown>
const agent = (overrides: AppRecord = {}): AppRecord => ({
  id: 'agent-1', name: 'Sales Agent', description: 'Helps sales', icon: null, status: 'draft',
  conversation_count: 2, message_count: 5, created_at: '2026-01-01', updated_at: '2026-01-03',
  created_by: { id: 'user-1', username: 'alice' }, ...overrides,
})
const workflow = (overrides: AppRecord = {}): AppRecord => ({
  id: 'workflow-1', name: 'Billing Flow', description: null, icon: '⚙️', status: 'published',
  run_count: 8, success_count: 7, fail_count: 1, created_at: '2026-01-01', updated_at: '2026-01-02',
  created_by_id: 'user-2', created_by_name: 'bob', ...overrides,
})

async function renderPage(wait = true) {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<AppsPage />)
    if (wait) await flushPromises()
  })
  return renderer
}
async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}
async function click(node: { props: { onClick?: (event: { preventDefault: () => void }) => unknown } }) {
  await act(async () => {
    await node.props.onClick?.({ preventDefault: () => undefined })
    await flushPromises()
  })
}
async function intersect() {
  await act(async () => {
    intersectionCallback?.([{ isIntersecting: true } as IntersectionObserverEntry])
    await flushPromises()
  })
  await flushPromises()
}
async function leaveViewport() {
  await act(async () => {
    intersectionCallback?.([{ isIntersecting: false } as IntersectionObserverEntry])
    await flushPromises()
  })
}
const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())
const buttons = (renderer: ReactTestRenderer) => renderer.root.findAllByType('button')
const nodeText = (node: { children?: unknown[] }): string => (node.children ?? []).map((child) => typeof child === 'string' ? child : nodeText(child as { children?: unknown[] })).join('')
const button = (renderer: ReactTestRenderer, label: string) => buttons(renderer).find((item) => nodeText(item).includes(label))!

beforeEach(() => {
  currentTeam = { id: 'team-1', role: 'member' }
  user = { id: 'user-1' }
  search = ''
  intersectionCallback = null
  Object.defineProperty(globalThis, 'IntersectionObserver', {
    configurable: true,
    value: class {
      constructor(callback: (entries: IntersectionObserverEntry[]) => void) {
        intersectionCallback = callback
      }
      observe = () => undefined
      unobserve = () => undefined
      disconnect = () => undefined
    },
  })
  Object.defineProperty(globalThis, 'window', { value: { location: { pathname: '/app/apps' } }, configurable: true })
  for (const fn of [getAgents, getWorkflows, deleteAgent, deleteWorkflow, duplicateAgent, duplicateWorkflow, publishAgent, unpublishAgent, publishWorkflow, unpublishWorkflow, exportPackage, downloadBlob, replace, push, requireTeam, canPerform, success]) fn.mockReset()
  getAgents.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  getWorkflows.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  deleteAgent.mockResolvedValue({})
  deleteWorkflow.mockResolvedValue({})
  duplicateAgent.mockResolvedValue({})
  duplicateWorkflow.mockResolvedValue({})
  publishAgent.mockResolvedValue({})
  unpublishAgent.mockResolvedValue({})
  publishWorkflow.mockResolvedValue({})
  unpublishWorkflow.mockResolvedValue({})
  exportPackage.mockResolvedValue({ blob: new Blob(['package']), filename: 'app.zip' })
  canPerform.mockReturnValue(false)
})

describe('platform apps page', () => {
  test('gates loading on team and loads both APIs with search and team pagination inputs', async () => {
    currentTeam = null
    let renderer = await renderPage()
    expect(requireTeam).toHaveBeenCalled()
    expect(getAgents).not.toHaveBeenCalled()
    expect(text(renderer)).toContain('py-12')
    act(() => renderer.unmount())

    currentTeam = { id: 'team-7', role: 'member' }
    getAgents.mockResolvedValue({ items: [agent()], total: 1, page: 1, page_size: 20 })
    getWorkflows.mockResolvedValue({ items: [workflow()], total: 1, page: 1, page_size: 20 })
    renderer = await renderPage()
    expect(getAgents).toHaveBeenCalledWith({ page: 1, pageSize: 20, search: undefined, teamId: 'team-7' })
    expect(getWorkflows).toHaveBeenCalledWith({ page: 1, pageSize: 20, keyword: undefined, teamId: 'team-7' })
    expect(text(renderer).indexOf('Sales Agent')).toBeLessThan(text(renderer).indexOf('Billing Flow'))

    await act(async () => renderer.root.findByType('input').props.onChange({ target: { value: 'billing' } }))
    await flushPromises()
    expect(getAgents).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: 'billing', teamId: 'team-7' })
    expect(getWorkflows).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, keyword: 'billing', teamId: 'team-7' })
    act(() => renderer.unmount())
  })

  test('shows a manual retry when the initial load fails and recovers on demand', async () => {
    getAgents.mockRejectedValueOnce(new Error('offline'))
    const renderer = await renderPage()
    expect(text(renderer)).toContain('loadFailed')
    expect(text(renderer)).not.toContain('noApps')

    await click(renderer.root.findByProps({ 'data-testid': 'apps-retry' }))
    expect(getAgents).toHaveBeenCalledTimes(2)
    expect(text(renderer)).toContain('noApps')
    act(() => renderer.unmount())
  })

  test('initializes query create/type/tab, clears action params, and changes tabs', async () => {
    canPerform.mockImplementation((permission: string) => permission === 'workflow:create')
    search = 'action=create&type=workflow&tab=agent&keep=yes'
    const renderer = await renderPage()
    expect(renderer.root.findByProps({ 'data-testid': 'create-dialog' }).props).toMatchObject({ 'data-open': true, 'data-type': 'workflow' })
    expect(replace).toHaveBeenCalledWith('/app/apps?tab=agent&keep=yes', { scroll: false })

    await act(async () => {
      renderer.root.findByProps({ 'data-testid': 'tabs' }).props['data-change']('workflow')
      await flushPromises()
    })
    expect(push).toHaveBeenCalledWith('?tab=workflow', { scroll: false })
    act(() => renderer.update(<AppsPage />))
    expect(push).toHaveBeenCalledWith('?tab=workflow', { scroll: false })
    act(() => renderer.unmount())
  })

  test('filters tabs and renders all card variants, links, icons, stats, and empty filters', async () => {
    currentTeam = { id: 'team-1', role: 'admin' }
    getAgents.mockResolvedValue({ items: [agent({ icon: '/agent.png' }), agent({ id: 'agent-2', name: 'Emoji Agent', icon: '✨', description: null, created_by: null })], total: 2, page: 1, page_size: 20 })
    getWorkflows.mockResolvedValue({ items: [workflow()], total: 1, page: 1, page_size: 20 })
    const renderer = await renderPage()
    expect(text(renderer)).toContain('Sales Agent')
    expect(text(renderer)).toContain('Emoji Agent')
    expect(text(renderer)).toContain('Billing Flow')
    expect(renderer.root.findAll((node) => node.type === 'div' && node.props['data-testid'] === 'app-card-first')).toHaveLength(1)
    expect(renderer.root.findAll((node) => node.type === 'button' && node.props['data-testid'] === 'app-actions-button-first')).toHaveLength(1)
    expect(renderer.root.findAll((node) => node.type === 'button' && node.props['data-testid'] === 'app-chat-button-first')).toHaveLength(1)
    expect(text(renderer)).toContain('conversations')
    expect(text(renderer)).toContain('messages')
    expect(text(renderer)).toContain('runs')
    expect(text(renderer)).toContain('failed')
    expect(renderer.root.findByProps({ alt: 'Sales Agent' })).toBeTruthy()
    expect(renderer.root.findAllByProps({ href: '/app/apps/agent-1' }).length).toBeGreaterThan(0)
    expect(renderer.root.findAllByProps({ href: '/app/apps/workflow/workflow-1' }).length).toBeGreaterThan(0)
    expect(renderer.root.findByProps({ href: '/chat/agent-1' })).toBeTruthy()
    expect(renderer.root.findByProps({ href: '/run/workflow-1?type=workflow' })).toBeTruthy()

    await act(async () => {
      renderer.root.findByProps({ 'data-testid': 'tabs' }).props['data-change']('agent')
      await flushPromises()
    })
    expect(text(renderer)).not.toContain('Billing Flow')
    await act(async () => {
      renderer.root.findByProps({ 'data-testid': 'tabs' }).props['data-change']('workflow')
      await flushPromises()
    })
    expect(text(renderer)).not.toContain('Sales Agent')
    await act(async () => renderer.root.findByProps({ 'data-testid': 'tabs' }).props['data-change']('all'))
    expect(text(renderer)).toContain('Sales Agent')
    act(() => renderer.unmount())
  })

  test('opens create/import controls and refreshes from their callbacks', async () => {
    canPerform.mockImplementation((permission: string) => permission === 'agent:create')
    const renderer = await renderPage()
    expect(renderer.root.findByProps({ 'data-testid': 'import-dialog' }).props).toMatchObject({ 'data-open': false, 'data-team': 'team-1', 'data-type': 'all' })

    await click(renderer.root.findByProps({ 'data-testid': 'apps-create-button' }))
    expect(renderer.root.findByProps({ 'data-testid': 'create-dialog' }).props['data-open']).toBe(true)
    await click(button(renderer, 'create-success'))
    expect(getAgents.mock.calls.length).toBeGreaterThan(1)

    await click(button(renderer, 'import'))
    expect(renderer.root.findByProps({ 'data-testid': 'import-dialog' }).props['data-open']).toBe(true)
    await click(button(renderer, 'import-success'))
    expect(getWorkflows.mock.calls.length).toBeGreaterThan(2)
    act(() => renderer.unmount())
  })

  test('enforces member ownership and per-type create permissions', async () => {
    canPerform.mockImplementation((permission: string) => permission === 'agent:create')
    getAgents.mockResolvedValue({ items: [agent(), agent({ id: 'agent-2', name: 'Other Agent', created_by: { id: 'other', username: 'other' } })] })
    getWorkflows.mockResolvedValue({ items: [workflow()] })
    const renderer = await renderPage()
    const rendered = text(renderer)
    expect(rendered).toContain('configure')
    expect(rendered).toContain('export')
    expect(rendered).toContain('duplicate')
    expect(buttons(renderer).filter((item) => nodeText(item) === 'publish')).toHaveLength(0)
    expect(buttons(renderer).filter((item) => nodeText(item) === 'unpublish')).toHaveLength(0)
    expect(buttons(renderer).filter((item) => nodeText(item) === 'delete')).toHaveLength(1)
    expect(buttons(renderer).filter((item) => nodeText(item).includes('duplicate'))).toHaveLength(2)
    expect(buttons(renderer).filter((item) => nodeText(item).includes('export'))).toHaveLength(1)
    act(() => renderer.unmount())
  })

  test('runs agent action callbacks and refreshes only successful mutations', async () => {
    currentTeam = { id: 'team-1', role: 'admin' }
    getAgents.mockResolvedValue({ items: [agent()] })
    const renderer = await renderPage()

    await click(button(renderer, 'publish'))
    expect(publishAgent).toHaveBeenCalledWith('agent-1')
    expect(success).toHaveBeenCalledWith('appPublished')
    await click(button(renderer, 'duplicate'))
    expect(duplicateAgent).toHaveBeenCalledWith('agent-1')
    await click(button(renderer, 'export'))
    expect(exportPackage).toHaveBeenCalledWith('agent', 'agent-1')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'app.zip')
    await click(button(renderer, 'delete'))
    expect(text(renderer)).toContain('deleteConfirmMessage Sales Agent')
    await click(buttons(renderer).filter((item) => nodeText(item).includes('delete')).at(-1)!)
    expect(deleteAgent).toHaveBeenCalledWith('agent-1')
    expect(success).toHaveBeenCalledWith('appDeleted')

    duplicateAgent.mockRejectedValueOnce(new Error('duplicate failed'))
    exportPackage.mockRejectedValueOnce(new Error('export failed'))
    const calls = getAgents.mock.calls.length
    await click(button(renderer, 'duplicate'))
    await click(button(renderer, 'export'))
    expect(getAgents.mock.calls).toHaveLength(calls)
    act(() => renderer.unmount())
  })

  test('runs every workflow publish, duplicate, export, and delete branch including failures', async () => {
    currentTeam = { id: 'team-1', role: 'admin' }
    getWorkflows.mockResolvedValue({ items: [workflow(), workflow({ id: 'workflow-2', name: 'Draft Flow', status: 'draft' })] })
    const renderer = await renderPage()

    await click(button(renderer, 'unpublish'))
    expect(unpublishWorkflow).toHaveBeenCalledWith('workflow-1')
    await click(buttons(renderer).find((item) => nodeText(item) === 'publish')!)
    expect(publishWorkflow).toHaveBeenCalledWith('workflow-2')
    await click(button(renderer, 'duplicate'))
    expect(duplicateWorkflow).toHaveBeenCalledWith('workflow-1')
    await click(button(renderer, 'export'))
    expect(exportPackage).toHaveBeenCalledWith('workflow', 'workflow-1')
    await click(button(renderer, 'delete'))
    await click(buttons(renderer).filter((item) => nodeText(item).includes('delete')).at(-1)!)
    expect(deleteWorkflow).toHaveBeenCalledWith('workflow-1')

    publishWorkflow.mockRejectedValueOnce(new Error('publish failed'))
    deleteWorkflow.mockRejectedValueOnce(new Error('delete failed'))
    await click(buttons(renderer).find((item) => nodeText(item) === 'publish')!)
    await click(button(renderer, 'delete'))
    await click(buttons(renderer).filter((item) => nodeText(item).includes('delete')).at(-1)!)
    expect(publishWorkflow).toHaveBeenCalledTimes(2)
    expect(deleteWorkflow).toHaveBeenCalledTimes(2)
    act(() => renderer.unmount())
  })

  test('allows superusers and hides all create actions for unprivileged empty state', async () => {
    user = { id: 'root', is_superuser: true }
    let renderer = await renderPage()
    expect(text(renderer)).toContain('apps-create-button')
    expect(text(renderer)).toContain('createFirstApp')
    act(() => renderer.unmount())

    user = null
    renderer = await renderPage()
    expect(text(renderer)).not.toContain('apps-create-button')
    expect(text(renderer)).not.toContain('createFirstApp')
    act(() => renderer.unmount())
  })

  test('appends page 2 for both sources, dedups, and stops once each source reaches its total', async () => {
    getAgents.mockImplementation(async ({ page }: PageArgs = {}) => page === 1
      ? { items: [agent({ updated_at: '2026-01-05' }), agent({ id: 'agent-2', name: 'Second Agent', updated_at: '2026-01-04' })], total: 4, page: 1, page_size: 20 }
      : { items: [agent({ id: 'agent-2', name: 'Second Agent', updated_at: '2026-01-04' }), agent({ id: 'agent-3', name: 'Third Agent', updated_at: '2026-01-03' }), agent({ id: 'agent-4', name: 'Fourth Agent', updated_at: '2026-01-01' })], total: 4, page: 2, page_size: 20 })
    getWorkflows.mockImplementation(async ({ page }: PageArgs = {}) => page === 1
      ? { items: [workflow({ updated_at: '2026-01-06' })], total: 2, page: 1, page_size: 20 }
      : { items: [workflow({ id: 'workflow-2', name: 'Billing Flow 2', updated_at: '2026-01-02' })], total: 2, page: 2, page_size: 20 })
    const renderer = await renderPage()
    expect(renderer.root.findByProps({ 'data-testid': 'apps-scroll-sentinel' })).toBeTruthy()
    expect(getWorkflows).toHaveBeenCalledTimes(1)

    await intersect()
    expect(getAgents).toHaveBeenLastCalledWith({ page: 2, pageSize: 20, search: undefined, teamId: 'team-1' })
    expect(getWorkflows).toHaveBeenLastCalledWith({ page: 2, pageSize: 20, keyword: undefined, teamId: 'team-1' })
    const rendered = text(renderer)
    expect(rendered).toContain('Third Agent')
    expect(rendered).toContain('Fourth Agent')
    expect(rendered).toContain('Billing Flow 2')
    expect((rendered.match(/Second Agent/g) ?? []).length).toBe(1)
    expect(rendered.indexOf('Third Agent')).toBeLessThan(rendered.indexOf('Billing Flow 2'))

    await intersect()
    expect(getAgents).toHaveBeenCalledTimes(2)
    expect(getWorkflows).toHaveBeenCalledTimes(2)
    act(() => renderer.unmount())
  })

  test('typed tabs advance only their own source and restart at page 1 after a tab change', async () => {
    getAgents.mockImplementation(async ({ page }: PageArgs = {}) => page === 1
      ? { items: [agent()], total: 2, page: 1, page_size: 20 }
      : { items: [agent({ id: 'agent-2', name: 'Agent Two' })], total: 2, page: 2, page_size: 20 })
    getWorkflows.mockImplementation(async ({ page }: PageArgs = {}) => page === 1
      ? { items: [workflow()], total: 2, page: 1, page_size: 20 }
      : { items: [workflow({ id: 'workflow-2', name: 'Flow Two' })], total: 2, page: 2, page_size: 20 })
    const renderer = await renderPage()

    await act(async () => {
      renderer.root.findByProps({ 'data-testid': 'tabs' }).props['data-change']('agent')
      await flushPromises()
    })
    expect(getAgents).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: undefined, teamId: 'team-1' })
    getAgents.mockClear()
    getWorkflows.mockClear()

    await intersect()
    expect(getAgents).toHaveBeenCalledWith({ page: 2, pageSize: 20, search: undefined, teamId: 'team-1' })
    expect(getWorkflows).not.toHaveBeenCalled()
    act(() => renderer.unmount())
  })

  test('a typed tab with an exhausted source does not pull the other source', async () => {
    getAgents.mockResolvedValue({ items: [agent()], total: 5, page: 1, page_size: 20 })
    getWorkflows.mockResolvedValue({ items: [workflow()], total: 1, page: 1, page_size: 20 })
    const renderer = await renderPage()

    await act(async () => {
      renderer.root.findByProps({ 'data-testid': 'tabs' }).props['data-change']('workflow')
      await flushPromises()
    })
    getAgents.mockClear()
    getWorkflows.mockClear()

    await intersect()
    expect(getWorkflows).not.toHaveBeenCalled()
    expect(getAgents).not.toHaveBeenCalled()
    act(() => renderer.unmount())
  })

  test('discards a stale page response after a search reset and restarts at page 1', async () => {
    const pendingPage2 = Promise.withResolvers<{ items: AppRecord[]; total: number; page: number; page_size: number }>()
    getAgents.mockImplementation(({ page, search: keyword }: PageArgs = {}) => {
      if (keyword === 'billing') {
        return Promise.resolve({ items: [agent({ id: 'agent-new', name: 'Billing Agent' })], total: 1, page: 1, page_size: 20 })
      }
      if (page === 1) {
        return Promise.resolve({ items: [agent()], total: 2, page: 1, page_size: 20 })
      }
      return pendingPage2.promise
    })
    getWorkflows.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    const renderer = await renderPage()

    await intersect()
    await leaveViewport()

    await act(async () => {
      renderer.root.findByType('input').props.onChange({ target: { value: 'billing' } })
      await flushPromises()
    })
    expect(getAgents).toHaveBeenLastCalledWith({ page: 1, pageSize: 20, search: 'billing', teamId: 'team-1' })
    expect(text(renderer)).toContain('Billing Agent')

    await act(async () => {
      pendingPage2.resolve({ items: [agent({ id: 'agent-stale', name: 'Stale Agent' })], total: 2, page: 2, page_size: 20 })
      await flushPromises()
    })
    expect(text(renderer)).not.toContain('Stale Agent')
    expect(text(renderer)).toContain('Billing Agent')
    act(() => renderer.unmount())
  })

  test('a failed next page exposes retry without auto retrying on further intersections', async () => {
    let page2Attempts = 0
    getAgents.mockImplementation(async ({ page }: PageArgs = {}) => {
      if (page === 1) return { items: [agent()], total: 5, page: 1, page_size: 20 }
      page2Attempts += 1
      throw new Error('offline')
    })
    getWorkflows.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    const renderer = await renderPage()

    await intersect()
    expect(page2Attempts).toBe(1)
    expect(text(renderer)).toContain('loadFailed')
    expect(renderer.root.findByProps({ 'data-testid': 'apps-retry' })).toBeTruthy()

    await intersect()
    expect(page2Attempts).toBe(1)

    await click(renderer.root.findByProps({ 'data-testid': 'apps-retry' }))
    expect(page2Attempts).toBe(2)
    act(() => renderer.unmount())
  })
})
