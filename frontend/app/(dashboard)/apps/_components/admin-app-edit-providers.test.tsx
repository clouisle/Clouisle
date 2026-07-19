import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

function TeamProvider() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('@/contexts/team-context', () => ({ TeamProvider }))

const { AdminAppEditProviders } = await import('./admin-app-edit-providers')

test('provides team state to the admin app editor children', () => {
  const tree = AdminAppEditProviders({ children: 'editor' }) as { props: Record<string, unknown> }

  expect((tree.type as Function).name).toBe('TeamProvider')
  expect(tree.props.children).toBe('editor')
})
