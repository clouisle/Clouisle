import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

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

let currentTeam: { id: string; role?: string } | null = { id: 'team-1', role: 'member' }
let isTeamLoading = false
let user: { is_superuser?: boolean } | null = { is_superuser: false }
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

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
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
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam, isLoading: isTeamLoading }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user, loading: permissionsLoading }) }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { getKnowledgeBases },
  teamModelsApi: { getTeamModels },
  agentsApi: { getAgents },
  workflowsApi: { getWorkflows },
}))
mock.module('@/lib/api/agents', () => ({ conversationsApi: { getTrends } }))
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
mock.module('@/components/ui/chart', () => ({
  ChartContainer: div,
  ChartTooltip: div,
  ChartTooltipContent: div,
}))
const chart = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>
mock.module('recharts', () => ({
  BarChart: chart,
  Bar: chart,
  XAxis: chart,
  YAxis: chart,
  CartesianGrid: chart,
  ComposedChart: chart,
  Area: chart,
  Line: chart,
  Cell: chart,
  ResponsiveContainer: chart,
  Tooltip: chart,
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

function text(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('p').map((node) => node.children.join(''))
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
  getKnowledgeBases.mockImplementation(() => Promise.resolve({ total: 2 }))
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
  expect(getAgents).toHaveBeenCalledWith({ pageSize: 8, teamId: 'team-1', ownOnly: true })
  expect(getTrends).toHaveBeenCalledWith('team-1', '7d')
  expect(text(renderer)).toEqual(expect.arrayContaining(['5', '10', '1.0K']))
  expect(text(renderer).some((item) => item.startsWith('75'))).toBe(true)
  expect(renderer.root.findAllByType('a').map((node) => node.props.href)).toEqual(expect.arrayContaining([
    '/app/apps?action=create&type=agent',
    '/app/apps?action=create&type=workflow',
    '/app/kb?action=create',
    '/app/capabilities?action=create',
    '/app/apps/agent-new',
    '/app/apps/workflow/workflow-1',
  ]))
  act(() => renderer.unmount())
})

test('loads admin usage by user and toggles legend visibility', async () => {
  currentTeam = { id: 'team-1', role: 'admin' }
  const renderer = await renderPage()

  expect(getKnowledgeBases).toHaveBeenCalledWith({ pageSize: 1, teamId: 'team-1', ownOnly: false })
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
