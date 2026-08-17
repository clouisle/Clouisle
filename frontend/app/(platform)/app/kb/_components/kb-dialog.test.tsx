import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'

const createKnowledgeBase = mock(() => Promise.resolve({}))
const updateKnowledgeBase = mock(() => Promise.resolve({}))
const getTeamModels = mock(() => Promise.resolve([]))
const success = mock(() => undefined)
const error = mock(() => undefined)
const push = mock(() => undefined)

let currentTeam: { id: string } | null = { id: 'team-1' }
let states: unknown[] = []
let hookIndex = 0
let effects: Array<{ dependencies: unknown[]; cleanup?: () => void }> = []
let effectIndex = 0

const react = {
  __CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE: {
    recentlyCreatedOwnerStacks: 0,
    A: null,
  },
  useState: <T,>(initial: T) => {
    const index = hookIndex++
    if (states[index] === undefined) states[index] = initial
    return [states[index] as T, (value: T | ((previous: T) => T)) => {
      states[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(states[index] as T)
        : value
    }] as const
  },
  useEffect: (effect: () => void | (() => void), dependencies: unknown[]) => {
    const index = effectIndex++
    const previous = effects[index]
    if (!previous || dependencies.some((dependency, i) => dependency !== previous.dependencies[i])) {
      previous?.cleanup?.()
      const cleanup = effect()
      effects[index] = { dependencies, cleanup: typeof cleanup === 'function' ? cleanup : undefined }
    }
  },
  useMemo: <T,>(factory: () => T) => factory(),
}

mock.module('react', () => react)
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({
  knowledgeBasesApi: { createKnowledgeBase, updateKnowledgeBase },
  teamModelsApi: { getTeamModels },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) =>
    Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: () => ({}),
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))

mock.module('@/components/ui/button', () => ({ Button: 'Button' }))
mock.module('@/components/ui/input', () => ({ Input: 'Input' }))
mock.module('@/components/ui/textarea', () => ({ Textarea: 'Textarea' }))
mock.module('@/components/ui/label', () => ({ Label: 'Label' }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: 'Dialog', DialogContent: 'DialogContent', DialogDescription: 'DialogDescription',
  DialogFooter: 'DialogFooter', DialogHeader: 'DialogHeader', DialogTitle: 'DialogTitle',
}))
mock.module('@/components/ui/select', () => ({
  Select: 'Select', SelectContent: 'SelectContent', SelectEmpty: 'SelectEmpty',
  SelectItem: 'SelectItem', SelectTrigger: 'SelectTrigger', SelectValue: 'SelectValue',
}))
mock.module('@/components/ui/switch', () => ({ Switch: 'Switch' }))
mock.module('@/components/ui/field', () => ({ FieldError: 'FieldError' }))

const { KnowledgeBaseDialog } = await import('./kb-dialog')

type ElementNode = { props?: Record<string, unknown>; type?: unknown }

function find(node: unknown, predicate: (element: ElementNode) => boolean): ElementNode {
  if (Array.isArray(node)) {
    for (const child of node) {
      try { return find(child, predicate) } catch { /* keep searching */ }
    }
  }
  if (node && typeof node === 'object') {
    const element = node as ElementNode
    if (predicate(element)) return element
    if (element.props?.children !== undefined) return find(element.props.children, predicate)
  }
  throw new Error('element not found')
}

function render(overrides: Partial<Parameters<typeof KnowledgeBaseDialog>[0]> = {}) {
  hookIndex = 0
  effectIndex = 0
  return KnowledgeBaseDialog({
    open: true,
    onOpenChange: mock(() => undefined),
    knowledgeBase: null,
    onSuccess: mock(() => undefined),
    ...overrides,
  })
}

const submit = (tree: unknown) => find(tree, (element) => element.props?.['data-testid'] === 'kb-dialog-submit')
const input = (tree: unknown, id: string) => find(tree, (element) => element.props?.id === id)
const form = (tree: unknown) => find(tree, (element) => typeof element.props?.onSubmit === 'function')

beforeEach(() => {
  states = []
  effects = []
  currentTeam = { id: 'team-1' }
  createKnowledgeBase.mockReset()
  updateKnowledgeBase.mockReset()
  getTeamModels.mockReset()
  getTeamModels.mockResolvedValue([])
  success.mockReset()
  error.mockReset()
  push.mockReset()
  createKnowledgeBase.mockResolvedValue({ id: 'kb-1' })
})

afterEach(() => mock.restore())

describe('KnowledgeBaseDialog', () => {
  test('loads authorized models on open and blocks an unnamed create', async () => {
    const tree = render()
    await Promise.resolve()

    expect(getTeamModels).toHaveBeenCalledWith('team-1', 'embedding')
    expect(getTeamModels).toHaveBeenCalledWith('team-1', 'rerank')

    await form(tree).props!.onSubmit!({ preventDefault() {} })
    const updated = render()

    expect(createKnowledgeBase).not.toHaveBeenCalled()
    expect(input(updated, 'name').props?.['aria-invalid']).toBe(true)
    expect(push).not.toHaveBeenCalled()
  })

  test('creates a trimmed knowledge base, reports success, and closes', async () => {
    const onOpenChange = mock(() => undefined)
    const onSuccess = mock(() => undefined)
    let tree = render({ onOpenChange, onSuccess })
    input(tree, 'name').props!.onChange!({ target: { value: '  Product docs  ' } })
    input(tree, 'description').props!.onChange!({ target: { value: '  Searchable  ' } })
    tree = render({ onOpenChange, onSuccess })

    await form(tree).props!.onSubmit!({ preventDefault() {} })

    expect(createKnowledgeBase).toHaveBeenCalledWith(expect.objectContaining({
      team_id: 'team-1', name: 'Product docs', description: 'Searchable',
    }))
    expect(success).toHaveBeenCalledWith('kbCreated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1')
  })

  test('edits existing data without requiring a current team', async () => {
    currentTeam = null
    const knowledgeBase = {
      id: 'kb-1', name: 'Existing', description: null, embedding_model_id: 'embedding-1',
      rerank_model_id: null, status: 'active', settings: {}, embedding_model: { name: 'Embedding' },
    } as never
    const onOpenChange = mock(() => undefined)
    let tree = render({ knowledgeBase, onOpenChange })
    tree = render({ knowledgeBase, onOpenChange })
    find(tree, (element) => element.props?.id === 'status').props!.onCheckedChange!(false)
    tree = render({ knowledgeBase, onOpenChange })

    await form(tree).props!.onSubmit!({ preventDefault() {} })

    expect(updateKnowledgeBase).toHaveBeenCalledWith('kb-1', expect.objectContaining({
      name: 'Existing', status: 'archived',
    }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(push).not.toHaveBeenCalled()
  })

  test('keeps the dialog open and clears loading after a failed save', async () => {
    createKnowledgeBase.mockRejectedValue(new Error('offline'))
    const onOpenChange = mock(() => undefined)
    const onSuccess = mock(() => undefined)
    let tree = render({ onOpenChange, onSuccess })
    input(tree, 'name').props!.onChange!({ target: { value: 'Will fail' } })
    tree = render({ onOpenChange, onSuccess })

    await form(tree).props!.onSubmit!({ preventDefault() {} })
    tree = render({ onOpenChange, onSuccess })

    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
    expect(submit(tree).props?.disabled).toBe(false)
  })
})
