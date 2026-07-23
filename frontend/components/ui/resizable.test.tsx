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
mock.module('react-resizable-panels', () => ({
  Group: () => null,
  Panel: () => null,
  Separator: () => null,
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { ResizablePanelGroup, ResizablePanel, ResizableHandle } = await import('./resizable')

test('forwards panel group and panel props with slots', () => {
  const group = ResizablePanelGroup({ direction: 'horizontal', className: 'layout' }) as {
    props: Record<string, unknown>
  }
  const panel = ResizablePanel({ minSize: 25 }) as { props: Record<string, unknown> }

  expect(group.props['data-slot']).toBe('resizable-panel-group')
  expect(group.props.className).toContain('layout')
  expect(group.props.direction).toBe('horizontal')
  expect(panel.props['data-slot']).toBe('resizable-panel')
  expect(panel.props.minSize).toBe(25)
})

test('renders an optional visual handle and forwards separator props', () => {
  const handle = ResizableHandle({ withHandle: true, className: 'splitter', id: 'resize' }) as {
    props: Record<string, unknown>
  }
  const withoutHandle = ResizableHandle({}) as { props: Record<string, unknown> }

  expect(handle.props['data-slot']).toBe('resizable-handle')
  expect(handle.props.className).toContain('splitter')
  expect(handle.props.id).toBe('resize')
  expect(JSON.stringify(handle.props.children)).toContain('h-6 w-1')
  expect(withoutHandle.props.children).toBeUndefined()
})
