import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

function Bot() {}
function Wrench() {}
function Grid3x3() {}
function ArrowRight() {}
function Loader2() {}
function Plus() {}
function Workflow() {}
function Clock() {}
function Zap() {}
function Activity() {}
function TrendingUp() {}
function MessageSquare() {}
function CheckCircle2() {}
function Coins() {}
function UserIcon() {}
function Users() {}
let currentTeam: { id: string; role?: string } | null = { id: 'team-1', role: 'member' }
let isTeamLoading = false
let user: { is_superuser?: boolean; username?: string } | null = { is_superuser: false, username: 'Alice' }
let permissionsLoading = false

const getKnowledgeBases = mock(() => Promise.resolve({ total: 2 }))
const getTeamModels = mock(() => Promise.resolve([{ is_enabled: true }, { is_enabled: false }]))
const getAgents = mock(() => Promise.resolve({
  total: 2,
  items: [
    { id: 'agent-old', name: 'Old agent', icon: '🤖', updated_at: '2024-01-01T00:00:00Z', conversation_count: 2, message_count: 4 },
    { id: 'agent-new', name: 'New agent', avatar_url: '/avatar.png', updated_at: '2024-01-03T00:00:00Z', conversation_count: 3, message_count: 6 },
  ],
}))
const getWorkflows = mock(() => Promise.resolve({
  total: 1,
  items: [
    { id: 'workflow-1', name: 'Workflow', icon: '⚙️', updated_at: '2024-01-02T00:00:00Z', run_count: 4, success_count: 3 },
  ],
}))
const getTrends = mock(() => Promise.resolve({
  data: [
    {
      date: '2024-01-01',
      conversations: 5,
      messages: 7,
      tokens: 1000,
      users: {
        user_1: { name: 'Alice', conversations: 2, tokens: 300 },
        user_2: { name: 'Bob', conversations: 3, tokens: 700 },
      },
    },
  ],
}))
const getStats = mock(() => Promise.resolve({ total_conversations: 5, total_messages: 10 }))
const getWorkflowRunStats = mock(() => Promise.resolve({ total_runs: 4, runs_by_status: { completed: 3 } }))
mock.module('next-intl', () => ({ useLocale: () => 'en', useTranslations: () => (key: string) => key }))
mock.module('next/link', () => ({
  default: ({ href, children }: React.PropsWithChildren<{ href: string }>) => <a href={href}>{children}</a>,
}))
mock.module('lucide-react', () => ({
  Bot,
  Wrench,
  Grid3x3,
  ArrowRight,
  Loader2,
  Plus,
  Workflow,
  Clock,
  Zap,
  Activity,
  TrendingUp,
  MessageSquare,
  CheckCircle2,
  Coins,
  User: UserIcon,
  Users,
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam, isLoading: isTeamLoading }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user, loading: permissionsLoading }) }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { getKnowledgeBases },
  teamModelsApi: { getTeamModels },
  agentsApi: { getAgents },
  workflowsApi: { getWorkflows, getWorkflowRunStats },
}))
mock.module('@/lib/api/agents', () => ({ conversationsApi: { getTrends, getStats } }))
mock.module('@/lib/chart-theme', () => ({
  CHART_AXIS_COLOR: '#aaa',
  CHART_COLOR_ORDER: ['#1', '#2', '#3', '#4', '#5', '#6'],
  CHART_GRID_COLOR: '#ddd',
  CHART_HOVER_CURSOR: false,
}))

const div = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('@/components/ui/card', () => ({ Card: div, CardContent: div, CardDescription: div, CardHeader: div, CardTitle: div }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: div }))
mock.module('@/components/ui/badge', () => ({ Badge: div }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, value, onValueChange, ...props }: React.PropsWithChildren<{ value?: string; onValueChange?: (v: string) => void; [key: string]: unknown }>) => (
    <div data-testid="tabs" data-value={value} {...props}>
      {children}
      <button data-testid="scope-team-trigger" onClick={() => onValueChange?.('team')}>team</button>
      <button data-testid="scope-personal-trigger" onClick={() => onValueChange?.('personal')}>personal</button>
    </div>
  ),
  TabsList: div,
  TabsTrigger: ({ children, value, ...props }: React.PropsWithChildren<{ value?: string; [key: string]: unknown }>) => (
    <div data-value={value} {...props}>{children}</div>
  ),
}))
mock.module('@/components/ui/chart', () => ({
  ChartContainer: div,
  ChartTooltip: div,
  ChartTooltipContent: div,
}))
let usageTooltipProps: { active?: boolean; payload?: Array<{ name: string; value: number | string; color: string }>; label?: string } = {
  active: false,
  payload: [],
  label: undefined,
}
const chart = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
const tooltip = ({ content, ...props }: { content?: React.ReactElement } & Record<string, unknown>) => (
  <div {...props}>
    {content && React.isValidElement(content) ? React.cloneElement(content, usageTooltipProps) : content}
  </div>
)
mock.module('recharts', () => ({
  BarChart: chart,
  Bar: chart,
  PieChart: chart,
  Pie: chart,
  XAxis: chart,
  YAxis: chart,
  CartesianGrid: chart,
  ComposedChart: chart,
  Area: chart,
  Line: chart,
  Cell: chart,
  ResponsiveContainer: chart,
  Tooltip: tooltip,
  Legend: ({ onClick, ...props }: Record<string, unknown>) => <button data-testid="legend" onClick={() => (onClick as (entry: { dataKey: string }) => void)?.({ dataKey: 'user_1:conversations' })} {...props} />,
}))
mock.module('./_components/no-team-state', () => ({ NoTeamState: () => <div data-testid="no-team" /> }))

const { default: PlatformHomePage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
Object.defineProperty(globalThis, 'window', {
  value: {
    matchMedia: () => ({ matches: true }),
    requestAnimationFrame: (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0),
    cancelAnimationFrame: (id: number) => clearTimeout(id),
  },
  writable: true,
})

async function renderPage() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<PlatformHomePage />)
    await Promise.resolve()
  })
  return renderer!
}

function series(renderer: ReactTestRenderer, dataKey: string, hide: boolean) {
  return renderer.root.findAll((node) => node.type !== 'div' && node.props.dataKey === dataKey && node.props.hide === hide)
}

afterEach(() => {
  mock.clearAllMocks()
  currentTeam = { id: 'team-1', role: 'member' }
  isTeamLoading = false
  user = { is_superuser: false }
  permissionsLoading = false
  usageTooltipProps = { active: false, payload: [], label: undefined }
})

test('waits for team loading and shows the no-team state without API calls', async () => {
  isTeamLoading = true
  currentTeam = null
  let renderer = await renderPage()

  expect(renderer.root.findAllByProps({ 'data-testid': 'no-team' })).toHaveLength(0)
  expect(getAgents).not.toHaveBeenCalled()
  act(() => renderer.unmount())

  isTeamLoading = false
  renderer = await renderPage()

  expect(renderer.root.findByProps({ 'data-testid': 'no-team' })).toBeDefined()
  expect(getAgents).not.toHaveBeenCalled()
  act(() => renderer.unmount())
})

test('loads member stats, trends, recent items, and quick action links', async () => {
  const renderer = await renderPage()

  expect(getKnowledgeBases).toHaveBeenCalledWith({ pageSize: 1, teamId: 'team-1', ownOnly: true })
  expect(getAgents).toHaveBeenCalledWith({ pageSize: 5, teamId: 'team-1', ownOnly: true })
  expect(getTrends).toHaveBeenCalledWith('team-1', '7d', true)
  expect(getWorkflowRunStats).toHaveBeenCalledWith('team-1', '7d', true)
  expect(renderer.root.findAllByProps({ 'data-testid': 'platform-home-scope-tabs' })).toHaveLength(0)
  expect(renderer.root.findByType('h1').children.join('')).toContain('greeting')
  expect(renderer.root.findAllByType('a').map((node) => node.props.href)).toEqual(expect.arrayContaining([
    '/app/apps?action=create&type=agent',
    '/app/apps?action=create&type=workflow',
    '/app/kb?action=create',
    '/app/apps/agent-new',
    '/app/apps/workflow/workflow-1',
  ]))
  act(() => renderer.unmount())
})
test('formats numeric and textual usage tooltip values', async () => {
  usageTooltipProps = {
    active: true,
    label: '2024-01-01',
    payload: [
      { name: 'Conversations', value: 1500000, color: '#1' },
      { name: 'Tokens', value: 2500, color: '#2' },
      { name: 'Status', value: 'n/a', color: '#3' },
    ],
  }
  const renderer = await renderPage()
  const output = JSON.stringify(renderer.toJSON())

  expect(output).toContain('2024-01-01')
  expect(output).toContain('1.5M')
  expect(output).toContain('2.5K')
  expect(output).toContain('n/a')
  act(() => renderer.unmount())
})
test('falls back to workflow totals when period stats are unavailable', async () => {
  getWorkflowRunStats.mockResolvedValueOnce({ total_runs: 0, runs_by_status: {} })
  const renderer = await renderPage()
  const output = JSON.stringify(renderer.toJSON())

  expect(output).toContain('"75"')
  act(() => renderer.unmount())
})
test('defaults admin to personal scope and switches to team overview', async () => {
  currentTeam = { id: 'team-1', role: 'admin' }
  const renderer = await renderPage()

  // Defaults to personal scope
  expect(getKnowledgeBases).toHaveBeenCalledWith({ pageSize: 1, teamId: 'team-1', ownOnly: true })
  expect(getTrends).toHaveBeenCalledWith('team-1', '7d', true)
  expect(renderer.root.findByProps({ 'data-testid': 'platform-home-scope-tabs' })).toBeDefined()

  // Switch to team scope
  await act(async () => {
    renderer.root.findByProps({ 'data-testid': 'scope-team-trigger' }).props.onClick()
    await Promise.resolve()
  })

  expect(getKnowledgeBases).toHaveBeenLastCalledWith({ pageSize: 1, teamId: 'team-1', ownOnly: false })
  expect(getTrends).toHaveBeenLastCalledWith('team-1', '7d', false)
  expect(series(renderer, 'user_1:conversations', false)).toHaveLength(1)
  expect(series(renderer, 'user_1:tokens', false)).toHaveLength(1)

  act(() => renderer.root.findByProps({ 'data-testid': 'legend' }).props.onClick())

  expect(series(renderer, 'user_1:conversations', true)).toHaveLength(1)
  expect(series(renderer, 'user_1:tokens', true)).toHaveLength(1)
  act(() => renderer.unmount())
})
test('cleans up loading state after API failure', async () => {
  const consoleError = console.error
  console.error = mock(() => {}) as never
  getKnowledgeBases.mockImplementationOnce(() => Promise.reject(new Error('boom')))

  const renderer = await renderPage()
  console.error = consoleError

  expect(getAgents).toHaveBeenCalled()
  expect(renderer.root.findAllByType('p').map((node) => node.children.join(''))).toContain('noRecentItems')
  act(() => renderer.unmount())
})
