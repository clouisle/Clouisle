import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('./input', () => ({
  Input: () => null,
}))

const { NumberInput } = await import('./number-input')

test('forwards numeric constraints and accepts empty or valid integer input', () => {
  const onChange = mock(() => {})
  const tree = NumberInput({ value: 2, onChange, min: 1, max: 3, placeholder: 'Count' }) as {
    props: Record<string, unknown>
  }
  const change = tree.props.onChange as (event: { target: { value: string } }) => void

  expect(tree.props.type).toBe('number')
  expect(tree.props.min).toBe(1)
  expect(tree.props.max).toBe(3)
  expect(tree.props.placeholder).toBe('Count')

  change({ target: { value: '' } })
  change({ target: { value: '12items' } })
  change({ target: { value: 'invalid' } })

  expect(onChange).toHaveBeenNthCalledWith(1, '')
  expect(onChange).toHaveBeenNthCalledWith(2, 12)
  expect(onChange).toHaveBeenCalledTimes(2)
})
