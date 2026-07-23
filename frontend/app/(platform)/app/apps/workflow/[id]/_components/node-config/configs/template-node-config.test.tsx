import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const setters = [mock(() => {}), mock(() => {}), mock(() => {})]
let states: unknown[] = [true, false, null], stateIndex = 0
mock.module('react', () => ({ default: { useState: (initial: unknown) => [states[stateIndex] ?? initial, setters[stateIndex++]] }, useState: (initial: unknown) => [states[stateIndex] ?? initial, setters[stateIndex++]] }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, ChevronDown: component, Pencil: component }))
for (const [path, names] of [['@/components/ui/button', ['Button']], ['@/components/ui/label', ['Label']], ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']]] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../components/code-editor', () => ({ CodeEditor: component }))
mock.module('../dialogs/template-input-dialog', () => ({ TemplateInputDialog: component }))
mock.module('../../nodes/template-node', () => ({ defaultTemplateConfig: { inputs: [], template: '', outputVariable: 'result', outputDescription: 'Rendered text' } }))

const { TemplateNodeConfig } = await import('./template-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
function render(config: Record<string, unknown>) {
  stateIndex = 0
  const onConfigChange = mock(() => {})
  const tree = TemplateNodeConfig({ config, variables: [], variableSearch: '', openVariablePopover: null, onConfigChange, onVariableSearchChange: mock(() => {}), onOpenVariablePopoverChange: mock(() => {}) }) as TreeNode
  return { tree, onConfigChange }
}

test('opens add dialog and edits template and output collapse', () => {
  states = [false, false, null]
  const { tree, onConfigChange } = render({ inputs: [], template: 'Hello', outputVariable: 'text', outputDescription: 'Rendered' })
  expect(findAll(tree, (node) => node.props.children === 'configTemplate.noInputVariables')).toHaveLength(1)
  const add = findAll(tree, (node) => node.props.className === 'h-6 w-6')[0]
  ;(add.props.onClick as () => void)()
  expect(setters[2]).toHaveBeenCalledWith(null)
  expect(setters[1]).toHaveBeenCalledWith(true)
  const editor = findAll(tree, (node) => node.props.language === 'jinja2')[0]
  ;(editor.props.onChange as (value: string) => void)('Hi {{name}}')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ template: 'Hi {{name}}' }))
  expect(findAll(tree, (node) => node.props.children === 'text')).toHaveLength(1)
  const collapsible = findAll(tree, (node) => node.props.open === false && node.props.onOpenChange && !('editingInput' in node.props))[0]
  ;(collapsible.props.onOpenChange as (open: boolean) => void)(true)
  expect(setters[0]).toHaveBeenCalledWith(true)
})

test('adds, updates, edits, deletes, and validates inputs', () => {
  states = [true, false, null]
  const first = { id: 'one', name: 'bad name', value: '{{input.name}}', valueSource: 'Input' }
  const duplicate = { id: 'two', name: 'bad name', value: '{{input.other}}' }
  const { tree, onConfigChange } = render({ inputs: [first, duplicate], template: '', outputVariable: 'result', outputDescription: '' })
  expect(findAll(tree, (node) => node.props.children === 'configCommon.invalidVariableNameFormat')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.duplicateVariableName')).toHaveLength(1)
  const actions = findAll(tree, (node) => node.props.size === 'icon')
  ;(actions[1].props.onClick as () => void)()
  expect(setters[2]).toHaveBeenCalledWith(first)
  ;(actions[2].props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: [duplicate] }))
  const dialog = findAll(tree, (node) => node.props.editingInput !== undefined)[0]
  const updated = { ...first, name: 'name' }
  ;(dialog.props.onSave as (input: typeof first) => void)(updated)
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: [updated, duplicate] }))
  ;(dialog.props.onSave as (input: typeof first) => void)({ id: 'three', name: 'new', value: '{{x}}' })
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: expect.arrayContaining([expect.objectContaining({ id: 'three' })]) }))
})
