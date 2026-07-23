import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let theme = 'system'
let resolvedTheme = 'dark'
const toast = mock(() => {})

mock.module('react/jsx-runtime', () => ({
  jsx,
  jsxs: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('react/jsx-dev-runtime', () => ({
  jsxDEV: jsx,
  Fragment: Symbol.for('react.fragment'),
}))
mock.module('next-themes', () => ({
  useTheme: () => ({ theme, resolvedTheme }),
}))
mock.module('sonner', () => ({
  Toaster: () => null,
  toast,
}))

const { Toaster, toast: exportedToast } = await import('./sonner')

test('uses the resolved system theme and preserves toaster options', () => {
  const tree = Toaster({ position: 'top-right' }) as {
    type: unknown
    props: Record<string, unknown>
  }

  expect(tree.props.theme).toBe('dark')
  expect(tree.props.position).toBe('top-right')
  expect(tree.props.className).toBe('toaster group')
  expect(JSON.stringify(tree.props.toastOptions)).toContain('actionButton')
})

test('uses explicit themes and re-exports toast', () => {
  theme = 'light'
  resolvedTheme = 'dark'
  const tree = Toaster({}) as { props: Record<string, unknown> }

  expect(tree.props.theme).toBe('light')
  expect(exportedToast).toBe(toast)
})
