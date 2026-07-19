import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

function SiteSettingsProvider() {}

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('@/contexts/site-settings-context', () => ({ SiteSettingsProvider }))

const { default: ChatLayout } = await import('./layout')

test('wraps chat pages in a fixed viewport without changing document metadata', () => {
  const tree = ChatLayout({ children: 'chat content' }) as { props: Record<string, unknown> }
  const viewport = tree.props.children as { props: Record<string, unknown> }

  expect((tree.type as Function).name).toBe('SiteSettingsProvider')
  expect(tree.props.skipTitleUpdate).toBe(true)
  expect(tree.props.skipFaviconUpdate).toBe(true)
  expect(viewport.props.className).toBe('fixed inset-0 bg-background')
  expect(viewport.props.children).toBe('chat content')
})
