import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const editor = function PromptVariableEditor() {}

mock.module('react', () => ({ useMemo: (factory: () => unknown) => factory() }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@/components/prompt-variable-editor', () => ({ PromptVariableEditor: editor }))

const { PromptTextarea } = await import('./prompt-textarea')

test('maps workflow variables and forwards editor options', () => {
  const onChange = mock(() => {})
  const tree = PromptTextarea({
    value: 'Hello {{input.name}}',
    onChange,
    variables: [{
      id: 'input.name',
      name: 'name',
      type: 'string',
      group: 'input',
      groupLabel: 'Input',
      isSystem: false,
    }],
    placeholder: 'Enter prompt',
    className: 'custom',
  }) as { type: unknown, props: Record<string, unknown> }

  expect(tree.type).toBe(editor)
  expect(tree.props).toMatchObject({
    value: 'Hello {{input.name}}',
    onChange,
    placeholder: 'Enter prompt',
    className: 'custom',
    groupMode: 'custom',
    minHeightClassName: 'min-h-20',
  })
  expect(tree.props.variables).toEqual([{
    ref: 'input.name',
    name: 'name',
    label: 'Input',
    groupId: 'input',
    groupLabel: 'Input',
    isSystem: false,
    type: 'string',
  }])
  ;(tree.props.onChange as (value: string) => void)('Updated')
  expect(onChange).toHaveBeenCalledWith('Updated')
})

test('supports custom minimum height and empty variables', () => {
  const tree = PromptTextarea({
    value: '',
    onChange: () => {},
    variables: [],
    minHeight: 'min-h-40',
  }) as { props: Record<string, unknown> }

  expect(tree.props.variables).toEqual([])
  expect(tree.props.minHeightClassName).toBe('min-h-40')
  expect(tree.props.editorClassName).toContain('text-xs')
})
