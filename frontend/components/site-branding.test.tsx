import { describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))

let siteSettings: Record<string, unknown>
mock.module('@/contexts/site-settings-context', () => ({
  useSiteSettings: () => siteSettings,
}))
mock.module('next/image', () => ({ default: (props: Record<string, unknown>) => jsx('img', props) }))
mock.module('@/components/default-site-icon', () => ({
  DefaultSiteIcon: (props: Record<string, unknown>) => jsx('default-site-icon', props),
}))

const { SiteBranding } = await import('./site-branding')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  for (const child of Array.isArray(node) ? node : [node]) {
    const tree = resolve(child)
    if (!tree || typeof tree !== 'object' || !('type' in tree)) continue
    if (predicate(tree as Tree)) return tree as Tree
    try {
      return find((tree as Tree).props.children as ReactNode, predicate)
    } catch {
      // Continue searching sibling elements.
    }
  }
  throw new Error('Element not found')
}

function settings(overrides: Record<string, unknown> = {}) {
  siteSettings = {
    loading: false,
    settings: {
      site_name: '',
      site_icon: '',
      site_description: '',
      theme_branding_display: 'full',
      ...overrides,
    },
  }
}

describe('SiteBranding', () => {
  test('renders configured branding image, name, and requested description', () => {
    settings({
      site_name: 'Acme Docs',
      site_icon: '/acme.svg',
      site_description: 'Internal knowledge',
    })

    const tree = SiteBranding({ size: 'lg', showDescription: true, className: 'hero' })
    const image = find(tree, (node) => node.type === 'img')

    expect(image.props).toMatchObject({
      src: '/acme.svg',
      alt: 'Acme Docs',
      width: 64,
      height: 64,
      unoptimized: true,
    })
    expect(find(tree, (node) => node.type === 'h1').props).toMatchObject({
      className: 'font-bold text-3xl',
      children: 'Acme Docs',
    })
    expect(find(tree, (node) => node.type === 'p').props).toMatchObject({
      className: 'text-muted-foreground text-center text-base',
      children: 'Internal knowledge',
    })
    expect((tree as Tree).props.className).toContain('hero')
    expect(find(tree, (node) => String(node.props.className).includes('size-16')).props.className).toContain('bg-primary')
  })

  test('uses the default icon and name without an unrequested description', () => {
    settings({ site_description: 'Hidden by default' })

    const tree = SiteBranding({})
    expect(find(tree, (node) => node.type === 'default-site-icon').props).toMatchObject({
      width: 48,
      height: 48,
      className: 'size-full',
    })
    expect(find(tree, (node) => node.type === 'h1').props.children).toBe('Clouisle')
    expect(() => find(tree, (node) => node.type === 'p')).toThrow('Element not found')
  })

  test('honors hidden branding and renders the loading skeleton first', () => {
    settings({ theme_branding_display: 'hidden' })
    expect(SiteBranding({})).toBeNull()

    siteSettings.loading = true
    const loading = SiteBranding({ size: 'sm', className: 'auth' }) as Tree
    expect(loading.props.className).toContain('auth')
    expect(find(loading, (node) => String(node.props.className).includes('size-8')).props.className).toContain('animate-pulse')
  })
})
