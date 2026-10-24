import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const listAll = mock()
const getTeams = mock(async () => ({ items: [] }))
const getAgents = mock(async () => ({ items: [] }))
const getUsers = mock(async () => ({ items: [] }))

const element = (tag: string) => {
  const Component = ({ children, render, ...props }: React.PropsWithChildren<{ render?: React.ReactElement } & Record<string, unknown>>) => {
    if (render) return React.cloneElement(render, props)
    return React.createElement(tag, props, children)
  }
  Component.displayName = tag
  return Component
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(value)) return text(value.props.children)
  if (value && typeof value === 'object' && 'children' in value) return text(value.children)
  return ''
}

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/lib/api', () => ({ agentsApi: { getAgents } }))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/lib/api/admin/conversations', () => ({
  conversationsApi: { listAll, getDetail: mock(async () => null), batchDelete: mock(async () => {}) },
}))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
// The debounce hook is intentionally not mocked: the real 300ms timer is under test.
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('input') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'), SelectContent: element('div'), SelectItem: element('option'),
  SelectTrigger: element('button'), SelectValue: element('span'),
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'), TableBody: element('tbody'), TableCell: element('td'),
  TableHead: element('th'), TableHeader: element('thead'), TableRow: element('tr'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element('div'), AlertDialogAction: element('button'), AlertDialogCancel: element('button'),
  AlertDialogContent: element('div'), AlertDialogDescription: element('p'), AlertDialogFooter: element('footer'),
  AlertDialogHeader: element('header'), AlertDialogTitle: element('h2'),
}))
mock.module('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: element('div'), DropdownMenuContent: element('div'), DropdownMenuItem: element('button'), DropdownMenuTrigger: element('button'),
}))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: element('button') }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element('div'), TooltipContent: element('span'), TooltipTrigger: element('button') }))
mock.module('./conversation-drawer', () => ({ ConversationDrawer: () => null }))
mock.module('lucide-react', () => Object.fromEntries([
  'Search', 'MessageSquare', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'Trash2', 'MoreHorizontal', 'Eye', 'Copy',
].map((name) => [name, element('svg')])) )

// The component is imported after the module mocks above are registered, which a
// static import cannot guarantee.
const { ConversationsTable } = await import('./conversations-table')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const conversation = {
  id: 'conversation-1', title: 'Daily chat', agent_name: 'Helper', user_name: 'Ada', message_count: 3,
  updated_at: '2026-01-01T10:00:00Z', agent_id: 'agent-1', user_id: 'user-1', team_id: 'team-1', created_at: '2026-01-01T09:00:00Z',
}

const renderers: ReactTestRenderer[] = []

async function render() {
  let renderer!: ReactTestRenderer
  await act(async () => {
    renderer = create(<ConversationsTable />)
    await Promise.resolve()
  })
  renderers.push(renderer)
  return renderer
}

function searchInput(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('input').find((node) => node.props.placeholder === 'activities.searchPlaceholder')!
}

function pageButtons(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('button').filter((button) => button.props.className === 'h-8 w-8' && 'disabled' in button.props)
}

async function type(renderer: ReactTestRenderer, value: string) {
  await act(async () => searchInput(renderer).props.onChange({ target: { value } }))
}

async function waitForDebounce(ms: number) {
  await act(async () => {
    const { promise, resolve } = Promise.withResolvers<void>()
    setTimeout(resolve, ms)
    await promise
  })
}

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
  listAll.mockClear()
})

describe('ConversationsTable search debounce', () => {
  test('keeps the input responsive, waits 300ms, and collapses rapid edits into one query', async () => {
    listAll.mockImplementation(async () => ({ items: [conversation], total: 1 }))
    const renderer = await render()
    expect(listAll).toHaveBeenCalledTimes(1)
    listAll.mockClear()

    await type(renderer, 'd')
    expect(searchInput(renderer).props.value).toBe('d')
    expect(renderer.root.findAllByType('button').filter((button) => text(button).includes('common.reset')).length).toBe(1)

    await type(renderer, 'da')
    await type(renderer, 'dai')
    await type(renderer, 'dail')
    await type(renderer, 'daily')
    expect(searchInput(renderer).props.value).toBe('daily')
    expect(listAll).not.toHaveBeenCalled()

    await waitForDebounce(150)
    expect(listAll).not.toHaveBeenCalled()

    await waitForDebounce(500)
    expect(listAll).toHaveBeenCalledTimes(1)
    expect(listAll).toHaveBeenCalledWith(expect.objectContaining({ page: 1, search: 'daily' }))
  })

  test('settles an edit made on a later page into a single first-page request', async () => {
    listAll.mockImplementation(async () => ({ items: [conversation], total: 45 }))
    const renderer = await render()
    await act(async () => pageButtons(renderer)[3].props.onClick())
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3 }))
    listAll.mockClear()

    await type(renderer, 'r')
    await type(renderer, 're')
    await type(renderer, 'report')
    await waitForDebounce(500)

    expect(listAll).toHaveBeenCalledTimes(1)
    expect(listAll).toHaveBeenCalledWith(expect.objectContaining({ page: 1, search: 'report' }))
  })
})
