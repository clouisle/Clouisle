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
mock.module('@base-ui/react/scroll-area', () => ({
  ScrollArea: {
    Root: () => null,
    Viewport: () => null,
    Scrollbar: () => null,
    Thumb: () => null,
    Corner: () => null,
  },
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { ScrollArea, ScrollBar } = await import('./scroll-area')

test('renders a scroll area with viewport, scrollbar, and corner', () => {
  const tree = ScrollArea({ className: 'panel', children: 'content' }) as {
    props: Record<string, unknown>
  }
  const content = JSON.stringify(tree.props.children)

  expect(tree.props['data-slot']).toBe('scroll-area')
  expect(tree.props.className).toBe('relative panel')
  const [, scrollbar, corner] = tree.props.children as Array<{
    type: unknown
    props: Record<string, unknown>
  }>

  expect(content).toContain('scroll-area-viewport')
  expect(content).toContain('content')
  expect((scrollbar.type as Function).name).toBe('ScrollBar')
  expect((corner.type as Function).name).toBe('Corner')
})

test('uses horizontal scrollbar orientation and forwards props', () => {
  const tree = ScrollBar({ orientation: 'horizontal', className: 'custom', id: 'bar' }) as {
    props: Record<string, unknown>
  }

  expect(tree.props['data-orientation']).toBe('horizontal')
  expect(tree.props.orientation).toBe('horizontal')
  expect(tree.props.className).toContain('custom')
  expect(tree.props.id).toBe('bar')
  expect(JSON.stringify(tree.props.children)).toContain('scroll-area-thumb')
})
