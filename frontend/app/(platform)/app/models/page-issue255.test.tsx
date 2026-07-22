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
