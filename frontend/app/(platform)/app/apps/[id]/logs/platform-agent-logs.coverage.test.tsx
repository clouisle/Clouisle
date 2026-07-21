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

const Fragment = Symbol('Fragment')
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ Fragment, jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ Fragment, jsxDEV: jsx }))
mock.module('react', () => ({
  useCallback: <T extends (...args: never[]) => unknown>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => { effect() },
  useMemo: <T,>(factory: () => T) => factory(),
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
  ChevronLeft: element('svg'),
  ChevronRight: element('svg'),
  ChevronsLeft: element('svg'),
  ChevronsRight: element('svg'),
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
})

describe('platform agent logs page', () => {
  test('imports and renders the loading shell while requesting the agent', () => {
    const page = renderLogsPage()

    expect(getAgent).toHaveBeenCalledWith('agent-1')
    expect(find(page, (tree) => tree.type === 'skeleton')).toBeDefined()
  })

  test('loads conversations, opens a detail, and paginates', async () => {
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

    let page = await renderLoadedPage()
    expect(getAgentConversations).toHaveBeenCalledWith('agent-1', {
      page: 1,
      pageSize: 20,
      search: undefined,
      createdAfter: undefined,
      sortBy: 'created_at',
    })
    expect(find(page, (tree) => tree.type === 'td' && tree.props.children === 3)).toBeDefined()

    await (find(page, (tree) => tree.type === 'tr' && tree.props.onClick).props.onClick as () => Promise<void>)()
    expect(getConversation).toHaveBeenCalledWith('conversation-1')

    page = renderLogsPage()
    const next = find(page, (tree) => tree.type === 'button' && tree.props['aria-label'] === 'next')
    await (next.props.onClick as () => Promise<void>)()
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
