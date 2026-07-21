import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
function component() {
  return function Component() {}
}

let stateValues: unknown[] = []
let refValues: Array<{ current: unknown }> = []
let stateIndex = 0
let refIndex = 0
const effects: Array<() => void | Promise<void>> = []
const getGraph = mock(() => Promise.resolve(graphData))
const deleteEntity = mock(() => Promise.resolve({}))
const toastError = mock(() => {})
const toastSuccess = mock(() => {})

const GraphToolbar = component()
const GraphFilters = component()
const EntityDetailSheet = component()
const EmptyState = component()
const listeners = new Map<string, (event: Event) => void>()

Object.assign(globalThis, {
  window: {
    addEventListener: (type: string, listener: (event: Event) => void) => listeners.set(type, listener),
    removeEventListener: (type: string) => listeners.delete(type),
    dispatchEvent: (event: Event) => listeners.get(event.type)?.(event),
  },
  KeyboardEvent: class KeyboardEvent extends Event {
    key: string
    constructor(type: string, init: { key: string }) {
      super(type)
      this.key = init.key
    }
  },
})

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
  useMemo: <T,>(factory: () => T) => factory(),
  useRef: <T,>(initial: T) => {
    const index = refIndex++
    if (!refValues[index]) refValues[index] = { current: initial }
    return refValues[index]
  },
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (stateValues[index] === undefined) stateValues[index] = initial
    const setState = (value: T | ((current: T) => T)) => {
      stateValues[index] = typeof value === 'function' ? (value as (current: T) => T)(stateValues[index] as T) : value
    }
    return [stateValues[index], setState] as [T, typeof setState]
  },
}))
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => Object.assign(
    (key: string, values?: Record<string, unknown>) => values?.count === undefined ? `${namespace}.${key}` : `${namespace}.${key}.${values.count}`,
    { has: (key: string) => key !== 'relationTypes.custom_relation' }
  ),
}))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/lib/api/memories', () => ({ memoriesApi: { getGraph, deleteEntity } }))
mock.module('./empty-state', () => ({ EmptyState }))
mock.module('./graph-toolbar', () => ({ GraphToolbar }))
mock.module('./graph-filters', () => ({ GraphFilters }))
mock.module('./entity-detail-sheet', () => ({ EntityDetailSheet }))
mock.module('d3-force', () => ({
  forceCenter: () => ({}),
  forceCollide: () => ({ radius: () => ({}) }),
  forceLink: () => ({ id: () => ({ distance: () => ({}) }) }),
  forceManyBody: () => ({ strength: () => ({}) }),
  forceSimulation: () => ({ force: () => ({ force: () => ({ force: () => ({ force: () => ({ on: () => {}, stop: () => {} }) }) }) }), alphaTarget: () => ({ restart: () => {} }) }),
}))
mock.module('d3-selection', () => ({ select: () => ({ selectAll: () => ({ remove: () => {}, each: () => {} }), style: () => {} }) }))
mock.module('d3-zoom', () => ({ zoom: () => ({ scaleExtent: () => ({ filter: () => ({ on: () => {} }) }) }), zoomIdentity: {}, zoomTransform: () => ({ x: 0, y: 0, k: 1 }) }))
mock.module('d3-drag', () => ({ drag: () => ({ on: () => ({ on: () => ({ on: () => ({}) }) }) }) }))

const { MemoryGraphCanvas } = await import('./memory-graph-canvas')

type TreeNode = { type?: unknown; props: Record<string, unknown> }

const entityAda = {
  id: 'entity-1',
  name: 'Ada Lovelace',
  entity_type: 'person',
  description: 'First programmer',
  properties: {},
  access_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
const entityTea = {
  ...entityAda,
  id: 'entity-2',
  name: 'Strong tea',
  entity_type: 'preference',
  description: 'Ada likes it',
}
const relation = {
  id: 'relation-1',
  source_entity_id: 'entity-1',
  target_entity_id: 'entity-2',
  relation_type: 'custom_relation',
  description: null,
  weight: 1,
  created_at: '2026-01-01T00:00:00Z',
}
const graphData = { entities: [entityAda, entityTea], relations: [relation] }

function render() {
  stateIndex = 0
  refIndex = 0
  effects.length = 0
  return MemoryGraphCanvas() as TreeNode
}

async function runEffects() {
  for (const effect of effects.splice(0)) await effect()
  await Promise.resolve()
}

async function renderLoaded() {
  render()
  await runEffects()
  render()
  await runEffects()
  return render()
}

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll([current.props.children, current.props.render], predicate)]
}

function findByType(node: unknown, type: unknown) {
  return findAll(node, (item) => item.type === type)[0]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object') return ''
  const props = (node as TreeNode).props
  return [props?.children, props?.render].flat().map(text).join('')
}

function reset(apiResult: Promise<unknown> = Promise.resolve(graphData)) {
  stateValues = []
  refValues = []
  getGraph.mockReset()
  getGraph.mockImplementation(() => apiResult)
  deleteEntity.mockReset()
  deleteEntity.mockImplementation(() => Promise.resolve({}))
  toastError.mockReset()
  toastSuccess.mockReset()
}

test('renders loading, empty, and fetch failure states', async () => {
  reset(new Promise(() => {}))
  expect(text(render())).toContain('common.loading')

  reset(Promise.resolve({ entities: [], relations: [] }))
  render()
  await runEffects()
  expect(findByType(render(), EmptyState)).toBeDefined()

  reset()
  getGraph.mockImplementation(() => Promise.reject(new Error('no graph')))
  render()
  await runEffects()
  expect(toastError).toHaveBeenCalledWith('memories.fetchError')
  expect(findByType(render(), EmptyState)).toBeDefined()
})

test('loads graph data and filters by search, entity type, and relation type', async () => {
  reset()
  let tree = await renderLoaded()

  expect(findByType(tree, GraphToolbar).props).toMatchObject({ entityCount: 2, relationCount: 1, selectedCount: 0 })
  expect(findByType(tree, GraphFilters).props).toMatchObject({
    availableEntityTypes: ['person', 'preference'],
    availableRelationTypes: ['custom_relation'],
    entityTypeFilter: ['person', 'preference'],
    relationTypeFilter: ['custom_relation'],
  })

  ;(findByType(tree, GraphToolbar).props.onSearchChange as (query: string) => void)('tea')
  tree = render()
  expect(findByType(tree, GraphToolbar).props).toMatchObject({ entityCount: 1, relationCount: 0 })

  ;(findByType(tree, GraphFilters).props.onEntityTypeFilterChange as (types: string[]) => void)(['person'])
  tree = render()
  expect(findByType(tree, GraphToolbar).props.entityCount).toBe(0)

  ;(findByType(tree, GraphToolbar).props.onSearchChange as (query: string) => void)('')
  ;(findByType(tree, GraphFilters).props.onRelationTypeFilterChange as (types: string[]) => void)([])
  tree = render()
  expect(findByType(tree, GraphToolbar).props).toMatchObject({ entityCount: 1, relationCount: 0 })
})

test('select mode, escape, and batch delete update toolbar and sheet props', async () => {
  reset()
  let tree = await renderLoaded()
  const toolbar = findByType(tree, GraphToolbar)
  const sheet = findByType(tree, EntityDetailSheet)

  expect(sheet.props).toMatchObject({ entity: null, entities: graphData.entities, relations: graphData.relations })

  ;(toolbar.props.onToggleSelectMode as () => void)()
  tree = render()
  expect(findByType(tree, GraphToolbar).props.selectMode).toBe(true)

  ;(findByType(tree, EntityDetailSheet).props.onDeleteEntity as (id: string) => void)('entity-1')
  tree = render()
  expect(findByType(tree, GraphToolbar).props).toMatchObject({ entityCount: 1, relationCount: 0 })

  ;(findByType(tree, GraphToolbar).props.onDeleteSelected as () => Promise<void>)()
  expect(deleteEntity).not.toHaveBeenCalled()

  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
  tree = render()
  expect(findByType(tree, GraphToolbar).props).toMatchObject({ selectMode: false, selectedCount: 0 })
})
