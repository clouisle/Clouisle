import { describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@base-ui/react/avatar', () => ({
  Avatar: {
    Root: (props: Record<string, unknown>) => jsx('avatar-root', props),
    Image: (props: Record<string, unknown>) => jsx('avatar-image', props),
    Fallback: (props: Record<string, unknown>) => jsx('avatar-fallback', props),
  },
}))

const { Avatar, AvatarBadge, AvatarFallback, AvatarGroup, AvatarGroupCount, AvatarImage } = await import('./avatar')

type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

describe('Avatar primitives', () => {
  test('renders every avatar building block', () => {
    const root = resolve(Avatar({ className: 'custom', size: 'lg', 'data-test': 'root' })) as Tree
    expect(root.type).toBe('avatar-root')
    expect(root.props['data-slot']).toBe('avatar')
    expect(root.props['data-size']).toBe('lg')
    expect(root.props['data-test']).toBe('root')
    expect(root.props.className).toContain('custom')

    const image = resolve(AvatarImage({ 'data-test': 'img' })) as Tree
    expect(image.type).toBe('avatar-image')
    expect(image.props['data-slot']).toBe('avatar-image')

    const fallback = resolve(AvatarFallback({ children: 'JD' })) as Tree
    expect(fallback.type).toBe('avatar-fallback')

    expect(resolve(AvatarBadge({ 'data-test': 'badge' }))).toMatchObject({ type: 'span', props: { 'data-test': 'badge' } })
    expect(resolve(AvatarGroup({ 'data-test': 'group' }))).toMatchObject({ type: 'div', props: { 'data-test': 'group' } })
    expect(resolve(AvatarGroupCount({ 'data-test': 'count' }))).toMatchObject({ type: 'div', props: { 'data-test': 'count' } })
  })
})
