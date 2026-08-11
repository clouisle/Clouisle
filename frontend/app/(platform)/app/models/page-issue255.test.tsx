import { afterAll, beforeAll, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

let states: unknown[] = []
let stateIndex = 0
let effects: Array<() => void> = []
let currentTeam: { id: string } | null = { id: 'team-1' }
const getTeamModels = mock(() => Promise.resolve([]))
const consoleError = spyOn(console, 'error').mockImplementation(() => {})

const components = new Proxy<Record<string, (props: Record<string, unknown>) => ReactElement>>({}, {
  get: (target, key: string) => target[key] ??= (props) => ({ type: key, props, key: null }),
})
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: (initial: unknown) => {
    const index = stateIndex++
    if (states.length <= index) states[index] = typeof initial === 'function' ? initial() : initial
    return [states[index], (value: unknown) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: unknown) => unknown)(states[index])
        : value
    }]
  },
  useEffect: (callback: () => void) => effects.push(callback),
  useCallback: (callback: unknown) => callback,
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Bot: components.Bot, Search: components.Search, X: components.X }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-require-team', () => ({ useRequireTeam: () => undefined }))
mock.module('@/lib/api', () => ({ teamModelsApi: { getTeamModels } }))
mock.module('@/components/ui/input', () => ({ Input: components.Input }))
mock.module('@/components/ui/button', () => ({ Button: components.Button }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: components.Skeleton }))
mock.module('@/components/ui/data-table-faceted-filter', () => ({ DataTableFacetedFilter: components.DataTableFacetedFilter }))
mock.module('./_components', () => ({
  ModelCard: components.ModelCard,
  ModelCardSkeleton: components.ModelCardSkeleton,
  ModelDetailDialog: components.ModelDetailDialog,
}))

type Page = typeof import('./page').default
let ModelsPage: Page

function render() {
  stateIndex = 0
  effects = []
  return ModelsPage()
}

async function load() {
  render()
  for (const effect of effects) effect()
  await Promise.resolve()
  await Promise.resolve()
  return render()
}

function findAll(node: ReactNode, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (!node || typeof node !== 'object') return []
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, type))
  const element = node as ReactElement<Record<string, unknown>>
  return [...(element.type === type ? [element] : []), ...findAll(element.props?.children as ReactNode, type)]
}

beforeAll(async () => {
  ({ default: ModelsPage } = await import('./page'))
})

afterAll(() => consoleError.mockRestore())

beforeEach(() => {
  states = []
  effects = []
  currentTeam = { id: 'team-1' }
  getTeamModels.mockReset()
  getTeamModels.mockResolvedValue([])
  consoleError.mockClear()
})

describe('ModelsPage', () => {
  test('searches, filters, clears, and opens a card from the flat view', async () => {
    const chatModel = {
      id: 'chat-model', priority: 1, is_enabled: true,
      model: { name: 'GPT Test', model_id: 'gpt-test', provider: 'openai', model_type: 'chat' },
    }
    const higherPriorityChat = {
      id: 'priority-chat', priority: 3, is_enabled: true,
      model: { name: 'Claude', model_id: 'claude-3', provider: 'anthropic', model_type: 'chat' },
    }
    const embeddingModel = {
      id: 'embedding-model', priority: 2, is_enabled: false,
      model: { name: 'Embedder', model_id: 'embed-v1', provider: 'openai', model_type: 'embedding' },
    }
    getTeamModels.mockResolvedValue([chatModel, higherPriorityChat, embeddingModel])

    let tree = await load()
    expect(findAll(tree, components.ModelCard).map(card => card.props.teamModel)).toEqual([
      higherPriorityChat, chatModel, embeddingModel,
    ])

    const input = findAll(tree, components.Input)[0]
    ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'claude-3' } })
    tree = render()
    expect(findAll(tree, components.ModelCard).map(card => card.props.teamModel)).toEqual([higherPriorityChat])

    ;(findAll(tree, components.Button)[0].props.onClick as () => void)()
    expect(states.slice(2, 6)).toEqual(['', new Set(), new Set(), new Set()])

    tree = render()
    const filters = findAll(tree, components.DataTableFacetedFilter)
    ;(filters[0].props.onSelectionChange as (values: Set<string>) => void)(new Set(['anthropic']))
    tree = render()
    expect(findAll(tree, components.ModelCard).map(card => card.props.teamModel)).toEqual([higherPriorityChat])

    ;(findAll(tree, components.Button)[0].props.onClick as () => void)()
    tree = render()
    ;(findAll(tree, components.DataTableFacetedFilter)[1].props.onSelectionChange as (values: Set<string>) => void)(new Set(['embedding']))
    tree = render()
    const flatCard = findAll(tree, components.ModelCard)[0]
    expect(flatCard.props.teamModel).toBe(embeddingModel)
    ;(flatCard.props.onClick as () => void)()
    expect(states.slice(6, 8)).toEqual([true, embeddingModel])

    states[3] = new Set()
    states[5] = new Set(['enabled'])
    tree = render()
    expect(findAll(tree, components.ModelCard).map(card => card.props.teamModel)).toEqual([higherPriorityChat, chatModel])
    states[5] = new Set(['disabled'])
    tree = render()
    expect(findAll(tree, components.ModelCard).map(card => card.props.teamModel)).toEqual([embeddingModel])
    states[5] = new Set(['enabled', 'disabled'])
    tree = render()
    expect(findAll(tree, components.ModelCard)).toHaveLength(0)

    states[2] = 'missing'
    states[5] = new Set()
    tree = render()
    expect(findAll(tree, components.ModelCard)).toHaveLength(0)
    ;(findAll(tree, components.Button).find(button => button.props.variant === 'outline')!.props.onClick as () => void)()
    expect(states.slice(2, 6)).toEqual(['', new Set(), new Set(), new Set()])
  })

  test('matches searches by model name, provider, and provider display name', async () => {
    const teamModel = {
      id: 'team-model', priority: 1, is_enabled: true,
      model: {
        name: 'GPT Test', model_id: 'gpt-test', provider: 'custom',
        provider_display_name: 'Acme Gateway', model_type: 'chat',
      },
    }
    getTeamModels.mockResolvedValue([teamModel])
    await load()

    states[2] = 'gpt test'
    expect(findAll(render(), components.ModelCard)).toHaveLength(1)
    states[2] = 'custom'
    expect(findAll(render(), components.ModelCard)).toHaveLength(1)
    states[2] = 'acme gateway'
    expect(findAll(render(), components.ModelCard)).toHaveLength(1)
  })

  test('loads team models and wires card clicks to the detail dialog', async () => {
    const teamModel = {
      id: 'team-model-1',
      priority: 2,
      is_enabled: true,
      model: { name: 'GPT Test', model_id: 'gpt-test', provider: 'openai', model_type: 'chat' },
    }
    getTeamModels.mockResolvedValue([teamModel])

    let tree = await load()
    expect(getTeamModels).toHaveBeenCalledWith('team-1')

    const card = findAll(tree, components.ModelCard)[0]
    expect(card.props.teamModel).toBe(teamModel)
    ;(card.props.onClick as () => void)()

    tree = render()
    const dialog = findAll(tree, components.ModelDetailDialog)[0]
    expect(dialog.props).toMatchObject({ open: true, teamModel })
    ;(dialog.props.onOpenChange as (open: boolean) => void)(false)
    expect(states[6]).toBe(false)
  })

  test('skips loading without a team and recovers from API errors', async () => {
    currentTeam = null
    render()
    for (const effect of effects) effect()
    expect(getTeamModels).not.toHaveBeenCalled()

    currentTeam = { id: 'team-1' }
    getTeamModels.mockRejectedValue(new Error('network'))
    const tree = await load()

    expect(consoleError).toHaveBeenCalledWith('Failed to fetch team models:', expect.any(Error))
    expect(JSON.stringify(tree)).toContain('models.noModels')
    expect(states[1]).toBe(false)
  })
})
