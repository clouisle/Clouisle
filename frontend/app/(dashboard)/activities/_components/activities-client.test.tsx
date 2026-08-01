import { beforeEach, expect, mock, test } from 'bun:test'

interface Node {
  type: unknown
  props: Record<string, unknown>
}

const jsx = (type: unknown, props: Record<string, unknown>): Node => ({ type, props })
const states: unknown[] = []
let stateIndex = 0
let effectRan = false

const useState = <T,>(initial: T | (() => T)) => {
  const index = stateIndex++
  if (states.length <= index) states[index] = typeof initial === 'function' ? (initial as () => T)() : initial
  return [states[index], (value: T | ((current: T) => T)) => {
    states[index] = typeof value === 'function'
      ? (value as (current: T) => T)(states[index] as T)
      : value
  }] as const
}

const useEffect = (effect: () => void) => {
  if (!effectRan) {
    effectRan = true
    effect()
  }
}

function Card() {}
function CardContent() {}
function CardHeader() {}
function CardTitle() {}
function Tabs() {}
function TabsContent() {}
function TabsList() {}
function TabsTrigger() {}
function ConversationsTable() {}
function WorkflowRunsTable() {}
function Activity() {}
function MessageSquare() {}
function Workflow() {}

let conversationResult: unknown
let workflowResult: unknown
const getStats = mock(async () => conversationResult)
const getWorkflowRunStats = mock(async () => workflowResult)

mock.module('react', () => ({ useState, useEffect }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
const routerReplace = mock(() => {})
const urlSearchParams = new URLSearchParams()
mock.module('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace }),
  usePathname: () => '/activities',
  useSearchParams: () => urlSearchParams,
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => `activities.${key}`,
}))
mock.module('lucide-react', () => ({ Activity, MessageSquare, Workflow }))
mock.module('@/components/ui/card', () => ({ Card, CardContent, CardHeader, CardTitle }))
mock.module('@/components/ui/tabs', () => ({ Tabs, TabsContent, TabsList, TabsTrigger }))
mock.module('@/lib/api/admin/conversations', () => ({ conversationsApi: { getStats } }))
mock.module('@/lib/api', () => ({ workflowsApi: { getWorkflowRunStats } }))
mock.module('./conversations-table', () => ({ ConversationsTable }))
mock.module('./workflow-runs-table', () => ({ WorkflowRunsTable }))

const { ActivitiesClient } = await import('./activities-client')

function render() {
  stateIndex = 0
  return ActivitiesClient() as Node
}

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (Array.isArray(value)) return value.map(text).join('')
  if (value === null || value === undefined || typeof value === 'boolean') return ''
  if (typeof value !== 'object') return String(value)
  return 'props' in value ? text((value as Node).props.children) : ''
}

async function settleStats() {
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
}

beforeEach(() => {
  states.length = 0
  stateIndex = 0
  effectRan = false
  getStats.mockClear()
  getWorkflowRunStats.mockClear()
  conversationResult = { total_conversations: 1234, active_users: 17 }
  workflowResult = { total_runs: 56 }
})

test('replaces loading placeholders with statistics from both APIs', async () => {
  const loadingCards = descendants(render()).filter((node) => node.type === CardContent)
  expect(loadingCards.map((node) => text(node))).toEqual(['...', '...', '...', '...'])

  await settleStats()

  const loadedCards = descendants(render()).filter((node) => node.type === CardContent)
  expect(loadedCards.map((node) => text(node))).toEqual(['1,234', '56', '0', '17'])
  expect(getStats).toHaveBeenCalledTimes(1)
  expect(getWorkflowRunStats).toHaveBeenCalledTimes(1)
})

test('falls back independently when either statistics request fails', async () => {
  getStats.mockRejectedValueOnce(new Error('conversation stats unavailable'))
  getWorkflowRunStats.mockRejectedValueOnce(new Error('workflow stats unavailable'))
  const originalError = console.error
  console.error = () => {}

  try {
    render()
    await settleStats()
  } finally {
    console.error = originalError
  }

  const cards = descendants(render()).filter((node) => node.type === CardContent)
  expect(cards.map((node) => text(node))).toEqual(['0', '0', '0', '0'])
})

test('exposes both activity tables and updates the controlled tab boundary', () => {
  let nodes = descendants(render())
  let tabs = nodes.find((node) => node.type === Tabs)!

  expect(tabs.props.value).toBe('conversations')
  expect(nodes.some((node) => node.type === ConversationsTable)).toBe(true)
  expect(nodes.some((node) => node.type === WorkflowRunsTable)).toBe(true)

  ;(tabs.props.onValueChange as (value: string) => void)('workflows')
  nodes = descendants(render())
  tabs = nodes.find((node) => node.type === Tabs)!
  expect(tabs.props.value).toBe('workflows')
})
