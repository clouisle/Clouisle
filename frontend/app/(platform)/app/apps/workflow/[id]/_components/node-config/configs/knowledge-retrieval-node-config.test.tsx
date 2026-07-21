import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = function Component() {}
const getKnowledgeBases = mock(async () => ({ items: [] as Props[] }))
let states: unknown[] = []
let effects: (() => void | Promise<void>)[] = []
const setState = mock(() => {})

mock.module('react', () => ({
  useState: (initial: unknown) => [states.length ? states.shift() : initial, setState],
  useMemo: (factory: () => unknown) => factory(),
  useCallback: (callback: unknown) => callback,
  useEffect: (effect: () => void | Promise<void>) => effects.push(effect),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => Object.fromEntries(['Search', 'ChevronDown', 'Database', 'Check', 'Loader2', 'Trash2'].map(name => [name, component])))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/slider', ['Slider']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam: { id: 'team-1' } }) }))
mock.module('@/lib/api/knowledge-bases', () => ({ knowledgeBasesApi: { getKnowledgeBases } }))
mock.module('../utils', () => ({ isValidVariableName: (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) }))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/[{}]/g, '') }))

const { KnowledgeRetrievalNodeConfig, defaultKnowledgeRetrievalNodeConfig } = await import('./knowledge-retrieval-node-config')

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  return [node, ...descendants(node.props.children)]
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(text).join('')
  if (!value || typeof value !== 'object' || !('props' in value)) return ''
  return text((value as Node).props.children)
}

function render(config: Props, overrides: Props = {}) {
  effects = []
  return KnowledgeRetrievalNodeConfig({
    config: config as never,
    variables: [{ id: 'input.question', name: 'Question', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false }],
    variableSearch: '',
    openVariablePopover: null,
    onConfigChange: mock(() => {}),
    onVariableSearchChange: mock(() => {}),
    onOpenVariablePopoverChange: mock(() => {}),
    ...overrides,
  }) as Node
}

beforeEach(() => {
  states = []
  effects = []
  setState.mockClear()
  getKnowledgeBases.mockReset()
  getKnowledgeBases.mockResolvedValue({ items: [] })
})

test('loads and selects a team knowledge base', async () => {
  const kb = { id: 'kb-1', name: 'Product docs', description: 'Published docs' }
  getKnowledgeBases.mockResolvedValue({ items: [kb] } as never)
  const onConfigChange = mock(() => {})
  render({}, { onConfigChange })
  await effects[0]()

  expect(getKnowledgeBases).toHaveBeenCalledWith({ teamId: 'team-1', pageSize: 100 })
  states = [true, true, true, [kb], false, true, '']
  const tree = render({}, { onConfigChange })
  descendants(tree).find(node => node.type === 'button' && text(node).includes('Product docs'))!.props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith({
    ...defaultKnowledgeRetrievalNodeConfig,
    knowledgeBaseId: 'kb-1',
    knowledgeBaseName: 'Product docs',
  })
  expect(setState).toHaveBeenCalledWith(false)
  expect(setState).toHaveBeenCalledWith('')
})

test('updates query, retrieval, and output settings for a selected knowledge base', () => {
  const kb = { id: 'kb-1', name: 'Product docs', description: 'Published docs' }
  states = [true, true, true, [kb], false, false, '']
  const onConfigChange = mock(() => {})
  const tree = render({ knowledgeBaseId: 'kb-1', knowledgeBaseName: 'Product docs', querySource: 'variable', searchMode: 'hybrid', topK: 5, threshold: 0, outputVariable: 'not valid' }, { onConfigChange, openVariablePopover: 'query-input' })

  expect(text(tree)).toContain('configCommon.invalidVariableName')
  const buttons = descendants(tree).filter(node => typeof node.props.onClick === 'function')
  buttons.find(node => text(node).includes('configCommon.constant'))!.props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ querySource: 'constant', queryVariableRef: undefined }))

  buttons.find(node => text(node).includes('Question'))!.props.onClick!()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ queryVariableRef: '{{input.question}}', queryConstantValue: undefined }))

  const selects = descendants(tree).filter(node => node.type === component && typeof node.props.onValueChange === 'function')
  ;(selects[0].props.onValueChange as (value: string) => void)('vector')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ searchMode: 'vector' }))

  const sliders = descendants(tree).filter(node => node.type === component && Array.isArray(node.props.value))
  ;(sliders[0].props.onValueChange as (value: number[]) => void)([10])
  ;(sliders[1].props.onValueChange as (value: number[]) => void)([0.7])
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ topK: 10 }))
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ threshold: 0.7 }))
})

test('ignores a recoverable knowledge-base list failure', async () => {
  getKnowledgeBases.mockRejectedValue(new Error('temporary failure'))
  render({})
  await effects[0]()

  expect(setState).toHaveBeenCalledWith(true)
  expect(setState).toHaveBeenCalledWith(false)
})
