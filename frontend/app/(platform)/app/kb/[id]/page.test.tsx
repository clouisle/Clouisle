import { beforeEach, expect, mock, test } from 'bun:test'

interface Node {
  type: unknown
  props: Record<string, unknown>
}

type Setter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Record<string, unknown> = {}): Node => ({ type, props })
const states: unknown[] = []
const effects: Array<() => void> = []
let stateIndex = 0

const useState = <T,>(initial: T): [T, Setter<T>] => {
  const index = stateIndex++
  if (!(index in states)) states[index] = initial
  return [states[index] as T, (value) => {
    states[index] = typeof value === 'function'
      ? (value as (current: T) => T)(states[index] as T)
      : value
  }]
}

const push = mock(() => undefined)
const getKnowledgeBase = mock(async () => knowledgeBase)
const getStats = mock(async () => stats)

let currentTeam: Record<string, unknown> | null
let user: Record<string, unknown> | null
let knowledgeBase: Record<string, unknown>
let stats: Record<string, unknown>

function component(name: string) {
  return function Component() {
    return name
  }
}

const Button = component('Button')
const Card = component('Card')
const CardContent = component('CardContent')
const CardDescription = component('CardDescription')
const CardHeader = component('CardHeader')
const CardTitle = component('CardTitle')
const Badge = component('Badge')
const DocumentsTable = component('DocumentsTable')
const UploadDocumentDialog = component('UploadDocumentDialog')
const ImportUrlDialog = component('ImportUrlDialog')
const KnowledgeBaseDialog = component('KnowledgeBaseDialog')

mock.module('react', () => ({
  use: () => ({ id: 'kb-1' }),
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void) => effects.push(effect),
  useState,
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user }) }))
mock.module('@/lib/api', () => ({ knowledgeBasesApi: { getKnowledgeBase, getStats } }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/card', () => ({ Card, CardContent, CardDescription, CardHeader, CardTitle }))
mock.module('@/components/ui/badge', () => ({ Badge }))
mock.module('./_components', () => ({ DocumentsTable, UploadDocumentDialog, ImportUrlDialog }))
mock.module('../_components/kb-dialog', () => ({ KnowledgeBaseDialog }))
mock.module('lucide-react', () => ({
  ArrowLeft: component('ArrowLeft'),
  Upload: component('Upload'),
  Link: component('Link'),
  Settings: component('Settings'),
  FileText: component('FileText'),
  Layers: component('Layers'),
  HardDrive: component('HardDrive'),
  Clock: component('Clock'),
  CheckCircle: component('CheckCircle'),
  XCircle: component('XCircle'),
  Loader2: component('Loader2'),
  Search: component('Search'),
  Cpu: component('Cpu'),
  ArrowUpDown: component('ArrowUpDown'),
}))

const { default: KnowledgeBaseDetailPage } = await import('./page')

function render() {
  stateIndex = 0
  effects.length = 0
  return KnowledgeBaseDetailPage({ params: Promise.resolve({ id: 'kb-1' }) }) as Node
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

async function load() {
  render()
  effects[0]?.()
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()
  return render()
}

beforeEach(() => {
  states.length = 0
  effects.length = 0
  stateIndex = 0
  push.mockClear()
  getKnowledgeBase.mockClear()
  getStats.mockClear()
  currentTeam = { id: 'team-1', role: 'member' }
  user = { id: 'user-1', is_superuser: false }
  knowledgeBase = {
    id: 'kb-1',
    name: 'Engineering',
    description: 'Internal docs',
    status: 'active',
    team: { id: 'team-1' },
    created_by: { id: 'user-1' },
    embedding_model: { name: 'embed-v3', provider: 'OpenAI' },
    rerank_model: { name: 'rerank-v2', provider: 'Cohere' },
  }
  stats = {
    document_count: 7,
    total_chunks: 1234,
    total_tokens: 5678,
    documents_by_status: { completed: 4, processing: 1, pending: 2, error: 3 },
  }
})

test('loads details, statistics, model metadata, and owner actions', async () => {
  const loadingNodes = descendants(render())
  expect(loadingNodes.some((node) => node.props['data-testid'] === 'kb-detail-page')).toBe(true)
  expect(loadingNodes.some((node) => text(node) === 'Engineering')).toBe(false)

  let tree = await load()
  let nodes = descendants(tree)

  expect(text(tree)).toContain('Engineering')
  expect(text(tree)).toContain('Internal docs')
  expect(text(tree)).toContain('1,234')
  expect(text(tree)).toContain('5,678')
  expect(text(tree)).toContain('embed-v3')
  expect(text(tree)).toContain('rerank-v2')
  expect(getKnowledgeBase).toHaveBeenCalledWith('kb-1')
  expect(getStats).toHaveBeenCalledWith('kb-1')
  expect(nodes.some((node) => node.props['data-testid'] === 'kb-detail-page')).toBe(true)
  expect(nodes.some((node) => node.props['data-testid'] === 'kb-search-test-button')).toBe(true)
  expect(nodes.some((node) => node.props['data-testid'] === 'kb-import-url-button')).toBe(true)
  expect(nodes.some((node) => node.props['data-testid'] === 'kb-upload-button')).toBe(true)

  const buttons = nodes.filter((node) => node.type === Button)
  expect(buttons).toHaveLength(5)
  ;(buttons[0].props.onClick as () => void)()
  ;(buttons[1].props.onClick as () => void)()
  ;(buttons[2].props.onClick as () => void)()
  ;(buttons[3].props.onClick as () => void)()
  ;(buttons[4].props.onClick as () => void)()

  expect(push).toHaveBeenNthCalledWith(1, '/app/kb')
  expect(push).toHaveBeenNthCalledWith(2, '/app/kb/kb-1/search')

  tree = render()
  nodes = descendants(tree)
  expect(nodes.find((node) => node.type === ImportUrlDialog)?.props.open).toBe(true)
  expect(nodes.find((node) => node.type === UploadDocumentDialog)?.props.open).toBe(true)
  expect(nodes.find((node) => node.type === KnowledgeBaseDialog)?.props.open).toBe(true)
})

test('hides update actions from non-owner members and silently refreshes documents', async () => {
  user = { id: 'viewer', is_superuser: false }
  knowledgeBase = { ...knowledgeBase, status: 'archived', created_by: { id: 'owner' } }

  let tree = await load()
  let nodes = descendants(tree)
  expect(nodes.filter((node) => node.type === Button)).toHaveLength(2)
  expect(text(tree)).toContain('archived')

  const table = nodes.find((node) => node.type === DocumentsTable)!
  ;(table.props.onRefresh as () => void)()
  await Promise.resolve()
  await Promise.resolve()
  await Promise.resolve()

  tree = render()
  nodes = descendants(tree)
  expect(nodes.find((node) => node.type === DocumentsTable)?.props.refreshTrigger).toBe(1)
  expect(getKnowledgeBase).toHaveBeenCalledTimes(2)
  expect(getStats).toHaveBeenCalledTimes(2)
})

test('redirects when the knowledge base belongs to another team or loading fails', async () => {
  knowledgeBase = { ...knowledgeBase, team: { id: 'team-2' } }
  await load()
  expect(push).toHaveBeenCalledWith('/app/kb')

  states.length = 0
  push.mockClear()
  getKnowledgeBase.mockRejectedValueOnce(new Error('not found'))
  await load()
  expect(push).toHaveBeenCalledWith('/app/kb')
})
