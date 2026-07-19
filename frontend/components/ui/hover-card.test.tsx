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
mock.module('@base-ui/react/preview-card', () => ({
  PreviewCard: {
    Root: () => null,
    Trigger: () => null,
    Portal: () => null,
    Positioner: () => null,
    Popup: () => null,
  },
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { HoverCard, HoverCardTrigger, HoverCardContent } = await import('./hover-card')

test('forwards root and trigger props with hover-card slots', () => {
  const root = HoverCard({ open: true }) as { props: Record<string, unknown> }
  const trigger = HoverCardTrigger({ className: 'link', children: 'More' }) as {
    props: Record<string, unknown>
  }

  expect(root.props['data-slot']).toBe('hover-card')
  expect(root.props.open).toBe(true)
  expect(trigger.props['data-slot']).toBe('hover-card-trigger')
  expect(trigger.props.className).toBe('cursor-pointer link')
  expect(trigger.props.children).toBe('More')
})

test('uses default and custom content positioning', () => {
  const defaults = HoverCardContent({ children: 'Details' }) as { props: { children: unknown } }
  const custom = HoverCardContent({
    side: 'left',
    sideOffset: 8,
    align: 'start',
    alignOffset: 2,
  }) as {
    props: { children: { props: Record<string, unknown> } }
  }
  const defaultPositioner = defaults.props.children as { props: Record<string, unknown> }
  const customPositioner = custom.props.children

  expect(defaults.props.children).toBeDefined()
  expect(defaultPositioner.props.side).toBe('bottom')
  expect(defaultPositioner.props.sideOffset).toBe(4)
  expect(customPositioner.props.side).toBe('left')
  expect(customPositioner.props.align).toBe('start')
  expect(JSON.stringify(custom)).toContain('hover-card-content')
})
