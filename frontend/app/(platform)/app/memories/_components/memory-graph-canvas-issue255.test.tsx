import { Window } from 'happy-dom'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { select } from 'd3-selection'

const window = new Window()
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document as unknown as Document
globalThis.navigator = window.navigator as unknown as Navigator
globalThis.MouseEvent = window.MouseEvent as unknown as typeof MouseEvent
globalThis.WheelEvent = window.WheelEvent as unknown as typeof WheelEvent
globalThis.KeyboardEvent = window.KeyboardEvent as unknown as typeof KeyboardEvent
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const getGraph = mock<() => Promise<{ entities: Entity[]; relations: Relation[] }>>()
const deleteEntity = mock<(id: string) => Promise<void>>()
const toastError = mock<(message: string) => void>()
const toastSuccess = mock<(message: string) => void>()
let zoomFilter: ((event: { type: string; ctrlKey?: boolean; metaKey?: boolean }) => boolean) | undefined
let zoomEvent: ((event: { transform: string }) => void) | undefined
let dragHandlers: Record<string, (event: Record<string, unknown>, datum: NodeDatum) => void> = {}

interface Entity {
  id: string
  name: string
  entity_type: string
  description: string
  properties: Record<string, unknown>
  user_id: string
  access_count: number
  created_at: string
  updated_at: string
}
interface Relation {
  id: string
  user_id: string
  source_entity_id: string
  target_entity_id: string
  relation_type: string
  properties: Record<string, unknown>
  created_at: string
  updated_at: string
}
interface NodeDatum { id: string; x?: number; y?: number; fx?: number | null; fy?: number | null }
interface ChildProps { [key: string]: unknown }
let toolbarProps: ChildProps
let filterProps: ChildProps
let detailProps: ChildProps

const translations = new Map<string, ((key: string) => string) & { has: (key: string) => boolean }>()
mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => {
    if (!translations.has(namespace)) {
      translations.set(namespace, Object.assign(
        (key: string) => `${namespace}.${key}`,
        { has: (key: string) => !key.endsWith('mystery') }
      ))
    }
    return translations.get(namespace)!
  },
}))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/lib/api/memories', () => ({ memoriesApi: { getGraph, deleteEntity } }))
mock.module('./empty-state', () => ({ EmptyState: () => <div data-testid="empty">empty</div> }))
mock.module('./graph-toolbar', () => ({
  GraphToolbar: (props: ChildProps) => {
    toolbarProps = props
    return <div data-testid="toolbar">
      <input aria-label="search" value={props.searchQuery as string} onChange={(event) => (props.onSearchChange as (value: string) => void)(event.currentTarget.value)} />
      {['zoom-in', 'zoom-out', 'fit', 'select', 'delete'].map((label, index) => <button key={label} onClick={([props.onZoomIn, props.onZoomOut, props.onFitView, props.onToggleSelectMode, props.onDeleteSelected][index] as () => void)}>{label}</button>)}
    </div>
  },
}))
mock.module('./graph-filters', () => ({
  GraphFilters: (props: ChildProps) => {
    filterProps = props
    return <div data-testid="filters">
      <button onClick={() => (props.onEntityTypeFilterChange as (types: string[]) => void)(['person'])}>person-only</button>
      <button onClick={() => (props.onRelationTypeFilterChange as (types: string[]) => void)([]) }>no-relations</button>
    </div>
  },
}))
mock.module('./entity-detail-sheet', () => ({
  EntityDetailSheet: (props: ChildProps) => {
    detailProps = props
    const entity = props.entity as Entity | null
    return <div data-testid="detail">{entity?.name ?? 'closed'}
      <button onClick={() => (props.onNavigateToEntity as (id: string) => void)('b')}>navigate</button>
      <button onClick={() => (props.onNavigateToEntity as (id: string) => void)('missing')}>navigate-missing</button>
      <button onClick={() => (props.onDeleteEntity as (id: string) => void)('b')}>delete-entity</button>
      <button onClick={() => (props.onDeleteRelation as (id: string) => void)('r1')}>delete-relation</button>
      <button onClick={props.onClose as () => void}>close</button>
    </div>
  },
}))
mock.module('d3-force', () => ({
  forceSimulation: (nodes: NodeDatum[]) => {
    nodes.forEach((node, index) => { node.x = 20 + index * 40; node.y = 20 + index * 40 })
    const simulation = {
      force: () => simulation,
      on: (_name: string, callback: () => void) => { callback(); return simulation },
      alphaTarget: () => simulation,
      restart: () => simulation,
      stop: mock(() => undefined),
    }
    return simulation
  },
  forceLink: () => { const force = { id: () => force, distance: () => force }; return force },
  forceManyBody: () => { const force = { strength: () => force }; return force },
  forceCenter: () => ({}),
  forceCollide: () => { const force = { radius: () => force }; return force },
}))
mock.module('d3-drag', () => ({
  drag: () => {
    const behavior = ((selection: unknown) => selection) as ((selection: unknown) => unknown) & { on: (name: string, handler: typeof dragHandlers[string]) => unknown }
    behavior.on = (name, handler) => { dragHandlers[name] = handler; return behavior }
    return behavior
  },
}))
mock.module('d3-zoom', () => {
  const identity = { x: 0, y: 0, k: 1, translate(x: number, y: number) { return { ...this, x, y, scale: (k: number) => ({ ...this, x, y, k }) } } }
  return {
    zoomIdentity: identity,
    zoomTransform: () => identity,
    zoom: () => {
      const behavior = ((selection: unknown) => selection) as ((selection: unknown) => unknown) & ChildProps
      behavior.scaleExtent = () => behavior
      behavior.filter = (callback: typeof zoomFilter) => { zoomFilter = callback; return behavior }
      behavior.on = (_name: string, callback: typeof zoomEvent) => { zoomEvent = callback; return behavior }
      behavior.scaleBy = mock(() => undefined)
      behavior.transform = mock(() => undefined)
      return behavior
    },
  }
})

const entities: Entity[] = [
  { id: 'a', user_id: 'u', name: 'A very long person name', entity_type: 'person', description: 'Alpha description', properties: {}, access_count: 1, created_at: '2026-01-01', updated_at: '2026-01-01' },
  { id: 'b', user_id: 'u', name: 'Beta', entity_type: 'mystery', description: '', properties: {}, access_count: 2, created_at: '2026-01-01', updated_at: '2026-01-01' },
]
const relations: Relation[] = [
  { id: 'r1', user_id: 'u', source_entity_id: 'a', target_entity_id: 'b', relation_type: 'mystery', properties: {}, created_at: '2026-01-01', updated_at: '2026-01-01' },
]

let container: HTMLDivElement
let root: Root
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
async function render() {
  const { MemoryGraphCanvas } = await import('./memory-graph-canvas')
  container = document.createElement('div')
  Object.defineProperties(container, { clientWidth: { value: 600 }, clientHeight: { value: 400 } })
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => root.render(<MemoryGraphCanvas />))
  await act(async () => { await flush() })
}
async function click(label: string) {
  const button = [...container.querySelectorAll('button')].find((element) => element.textContent === label)
  expect(button).toBeTruthy()
  await act(async () => { button!.dispatchEvent(new MouseEvent('click', { bubbles: true })); await flush() })
}

beforeEach(() => {
  getGraph.mockReset(); deleteEntity.mockReset(); toastError.mockReset(); toastSuccess.mockReset()
  getGraph.mockResolvedValue({ entities, relations }); deleteEntity.mockResolvedValue(undefined)
  dragHandlers = {}; toolbarProps = {}; filterProps = {}; detailProps = {}; zoomFilter = undefined; zoomEvent = undefined
  const selection = select(document.createElement('div')) as unknown as { transition: () => unknown; duration: () => unknown }
  const prototype = Object.getPrototypeOf(selection)
  prototype.transition = function () { return this }
  prototype.duration = function () { return this }
})
afterEach(() => { act(() => root?.unmount()); container?.remove() })

describe('MemoryGraphCanvas issue #255 coverage', () => {
  test('shows loading, empty data, and fetch errors', async () => {
    let resolveGraph!: (value: { entities: Entity[]; relations: Relation[] }) => void
    getGraph.mockImplementation(() => new Promise((resolve) => { resolveGraph = resolve }))
    await render()
    expect(container.textContent).toContain('common.loading')
    await act(async () => { resolveGraph({ entities: [], relations: [] }); await flush() })
    expect(container.querySelector('[data-testid="empty"]')).toBeTruthy()

    act(() => root.unmount()); container.remove()
    getGraph.mockRejectedValueOnce(new Error('offline'))
    const errorSpy = mock(() => undefined)
    console.error = errorSpy
    await render()
    expect(toastError).toHaveBeenCalledWith('memories.fetchError')
    expect(errorSpy).toHaveBeenCalled()
    expect(container.querySelector('[data-testid="empty"]')).toBeTruthy()
  })

  test('renders graph data, labels, fallback colors, filters, and search', async () => {
    await render()
    expect(toolbarProps.entityCount).toBe(2)
    expect(toolbarProps.relationCount).toBe(1)
    expect(filterProps.availableEntityTypes).toEqual(['person', 'mystery'])
    expect([...container.querySelectorAll('title')].map((node) => node.textContent)).toEqual(['A very long person name', 'Beta'])
    expect(container.textContent).toContain('A very lon...')
    expect(container.textContent).toContain('mystery')
    expect(container.querySelectorAll('circle')[1]?.getAttribute('fill')).toBe('#6b7280')
    expect(container.querySelector('line')?.getAttribute('stroke')).toBe('#999')

    await act(async () => { (toolbarProps.onSearchChange as (value: string) => void)('alpha'); await flush() })
    expect(toolbarProps.entityCount).toBe(1)
    expect(toolbarProps.relationCount).toBe(0)
    await click('person-only')
    await click('no-relations')
    expect(toolbarProps.relationCount).toBe(0)
  })

  test('opens, navigates, closes, and removes entity and relation details', async () => {
    await render()
    const nodes = container.querySelectorAll('.nodes > g')
    await act(async () => nodes[0]!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect((detailProps.entity as Entity).id).toBe('a')
    await click('navigate')
    expect((detailProps.entity as Entity).id).toBe('b')
    await click('navigate-missing')
    expect((detailProps.entity as Entity).id).toBe('b')
    await click('delete-relation')
    expect((detailProps.relations as Relation[])).toHaveLength(0)
    await click('delete-entity')
    expect((detailProps.entities as Entity[]).map((entity) => entity.id)).toEqual(['a'])
    await click('close')
    expect(detailProps.entity).toBeNull()
  })

  test('toggles selection, clears with Escape, and batch deletes successfully', async () => {
    await render()
    await click('select')
    const firstNode = container.querySelector('.nodes > g')!
    await act(async () => firstNode.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(toolbarProps.selectedCount).toBe(1)
    expect(container.querySelector('circle')?.getAttribute('stroke-dasharray')).toBe('4 2')
    await act(async () => firstNode.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    expect(toolbarProps.selectedCount).toBe(0)
    await act(async () => firstNode.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await click('delete')
    expect(deleteEntity).toHaveBeenCalledWith('a')
    expect(toastSuccess).toHaveBeenCalledWith('memories.deleteEntitySuccess')
    expect(toolbarProps.entityCount).toBe(1)

    await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })))
    expect(toolbarProps.selectMode).toBe(false)
    expect(toolbarProps.selectedCount).toBe(0)
  })

  test('handles zoom filters, wheel panning, drag callbacks, and selection rectangle', async () => {
    await render()
    expect(zoomFilter!({ type: 'wheel', ctrlKey: false, metaKey: false })).toBe(false)
    expect(zoomFilter!({ type: 'wheel', ctrlKey: true })).toBe(true)
    expect(zoomFilter!({ type: 'mousedown', ctrlKey: false, metaKey: false })).toBe(true)
    await click('select')
    expect(zoomFilter!({ type: 'pointerdown', ctrlKey: false, metaKey: false })).toBe(false)
    expect(zoomFilter!({ type: 'pointerdown', metaKey: true })).toBe(true)
    expect(zoomFilter!({ type: 'mouseup' })).toBe(true)

    const svg = container.querySelector('svg')!
    const wheel = new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaX: 4, deltaY: 8 })
    svg.dispatchEvent(wheel)
    expect(wheel.defaultPrevented).toBe(true)
    const modifiedWheel = new WheelEvent('wheel', { bubbles: true, ctrlKey: true })
    svg.dispatchEvent(modifiedWheel)
    expect(modifiedWheel.defaultPrevented).toBe(false)
    zoomEvent!({ transform: 'translate(1,2)' })
    expect(container.querySelector('svg > g')?.getAttribute('transform')).toBe('translate(1,2)')
    await click('zoom-in'); await click('zoom-out'); await click('fit')

    const datum = { id: 'x', x: 3, y: 4 }
    dragHandlers.start({ active: false }, datum); expect(datum).toMatchObject({ fx: 3, fy: 4 })
    dragHandlers.drag({ x: 8, y: 9 }, datum); expect(datum).toMatchObject({ fx: 8, fy: 9 })
    dragHandlers.end({ active: false }, datum); expect(datum).toMatchObject({ fx: null, fy: null })

    svg.getBoundingClientRect = () => ({ left: 0, top: 0, right: 600, bottom: 400, width: 600, height: 400, x: 0, y: 0, toJSON() {} })
    svg.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: 0, clientY: 0 }))
    window.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 100, clientY: 100 }))
    await act(async () => window.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: 100, clientY: 100 })))
    expect(toolbarProps.selectedCount).toBe(2)
  })

  test('keeps selected entities when batch deletion rejects and clears selection when mode exits', async () => {
    deleteEntity.mockRejectedValue(new Error('blocked'))
    await render()
    await click('select')
    await act(async () => container.querySelector('.nodes > g')!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
    await click('delete')
    expect(toolbarProps.entityCount).toBe(2)
    expect(toolbarProps.selectedCount).toBe(1)
    expect(toastSuccess).not.toHaveBeenCalled()
    await click('select')
    expect(toolbarProps.selectedCount).toBe(0)
  })
})
