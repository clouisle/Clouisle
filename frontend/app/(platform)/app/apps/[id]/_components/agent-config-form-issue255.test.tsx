import { beforeEach, expect, mock, test } from 'bun:test'
import type { Agent } from '@/lib/api'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }
type Setter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Props = {}) => ({ type, props })
const states: unknown[] = []
const effects: Array<() => void> = []
let stateIndex = 0
let currentTeam: { id: string } | null = { id: 'team-1' }

function resolve(node: unknown): unknown {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const element = node as Node
  return typeof element.type === 'function'
    ? resolve((element.type as (props: Props) => unknown)(element.props))
    : element
}

function walk(node: unknown): Node[] {
  const resolved = resolve(node)
  if (Array.isArray(resolved)) return resolved.flatMap(walk)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const element = resolved as Node
  return [element, ...walk(element.props.children)]
}

function text(node: unknown): string {
  const resolved = resolve(node)
  if (typeof resolved === 'string' || typeof resolved === 'number') return String(resolved)
  if (Array.isArray(resolved)) return resolved.map(text).join('')
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return ''
  return text((resolved as Node).props.children)
}

function component(type: string) {
  return (props: Props) => jsx(type, props)
}

const getTeamModels = mock(async () => [
  { id: 'enabled-model', is_enabled: true, model: { name: 'Enabled model' } },
  { id: 'disabled-model', is_enabled: false, model: { name: 'Disabled model' } },
])
const getKnowledgeBases = mock(async () => ({
  items: [
    { id: 'kb-1', name: 'Team KB', description: 'Connected docs', document_count: 3, team: { id: 'team-1' } },
    { id: 'kb-2', name: 'Other KB', description: null, document_count: 4, team: { id: 'team-2' } },
  ],
}))

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useEffect: (effect: () => void) => effects.push(effect),
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T): [T, Setter<T>] => {
    const index = stateIndex++
    if (states[index] === undefined) states[index] = initial
    return [states[index] as T, (value) => {
      states[index] = typeof value === 'function'
        ? (value as (current: T) => T)(states[index] as T)
        : value
    }]
  },
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${values.count}` : key,
}))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({
  teamModelsApi: { getTeamModels },
  knowledgeBasesApi: { getKnowledgeBases },
}))
mock.module('@/components/ui/input', () => ({ Input: component('input') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: component('textarea') }))
mock.module('@/components/ui/label', () => ({ Label: component('label') }))
mock.module('@/components/ui/switch', () => ({ Switch: component('switch') }))
mock.module('@/components/ui/card', () => ({
  Card: component('card'),
  CardContent: component('card-content'),
  CardDescription: component('card-description'),
  CardHeader: component('card-header'),
  CardTitle: component('card-title'),
}))
mock.module('@/components/ui/tabs', () => ({
  Tabs: component('tabs'),
  TabsContent: component('tabs-content'),
  TabsList: component('tabs-list'),
  TabsTrigger: component('tabs-trigger'),
}))
mock.module('@/components/ui/select', () => ({
  Select: component('select'),
  SelectContent: component('select-content'),
  SelectEmpty: component('select-empty'),
  SelectItem: component('select-item'),
  SelectTrigger: component('select-trigger'),
  SelectValue: component('select-value'),
}))

const { AgentConfigForm } = await import('./agent-config-form')

const baseAgent = {
  id: 'agent-1',
  name: 'Original',
  description: 'Description',
  icon: 'bot',
  model_id: 'legacy-model',
  model: { name: 'Legacy model' },
  system_prompt: 'Be useful',
  opening_message: 'Hello',
  suggested_questions: ['First?'],
  visibility: 'private',
  enable_user_input_request: false,
  enable_memory: false,
  memory_config: null,
  knowledge_bases: [{ knowledge_base: { id: 'kb-1' } }],
} as unknown as Agent

function render(agent: Agent = baseAgent, reset = false) {
  if (reset) states.length = 0
  stateIndex = 0
  effects.length = 0
  return AgentConfigForm({ agent, onSubmit })
}

function findById(tree: unknown, id: string) {
  return walk(tree).find((node) => node.props.id === id)
}

function change(node: Node | undefined, value: string) {
  expect(node).toBeDefined()
  ;(node?.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
}

async function runEffect() {
  effects[0]?.()
  await Promise.resolve()
  await Promise.resolve()
}

const onSubmit = mock(async (data: Partial<Agent>) => data)

beforeEach(() => {
  currentTeam = { id: 'team-1' }
  onSubmit.mockClear()
  getTeamModels.mockClear()
  getKnowledgeBases.mockClear()
})

test('skips loading without a team and tolerates API failures', async () => {
  currentTeam = null
  render(baseAgent, true)
  await runEffect()
  expect(getTeamModels).not.toHaveBeenCalled()

  currentTeam = { id: 'team-1' }
  getTeamModels.mockImplementationOnce(async () => { throw new Error('offline') })
  render(baseAgent, true)
  await runEffect()

  expect(getTeamModels).toHaveBeenCalledWith('team-1', 'chat')
  expect(states[16]).toBe(false)
})

test('loads only enabled team data and renders model and knowledge-base branches', async () => {
  let tree = render(baseAgent, true)
  expect(text(tree)).toContain('Legacy model')
  expect(text(tree)).toContain('noKnowledgeBasesSelected')

  await runEffect()
  tree = render()

  expect(text(tree)).toContain('Enabled model')
  expect(text(tree)).not.toContain('Disabled model')
  expect(text(tree)).toContain('Team KBConnected docssettings.documents:3')
  expect(text(tree)).not.toContain('Other KB')
  expect(walk(tree).find((node) => node.props.value === 'kb-1')?.props.className).toBeUndefined()
})

test('applies field callbacks and submits the enabled-memory payload', async () => {
  let tree = render(baseAgent, true)
  change(findById(tree, 'name'), 'Updated')
  change(findById(tree, 'icon'), '')
  change(findById(tree, 'description'), '')
  change(findById(tree, 'openingMessage'), '')
  change(findById(tree, 'suggestedQuestions'), ' Keep? \n\nSecond?\n  ')
  change(findById(tree, 'poweredByText'), '  Acme Inc  ')
  change(findById(tree, 'systemPrompt'), '')
  ;(findById(tree, 'enableUserInputRequest')?.props.onCheckedChange as (value: boolean) => void)(true)
  ;(findById(tree, 'enableMemory')?.props.onCheckedChange as (value: boolean) => void)(true)

  tree = render()
  ;(findById(tree, 'maxMemoriesPerRetrieval')?.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '25' } })
  ;(findById(tree, 'autoExtract')?.props.onCheckedChange as (value: boolean) => void)(false)
  ;(walk(tree).find((node) => node.type === 'select' && node.props.value === 'private')?.props.onValueChange as (value: string) => void)('team')
  ;(walk(tree).find((node) => node.type === 'select' && node.props.value === 'legacy-model')?.props.onValueChange as (value: string) => void)('enabled-model')

  tree = render()
  await (tree.props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: mock(() => {}) })

  expect(onSubmit).toHaveBeenCalledWith({
    name: 'Updated',
    description: null,
    icon: null,
    model_id: 'enabled-model',
    system_prompt: null,
    opening_message: null,
    suggested_questions: [' Keep? ', 'Second?'],
    powered_by_text: 'Acme Inc',
    visibility: 'team',
    enable_user_input_request: true,
    enable_memory: true,
    memory_config: {
      max_memories_per_retrieval: 25,
      auto_extract: false,
      importance_threshold: 'medium',
    },
  })
})

test('uses memory defaults and submits null memory config while disabled', async () => {
  const agent = {
    ...baseAgent,
    model_id: null,
    model: null,
    enable_memory: true,
    memory_config: { max_memories_per_retrieval: 0, auto_extract: false, importance_threshold: 'high' },
  } as unknown as Agent
  let tree = render(agent, true)

  expect(findById(tree, 'maxMemoriesPerRetrieval')?.props.value).toBe(10)
  expect(findById(tree, 'autoExtract')?.props.checked).toBe(false)
  expect(text(tree)).toContain('selectModel')
  ;(findById(tree, 'enableMemory')?.props.onCheckedChange as (value: boolean) => void)(false)

  tree = render(agent)
  await (tree.props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: mock(() => {}) })

  expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({
    model_id: null,
    enable_memory: false,
    memory_config: null,
  })
})
