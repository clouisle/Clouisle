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
mock.module('class-variance-authority', () => ({
  cva: () => (values: Record<string, unknown>) => `variant:${JSON.stringify(values)}`,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))
mock.module('@/components/ui/button', () => ({ Button: () => null }))
mock.module('@/components/ui/input', () => ({ Input: () => null }))
mock.module('@/components/ui/textarea', () => ({ Textarea: () => null }))

const {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
  InputGroupTextarea,
} = await import('./input-group')

test('renders group controls with their defaults and forwarded props', () => {
  const group = InputGroup({ className: 'search', id: 'group' }) as {
    props: Record<string, unknown>
  }
  const button = InputGroupButton({ children: 'Go' }) as { props: Record<string, unknown> }
  const input = InputGroupInput({ placeholder: 'Search' }) as { props: Record<string, unknown> }
  const textarea = InputGroupTextarea({ rows: 3 }) as { props: Record<string, unknown> }
  const text = InputGroupText({ children: 'Hint', className: 'help' }) as {
    props: Record<string, unknown>
  }

  expect(group.props['data-slot']).toBe('input-group')
  expect(group.props.className).toContain('search')
  expect(group.props.id).toBe('group')
  expect(button.props.type).toBe('button')
  expect(button.props.variant).toBe('ghost')
  expect(button.props['data-size']).toBe('xs')
  expect(input.props['data-slot']).toBe('input-group-control')
  expect(input.props.placeholder).toBe('Search')
  expect(textarea.props.rows).toBe(3)
  expect(text.props.className).toContain('help')
})

test('focuses the input from non-button addons but preserves button clicks', () => {
  const addon = InputGroupAddon({ align: 'block-end' }) as { props: Record<string, unknown> }
  const focus = mock(() => {})
  const querySelector = mock(() => ({ focus }))
  const currentTarget = { parentElement: { querySelector } }

  addon.props.onClick({ target: { closest: () => null }, currentTarget })
  addon.props.onClick({ target: { closest: () => ({}) }, currentTarget })

  expect(addon.props['data-slot']).toBe('input-group-addon')
  expect(addon.props['data-align']).toBe('block-end')
  expect(addon.props.className).toContain('block-end')
  expect(querySelector).toHaveBeenCalledTimes(1)
  expect(focus).toHaveBeenCalledTimes(1)
})
