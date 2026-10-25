import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const getAgent = mock(() => Promise.resolve({ id: 'agent-1', name: 'Support Agent' }))
const getAgentConversations = mock(() => Promise.resolve({ items: [], total: 0, page: 1, page_size: 20 }))
const getConversation = mock()
const deleteConversation = mock()
const push = mock()
const onOpenChange = mock()

let params = { id: 'agent-1' }
let state: unknown[] = []
let stateIndex = 0
let refs: { current: unknown }[] = []
let refIndex = 0
let infiniteOptions: { hasMore: boolean; loading: boolean; onLoadMore: () => Promise<void> | undefined } | null = null

const Fragment = Symbol('Fragment')
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ Fragment, jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ Fragment, jsxDEV: jsx }))
mock.module('react', () => ({
  useCallback: <T extends (...args: never[]) => unknown>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => { effect() },
  useMemo: <T,>(factory: () => T) => factory(),
  useRef: <T,>(initial: T) => {
    const index = refIndex++
    refs[index] ??= { current: initial }
    return refs[index] as { current: T }
  },
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
}))
mock.module('next/navigation', () => ({
  useParams: () => params,
  useRouter: () => ({ push }),
}))
mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string, values?: Record<string, number>) => values ? `${key}:${values.from}-${values.to}-${values.total}` : key,
}))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: <T,>(value: T) => value }))
mock.module('@/hooks/use-infinite-scroll', () => ({
  useInfiniteScroll: (options: { hasMore: boolean; loading: boolean; onLoadMore: () => Promise<void> | undefined }) => {
    infiniteOptions = options
    return { current: null }
  },
}))
mock.module('@/lib/api', () => ({
  agentsApi: { getAgent, getAgentConversations, getConversation, deleteConversation },
}))
mock.module('@/lib/utils/message-converter', () => ({
  convertBackendMessages: (messages: Array<{ id: string }>) => messages.map((message) => ({ id: message.id })),
}))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/skeleton', () => ({ Skeleton: element('skeleton') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: element('tooltip'), TooltipContent: element('tooltip-content'), TooltipTrigger: element('button') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: element('select-content'),
  SelectItem: element('select-item'),
  SelectTrigger: element('select-trigger'),
  SelectValue: element('select-value'),
}))
mock.module('@/components/ui/table', () => ({
  Table: element('table'),
  TableBody: element('tbody'),
  TableCell: element('td'),
  TableHead: element('th'),
  TableHeader: element('thead'),
  TableRow: element('tr'),
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: element('alert-dialog'),
  AlertDialogAction: element('alert-dialog-action'),
  AlertDialogCancel: element('alert-dialog-cancel'),
  AlertDialogContent: element('alert-dialog-content'),
  AlertDialogDescription: element('alert-dialog-description'),
  AlertDialogFooter: element('alert-dialog-footer'),
  AlertDialogHeader: element('alert-dialog-header'),
  AlertDialogTitle: element('alert-dialog-title'),
}))
mock.module('@/components/ui/sheet', () => ({ Sheet: element('sheet'), SheetContent: element('sheet-content') }))
mock.module('@/components/chat', () => ({ Message: element('chat-message') }))
mock.module('@/components/chat/conversation-drawer-header', () => ({ ConversationDrawerHeader: element('conversation-drawer-header') }))
mock.module('../_components/agent-sidebar', () => ({ AgentSidebar: element('agent-sidebar') }))
mock.module('lucide-react', () => ({
  ArrowUpDown: element('svg'),
  Calendar: element('svg'),
  Loader2: element('svg'),
  MessageSquare: element('svg'),
  Search: element('svg'),
  X: element('svg'),
}))

const { default: LogsPage } = await import('./page')
const { ConversationDrawer } = await import('./_components/conversation-drawer')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  if (tree.type === Fragment) return { type: Fragment, props: tree.props }
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) throw new Error('Element not found')
  const tree = resolved as Tree
  if (predicate(tree)) return tree
  const children = tree.props.children
  for (const child of Array.isArray(children) ? children : [children]) {
    try {
      return find(child as ReactNode, predicate)
    } catch {
      // Continue searching siblings.
    }
  }
  throw new Error('Element not found')
}

function renderLogsPage() {
  stateIndex = 0
  refIndex = 0
  return LogsPage()
}

async function flush() {
  await Promise.resolve()
  await Promise.resolve()
}

async function renderLoadedPage() {
  renderLogsPage()
  await flush()
  renderLogsPage()
  await flush()
  return renderLogsPage()
}

beforeEach(() => {
  getAgent.mockClear()
  getAgentConversations.mockClear()
  getConversation.mockClear()
  deleteConversation.mockClear()
  push.mockClear()
  onOpenChange.mockClear()
  params = { id: 'agent-1' }
  state = []
  refs = []
  infiniteOptions = null
})

describe('platform agent logs page', () => {
  test('imports and renders the loading shell while requesting the agent', () => {
    const page = renderLogsPage()

    expect(getAgent).toHaveBeenCalledWith('agent-1')
    expect(find(page, (tree) => tree.type === 'skeleton')).toBeDefined()
  })

  test('loads conversations, opens a detail, and loads the next page when the sentinel intersects', async () => {
    getAgentConversations.mockResolvedValue({
      items: [{
        id: 'conversation-1',
        title: '',
        message_count: 3,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
      }],
      total: 41,
      page: 1,
      page_size: 20,
    })
    getConversation.mockResolvedValue({ id: 'conversation-1', messages: [] })

    const page = await renderLoadedPage()
    expect(getAgentConversations).toHaveBeenCalledWith('agent-1', {
      page: 1,
      pageSize: 20,
      search: undefined,
      createdAfter: undefined,
      sortBy: 'created_at',
    })
    expect(find(page, (tree) => tree.type === 'td' && tree.props.children === 3)).toBeDefined()
    expect(infiniteOptions?.hasMore).toBe(true)
    expect(find(page, (tree) => tree.type === 'div' && tree.props['aria-hidden'] === true)).toBeDefined()

    await (find(page, (tree) => tree.type === 'tr' && tree.props.onClick).props.onClick as () => Promise<void>)()
    expect(getConversation).toHaveBeenCalledWith('conversation-1')

    await infiniteOptions?.onLoadMore()
    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 2 }))
  })

  test('applies search and select filters and clears the search', async () => {
    let page = await renderLoadedPage()
    const input = find(page, (tree) => tree.type === 'input')
    ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: ' billing ' } })

    page = renderLogsPage()
    await flush()
    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ search: 'billing' }))

    const selects: Tree[] = []
    const collect = (node: ReactNode) => {
      const resolved = resolve(node)
      if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return
      const tree = resolved as Tree
      if (tree.type === 'select') selects.push(tree)
      const children = tree.props.children
      for (const child of Array.isArray(children) ? children : [children]) collect(child as ReactNode)
    }
    collect(page)
    ;(selects[0].props.onValueChange as (value: string) => void)('7d')
    ;(selects[1].props.onValueChange as (value: string) => void)('message_count')
    renderLogsPage()
    await flush()
    expect(getAgentConversations.mock.calls.at(-1)?.[1]).toMatchObject({ sortBy: 'message_count' })
    expect(getAgentConversations.mock.calls.at(-1)?.[1]?.createdAfter).toBeString()

    page = renderLogsPage()
    ;(find(page, (tree) => tree.type === 'button' && !tree.props['aria-label']).props.onClick as () => void)()
    renderLogsPage()
    await flush()
    expect(getAgentConversations.mock.calls.at(-1)?.[1]?.search).toBeUndefined()
  })
  test('uses the selected 30-day and 90-day filters in conversation requests', async () => {
    let page = await renderLoadedPage()
    const selects: Tree[] = []
    const collect = (node: ReactNode) => {
      const resolved = resolve(node)
      if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return
      const tree = resolved as Tree
      if (tree.type === 'select') selects.push(tree)
      const children = tree.props.children
      for (const child of Array.isArray(children) ? children : [children]) collect(child as ReactNode)
    }
    collect(page)

    for (const filter of ['30d', '90d']) {
      ;(selects[0].props.onValueChange as (value: string) => void)(filter)
      page = renderLogsPage()
      await flush()
      const request = getAgentConversations.mock.calls.at(-1)?.[1]
      expect(request?.createdAfter).toBeString()
      expect(Date.parse(request?.createdAfter ?? '')).toBeLessThanOrEqual(Date.now())
      expect(request?.sortBy).toBe('created_at')
    }
  })

  test('confirms deletion and refreshes the first conversation page', async () => {
    getAgentConversations.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    await renderLoadedPage()
    state[14] = 'conversation-1'
    const page = renderLogsPage()

    await (find(page, (tree) => tree.type === 'alert-dialog-action').props.onClick as () => Promise<void>)()

    expect(deleteConversation).toHaveBeenCalledWith('conversation-1')
    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 1 }))
    expect(state[14]).toBeNull()
  })

  test('shows a manual retry when the initial conversation load fails', async () => {
    getAgentConversations.mockRejectedValue(new Error('unavailable'))

    const page = await renderLoadedPage()
    await flush()

    expect(find(page, (tree) => tree.type === 'p' && tree.props.children === 'loadFailed')).toBeDefined()

    getAgentConversations.mockResolvedValue({
      items: [{ id: 'conversation-1', title: 'One', message_count: 1, created_at: '', updated_at: '' }],
      total: 1,
      page: 1,
      page_size: 20,
    })
    const retry = find(page, (tree) => tree.type === 'button' && tree.props.children === 'retry')
    await (retry.props.onClick as () => Promise<void>)()

    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 1 }))
    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual(['conversation-1'])
    expect(state[7]).toBeNull()
  })

  test('closes a conversation drawer after deleting its selected conversation', async () => {
    getAgentConversations.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    await renderLoadedPage()
    state[11] = true
    state[12] = { id: 'conversation-1', messages: [] }
    state[14] = 'conversation-1'
    const page = renderLogsPage()

    await (find(page, (tree) => tree.type === 'alert-dialog-action').props.onClick as () => Promise<void>)()

    expect(state[12]).toBeNull()
    expect(state[11]).toBe(false)
  })
  test('opens the drawer when conversation detail cannot be loaded', async () => {
    getAgentConversations.mockResolvedValue({
      items: [{ id: 'conversation-1', title: 'Billing', message_count: 1, created_at: '', updated_at: '' }],
      total: 1,
      page: 1,
      page_size: 20,
    })
    getConversation.mockRejectedValueOnce(new Error('unavailable'))
    const page = await renderLoadedPage()

    await (find(page, (tree) => tree.type === 'tr' && tree.props.onClick).props.onClick as () => Promise<void>)()

    expect(getConversation).toHaveBeenCalledWith('conversation-1')
    expect(state[11]).toBe(true)
    expect(state[13]).toBe(false)
  })

  test('closes the delete confirmation when deletion fails', async () => {
    deleteConversation.mockRejectedValueOnce(new Error('unavailable'))
    await renderLoadedPage()
    state[14] = 'conversation-1'
    const page = renderLogsPage()

    await (find(page, (tree) => tree.type === 'alert-dialog-action').props.onClick as () => Promise<void>)()

    expect(deleteConversation).toHaveBeenCalledWith('conversation-1')
    expect(state[14]).toBeNull()
  })



  test('shows the search-specific empty state after a filtered request returns no matches', async () => {
    getAgentConversations.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 })
    let page = await renderLoadedPage()

    const search = find(page, (tree) => tree.type === 'input')
    ;(search.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'missing topic' } })
    page = renderLogsPage()
    await flush()
    page = renderLogsPage()

    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ search: 'missing topic' }))
    expect(find(page, (tree) => tree.type === 'p' && tree.props.children === 'noSearchResults')).toBeDefined()
  })

  test('appends the next page, deduplicates ids, and stops at the total', async () => {
    const pageOne = {
      items: [
        { id: 'conversation-1', title: 'One', message_count: 1, created_at: '', updated_at: '' },
        { id: 'conversation-2', title: 'Two', message_count: 2, created_at: '', updated_at: '' },
      ],
      total: 3,
      page: 1,
      page_size: 20,
    }
    const pageTwo = {
      items: [
        { id: 'conversation-2', title: 'Two', message_count: 2, created_at: '', updated_at: '' },
        { id: 'conversation-3', title: 'Three', message_count: 3, created_at: '', updated_at: '' },
        { id: 'conversation-3', title: 'Three', message_count: 3, created_at: '', updated_at: '' },
      ],
      total: 3,
      page: 2,
      page_size: 20,
    }
    getAgentConversations.mockImplementation((_agentId: string, options: { page?: number }) =>
      Promise.resolve(options.page === 2 ? pageTwo : pageOne)
    )

    await renderLoadedPage()
    await flush()
    expect(infiniteOptions?.hasMore).toBe(true)

    await infiniteOptions?.onLoadMore()

    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 2 }))
    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual([
      'conversation-1',
      'conversation-2',
      'conversation-3',
    ])
    expect(state[3]).toBe(3)
    expect(state[4]).toBe(2)

    renderLogsPage()
    expect(infiniteOptions?.hasMore).toBe(false)
  })

  test('suppresses duplicate load-more requests in the same tick', async () => {
    const pageOne = { items: [], total: 41, page: 1, page_size: 20 }
    const pageTwo = {
      items: [{ id: 'conversation-1', title: 'One', message_count: 1, created_at: '', updated_at: '' }],
      total: 41,
      page: 2,
      page_size: 20,
    }
    getAgentConversations.mockImplementation((_agentId: string, options: { page?: number }) =>
      Promise.resolve(options.page === 2 ? pageTwo : pageOne)
    )

    await renderLoadedPage()
    await flush()

    const callsBefore = getAgentConversations.mock.calls.length
    const first = infiniteOptions?.onLoadMore()
    const second = infiniteOptions?.onLoadMore()
    await Promise.all([first, second])

    expect(getAgentConversations.mock.calls.length).toBe(callsBefore + 1)
    expect(state[2]).toHaveLength(1)
  })

  test('stops paging when a next page adds no new conversations', async () => {
    const pageOne = {
      items: [{ id: 'conversation-1', title: 'One', message_count: 1, created_at: '', updated_at: '' }],
      total: 41,
      page: 1,
      page_size: 20,
    }
    getAgentConversations.mockImplementation((_agentId: string, options: { page?: number }) =>
      Promise.resolve(options.page === 2
        ? { items: [], total: 41, page: 2, page_size: 20 }
        : pageOne)
    )

    await renderLoadedPage()
    await flush()
    expect(infiniteOptions?.hasMore).toBe(true)

    await infiniteOptions?.onLoadMore()

    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 2 }))
    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual(['conversation-1'])
    expect(state[3]).toBe(1)

    renderLogsPage()
    expect(infiniteOptions?.hasMore).toBe(false)
  })

  test('resets to page one and discards a stale page-two response when a filter changes', async () => {
    const pageOne = {
      items: [{ id: 'conversation-old', title: 'Old', message_count: 1, created_at: '', updated_at: '' }],
      total: 2,
      page: 1,
      page_size: 20,
    }
    getAgentConversations.mockImplementation(() => Promise.resolve(pageOne))
    const page = await renderLoadedPage()
    await flush()

    const stalePage = Promise.withResolvers<{
      items: Array<{ id: string; title: string; message_count: number; created_at: string; updated_at: string }>
      total: number
    }>()
    getAgentConversations.mockImplementation((_agentId: string, options: { page?: number }) => {
      if (options.page === 2) return stalePage.promise
      return Promise.resolve({
        items: [{ id: 'conversation-new', title: 'New', message_count: 1, created_at: '', updated_at: '' }],
        total: 1,
        page: 1,
        page_size: 20,
      })
    })

    const stale = infiniteOptions?.onLoadMore()

    const selects: Tree[] = []
    const collect = (node: ReactNode) => {
      const resolved = resolve(node)
      if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return
      const tree = resolved as Tree
      if (tree.type === 'select') selects.push(tree)
      const children = tree.props.children
      for (const child of Array.isArray(children) ? children : [children]) collect(child as ReactNode)
    }
    collect(page)
    ;(selects[0].props.onValueChange as (value: string) => void)('7d')
    renderLogsPage()
    await flush()

    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 1 }))
    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual(['conversation-new'])

    stalePage.resolve({
      items: [{ id: 'conversation-stale', title: 'Stale', message_count: 1, created_at: '', updated_at: '' }],
      total: 2,
    })
    await stale
    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual(['conversation-new'])
    expect(state[3]).toBe(1)
  })

  test('keeps loaded conversations after a next-page error and retries manually', async () => {
    const pageOne = {
      items: [{ id: 'conversation-1', title: 'One', message_count: 1, created_at: '', updated_at: '' }],
      total: 2,
      page: 1,
      page_size: 20,
    }
    const pageTwo = {
      items: [{ id: 'conversation-2', title: 'Two', message_count: 2, created_at: '', updated_at: '' }],
      total: 2,
      page: 2,
      page_size: 20,
    }
    getAgentConversations.mockImplementation((_agentId: string, options: { page?: number }) =>
      options.page === 2 ? Promise.reject(new Error('unavailable')) : Promise.resolve(pageOne)
    )
    await renderLoadedPage()
    await flush()

    await infiniteOptions?.onLoadMore()

    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual(['conversation-1'])
    expect(state[6]).toBe(false)
    expect(state[7]).toEqual({ page: 2, append: true })

    const page = renderLogsPage()
    expect(infiniteOptions?.hasMore).toBe(false)
    await flush()

    getAgentConversations.mockImplementation((_agentId: string, options: { page?: number }) =>
      Promise.resolve(options.page === 2 ? pageTwo : pageOne)
    )
    const retry = find(page, (tree) => tree.type === 'button' && tree.props.children === 'retry')
    await (retry.props.onClick as () => Promise<void>)()

    expect(getAgentConversations).toHaveBeenLastCalledWith('agent-1', expect.objectContaining({ page: 2 }))
    expect((state[2] as Array<{ id: string }>).map((conversation) => conversation.id)).toEqual([
      'conversation-1',
      'conversation-2',
    ])
    expect(state[3]).toBe(2)
  })

  test('canceling the delete confirmation closes it without deleting', async () => {
    await renderLoadedPage()
    state[14] = 'conversation-1'
    const page = renderLogsPage()

    ;(find(page, (tree) => tree.type === 'alert-dialog').props.onOpenChange as (open: boolean) => void)(false)

    expect(state[14]).toBeNull()
    expect(deleteConversation).not.toHaveBeenCalled()
  })

  test('routes away when the agent request fails', async () => {
    getAgent.mockRejectedValueOnce(new Error('missing'))
    renderLogsPage()
    await flush()
    expect(push).toHaveBeenCalledWith('/app/apps')
  })

  test('renders conversation drawer token totals and converted messages', () => {
    const drawer = ConversationDrawer({
      open: true,
      onOpenChange,
      isLoading: false,
      conversation: {
        id: 'conversation-1',
        title: 'Install help',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        agent_id: 'agent-1',
        agent_name: 'Support Agent',
        agent_icon: 'Bot',
        variables: { plan: 'team' },
        messages: [
          { id: 'message-1', role: 'user', content: 'Hi', created_at: '2026-01-01T00:00:00Z', token_usage: { prompt: 3, completion: 2 } },
          { id: 'message-2', role: 'assistant', content: 'Hello', created_at: '2026-01-01T00:00:01Z', token_usage: { prompt: 1 } },
        ],
      },
    })

    const header = find(drawer, (tree) => tree.type === 'conversation-drawer-header')
    expect(header.props).toMatchObject({ title: 'Install help', totalTokens: 6, agentName: 'Support Agent' })
    expect(find(drawer, (tree) => tree.type === 'chat-message' && tree.props.message.id === 'message-1')).toBeDefined()
  })

  test('renders the drawer loading spinner without a conversation', () => {
    const drawer = ConversationDrawer({ open: true, onOpenChange, isLoading: true, conversation: null })

    expect(find(drawer, (tree) => tree.type === 'svg')).toBeDefined()
  })
})
