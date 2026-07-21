import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const EmptyState = function EmptyState() {}
const GraphToolbar = function GraphToolbar() {}
const GraphFilters = function GraphFilters() {}
const EntityDetailSheet = function EntityDetailSheet() {}
const getGraph = mock(async () => ({ entities: [] as Props[], relations: [] as Props[] }))
const deleteEntity = mock(async () => undefined)
const success = mock(() => {})
const error = mock(() => {})
const consoleError = mock(() => {})
let states: unknown[] = []
let stateIndex = 0
let effects: (() => void | Promise<void>)[] = []

mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (states.length <= index) states[index] = initial
    return [states[index] as T, (value: T | ((previous: T) => T)) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(states[index] as T)
        : value
    }] as const
  },
  useRef: <T,>(initial: T) => ({ current: initial }),
  useMemo: <T,>(factory: () => T) => factory(),
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => Object.assign(
    (key: string) => `${namespace}.${key}`,
    { has: (key: string) => key !== 'relationTypes.unknown' },
  ),
}))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('d3-force', () => ({}))
mock.module('d3-selection', () => ({ select: mock(() => ({})) }))
mock.module('d3-zoom', () => ({ zoom: mock(), zoomIdentity: {}, zoomTransform: mock() }))
mock.module('d3-drag', () => ({ drag: mock() }))
mock.module('@/lib/api/memories', () => ({ memoriesApi: { getGraph, deleteEntity } }))
mock.module('./empty-state', () => ({ EmptyState }))
mock.module('./graph-toolbar', () => ({ GraphToolbar }))
mock.module('./graph-filters', () => ({ GraphFilters }))
mock.module('./entity-detail-sheet', () => ({ EntityDetailSheet }))

const { MemoryGraphCanvas } = await import('./memory-graph-canvas')

function render() {
  stateIndex = 0
  effects = []
  return MemoryGraphCanvas() as Node
}

const entity = (id: string, name: string, type = 'person') => ({
  id, name, entity_type: type, description: `${name} description`, properties: {},
  user_id: 'user-1', access_count: 0, created_at: '', updated_at: '',
})
const relation = {
  id: 'relation-1', user_id: 'user-1', source_entity_id: 'entity-1',
  target_entity_id: 'entity-2', relation_type: 'knows', properties: {},
  created_at: '', updated_at: '',
}

beforeEach(() => {
  states = []
  effects = []
  getGraph.mockReset()
  getGraph.mockResolvedValue({ entities: [], relations: [] })
  deleteEntity.mockClear()
  success.mockClear()
  error.mockClear()
  console.error = consoleError
  consoleError.mockClear()
})

test('loads the graph and exposes filtered data to the toolbar and detail sheet', async () => {
  getGraph.mockResolvedValue({
    entities: [entity('entity-1', 'Alice'), entity('entity-2', 'Project', 'project')],
    relations: [relation],
  } as never)

  expect(JSON.stringify(render())).toContain('common.loading')
  await effects[2]()
  render()
  effects[1]()
  const tree = render()
  const children = tree.props.children as Node[]
  const toolbar = (children[1].props.children as Node)
  const filters = (children[2].props.children as Node)
  const detail = children[3]

  expect(getGraph).toHaveBeenCalledTimes(1)
  expect(toolbar.type).toBe(GraphToolbar)
  expect(toolbar.props.entityCount).toBe(2)
  expect(toolbar.props.relationCount).toBe(1)
  expect(filters.type).toBe(GraphFilters)
  expect(filters.props.availableEntityTypes).toEqual(['person', 'project'])
  expect(filters.props.availableRelationTypes).toEqual(['knows'])
  expect(detail.type).toBe(EntityDetailSheet)
  expect(detail.props.entities).toHaveLength(2)
})

test('shows the empty boundary and reports a recoverable load failure', async () => {
  getGraph.mockRejectedValue(new Error('temporary failure'))
  render()
  await effects[2]()
  const tree = render()

  expect(tree.type).toBe(EmptyState)
  expect(error).toHaveBeenCalledWith('memories.fetchError')
})

test('filters visible counts and handles selection deletion callbacks', async () => {
  states = [
    [entity('entity-1', 'Alice'), entity('entity-2', 'Project', 'project')],
    [relation], null, new Set(['entity-1']), true, 'alice', ['person'], ['knows'], false, true,
  ]
  const tree = render()
  const children = tree.props.children as Node[]
  const toolbar = children[1].props.children as Node
  const detail = children[3]

  expect(toolbar.props.entityCount).toBe(1)
  expect(toolbar.props.relationCount).toBe(0)
  ;(toolbar.props.onToggleSelectMode as () => void)()
  expect(states[3]).toEqual(new Set())

  states[3] = new Set(['entity-1'])
  await (toolbar.props.onDeleteSelected as () => Promise<void>)()
  expect(deleteEntity).toHaveBeenCalledWith('entity-1')
  expect(success).toHaveBeenCalledWith('memories.deleteEntitySuccess')
  expect(states[0]).toEqual([expect.objectContaining({ id: 'entity-2' })])
  expect(states[1]).toEqual([])

  ;(detail.props.onNavigateToEntity as (id: string) => void)('entity-2')
  expect(states[2]).toEqual(expect.objectContaining({ id: 'entity-2' }))
  ;(detail.props.onDeleteRelation as (id: string) => void)('relation-1')
  expect(states[1]).toEqual([])
  ;(detail.props.onClose as () => void)()
  expect(states[2]).toBeNull()

  ;(detail.props.onDeleteEntity as (id: string) => void)('entity-2')
  expect(states[0]).toEqual([])
})

test('keeps selected entities when bulk deletion is rejected', async () => {
  states = [
    [entity('entity-1', 'Alice')], [], null, new Set(['entity-1']), true,
    '', ['person'], [], false, true,
  ]
  deleteEntity.mockRejectedValueOnce(new Error('delete failed'))
  const tree = render()
  const toolbar = ((tree.props.children as Node[])[1].props.children as Node)

  await (toolbar.props.onDeleteSelected as () => Promise<void>)()

  expect(states[0]).toEqual([expect.objectContaining({ id: 'entity-1' })])
  expect(states[3]).toEqual(new Set(['entity-1']))
  expect(success).not.toHaveBeenCalled()
})
