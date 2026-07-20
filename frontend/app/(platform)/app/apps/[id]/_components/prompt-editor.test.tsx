import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const promptVariableEditor = function PromptVariableEditor() {}
const messageSquare = function MessageSquare() {}

mock.module('react', () => ({
  useCallback: (callback: unknown) => callback,
  useMemo: (factory: () => unknown) => factory(),
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => values ? `${key}:${values.query ?? values.name}` : key,
}))
mock.module('lucide-react', () => ({ MessageSquare: messageSquare }))
mock.module('@/components/prompt-variable-editor', () => ({ PromptVariableEditor: promptVariableEditor }))

const { PromptEditor } = await import('./prompt-editor')

type EditorNode = { type: unknown, props: Record<string, unknown> }

function render(value = 'Hello {{draft') {
  const onChange = mock(() => {})
  const onAddVariable = mock(() => {})
  const tree = PromptEditor({
    value,
    onChange,
    onAddVariable,
    variables: [{ name: 'audience', label: null }],
    placeholder: 'Write a prompt',
    className: 'custom',
  }) as unknown as EditorNode
  return { tree, onChange, onAddVariable }
}

test('maps variables and forwards editor callbacks and labels', () => {
  const { tree, onChange, onAddVariable } = render()

  expect(tree.type).toBe(promptVariableEditor)
  expect(tree.props).toMatchObject({
    value: 'Hello {{draft',
    placeholder: 'Write a prompt',
    className: 'custom',
    groupMode: 'system-user',
    systemGroupLabel: 'systemVariables',
    userGroupLabel: 'userVariables',
    allowCreateVariable: true,
    showUndefinedWarnings: true,
    noVariablesText: 'noVariables',
  })
  expect(tree.props.variables).toEqual([
    { ref: 'query', name: 'query', label: 'systemVars.query', isSystem: true, icon: messageSquare },
    { ref: 'audience', name: 'audience', label: undefined, isSystem: false },
  ])
  expect((tree.props.variableNotFoundText as (query: string) => string)('missing')).toBe('variableNotFound:missing')
  expect((tree.props.createVariableText as (name: string) => string)('topic')).toBe('createVariable:topic')

  ;(tree.props.onChange as (value: string) => void)('Updated')
  expect(onChange).toHaveBeenCalledWith('Updated')
  ;(tree.props.onUndefinedVariableClick as (name: string) => void)('missing')
  expect(onAddVariable).toHaveBeenCalledWith('missing', 'text')
})

test('creates a text variable and only replaces an unfinished token', () => {
  const active = render()
  ;(active.tree.props.onCreateVariable as (name: string) => void)('topic')
  expect(active.onAddVariable).toHaveBeenCalledWith('topic', 'text')
  expect(active.onChange).toHaveBeenCalledWith('Hello {{topic}}')

  const boundary = render('Hello {{draft value')
  ;(boundary.tree.props.onCreateVariable as (name: string) => void)('topic')
  expect(boundary.onAddVariable).toHaveBeenCalledWith('topic', 'text')
  expect(boundary.onChange).toHaveBeenCalledWith('Hello {{draft value')
})
