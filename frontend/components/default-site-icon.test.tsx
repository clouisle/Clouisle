import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let mounted = false
let resolvedTheme = 'light'

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react', () => ({
  useState: () => [mounted, mock(() => {})],
  useEffect: (effect: () => void) => effect(),
}))
mock.module('next/image', () => ({ default: function Image() {} }))
mock.module('next-themes', () => ({
  useTheme: () => ({ resolvedTheme }),
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { DefaultSiteIcon } = await import('./default-site-icon')

test('uses a sized placeholder before the client mount', () => {
  mounted = false
  const tree = DefaultSiteIcon({ className: 'brand', width: 48, height: 24 }) as {
    props: Record<string, unknown>
  }

  expect(tree.type).toBe('div')
  expect(tree.props.className).toBe('bg-transparent brand')
  expect(tree.props.style).toEqual({ width: 48, height: 24 })
})

test('renders theme-aware icons with default and custom dimensions', () => {
  mounted = true
  resolvedTheme = 'dark'
  const dark = DefaultSiteIcon({ className: 'brand' }) as { props: Record<string, unknown> }
  resolvedTheme = 'light'
  const light = DefaultSiteIcon({ width: 40, height: 20 }) as { props: Record<string, unknown> }

  expect(dark.props.src).toBe('/clouisle-dark.svg')
  expect(dark.props.width).toBe(32)
  expect(dark.props.height).toBe(32)
  expect(dark.props.className).toBe('object-contain brand')
  expect(dark.props.priority).toBe(true)
  expect(light.props.src).toBe('/clouisle-light.svg')
  expect(light.props.width).toBe(40)
  expect(light.props.height).toBe(20)
})
