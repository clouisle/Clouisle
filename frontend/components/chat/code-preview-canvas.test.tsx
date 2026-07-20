import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateValues: unknown[] = []
let stateIndex = 0
const updates: unknown[][] = []
const effects: Array<() => void | (() => void)> = []
const writeText = mock(() => Promise.resolve())
const click = mock(() => {})

const element = function Element() {}
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    const setState = (value: T) => updates[index]?.push(value)
    return [stateValues[index] ?? initial, setState] as [T, typeof setState]
  },
  useMemo: <T,>(factory: () => T) => factory(),
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useCallback: <T,>(callback: T) => callback,
  useRef: <T,>(value: T) => ({ current: value }),
}))
mock.module('lucide-react', () => ({ Check: element, Copy: element, Download: element, Expand: element, Loader2: element, ZoomIn: element, ZoomOut: element, X: element }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }))
mock.module('streamdown', () => ({ Streamdown: element }))
mock.module('shiki', () => ({ bundledLanguages: { typescript: {}, html: {} } }))
mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/tabs', () => ({ Tabs: element, TabsContent: element, TabsList: element, TabsTrigger: element }))
mock.module('@/components/ai-elements/code-block', () => ({ CodeBlock: element }))

const { CodePreviewCanvas } = await import('./code-preview-canvas')

function render(preview: Record<string, unknown>, onClose = mock(() => {})) {
  stateIndex = 0
  stateValues = []
  updates.length = 2
  updates[0] = []
  updates[1] = []
  effects.length = 0
  return CodePreviewCanvas({ preview: preview as never, onClose }) as { props: Record<string, unknown> }
}

function findAll(node: unknown, predicate: (node: { props: Record<string, unknown> }) => boolean): Array<{ props: Record<string, unknown> }> {
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as { props: Record<string, unknown> }
  return [...(predicate(current) ? [current] : []), ...[current.props.children].flat().flatMap((child) => findAll(child, predicate))]
}

test('renders source code with Shiki for supported languages', () => {
  const tree = render({ kind: 'source', language: 'typescript', code: 'const value = 1' })
  const codeBlock = findAll(tree, (node) => node.props.showLineNumbers === true)[0]

  expect(codeBlock.props.language).toBe('typescript')
  expect(findAll(tree, (node) => node.props.value === 'preview')).toHaveLength(0)
})

test('builds a sandboxed HTML preview and supports copy, download, and close actions', async () => {
  const onClose = mock(() => {})
  const originalDocument = globalThis.document
  const originalUrl = globalThis.URL
  Object.assign(globalThis, {
    navigator: { clipboard: { writeText } },
    document: { createElement: () => ({ click }), body: { appendChild: mock(() => {}), removeChild: mock(() => {}) } },
    window: { setTimeout: mock(() => {}) },
    URL: { createObjectURL: mock(() => 'blob:preview'), revokeObjectURL: mock(() => {}) },
  })
  const tree = render({ kind: 'html', language: 'html', code: '<h1>Hello</h1>' }, onClose)
  const iframe = findAll(tree, (node) => node.props.sandbox === 'allow-scripts')[0]
  const buttons = findAll(tree, (node) => typeof node.props.onClick === 'function')

  expect(iframe.props.srcDoc).toBe('<h1>Hello</h1>')
  await buttons[0].props.onClick()
  buttons[1].props.onClick()
  buttons[2].props.onClick()

  expect(writeText).toHaveBeenCalledWith('<h1>Hello</h1>')
  expect(click).toHaveBeenCalledTimes(1)
  expect(onClose).toHaveBeenCalledTimes(1)
  expect(updates[0]).toContain(true)

  globalThis.document = originalDocument
  globalThis.URL = originalUrl
})

test('renders markdown previews and plain source fallback for unsupported languages', () => {
  const markdown = render({ kind: 'markdown', language: 'markdown', code: '# Hello' })
  const plainSource = render({ kind: 'source', language: 'unknown', code: 'raw content' })

  expect(findAll(markdown, (node) => node.props.children === '# Hello')).toHaveLength(1)
  expect(findAll(plainSource, (node) => node.props.children === 'raw content')).toHaveLength(1)
})
