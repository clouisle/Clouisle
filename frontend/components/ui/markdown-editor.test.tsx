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
mock.module('@uiw/react-md-editor', () => ({ default: () => null }))
mock.module('next/dynamic', () => ({
  default: (loader: () => Promise<unknown>) => {
    void loader()
    return function Editor() {}
  },
}))
mock.module('next-themes', () => ({
  useTheme: () => ({ resolvedTheme }),
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

const { MarkdownEditor } = await import('./markdown-editor')

test('renders editor defaults before the theme mounts', () => {
  mounted = false
  resolvedTheme = 'dark'
  const onChange = mock(() => {})
  const tree = MarkdownEditor({ value: '# Draft', onChange }) as {
    props: Record<string, unknown>
  }
  const [editor] = tree.props.children as Array<{ props: Record<string, unknown> }>

  expect(tree.props.className).toContain('markdown-editor')
  expect(tree.props['data-color-mode']).toBe('light')
  expect(editor.props.value).toBe('# Draft')
  expect(editor.props.preview).toBe('live')
  expect(editor.props.height).toBe(200)
  expect(editor.props.textareaProps).toEqual({ placeholder: undefined })
})

test('forwards configured editor options and normalizes empty edits', () => {
  mounted = true
  resolvedTheme = 'dark'
  const onChange = mock(() => {})
  const tree = MarkdownEditor({
    value: 'content',
    onChange,
    placeholder: 'Write markdown',
    height: 320,
    preview: 'preview',
    className: 'compact',
  }) as { props: Record<string, unknown> }
  const [editor] = tree.props.children as Array<{ props: Record<string, unknown> }>

  ;(editor.props.onChange as (value?: string) => void)(undefined)
  ;(editor.props.onChange as (value?: string) => void)('updated')

  expect(tree.props['data-color-mode']).toBe('dark')
  expect(tree.props.className).toContain('compact')
  expect(editor.props.preview).toBe('preview')
  expect(editor.props.height).toBe(320)
  expect(editor.props.textareaProps).toEqual({ placeholder: 'Write markdown' })
  expect(onChange).toHaveBeenNthCalledWith(1, '')
  expect(onChange).toHaveBeenNthCalledWith(2, 'updated')
})
