import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const getKnowledgeBases = mock(() => Promise.resolve({ items: [] }))
const deleteKnowledgeBase = mock(() => Promise.resolve({}))
const exportPackage = mock(() => Promise.resolve({ blob: new Blob(), filename: 'kb.zip' }))
const downloadBlob = mock(() => undefined)
const replace = mock(() => undefined)
const useRequireTeam = mock(() => undefined)
const canPerform = mock(() => true)
const success = mock(() => undefined)

let currentTeam: { id: string; role?: string } | null = { id: 'team-1', role: 'admin' }
let user: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
let actionParam: string | null = null
let searchString = ''

mock.module('next/link', () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => ({
    get: (key: string) => (key === 'action' ? actionParam : null),
    toString: () => searchString,
  }),
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-require-team', () => ({ useRequireTeam }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user }) }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform }) }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: {
    getKnowledgeBases,
    deleteKnowledgeBase,
    listKnowledgeBaseShares: mock(() => Promise.resolve({ shares: [] })),
  },
  teamsApi: { getMyTeams: mock(() => Promise.resolve([])) },
}))
mock.module('@/lib/api/packages', () => ({ packagesApi: { export: exportPackage }, downloadBlob }))
mock.module('lucide-react', () => ({
  Database: () => null,
  Plus: () => null,
  FileText: () => null,
  Layers: () => null,
  MoreHorizontal: () => null,
  Pencil: () => null,
  Trash2: () => null,
  Search: () => null,
  Upload: () => null,
  Download: () => null,
  Share2: () => null,
  XIcon: () => null,
  ChevronDownIcon: () => null,
  CheckIcon: () => null,
  ChevronUpIcon: () => null,
  Loader2: () => null,
  Users: () => null,
}))

const Box = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/card', () => ({ Card: Box, CardContent: Box }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: Box }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('./_components/kb-share-dialog', () => ({
  KnowledgeBaseShareDialog: ({ open }: { open: boolean }) => (
    <div data-testid="share-dialog" data-open={open} />
  ),
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: Box,
  DropdownMenuContent: Box,
  DropdownMenuItem: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement> & { variant?: string }) => <div role="menuitem" {...props}>{children}</div>,
  DropdownMenuSeparator: Box,
  DropdownMenuTrigger: ({ render }: { render: (props: Record<string, unknown>) => React.ReactNode }) => render({}),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: Box,
  AlertDialogContent: Box,
  AlertDialogDescription: Box,
  AlertDialogFooter: Box,
  AlertDialogHeader: Box,
  AlertDialogTitle: Box,
  AlertDialogCancel: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: string }) => <button {...props}>{children}</button>,
}))
mock.module('./_components/kb-dialog', () => ({
  KnowledgeBaseDialog: (props: { open: boolean; knowledgeBase: { id: string; name: string } | null; onSuccess: () => void }) => (
    <section data-testid="kb-dialog" data-open={props.open} data-editing={props.knowledgeBase?.name ?? ''}>
      <button onClick={props.onSuccess}>dialog-success</button>
    </section>
  ),
}))
mock.module('@/components/packages/import-package-dialog', () => ({
  ImportPackageDialog: (props: { open: boolean; teamId: string; expectedResourceType: string; onImported: () => void }) => (
    <section data-testid="import-dialog" data-open={props.open} data-team={props.teamId} data-type={props.expectedResourceType}>
      <button onClick={props.onImported}>imported</button>
    </section>
  ),
}))

const { default: KnowledgeBasePage } = await import('./page')

type ObserverCallback = ConstructorParameters<typeof IntersectionObserver>[0]

class FakeIntersectionObserver {
  static instances: FakeIntersectionObserver[] = []

  readonly observed: Element[] = []

  constructor(private readonly callback: ObserverCallback) {
    FakeIntersectionObserver.instances.push(this)
  }

  observe(element: Element) {
    this.observed.push(element)
  }

  disconnect() {}

  trigger(isIntersecting: boolean) {
    this.callback(
      [{ isIntersecting, target: this.observed[0] } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    )
  }
}

Object.assign(globalThis, { IntersectionObserver: FakeIntersectionObserver })

type KnowledgeBase = {
  id: string
  name: string
  description: string | null
  team: { id: string }
  created_by: { id: string; username: string } | null
  document_count: number
  total_chunks: number
  total_tokens: number
}

const kb = (overrides: Partial<KnowledgeBase> = {}): KnowledgeBase => ({
  id: 'kb-1',
  name: 'Product Docs',
  description: 'Searchable product handbook',
  team: { id: 'team-1' },
  created_by: { id: 'user-1', username: 'alice' },
  document_count: 2,
  total_chunks: 12,
  total_tokens: 1530,
  ...overrides,
})

async function renderPage() {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<KnowledgeBasePage />)
    await Promise.resolve()
    await Promise.resolve()
  })
  return renderer
}

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())
const buttons = (renderer: ReactTestRenderer) => renderer.root.findAllByType('button')
const input = (renderer: ReactTestRenderer) => renderer.root.findByType('input')

beforeEach(() => {
  currentTeam = { id: 'team-1', role: 'admin' }
  user = { id: 'user-1' }
  actionParam = null
  searchString = ''
  Object.defineProperty(globalThis, 'window', {
    value: {
      location: { pathname: '/app/kb' },
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
    },
    configurable: true,
  })
  getKnowledgeBases.mockReset()
  getKnowledgeBases.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
  FakeIntersectionObserver.instances = []
  deleteKnowledgeBase.mockReset()
  deleteKnowledgeBase.mockResolvedValue({})
  exportPackage.mockReset()
  exportPackage.mockResolvedValue({ blob: new Blob(), filename: 'kb.zip' })
  downloadBlob.mockReset()
  replace.mockReset()
  useRequireTeam.mockReset()
  canPerform.mockReset()
  canPerform.mockReturnValue(true)
  success.mockReset()
})

afterEach(() => mock.restore())

describe('platform knowledge base page', () => {
  test('keeps the team gate loading state when there is no current team', async () => {
    currentTeam = null
    const renderer = await renderPage()

    expect(useRequireTeam).toHaveBeenCalled()
    expect(getKnowledgeBases).not.toHaveBeenCalled()
    expect(renderer.root.findAllByType('input')).toHaveLength(0)
    expect(text(renderer)).toContain('h-40')

    act(() => renderer.unmount())
  })

  test('shows list loading before rendering the current team knowledge bases', async () => {
    const deferred = Promise.withResolvers<{ items: KnowledgeBase[]; total: number; page: number; page_size: number }>()
    getKnowledgeBases.mockReturnValue(deferred.promise)

    let renderer!: ReactTestRenderer
    await act(async () => {
      renderer = create(<KnowledgeBasePage />)
    })
    expect(text(renderer)).toContain('h-40')

    deferred.resolve({ items: [kb(), kb({ id: 'kb-2', name: 'Other Team', team: { id: 'team-2' } })], total: 2, page: 1, page_size: 20 })
    await flush()

    expect(text(renderer)).toContain('Product Docs')
    expect(text(renderer)).not.toContain('Other Team')
    expect(text(renderer)).toContain('1.5K tokens')
    expect(renderer.root.findByProps({ href: '/app/kb/kb-1' })).toBeTruthy()

    act(() => renderer.unmount())
  })

  test('surfaces a manual retry after a list error without looping', async () => {
    const consoleError = mock(() => undefined)
    const previous = console.error
    console.error = consoleError
    getKnowledgeBases.mockRejectedValue(new Error('offline'))

    const renderer = await renderPage()

    expect(consoleError).toHaveBeenCalled()
    expect(text(renderer)).toContain('loadFailed')
    expect(text(renderer)).toContain('retry')
    expect(text(renderer)).not.toContain('kb.noKbs')

    const observer = FakeIntersectionObserver.instances[0]
    act(() => observer.trigger(true))
    await flush()
    expect(getKnowledgeBases).toHaveBeenCalledTimes(1)

    getKnowledgeBases.mockResolvedValue({ items: [kb()], total: 1, page: 1, page_size: 20 })
    await act(async () => buttons(renderer).find((button) => button.children.join('').includes('retry'))!.props.onClick())
    await flush()

    expect(getKnowledgeBases).toHaveBeenCalledTimes(2)
    expect(text(renderer)).toContain('Product Docs')

    console.error = previous
    act(() => renderer.unmount())
  })

  test('searches server-side after the debounce and clears an empty search', async () => {
    getKnowledgeBases.mockImplementation((params: { search?: string } = {}) => Promise.resolve(
      params.search
        ? { items: [], total: 0, page: 1, page_size: 20 }
        : { items: [kb(), kb({ id: 'kb-2', name: 'Runbooks', description: null })], total: 2, page: 1, page_size: 20 }
    ))
    const renderer = await renderPage()

    await act(async () => input(renderer).props.onChange({ target: { value: 'missing' } }))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)) })
    await flush()

    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'missing', page: 1 }))
    expect(text(renderer)).toContain('noSearchResults')
    expect(text(renderer)).not.toContain('Product Docs')

    const clear = buttons(renderer).find((button) => button.children.join('').includes('clearFilters'))
    await act(async () => clear!.props.onClick())
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)) })
    await flush()

    expect(text(renderer)).toContain('Product Docs')
    expect(text(renderer)).toContain('Runbooks')

    act(() => renderer.unmount())
  })

  test('opens create, import, edit, export, and delete actions', async () => {
    getKnowledgeBases.mockResolvedValue({ items: [kb()], total: 1, page: 1, page_size: 20 })
    const renderer = await renderPage()

    await act(async () => renderer.root.findByProps({ 'data-testid': 'kb-create-card' }).props.onClick())
    expect(renderer.root.findByProps({ 'data-testid': 'kb-dialog' }).props['data-open']).toBe(true)
    expect(renderer.root.findByProps({ 'data-testid': 'kb-dialog' }).props['data-editing']).toBe('')

    await act(async () => renderer.root.findByProps({ 'data-testid': 'kb-import-button' }).props.onClick())
    expect(renderer.root.findByProps({ 'data-testid': 'import-dialog' }).props).toMatchObject({
      'data-open': true,
      'data-team': 'team-1',
      'data-type': 'knowledge_base',
    })

    const menuItems = renderer.root.findAllByProps({ role: 'menuitem' })
    await act(async () => menuItems[0].props.onClick({ preventDefault() {} }))
    expect(renderer.root.findByProps({ 'data-testid': 'kb-dialog' }).props['data-editing']).toBe('Product Docs')

    await act(async () => menuItems[2].props.onClick({ preventDefault() {} }))
    expect(exportPackage).toHaveBeenCalledWith('knowledge_base', 'kb-1')
    expect(downloadBlob).toHaveBeenCalledWith(expect.any(Blob), 'kb.zip')

    const deleteMenuItem = menuItems.find((item) => item.children?.includes('delete')) || menuItems[menuItems.length - 1]
    await act(async () => deleteMenuItem.props.onClick({ preventDefault() {} }))
    await act(async () => buttons(renderer).find((button) => button.children.join('').includes('delete'))!.props.onClick())
    expect(deleteKnowledgeBase).toHaveBeenCalledWith('kb-1')
    expect(success).toHaveBeenCalledWith('kbDeleted')
    expect(getKnowledgeBases).toHaveBeenCalledTimes(2)

    act(() => renderer.unmount())
  })
  test('renders shared badge, shared count, and opens share dialog', async () => {
    const sharedKb = kb({
      id: 'kb-shared',
      name: 'Shared KB',
      is_owned: false,
      owner_team_name: 'Partner Team',
    })
    const ownedWithShares = kb({
      id: 'kb-owned-shared',
      name: 'Owned With Shares',
      is_owned: true,
      shared_with_count: 2,
    })
    getKnowledgeBases.mockResolvedValue({ items: [sharedKb, ownedWithShares], total: 2, page: 1, page_size: 20 })
    const renderer = await renderPage()

    const renderedText = JSON.stringify(renderer.toJSON())
    expect(renderedText).toContain('Partner Team')
    expect(renderedText).toContain('kb.sharedCount:2')

    const menuItems = renderer.root.findAllByProps({ role: 'menuitem' })
    const shareItem = menuItems.find((item) => item.children?.includes('kb.shareAction'))
    expect(shareItem).toBeDefined()
    await act(async () => shareItem?.props.onClick({ preventDefault() {} }))

    expect(renderer.root.findByProps({ 'data-testid': 'share-dialog' }).props['data-open']).toBe(true)
    act(() => renderer.unmount())
  })

  test('appends the next page only after a fresh intersect entry, dedupes, and stops at the total', async () => {
    getKnowledgeBases.mockImplementation((params: { page?: number } = {}) => {
      if (params.page === 3) {
        return Promise.resolve({ items: [kb({ id: 'kb-4', name: 'Playbooks 2' })], total: 60, page: 3, page_size: 20 })
      }
      if (params.page === 2) {
        return Promise.resolve({ items: [kb({ id: 'kb-2', name: 'Runbooks' }), kb({ id: 'kb-3', name: 'Playbooks' })], total: 60, page: 2, page_size: 20 })
      }
      return Promise.resolve({ items: [kb(), kb({ id: 'kb-2', name: 'Runbooks' })], total: 60, page: 1, page_size: 20 })
    })
    const renderer = await renderPage()

    await act(async () => FakeIntersectionObserver.instances[0].trigger(true))
    await flush()

    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, pageSize: 20 }))
    expect(text(renderer)).toContain('Playbooks')
    expect(text(renderer).split('Runbooks')).toHaveLength(2)
    expect(getKnowledgeBases).toHaveBeenCalledTimes(2)

    await act(async () => FakeIntersectionObserver.instances.at(-1)!.trigger(false))
    await flush()
    expect(getKnowledgeBases).toHaveBeenCalledTimes(2)

    await act(async () => FakeIntersectionObserver.instances.at(-1)!.trigger(true))
    await flush()
    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, pageSize: 20 }))
    expect(text(renderer)).toContain('Playbooks 2')

    await act(async () => FakeIntersectionObserver.instances.at(-1)!.trigger(true))
    await flush()
    expect(getKnowledgeBases).toHaveBeenCalledTimes(3)

    act(() => renderer.unmount())
  })

  test('discards a stale append when a new search starts', async () => {
    const stalePage = Promise.withResolvers<{ items: KnowledgeBase[]; total: number; page: number; page_size: number }>()
    getKnowledgeBases.mockImplementation((params: { page?: number; search?: string } = {}) => {
      if (params.search === 'fresh') {
        return Promise.resolve({ items: [kb({ id: 'kb-9', name: 'Fresh KB' })], total: 1, page: 1, page_size: 20 })
      }
      if (params.page === 2) return stalePage.promise
      return Promise.resolve({ items: [kb()], total: 40, page: 1, page_size: 20 })
    })
    const renderer = await renderPage()

    await act(async () => FakeIntersectionObserver.instances[0].trigger(true))
    await flush()

    await act(async () => input(renderer).props.onChange({ target: { value: 'fresh' } }))
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 350)) })
    await flush()

    stalePage.resolve({ items: [kb({ id: 'kb-8', name: 'Stale KB' })], total: 40, page: 2, page_size: 20 })
    await flush()

    expect(text(renderer)).toContain('Fresh KB')
    expect(text(renderer)).not.toContain('Stale KB')
    expect(text(renderer)).not.toContain('Product Docs')

    act(() => renderer.unmount())
  })

  test('retries the failed append page even when the rendered list is empty', async () => {
    const consoleError = mock(() => undefined)
    const previous = console.error
    console.error = consoleError
    let pageTwoAttempts = 0
    getKnowledgeBases.mockImplementation((params: { page?: number } = {}) => {
      if (params.page === 1) {
        return Promise.resolve({ items: [kb({ id: 'foreign', name: 'Other Team KB', team: { id: 'team-2' } })], total: 40, page: 1, page_size: 20 })
      }
      pageTwoAttempts += 1
      if (pageTwoAttempts === 1) return Promise.reject(new Error('offline'))
      return Promise.resolve({ items: [kb({ id: 'kb-2', name: 'Runbooks' })], total: 40, page: 2, page_size: 20 })
    })
    const renderer = await renderPage()
    expect(text(renderer)).not.toContain('Other Team KB')

    await act(async () => FakeIntersectionObserver.instances.at(-1)!.trigger(true))
    await flush()
    expect(text(renderer)).toContain('loadFailed')

    await act(async () => buttons(renderer).find((button) => button.children.join('').includes('retry'))!.props.onClick())
    await flush()

    expect(getKnowledgeBases).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    expect(text(renderer)).toContain('Runbooks')

    console.error = previous
    act(() => renderer.unmount())
  })

  test('opens the create dialog from the route query and preserves unrelated params', async () => {
    actionParam = 'create'
    searchString = 'action=create&tab=mine'

    const renderer = await renderPage()

    expect(renderer.root.findByProps({ 'data-testid': 'kb-dialog' }).props['data-open']).toBe(true)
    expect(replace).toHaveBeenCalledWith('/app/kb?tab=mine', { scroll: false })

    act(() => renderer.unmount())
  })
})
