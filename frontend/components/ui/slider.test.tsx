import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const useMemo = <T,>(factory: () => T) => factory()

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({ useMemo }))
mock.module('@base-ui/react/slider', () => ({
  Slider: {
    Root: () => null,
    Control: () => null,
    Track: () => null,
    Indicator: () => null,
    Thumb: () => null,
  },
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { Slider } = await import('./slider')

test('uses provided values and renders one thumb per value', () => {
  const tree = Slider({ value: [20, 80], min: 10, max: 90, className: 'range' }) as {
    props: Record<string, unknown>
  }
  const control = tree.props.children as { props: Record<string, unknown> }

  expect(tree.props['data-slot']).toBe('slider')
  expect(tree.props.min).toBe(10)
  expect(tree.props.max).toBe(90)
  expect(tree.props.thumbAlignment).toBe('edge-client-only')
  expect(control.props.className).toContain('range')
  const [, thumbs] = control.props.children as [unknown, unknown[]]

  expect(JSON.stringify(thumbs)).toContain('slider-thumb')
  expect(thumbs).toHaveLength(2)
})

test('derives thumbs from defaults or the min/max fallback', () => {
  const defaults = Slider({ defaultValue: [30] }) as { props: Record<string, unknown> }
  const fallback = Slider({ min: 5, max: 15 }) as { props: Record<string, unknown> }

  const [, defaultThumbs] = (
    defaults.props.children as { props: { children: [unknown, unknown[]] } }
  ).props.children
  const [, fallbackThumbs] = (
    fallback.props.children as { props: { children: [unknown, unknown[]] } }
  ).props.children

  expect(defaultThumbs).toHaveLength(1)
  expect(fallbackThumbs).toHaveLength(2)
})
