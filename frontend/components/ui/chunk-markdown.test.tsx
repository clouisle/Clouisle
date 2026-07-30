import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const rehypeSanitize = mock(() => {})

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
  useState: () => [true, mock(() => {})],
  useEffect: (effect: () => void) => effect(),
}))
mock.module('@uiw/react-markdown-preview', () => ({ default: () => null }))
mock.module('rehype-sanitize', () => ({ default: rehypeSanitize }))
mock.module('next/dynamic', () => ({
  default: (loader: () => Promise<unknown>) => {
    void loader()
    return function MarkdownPreview() {}
  },
}))
mock.module('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'dark' }),
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { ChunkMarkdown } = await import('./chunk-markdown')

test('renders with the preview-only package and sanitizes untrusted Markdown', () => {
  const tree = ChunkMarkdown({ source: '<iframe src="javascript:alert(1)"></iframe>', className: 'compact' }) as {
    props: Record<string, unknown>
  }
  const preview = tree.props.children as { props: Record<string, unknown> }

  expect(tree.props.className).toContain('compact')
  expect(tree.props['data-color-mode']).toBe('dark')
  expect(preview.props.source).toContain('<iframe')
  expect(preview.props.rehypePlugins).toEqual([[rehypeSanitize]])
})
