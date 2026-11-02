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
mock.module('@/components/watermark/global-watermark', () => ({ GlobalWatermark: () => null }))

const { default: ChatLayout } = await import('./layout')

test('wraps chat pages in a fixed viewport without changing document metadata', () => {
  // jsx-runtime is mocked above, so the returned tree is plain {type, props} objects.
  const tree = ChatLayout({ children: 'chat content' })
  const [viewport, watermark] = tree.props.children
  const providerName = typeof tree.type === 'function' ? tree.type.name : null

  expect(providerName).toBe('SiteSettingsProvider')
  expect(tree.props.skipTitleUpdate).toBe(true)
  expect(tree.props.skipFaviconUpdate).toBe(true)
  expect(viewport.props.className).toBe('fixed inset-0 bg-background')
  expect(viewport.props.children).toBe('chat content')
  expect(watermark.type.name).toBe('GlobalWatermark')
})
