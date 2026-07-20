import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const codeEditor = function CodeEditor() {}
const typeSpecEditor = function TypeSpecEditor() {}
const setRetryOpen = mock(() => {})
mock.module('react', () => ({
  default: { useState: (initial: unknown) => [initial, setRetryOpen] },
  useState: (initial: unknown) => [initial, setRetryOpen],
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Plus: component, Trash2: component, Info: component }))
for (const [path, names] of [
  ['@/components/ui/button', ['Button']], ['@/components/ui/input', ['Input']], ['@/components/ui/label', ['Label']],
  ['@/components/ui/textarea', ['Textarea']], ['@/components/ui/select', ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue']],
  ['@/components/ui/switch', ['Switch']], ['@/components/ui/radio-group', ['RadioGroup', 'RadioGroupItem']],
  ['@/components/ui/collapsible', ['Collapsible', 'CollapsibleContent']],
  ['@/components/ui/tooltip', ['Tooltip', 'TooltipContent', 'TooltipProvider', 'TooltipTrigger']],
] as const) mock.module(path, () => Object.fromEntries(names.map((name) => [name, component])))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('../utils', () => ({ isValidVariableName: (value: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(value) }))
mock.module('../types', () => ({ extractVariableDisplayName: (value: string) => value.replace(/^{{|}}$/g, '') }))
mock.module('../components/code-editor', () => ({ CodeEditor: codeEditor }))
mock.module('../type-spec-editor', () => ({ TypeSpecEditor: typeSpecEditor }))
mock.module('@/lib/workflow/type-spec', () => ({ describeTypeSpec: (spec: { kind: string }) => `type:${spec.kind}` }))
const pythonTemplate = 'PYTHON_TEMPLATE', javascriptTemplate = 'JAVASCRIPT_TEMPLATE'
const defaultRetryConfig = { enabled: false, maxRetries: 3, retryInterval: 1000 }
const defaultErrorHandlingConfig = { type: 'none', defaultValue: '' }
mock.module('../../nodes/code-node', () => ({ pythonTemplate, javascriptTemplate, defaultRetryConfig, defaultErrorHandlingConfig }))

const { CodeNodeConfig } = await import('./code-node-config')
type TreeNode = { type?: unknown, props: Record<string, unknown> }
function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}
const change = (node: TreeNode, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
const base = {
  language: 'python', code: 'print(1)',
  inputs: [{ id: 'input-1', name: 'query', value: '{{start.query}}', valueSource: 'Start' }],
  outputs: [{ id: 'first', name: 'result', type: 'string' }, { id: 'second', name: 'details', type: 'object' }],
  outputVariable: 'result', retry: { enabled: false, maxRetries: 3, retryInterval: 1000 }, errorHandling: { type: 'none' },
}
function render(config: Record<string, unknown> = base, inferredSchema?: Record<string, { kind: string }>) {
  const onConfigChange = mock(() => {}), onAddInput = mock(() => {})
  const tree = CodeNodeConfig({ config, onConfigChange, onAddInput, inferredSchema } as never) as TreeNode
  return { tree, onConfigChange, onAddInput }
}

 test('adds and deletes inputs and switches code language templates', () => {
  const { tree, onConfigChange, onAddInput } = render()
  expect(findAll(tree, (node) => node.props.children === 'Start')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'start.query')).toHaveLength(1)
  const addInput = findAll(tree, (node) => node.props.onClick === onAddInput)[0]
  ;(addInput.props.onClick as () => void)()
  expect(onAddInput).toHaveBeenCalledTimes(1)
  const deleteInput = findAll(tree, (node) => String(node.props.className).includes('opacity-0'))[0]
  ;(deleteInput.props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ inputs: [] }))

  const editor = findAll(tree, (node) => node.type === codeEditor)[0]
  ;(editor.props.onChange as (value: string) => void)('return 2')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ code: 'return 2' }))
  ;(editor.props.onLanguageChange as (value: string) => void)('javascript')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ language: 'javascript', code: javascriptTemplate }))
  ;(editor.props.onLanguageChange as (value: string) => void)('python')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ language: 'python', code: pythonTemplate }))
})

test('adds, updates, types, specifies, and deletes outputs', () => {
  const { tree, onConfigChange } = render()
  const addOutput = findAll(tree, (node) => node.props.className === 'h-6 w-6' && node.props.onClick)[1]
  ;(addOutput.props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: expect.arrayContaining([expect.objectContaining({ name: '', type: 'string' })]) }))

  const outputInputs = findAll(tree, (node) => node.props.placeholder === 'configCommon.variableNamePlaceholder')
  change(outputInputs[0], 'primary')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputVariable: 'primary', outputs: expect.arrayContaining([expect.objectContaining({ id: 'first', name: 'primary' })]) }))
  const selects = findAll(tree, (node) => node.props.value === 'string' || node.props.value === 'object')
  ;(selects[0].props.onValueChange as (value: string) => void)('number')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: expect.arrayContaining([expect.objectContaining({ id: 'first', type: 'number' })]) }))

  const spec = findAll(tree, (node) => node.type === typeSpecEditor)[0]
  expect(spec.props).toMatchObject({ value: { kind: 'object' }, lockKind: true })
  ;(spec.props.onChange as (value: object) => void)({ kind: 'object', fields: { name: { kind: 'string' } } })
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: expect.arrayContaining([expect.objectContaining({ id: 'second', typeSpec: expect.objectContaining({ kind: 'object' }) })]) }))

  const deletes = findAll(tree, (node) => node.props.className === 'h-6 w-6 text-destructive hover:text-destructive')
  ;(deletes[1].props.onClick as () => void)()
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ outputs: [base.outputs[0]] }))
  const single = render({ ...base, outputs: [base.outputs[0]] })
  const onlyDelete = findAll(single.tree, (node) => node.props.disabled === true)[0]
  ;(onlyDelete.props.onClick as () => void)()
  expect(single.onConfigChange).not.toHaveBeenCalled()
})

test('validates output names and renders declared and inferred structures', () => {
  const config = {
    ...base,
    outputs: [
      { id: 'blank', name: '', type: 'array', typeSpec: { kind: 'array', item: { kind: 'number' } } },
      { id: 'bad', name: 'bad name', type: 'string' },
      { id: 'dup-1', name: 'same', type: 'string' }, { id: 'dup-2', name: 'same', type: 'string' },
    ],
  }
  const { tree } = render(config, { result: { kind: 'object' }, count: { kind: 'number' } })
  for (const message of ['configCode.outputNameRequired', 'configCommon.invalidVariableNameFormat', 'configCode.duplicateVariableNamesInNode']) {
    expect(findAll(tree, (node) => node.props.children === message)).toHaveLength(1)
  }
  expect(findAll(tree, (node) => node.type === typeSpecEditor)[0].props.value).toEqual(config.outputs[0].typeSpec)
  expect(findAll(tree, (node) => node.props.children === 'configCommon.inferredSchema')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'type:object')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'type:number')).toHaveLength(1)

  const defaults = render({ language: 'python', code: '', inputs: [], outputVariable: 'legacy' })
  expect(findAll(defaults.tree, (node) => node.props.value === 'legacy')).toHaveLength(1)
  expect(findAll(defaults.tree, (node) => node.props.children === 'configCode.noInputVariables')).toHaveLength(1)
})

test('updates retry boundaries, error handling, and default output value', () => {
  const { tree, onConfigChange } = render({ ...base, retry: { enabled: true, maxRetries: 10, retryInterval: 60000 }, errorHandling: { type: 'default_value', defaultValue: 'fallback' } })
  const collapsible = findAll(tree, (node) => node.props.open === true && node.props.onOpenChange)[0]
  ;(collapsible.props.onOpenChange as (open: boolean) => void)(false)
  expect(setRetryOpen).toHaveBeenCalledWith(false)
  const retrySwitch = findAll(tree, (node) => node.props.checked === true)[0]
  ;(retrySwitch.props.onCheckedChange as (checked: boolean) => void)(false)
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ retry: { enabled: false, maxRetries: 10, retryInterval: 60000 } }))
  expect(setRetryOpen).toHaveBeenCalledWith(false)

  const numbers = findAll(tree, (node) => node.props.type === 'number')
  expect(numbers.map((node) => [node.props.min, node.props.max])).toEqual([[1, 10], [100, 60000]])
  change(numbers[0], '')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ retry: expect.objectContaining({ maxRetries: 1 }) }))
  change(numbers[1], '')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ retry: expect.objectContaining({ retryInterval: 1000 }) }))

  const radio = findAll(tree, (node) => node.props.value === 'default_value' && node.props.onValueChange)[0]
  ;(radio.props.onValueChange as (value: string) => void)('error_branch')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ errorHandling: expect.objectContaining({ type: 'error_branch' }) }))
  const textarea = findAll(tree, (node) => node.props.value === 'fallback')[0]
  change(textarea, 'safe result')
  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({ errorHandling: { type: 'default_value', defaultValue: 'safe result' } }))
})
