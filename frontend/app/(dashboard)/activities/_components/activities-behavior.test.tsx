import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

import { ActivitiesClient } from './activities-client'
import { ConversationsTable } from './conversations-table'
import { ConversationDrawer } from './conversation-drawer'
import { WorkflowRunDrawer } from './workflow-run-drawer'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const getStats = mock(() => Promise.resolve({ total_conversations: 12, active_users: 3 }))
const getWorkflowRunStats = mock(() => Promise.resolve({ total_runs: 7 }))
const listAll = mock(() => Promise.resolve({ items: [], total: 0 }))
const getDetail = mock(() => Promise.resolve(null))
const getTeams = mock(() => Promise.resolve({ items: [] }))
const getAgents = mock(() => Promise.resolve({ items: [] }))
const getUsers = mock(() => Promise.resolve({ items: [] }))
const getWorkflowRun = mock(() => Promise.resolve(null))
const getRunNodeExecutions = mock(() => Promise.resolve([]))
const deleteWorkflowRun = mock(() => Promise.resolve())
const onDelete = mock(() => {})
const onOpenChange = mock(() => {})

const routerReplace = mock(() => {})
const urlSearchParams = new URLSearchParams()
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace }),
  usePathname: () => '/activities',
  useSearchParams: () => urlSearchParams,
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join('/')}` : key,
}))
mock.module('@/lib/api/admin/conversations', () => ({ conversationsApi: { getStats, listAll, getDetail } }))
mock.module('@/lib/api', () => ({
  workflowsApi: { getWorkflowRunStats, getWorkflowRun, getRunNodeExecutions, deleteWorkflowRun },
  agentsApi: { getAgents },
}))
mock.module('@/lib/api/admin/teams', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/api/admin/users', () => ({ usersApi: { getUsers } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => true }) }))
mock.module('@/hooks/use-url-search-state', () => ({ useUrlSearchState: () => React.useState('') }))
mock.module('@/hooks/use-debounce', () => ({ useDebounce: (value: string) => value }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}) } }))
mock.module('@/components/chat', () => ({ Message: ({ message }: { message: { id: string } }) => <div>{message.id}</div> }))
mock.module('@/components/chat/conversation-drawer-header', () => ({
  ConversationDrawerHeader: ({ title, totalTokens, action }: { title: string; totalTokens: number; action: React.ReactNode }) => <header>{title}:{totalTokens}{action}</header>,
}))
mock.module('@/lib/utils/message-converter', () => ({ convertBackendMessages: (messages: Array<{ id: string }>) => messages }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
  TabsContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
mock.module('./workflow-runs-table', () => ({ WorkflowRunsTable: () => <div>workflow-table</div> }))
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: (props: { onCheckedChange?: () => void }) => <input type="checkbox" onChange={props.onCheckedChange} /> }))
mock.module('@/components/ui/select', () => ({ Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>, SelectValue: () => null }))
mock.module('@/components/ui/table', () => ({ Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>, TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>, TableCell: ({ children, ...props }: React.ComponentProps<'td'>) => <td {...props}>{children}</td>, TableHead: ({ children }: { children: React.ReactNode }) => <th>{children}</th>, TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>, TableRow: ({ children, ...props }: React.ComponentProps<'tr'>) => <tr {...props}>{children}</tr> }))
mock.module('@/components/ui/alert-dialog', () => ({ AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertDialogAction: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>, AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>, AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, DropdownMenuItem: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>, DropdownMenuTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</> }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: () => null }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>, TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>, TooltipTrigger: ({ render }: { render: React.ReactNode }) => <>{render}</> }))
mock.module('@/components/ui/sheet', () => ({ Sheet: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, SheetContent: ({ children }: { children: React.ReactNode }) => <section>{children}</section>, SheetHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>, SheetTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>, SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/alert', () => ({ Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>, AlertTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('@/components/ui/separator', () => ({ Separator: () => <hr /> }))

const renderers: ReactTestRenderer[] = []
function render(element: React.ReactElement) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(element) })
  renderers.push(renderer!)
  return renderer!
}

async function flush() { await act(async () => { await Promise.resolve(); await Promise.resolve() }) }

beforeEach(() => {
  for (const fn of [getStats, getWorkflowRunStats, listAll, getDetail, getTeams, getAgents, getUsers, getWorkflowRun, getRunNodeExecutions, deleteWorkflowRun, onDelete, onOpenChange]) fn.mockClear()
  getStats.mockResolvedValue({ total_conversations: 12, active_users: 3 })
  getWorkflowRunStats.mockResolvedValue({ total_runs: 7 })
  listAll.mockResolvedValue({ items: [], total: 0 })
  getDetail.mockResolvedValue(null)
  getTeams.mockResolvedValue({ items: [] }); getAgents.mockResolvedValue({ items: [] }); getUsers.mockResolvedValue({ items: [] })
  getWorkflowRun.mockResolvedValue(null); getRunNodeExecutions.mockResolvedValue([]); deleteWorkflowRun.mockResolvedValue()
})
afterEach(() => { for (const renderer of renderers.splice(0)) act(() => renderer.unmount()) })

describe('dashboard activity behavior', () => {
  test('loads activity statistics with independent fallbacks and renders both listings', async () => {
    getStats.mockRejectedValueOnce(new Error('unavailable'))
    const renderer = render(<ActivitiesClient />)
    expect(JSON.stringify(renderer.toJSON())).toContain('...')
    await flush()
    const output = JSON.stringify(renderer.toJSON())
    expect(output).toContain('0')
    expect(output).toContain('7')
    expect(output).toContain('workflow-table')
  })

  test('lists conversations, opens details, and recovers from an empty failed reload', async () => {
    const conversation = { id: 'c1', title: 'Incident review', agent_name: 'Agent', user_name: 'User', message_count: 2, updated_at: '2026-01-01T00:00:00Z' }
    listAll.mockResolvedValueOnce({ items: [conversation], total: 1 }).mockRejectedValueOnce(new Error('failed')).mockResolvedValueOnce({ items: [], total: 0 })
    getDetail.mockResolvedValue({ ...conversation, messages: [], variables: {}, created_at: '2026-01-01T00:00:00Z', agent_icon: null })
    const renderer = render(<ConversationsTable />)
    await flush()
    expect(JSON.stringify(renderer.toJSON())).toContain('Incident review')
    const row = renderer.root.findAllByType('tr').find((node) => node.findAllByType('span').some((span) => span.children.includes('Incident review')))!
    await act(async () => row.props.onClick())
    expect(getDetail).toHaveBeenCalledWith('c1')
    expect(JSON.stringify(renderer.toJSON())).toContain('Incident review')
    const input = renderer.root.findAllByType('input').find((node) => node.props.placeholder === 'searchPlaceholder')!
    await act(async () => input.props.onChange({ target: { value: 'retry' } }))
    await flush()
    expect(listAll).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(renderer.toJSON())).toContain('Incident review')
    await act(async () => input.props.onChange({ target: { value: 'recovered' } }))
    await flush()
    expect(listAll).toHaveBeenCalledTimes(3)
    expect(JSON.stringify(renderer.toJSON())).toContain('noConversations')
  })

  test('renders conversation loading, messages, token total, and permitted deletion', () => {
    const loading = render(<ConversationDrawer conversation={null} isLoading open onOpenChange={onOpenChange} />)
    expect(JSON.stringify(loading.toJSON())).toContain('animate-spin')
    const renderer = render(<ConversationDrawer conversation={{ id: 'c1', title: 'Thread', created_at: '2026-01-01', messages: [{ id: 'm1', token_usage: { prompt: 2, completion: 3 } }], variables: {}, agent_name: 'A', agent_icon: null, user_name: 'U' } as never} isLoading={false} open onOpenChange={onOpenChange} onDelete={onDelete} />)
    expect(renderer.root.findByType('header').children.slice(0, 3)).toEqual(['Thread', ':', '5'])
    act(() => renderer.root.findByProps({ 'aria-label': 'delete' }).props.onClick())
    expect(onDelete).toHaveBeenCalledWith('c1')
  })

  test('loads workflow details after an error retry and deletes the opened run', async () => {
    getWorkflowRun.mockRejectedValueOnce(new Error('failed')).mockResolvedValueOnce({ id: 'run-1', status: 'success', trigger_type: 'manual', created_at: '2026-01-01T00:00:00Z', started_at: null, finished_at: null, total_duration_ms: 65000, is_debug: false, executed_nodes: 1, total_nodes: 1, failed_nodes: 0, total_token_usage: {}, inputs: { question: 'hi' }, outputs: null })
    getRunNodeExecutions.mockResolvedValue([])
    const renderer = render(<WorkflowRunDrawer runId="run-1" open onOpenChange={onOpenChange} onDelete={onDelete} />)
    await flush()
    expect(JSON.stringify(renderer.toJSON())).toContain('animate-spin')
    await act(async () => renderer.update(<WorkflowRunDrawer runId="run-1" open={false} onOpenChange={onOpenChange} onDelete={onDelete} />))
    await act(async () => renderer.update(<WorkflowRunDrawer runId="run-1" open onOpenChange={onOpenChange} onDelete={onDelete} />))
    await flush()
    expect(JSON.stringify(renderer.toJSON())).toContain('1m 5s')
    const deleteButton = renderer.root.findAllByType('button').find((node) => node.children.includes('runDetail.deleteRun'))!
    act(() => deleteButton.props.onClick())
    const confirm = renderer.root.findAllByType('button').find((node) => node.children.includes('delete'))!
    await act(async () => confirm.props.onClick())
    expect(deleteWorkflowRun).toHaveBeenCalledWith('run-1')
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
