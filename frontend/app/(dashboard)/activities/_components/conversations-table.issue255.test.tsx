import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const listAll = mock()
const getDetail = mock()
const batchDelete = mock()
const getTeams = mock()
const getAgents = mock()
const getUsers = mock()
let canDelete = true

const element = (tag: string) => {
  const Component = ({ children, render, ...props }: React.PropsWithChildren<{ render?: React.ReactElement } & Record<string, unknown>>) =>
    render ? React.cloneElement(render, props) : React.createElement(tag, props, children)
  Component.displayName = tag
  return Component
}

mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: mock() } }))
mock.module('@/lib/api', () => ({ agentsApi: { getAgents } }))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/lib/api/admin/conversations', () => ({ conversationsApi: { listAll, getDetail, batchDelete } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => canDelete }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => ['', mock()] }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: <T,>(value: T) => value }))
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
].map((name) => [name, element('svg')])))

const { ConversationsTable } = await import('./conversations-table')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const conversations = [
  { id: 'one', title: 'One', agent_name: 'Agent', user_name: 'Ada', message_count: 1, updated_at: '2026-01-01T10:00:00Z' },
  { id: 'two', title: 'Two', agent_name: 'Agent', user_name: 'Lin', message_count: 2, updated_at: '2026-01-02T10:00:00Z' },
]
const renderers: ReactTestRenderer[] = []

async function renderTable() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<ConversationsTable />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  canDelete = true
  for (const fn of [listAll, getDetail, batchDelete, getTeams, getAgents, getUsers]) fn.mockReset()
})

describe('ConversationsTable uncovered behavior', () => {
  test('reports filter failures and excludes destructive actions without permission', async () => {
    const error = spyOn(console, 'error').mockImplementation(() => {})
    getTeams.mockRejectedValue(new Error('filters unavailable'))
    getUsers.mockRejectedValue(new Error('users unavailable'))
    listAll.mockResolvedValue({ items: conversations, total: 2 })
    canDelete = false

    const renderer = await renderTable()

    expect(error).toHaveBeenCalledWith('Failed to load filter options:', expect.any(Error))
    expect(error).toHaveBeenCalledWith('Failed to load user filter options:', expect.any(Error))
    expect(renderer.root.findAllByType('tr')).toHaveLength(3)
    error.mockRestore()
  })

  test('toggles individual and all selections, clears them, and reports failed deletion', async () => {
    const error = spyOn(console, 'error').mockImplementation(() => {})
    getTeams.mockResolvedValue({ items: [] })
    getAgents.mockResolvedValue({ items: [] })
    getUsers.mockResolvedValue({ items: [] })
    listAll.mockResolvedValue({ items: conversations, total: 2 })
    batchDelete.mockRejectedValue(new Error('delete unavailable'))
    const renderer = await renderTable()
    const checks = () => renderer.root.findAllByType('input').filter((input) => input.props.onCheckedChange)

    act(() => checks()[1].props.onCheckedChange())
    expect(checks()[1].props.checked).toBe(true)
    act(() => checks()[1].props.onCheckedChange())
    expect(checks()[1].props.checked).toBe(false)
    act(() => checks()[0].props.onCheckedChange())
    expect(checks().slice(1).every((input) => input.props.checked)).toBe(true)
    act(() => checks()[0].props.onCheckedChange())
    expect(checks().slice(1).every((input) => !input.props.checked)).toBe(true)

    act(() => checks()[1].props.onCheckedChange())
    const destructive = renderer.root.findAllByType('button').find((button) => button.props.className?.includes('text-destructive'))!
    act(() => destructive.props.onClick())
    const confirms = renderer.root.findAllByType('button').filter((button) => button.props.variant === 'destructive')
    await act(async () => confirms.at(-1)!.props.onClick())
    expect(batchDelete).toHaveBeenCalledWith(['one'])
    expect(error).toHaveBeenCalledWith('Failed to delete conversations:', expect.any(Error))
    error.mockRestore()
  })

  test('navigates every pagination boundary and handles detail failure', async () => {
    const error = spyOn(console, 'error').mockImplementation(() => {})
    getTeams.mockResolvedValue({ items: [] })
    getAgents.mockResolvedValue({ items: [] })
    getUsers.mockResolvedValue({ items: [] })
    listAll.mockResolvedValue({ items: conversations, total: 60 })
    getDetail.mockRejectedValue(new Error('detail unavailable'))
    const renderer = await renderTable()
    const pageButtons = () => renderer.root.findAllByType('button').filter((button) => button.props.className === 'h-8 w-8' && 'disabled' in button.props)

    await act(async () => pageButtons()[2].props.onClick())
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    await act(async () => pageButtons()[1].props.onClick())
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))
    await act(async () => pageButtons()[3].props.onClick())
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3 }))
    await act(async () => pageButtons()[0].props.onClick())
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }))

    await act(async () => renderer.root.findAllByType('tr')[1].props.onClick())
    expect(error).toHaveBeenCalledWith('Failed to load conversation detail:', expect.any(Error))
    error.mockRestore()
  })
})
