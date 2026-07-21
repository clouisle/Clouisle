import { beforeEach, describe, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

const jsx = (type: unknown, props: Props = {}): Node => ({ type, props })
const component = (name: string) => Object.assign(function Component() {}, { displayName: name })
const components = Object.fromEntries([
  'Button', 'Input', 'Label', 'Textarea', 'Select', 'SelectContent', 'SelectItem',
  'SelectTrigger', 'SelectValue', 'Switch', 'Dialog', 'DialogContent', 'DialogHeader',
  'DialogTitle', 'DialogFooter', 'Popover', 'PopoverContent', 'PopoverTrigger', 'ScrollArea',
].map(name => [name, component(name)])) as Record<string, (props: Props) => unknown>
const icons = Object.fromEntries(['Plus', 'Trash2', 'Pencil', 'Search', 'TypeIcon'].map(name => [name, component(name)]))

let states: unknown[] = []
let stateIndex = 0
const setters = [mock(() => {}), mock(() => {}), mock(() => {})]

mock.module('react', () => ({
  default: {},
  useState: (initial: unknown) => {
    const index = stateIndex++
    return [index < states.length ? states[index] : initial, setters[index]]
  },
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => icons)
for (const [path, names] of [
  ['@/components/ui/button', ['Button']],
  ['@/components/ui/input', ['Input']],
  ['@/components/ui/label', ['Label']],
  ['@/components/ui/textarea', ['Textarea']],
  ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/switch', ['Switch']],
  ['@/components/ui/dialog', ['Dialog', 'DialogContent', 'DialogHeader', 'DialogTitle', 'DialogFooter']],
  ['@/components/ui/popover', ['Popover', 'PopoverContent', 'PopoverTrigger']],
  ['@/components/ui/scroll-area', ['ScrollArea']],
] as const) mock.module(path, () => Object.fromEntries(names.map(name => [name, components[name]])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../utils', () => ({ isValidVariableName: (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) }))
mock.module('../constants', () => ({
  loopVariableTypeConfig: Object.fromEntries(['string', 'number', 'boolean', 'array', 'object'].map(type => [type, {
    icon: icons.TypeIcon,
    valueType: type,
    labelKey: type,
  }])),
}))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/[{}]/g, '') }))
mock.module('../../nodes/condition-node', () => ({
  getConditionOperatorLabels: () => ({ equals: 'equals', is_empty: 'is empty' }),
  getConditionOperatorShortLabels: () => ({ equals: '=', is_empty: 'empty' }),
  noValueOperators: ['is_empty'],
}))

const { LoopNodeConfig } = await import('./loop-node-config')

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

const baseConfig = {
  maxIterations: 10,
  indexVariable: 'index',
  loopVariables: [],
  exitConditions: [],
  exitLogicOperator: 'and',
  outputVariable: 'results',
}

function render(config: Props = baseConfig, overrides: Props = {}, stateValues: unknown[] = []) {
  states = stateValues
  stateIndex = 0
  return LoopNodeConfig({
    nodeId: 'loop-1',
    config: config as never,
    variables: [
      { id: 'input.question', name: 'Question', type: 'string', group: 'input', groupLabel: 'Input', isSystem: false },
      { id: 'system.now', name: 'Now', type: 'string', group: 'system', groupLabel: 'System', isSystem: true },
    ],
    variableSearch: '',
    openVariablePopover: null,
    onConfigChange: mock(() => {}),
    onVariableSearchChange: mock(() => {}),
    onOpenVariablePopoverChange: mock(() => {}),
    ...overrides,
  }) as Node
}

beforeEach(() => setters.forEach(setter => setter.mockClear()))

describe('loop node config issue #255 coverage', () => {
  test('updates loop controls and reports invalid and duplicate names', () => {
    const onConfigChange = mock(() => {})
    const config = {
      ...baseConfig,
      indexVariable: 'bad name',
      outputVariable: 'item',
      loopVariables: [{ id: 'var-1', name: 'item', type: 'string', defaultValue: '', description: '' }],
    }
    const tree = render(config, { onConfigChange })
    expect(text(tree)).toContain('configCommon.invalidVariableName')
    expect(text(tree)).toContain('configCommon.duplicateVariableInNode')

    const inputs = descendants(tree).filter(node => node.type === components.Input)
    inputs.find(node => node.props.type === 'number')!.props.onChange({ target: { value: '' } })
    inputs.find(node => node.props.placeholder === 'index')!.props.onChange({ target: { value: 'iteration' } })
    inputs.find(node => node.props.placeholder === 'results')!.props.onChange({ target: { value: 'output' } })

    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ maxIterations: 10 }))
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ indexVariable: 'iteration' }))
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'output' }))
  })

  test('adds, edits, opens, and removes loop variables', () => {
    const existing = { id: 'var-1', name: 'item', type: 'string', defaultValue: 'old', description: 'old desc' }
    const onConfigChange = mock(() => {})
    const config = { ...baseConfig, loopVariables: [existing] }
    const tree = render(config, { onConfigChange })

    descendants(tree).find(node => node.type === components.Button && node.props.size === 'sm')!.props.onClick()
    expect(setters[0]).toHaveBeenCalledWith(null)
    expect(setters[2]).toHaveBeenCalledWith(expect.objectContaining({ name: '', type: 'string' }))

    descendants(tree).find(node => node.type === 'div' && node.props.onClick && text(node).includes('item'))!.props.onClick()
    expect(setters[0]).toHaveBeenCalledWith(existing)
    expect(setters[1]).toHaveBeenCalledWith(true)

    const iconButtons = descendants(tree).filter(node => node.type === components.Button && node.props.size === 'icon')
    const event = { stopPropagation: mock(() => {}) }
    iconButtons[0].props.onClick(event)
    iconButtons[1].props.onClick(event)
    expect(event.stopPropagation).toHaveBeenCalledTimes(2)
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ loopVariables: [] }))

    const addTree = render(config, { onConfigChange }, [null, true, {
      name: ' count ', type: 'number', defaultValue: '2', description: 'counter',
    }])
    descendants(addTree).find(node => node.type === components.Button && node.props.size === 'sm' && !node.props.variant)!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      loopVariables: expect.arrayContaining([expect.objectContaining({ name: 'count', type: 'number', defaultValue: '2' })]),
    }))
    expect(setters[1]).toHaveBeenCalledWith(false)

    const editTree = render(config, { onConfigChange }, [existing, true, { ...existing, name: 'renamed' }])
    descendants(editTree).find(node => node.type === components.Button && node.props.size === 'sm' && !node.props.variant)!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      loopVariables: [expect.objectContaining({ id: 'var-1', name: 'renamed' })],
    }))
  })

  test('guards empty, invalid, and duplicate loop variable saves', () => {
    const onConfigChange = mock(() => {})
    for (const name of ['', 'bad name', 'INDEX', 'RESULTS', 'ITEM']) {
      const config = { ...baseConfig, loopVariables: [{ id: 'var-1', name: 'item', type: 'string' }] }
      const tree = render(config, { onConfigChange }, [null, true, { name, type: 'string' }])
      const save = descendants(tree).find(node => node.type === components.Button && node.props.size === 'sm' && !node.props.variant)!
      expect(save.props.disabled).toBe(true)
      save.props.onClick()
    }
    expect(onConfigChange).not.toHaveBeenCalled()

    const editingTree = render(
      { ...baseConfig, loopVariables: [{ id: 'var-1', name: 'item', type: 'string' }] },
      { onConfigChange },
      [{ id: 'var-1', name: 'item', type: 'string' }, true, { name: 'ITEM', type: 'string' }],
    )
    expect(text(editingTree)).not.toContain('configCommon.variableNameExists')
  })

  test('changes every loop variable form control and dialog controls', () => {
    for (const type of ['string', 'number', 'boolean', 'array', 'object']) {
      const tree = render(baseConfig, {}, [null, true, { name: 'value', type, defaultValue: type === 'boolean' ? 'true' : 'old' }])
      const nodes = descendants(tree)
      nodes.find(node => node.type === components.Input && node.props.id === 'loopvar-name')!.props.onChange({ target: { value: 'next' } })
      nodes.find(node => node.type === components.Select && node.props.value === type)!.props.onValueChange('string')
      const defaultControl = nodes.find(node =>
        (node.type === components.Input || node.type === components.Textarea || node.type === components.Switch)
        && node.props.id === 'loopvar-default')!
      if (type === 'boolean') defaultControl.props.onCheckedChange(false)
      else defaultControl.props.onChange({ target: { value: 'new default' } })
      expect(setters[2]).toHaveBeenCalled()
    }

    const tree = render(baseConfig, {}, [null, true, { name: 'value', type: 'string', description: 'old' }])
    const nodes = descendants(tree)
    nodes.find(node => node.type === components.Input && node.props.id === 'loopvar-desc')!.props.onChange({ target: { value: 'new desc' } })
    nodes.find(node => node.type === components.Button && node.props.variant === 'outline')!.props.onClick()
    descendants(tree).find(node => node.type === components.Dialog)!.props.onOpenChange(false)
    expect(setters[1]).toHaveBeenCalledWith(false)
  })

  test('adds and edits exit conditions, popovers, variables, and logic', () => {
    const rules = [
      { id: 'r1', variable: '', variableSource: '', operator: 'equals', value: 'old' },
      { id: 'r2', variable: '{{input.question}}', variableSource: 'Input', operator: 'is_empty', value: '' },
    ]
    const config = { ...baseConfig, exitConditions: rules, exitLogicOperator: 'or' }
    const onConfigChange = mock(() => {})
    const onVariableSearchChange = mock(() => {})
    const onOpenVariablePopoverChange = mock(() => {})
    const tree = render(config, {
      onConfigChange, onVariableSearchChange, onOpenVariablePopoverChange, openVariablePopover: 'exit-r1',
    })
    const nodes = descendants(tree)

    const addButtons = nodes.filter(node => node.type === components.Button && node.props.variant === 'ghost' && node.props.size === 'sm')
    addButtons[1].props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      exitConditions: expect.arrayContaining([expect.objectContaining({ operator: 'equals', variable: '' })]),
    }))

    const popovers = nodes.filter(node => node.type === components.Popover)
    popovers[0].props.onOpenChange(true)
    popovers[0].props.onOpenChange(false)
    expect(onOpenVariablePopoverChange).toHaveBeenCalledWith('exit-r1')
    expect(onOpenVariablePopoverChange).toHaveBeenCalledWith(null)
    expect(onVariableSearchChange).toHaveBeenCalledWith('')

    nodes.find(node => node.type === components.Input && node.props.placeholder === 'configCommon.searchVariable')!.props.onChange({ target: { value: 'ques' } })
    nodes.find(node => node.type === 'button' && text(node).includes('Question'))!.props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
      exitConditions: expect.arrayContaining([expect.objectContaining({ variable: '{{input.question}}', variableSource: 'Input' })]),
    }))

    nodes.find(node => node.type === components.Select && node.props.value === 'equals')!.props.onValueChange('is_empty')
    nodes.find(node => node.type === components.Input && node.props.value === 'old')!.props.onChange({ target: { value: 'new' } })
    nodes.find(node => node.type === components.Select && node.props.value === 'or')!.props.onValueChange('and')
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ exitLogicOperator: 'and' }))

    const removeButtons = nodes.filter(node => node.type === components.Button && node.props.size === 'icon')
    removeButtons[removeButtons.length - 1].props.onClick()
    expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ exitConditions: [rules[0]] }))
  })

  test('filters exit variables and uses fallback internal variable names', () => {
    const rule = { id: 'r1', variable: '', variableSource: '', operator: 'equals', value: '' }
    const emptyTree = render(
      { ...baseConfig, indexVariable: '', outputVariable: '', loopVariables: undefined, exitConditions: [rule] },
      { variableSearch: 'missing' },
    )
    expect(text(emptyTree)).toContain('configCommon.noMatchingVariables')

    const systemTree = render(
      { ...baseConfig, loopVariables: [{ id: 'var-1', name: 'item', type: 'string' }], exitConditions: [rule] },
      { variableSearch: 'now', openVariablePopover: 'exit-r1' },
    )
    expect(text(systemTree)).toContain('Now')
    expect(text(systemTree)).not.toContain('Question')

    const internalTree = render(
      { ...baseConfig, loopVariables: [{ id: 'var-1', name: 'item', type: 'string' }], exitConditions: [rule] },
      { variableSearch: 'item', openVariablePopover: 'exit-r1' },
    )
    expect(text(internalTree)).toContain('item')
  })
})
