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
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
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
mock.module('@/lib/api', () => ({ knowledgeBasesApi: { getKnowledgeBases, deleteKnowledgeBase } }))
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
}))

const Box = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/card', () => ({ Card: Box, CardContent: Box }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: Box }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
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
    value: { location: { pathname: '/app/kb' } },
    configurable: true,
  })
  getKnowledgeBases.mockReset()
  getKnowledgeBases.mockResolvedValue({ items: [] })
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
    let resolveList!: (value: { items: KnowledgeBase[] }) => void
    getKnowledgeBases.mockReturnValue(new Promise((resolve) => { resolveList = resolve }))

    let renderer!: ReactTestRenderer
    await act(async () => {
      renderer = create(<KnowledgeBasePage />)
    })
    expect(text(renderer)).toContain('h-40')

    resolveList!({ items: [kb(), kb({ id: 'kb-2', name: 'Other Team', team: { id: 'team-2' } })] })
    await flush()

    expect(text(renderer)).toContain('Product Docs')
    expect(text(renderer)).not.toContain('Other Team')
    expect(text(renderer)).toContain('1.5K tokens')
    expect(renderer.root.findByProps({ href: '/app/kb/kb-1' })).toBeTruthy()

    act(() => renderer.unmount())
  })

  test('falls back to the empty state after a list error', async () => {
    const consoleError = mock(() => undefined)
    const previous = console.error
    console.error = consoleError
    getKnowledgeBases.mockRejectedValue(new Error('offline'))

    const renderer = await renderPage()

    expect(consoleError).toHaveBeenCalled()
    expect(text(renderer)).toContain('kb.noKbs')
    expect(text(renderer)).toContain('kb.createKbHint')

    console.error = previous
    act(() => renderer.unmount())
  })

  test('filters results and clears an empty search', async () => {
    getKnowledgeBases.mockResolvedValue({ items: [kb(), kb({ id: 'kb-2', name: 'Runbooks', description: null })] })
    const renderer = await renderPage()

    await act(async () => input(renderer).props.onChange({ target: { value: 'missing' } }))
    expect(text(renderer)).toContain('noSearchResults')
    expect(text(renderer)).not.toContain('Product Docs')

    const clear = buttons(renderer).find((button) => button.children.join('').includes('clearFilters'))
    await act(async () => clear!.props.onClick())

    expect(text(renderer)).toContain('Product Docs')
    expect(text(renderer)).toContain('Runbooks')

    act(() => renderer.unmount())
  })

  test('opens create, import, edit, export, and delete actions', async () => {
    getKnowledgeBases.mockResolvedValue({ items: [kb()] })
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

    await act(async () => menuItems[3].props.onClick({ preventDefault() {} }))
    await act(async () => buttons(renderer).find((button) => button.children.join('').includes('delete'))!.props.onClick())
    expect(deleteKnowledgeBase).toHaveBeenCalledWith('kb-1')
    expect(success).toHaveBeenCalledWith('kbDeleted')
    expect(getKnowledgeBases).toHaveBeenCalledTimes(2)

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
