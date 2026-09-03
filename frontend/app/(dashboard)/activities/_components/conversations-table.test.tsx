import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const listAll = mock()
const getDetail = mock()
const batchDelete = mock(async () => {})
const getTeams = mock(() => Promise.resolve({ items: [] }))
const getAgents = mock(() => Promise.resolve({ items: [] }))
const getUsers = mock(() => Promise.resolve({ items: [] }))
const success = mock()
let search = ''
const setSearch = mock((value: string) => { search = value })

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
  if (value && typeof value === 'object' && 'children' in value) return text((value as { children?: unknown }).children)
  if (value && typeof value === 'object' && 'props' in value) return text((value as { props?: { children?: unknown } }).props?.children)
  return ''
}

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: (namespace: string) => (key: string, values?: Record<string, unknown>) =>
    values ? `${namespace}.${key}:${JSON.stringify(values)}` : `${namespace}.${key}`,
}))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('@/lib/api', () => ({ agentsApi: { getAgents } }))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/lib/api/admin/conversations', () => ({ conversationsApi: { listAll, getDetail, batchDelete } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => [search, setSearch] }))
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
mock.module('./conversation-drawer', () => ({
  ConversationDrawer: ({ conversation, isLoading, open, onDelete }: { conversation?: { id: string } | null; isLoading: boolean; open: boolean; onDelete: (id: string) => void }) =>
    open ? <aside role="dialog" aria-label={conversation?.id ?? (isLoading ? 'loading' : 'empty')}><button onClick={() => onDelete(conversation?.id ?? 'conversation-1')}>drawer-delete</button></aside> : null,
}))
mock.module('lucide-react', () => Object.fromEntries([
  'Search', 'MessageSquare', 'ChevronLeft', 'ChevronRight', 'ChevronsLeft', 'ChevronsRight', 'X', 'Trash2', 'MoreHorizontal', 'Eye', 'Copy',
].map((name) => [name, element('svg')])) )

const { ConversationsTable } = await import('./conversations-table')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const conversation = {
  id: 'conversation-1', title: 'Daily chat', agent_name: 'Helper', user_name: 'Ada', message_count: 3,
  updated_at: '2026-01-01T10:00:00Z', agent_id: 'agent-1', user_id: 'user-1', team_id: 'team-1', created_at: '2026-01-01T09:00:00Z',
}
const detail = { ...conversation, messages: [] }
const renderers: ReactTestRenderer[] = []

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<ConversationsTable />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

function buttons(renderer: ReactTestRenderer, label: string) {
  return renderer.root.findAllByType('button').filter((button) => text(button.props.children).includes(label))
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  search = ''
  for (const fn of [listAll, getDetail, batchDelete, getTeams, getAgents, getUsers, setSearch, success]) fn.mockReset?.()
  getTeams.mockResolvedValue({ items: [] })
  getAgents.mockResolvedValue({ items: [] })
  getUsers.mockResolvedValue({ items: [] })
  batchDelete.mockResolvedValue(undefined)
})

describe('ConversationsTable', () => {
  test('shows loading, empty, and failed-load states', async () => {
    listAll.mockImplementation(() => new Promise(() => {}))
    expect(text((await render()).toJSON())).toContain('common.loading')

    listAll.mockResolvedValueOnce({ items: [], total: 0 })
    expect(text((await render()).toJSON())).toContain('activities.noConversations')

    const error = spyOn(console, 'error').mockImplementation(() => {})
    listAll.mockRejectedValueOnce(new Error('unavailable'))
    expect(text((await render()).toJSON())).toContain('activities.noConversations')
    expect(error).toHaveBeenCalledWith('Failed to load conversations:', expect.any(Error))
  })

  test('filters option lists, search, reset, and page size', async () => {
    listAll.mockResolvedValue({ items: [], total: 40 })
    getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Core' }] })
    getAgents.mockResolvedValue({ items: [{ id: 'agent-1', name: 'Helper' }] })
    getUsers.mockResolvedValue({ items: [{ id: 'user-1', username: 'Ada' }] })
    const renderer = await render()

    const filters = renderer.root.findAllByType('button').filter((button) => button.props.onSelectionChange)
    await act(async () => filters.find((button) => button.props.title === 'common.team')!.props.onSelectionChange(new Set(['team-1'])))
    await act(async () => filters.find((button) => button.props.title === 'activities.agent')!.props.onSelectionChange(new Set(['agent-1'])))
    await act(async () => filters.find((button) => button.props.title === 'activities.user')!.props.onSearchChange('ada'))
    expect(getUsers).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'ada' }))
    await act(async () => filters.find((button) => button.props.title === 'activities.user')!.props.onSelectionChange(new Set(['user-1'])))
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ team_id: ['team-1'], agent_id: ['agent-1'], user_id: ['user-1'] }))

    await act(async () => renderer.root.findAllByType('input').find((input) => input.props.placeholder === 'activities.searchPlaceholder')!.props.onChange({ target: { value: 'daily' } }))
    expect(setSearch).toHaveBeenCalledWith('daily')

    await act(async () => renderer.root.findByType('select').props.onValueChange('50'))
    expect(listAll).toHaveBeenLastCalledWith(expect.objectContaining({ pageSize: 50 }))

    search = 'daily'
    await act(async () => buttons(renderer, 'common.reset')[0].props.onClick())
    expect(setSearch).toHaveBeenLastCalledWith('')
  })

  test('opens details, deletes rows, and bulk deletes selections', async () => {
    listAll.mockResolvedValue({ items: [conversation, { ...conversation, id: 'conversation-2', title: null }], total: 2 })
    getDetail.mockResolvedValue(detail)
    const renderer = await render()

    await act(async () => renderer.root.findAllByType('tr')[1].props.onClick())
    expect(getDetail).toHaveBeenCalledWith('conversation-1')
    expect(renderer.root.findByProps({ role: 'dialog' }).props['aria-label']).toBe('conversation-1')

    await act(async () => buttons(renderer, 'drawer-delete')[0].props.onClick())
    await act(async () => buttons(renderer, 'common.delete').at(-1)!.props.onClick())
    expect(batchDelete).toHaveBeenCalledWith(['conversation-1'])
    expect(success).toHaveBeenCalledWith('activities.deleteSuccess')

    const checkboxes = renderer.root.findAllByType('input').filter((input) => input.props.onCheckedChange)
    act(() => checkboxes[0].props.onCheckedChange())
    await act(async () => renderer.root.findAllByType('button').find((button) => button.props.className?.includes('text-destructive'))!.props.onClick())
    await act(async () => buttons(renderer, 'common.delete').at(-1)!.props.onClick())
    expect(batchDelete).toHaveBeenCalledWith(['conversation-1', 'conversation-2'])
  })
})
