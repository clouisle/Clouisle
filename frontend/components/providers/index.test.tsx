import { expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

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
mock.module('./theme-provider', () => ({
  ThemeProvider: ({ children }: { children: ReactNode }) => <theme>{children}</theme>,
}))
mock.module('@/hooks/use-settings', () => ({
  SettingsProvider: ({ children }: { children: ReactNode }) => <settings>{children}</settings>,
}))
mock.module('@/contexts/site-settings-context', () => ({
  SiteSettingsProvider: ({ children }: { children: ReactNode }) => <site>{children}</site>,
}))
mock.module('@/components/dynamic-favicon', () => ({
  DynamicFavicon: () => <favicon />,
}))

const { Providers } = await import('./index')

type Tree = { type: unknown; props: Record<string, unknown> }

test('nests application providers and renders the dynamic favicon', () => {
  const tree = Providers({ children: 'content' }) as Tree
  const settings = tree.props.children as Tree
  const site = settings.props.children as Tree
  const [favicon, content] = site.props.children as [Tree, string]

  expect((tree.type as Function).name).toBe('ThemeProvider')
  expect((settings.type as Function).name).toBe('SettingsProvider')
  expect((site.type as Function).name).toBe('SiteSettingsProvider')
  expect((favicon.type as Function).name).toBe('DynamicFavicon')
  expect(content).toBe('content')
})
