import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

function Header() {}
function APIKeysClient() {}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('@/components/layout/header', () => ({ Header }))
mock.module('./_components', () => ({ APIKeysClient }))

const { default: APIKeysPage } = await import('./page')

test('renders the API keys client inside the dashboard layout', () => {
  const tree = APIKeysPage() as { props: Record<string, unknown> }
  const [header, content] = tree.props.children as Array<{ props: Record<string, unknown> }>

  expect(tree.props.className).toBe('flex h-full flex-col')
  expect((header.type as Function).name).toBe('Header')
  expect(content.props.className).toBe('flex flex-1 flex-col gap-4 overflow-auto p-4')
  expect(((content.props.children as { type: Function }).type as Function).name).toBe(
    'APIKeysClient',
  )
})
