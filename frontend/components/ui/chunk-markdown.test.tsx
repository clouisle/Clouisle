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

const AuthenticatedImage = () => null
mock.module('@/components/chat/authenticated-media', () => ({ AuthenticatedImage }))

const { ChunkMarkdown } = await import('./chunk-markdown')

test('sanitizes untrusted Markdown and only renders protected KB media images', () => {
  const tree = ChunkMarkdown({ source: '<iframe src="javascript:alert(1)"></iframe>', className: 'compact' }) as {
    props: Record<string, unknown>
  }
  const preview = tree.props.children as { props: Record<string, unknown> }

  expect(tree.props.className).toContain('compact')
  expect(tree.props['data-color-mode']).toBe('dark')
  expect(preview.props.source).toContain('<iframe')
  expect(preview.props.rehypePlugins).toEqual([[rehypeSanitize]])
  const components = preview.props.components
  if (!components || typeof components !== 'object' || !('img' in components) || typeof components.img !== 'function') {
    throw new Error('Expected an image renderer')
  }
  const renderImage = components.img
  const protectedImage = renderImage({
    src: '/api/v1/knowledge-bases/kb-1/documents/doc-1/media/page.png',
    alt: 'Page',
    className: 'preview-image',
  })
  expect(protectedImage.type).toBe(AuthenticatedImage)
  expect(protectedImage.props).toMatchObject({
    src: '/api/v1/knowledge-bases/kb-1/documents/doc-1/media/page.png',
    alt: 'Page',
    className: 'preview-image',
  })
  const externalImage = renderImage({
    src: 'https://cdn.example.test/page.png',
    alt: 'External page',
  })
  expect(externalImage.type).toBe('span')
  expect(externalImage.props.children).toBe('External page')
  const externalApiImage = renderImage({
    src: 'https://cdn.example.test/api/v1/knowledge-bases/kb-1/documents/doc-1/media/page.png',
    alt: 'External API-looking image',
  })
  expect(externalApiImage.type).toBe('span')
  expect(externalApiImage.props.children).toBe('External API-looking image')
  const nonMediaApiUrl = renderImage({
    src: '/api/v1/knowledge-bases/kb-1/documents/doc-1/download',
    alt: 'Document',
  })
  expect(nonMediaApiUrl.type).toBe('span')
  expect(nonMediaApiUrl.props.children).toBe('Document')
})
