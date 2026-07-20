import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const setters = [mock(() => {}), mock(() => {}), mock(() => {})]
let states: unknown[] = [true, false, null]
let stateIndex = 0
mock.module('react', () => ({ default: { useState: (initial: unknown) => [states[stateIndex] ?? initial, setters[stateIndex++]] }, useState: (initial: unknown) => [states[stateIndex] ?? initial, setters[stateIndex++]] }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, ChevronDown: component, Pencil: component, File: component, Image: component, Files: component, Images: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/label', ['Label']], ['@/components/ui/switch', ['Switch']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent', 'CollapsibleTrigger']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../dialogs', () => ({ FileToUrlInputDialog: component }))
mock.module('../../nodes/file-to-url-node', () => ({ defaultFileToUrlConfig: { inputs: [], ensureAbsolute: true } }))

const { FileToUrlNodeConfig } = await import('./file-to-url-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
function render(config: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  stateIndex = 0
  const onConfigChange = mock(() => {})
  const tree = FileToUrlNodeConfig({ config, variables: [], variableSearch: '', openVariablePopover: null, onConfigChange, onVariableSearchChange: mock(() => {}), onOpenVariablePopoverChange: mock(() => {}), ...overrides }) as TreeNode
  return { tree, onConfigChange }
}

 test('shows empty hints and opens the add dialog with file variables only', () => {
  states = [true, false, null]
  const variables = [{ id: 'file', name: 'File', isFile: true }, { id: 'text', name: 'Text', isFile: false }]
  const { tree } = render({ inputs: [] }, { variables })
  expect(findAll(tree, (node) => node.props.children === 'configFileToUrl.noFileInputs')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configFileToUrl.autoGenerateOutputHint')).toHaveLength(1)
  const add = findAll(tree, (node) => node.type === component && node.props.className === 'h-6 w-6')[0]
  ;(add.props.onClick as () => void)()
  expect(setters[2]).toHaveBeenCalledWith(null)
  expect(setters[1]).toHaveBeenCalledWith(true)
  const dialog = findAll(tree, (node) => node.type === component && Array.isArray(node.props.variables))[0]
  expect(dialog.props.variables).toEqual([variables[0]])
})

test('adds, updates, edits, deletes, and validates inputs', () => {
  const first = { id: 'one', name: 'bad name', sourceVariable: '{{input.file}}', sourceType: 'file' }
  const duplicate = { id: 'two', name: 'bad name', sourceVariable: '{{input.files}}', sourceType: 'files' }
  const { tree, onConfigChange } = render({ inputs: [first, duplicate], ensureAbsolute: false })
  expect(findAll(tree, (node) => node.props.children === 'configCommon.invalidVariableNameFormat')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'configFileToUrl.duplicateVariableNames')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'string')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'string[]')).toHaveLength(1)

  const actions = findAll(tree, (node) => node.type === component && node.props.size === 'icon')
  ;(actions[1].props.onClick as () => void)()
  expect(setters[2]).toHaveBeenCalledWith(first)
  expect(setters[1]).toHaveBeenCalledWith(true)
  ;(actions[2].props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: [duplicate] }))

  const dialog = findAll(tree, (node) => node.type === component && node.props.existingInputs)[0]
  const updated = { ...first, name: 'file_url' }
  ;(dialog.props.onSave as (input: typeof first) => void)(updated)
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: [updated, duplicate] }))
  ;(dialog.props.onSave as (input: typeof first) => void)({ id: 'three', name: 'new_url', sourceVariable: '{{x}}', sourceType: 'image' })
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: expect.arrayContaining([expect.objectContaining({ id: 'three' })]) }))
})

test('toggles absolute URLs and output collapse state', () => {
  states = [false, false, null]
  const { tree, onConfigChange } = render({ inputs: [], ensureAbsolute: true })
  const toggle = findAll(tree, (node) => node.type === component && node.props.checked === true)[0]
  ;(toggle.props.onCheckedChange as (checked: boolean) => void)(false)
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ ensureAbsolute: false }))
  const collapsible = findAll(tree, (node) => node.type === component && node.props.open === false && !('existingInputs' in node.props))[0]
  ;(collapsible.props.onOpenChange as (open: boolean) => void)(true)
  expect(setters[0]).toHaveBeenCalledWith(true)
  expect(findAll(tree, (node) => String(node.props.className).includes('-rotate-90'))).toHaveLength(1)
})
