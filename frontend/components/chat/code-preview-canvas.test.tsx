import { beforeEach, expect, mock, test } from 'bun:test'

type Props = Record<string, unknown>
type Node = { type: unknown; props: Props }

type StateSetter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Props = {}) => ({ type, props })
const icon = (name: string) => (props: Props) => jsx(name, props)
const stateValues: unknown[] = []
const effects: Array<() => void | (() => void)> = []
const memos: unknown[] = []
const refValues: unknown[] = []

let stateIndex = 0
let memoIndex = 0
let refIndex = 0
let activeTab = ''
let lastBlobParts: unknown[] = []
let createdUrl = ''
let appendedLink: { href?: string; download?: string; clicked?: boolean } | null = null

function setStateValue<T>(index: number, value: T | ((current: T) => T)) {
  stateValues[index] = typeof value === 'function'
    ? (value as (current: T) => T)(stateValues[index] as T)
    : value
}

function resolve(node: unknown): unknown {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const element = node as Node
  return typeof element.type === 'function'
    ? resolve((element.type as (props: Props) => unknown)(element.props))
    : element
}

function walk(node: unknown): Node[] {
  const resolved = resolve(node)
  if (Array.isArray(resolved)) return resolved.flatMap(walk)
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return []
  const element = resolved as Node
  return [element, ...walk(element.props.children)]
}

function text(node: unknown): string {
  const resolved = resolve(node)
  if (typeof resolved === 'string' || typeof resolved === 'number') return String(resolved)
  if (Array.isArray(resolved)) return resolved.map(text).join('')
  if (!resolved || typeof resolved !== 'object' || !('props' in resolved)) return ''
  return text((resolved as Node).props.children)
}

function render(preview: Props, initialStates: unknown[] = [], initialRefs: unknown[] = []) {
  stateIndex = 0
  memoIndex = 0
  refIndex = 0
  stateValues.length = 0
  stateValues.push(...initialStates)
  effects.length = 0
  memos.length = 0
  refValues.length = 0
  refValues.push(...initialRefs)
  activeTab = preview.kind === 'source' ? 'source' : 'preview'
  return CodePreviewCanvas({ preview, onClose: close })
}

function findByAriaLabel(tree: unknown, label: string) {
  return walk(tree).find((node) => resolve(node.props['aria-label']) === label)
}

function tabNames(tree: unknown) {
  return walk(tree)
    .filter((node) => node.type === 'tabs-trigger')
    .map((node) => node.props.value)
}

function click(node: Node | undefined) {
  expect(node).toBeDefined()
  ;(node?.props.onClick as () => void)()
}

function Tabs(props: Props) {
  activeTab = props.value as string
  return jsx('tabs', props)
}
function TabsList(props: Props) { return jsx('tabs-list', props) }
function TabsTrigger(props: Props) { return jsx('tabs-trigger', props) }
function TabsContent(props: Props) {
  return props.value === activeTab ? jsx('tabs-content', props) : null
}
function Button(props: Props) { return jsx('button', props) }
function CodeBlock(props: Props) { return jsx('code-block', props) }
function Streamdown(props: Props) { return jsx('streamdown', props) }

const close = mock(() => {})
const writeText = mock(async () => {})

class TestBlob {
  parts: unknown[]
  type: string

  constructor(parts: unknown[], options?: { type?: string }) {
    this.parts = parts
    this.type = options?.type ?? ''
    lastBlobParts = parts
  }
}

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
  useMemo: <T,>(factory: () => T) => {
    const index = memoIndex++
    memos[index] = factory()
    return memos[index] as T
  },
  useRef: <T,>(current: T) => {
    const index = refIndex++
    if (refValues[index] === undefined) refValues[index] = current
    return {
      get current() { return refValues[index] as T },
      set current(value: T) { refValues[index] = value },
    }
  },
  useState: <T,>(initial: T): [T, StateSetter<T>] => {
    const index = stateIndex++
    if (stateValues[index] === undefined) stateValues[index] = initial
    return [stateValues[index] as T, (value) => setStateValue(index, value)]
  },
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${values.error}` : key,
}))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))
mock.module('lucide-react', () => ({
  Check: icon('Check'),
  Copy: icon('Copy'),
  Download: icon('Download'),
  Expand: icon('Expand'),
  Loader2: icon('Loader2'),
  ZoomIn: icon('ZoomIn'),
  ZoomOut: icon('ZoomOut'),
  X: icon('X'),
}))
mock.module('streamdown', () => ({ Streamdown }))
mock.module('shiki', () => ({ bundledLanguages: { javascript: {}, typescript: {}, html: {}, xml: {}, css: {}, markdown: {} } }))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: (props: Props) => jsx('tooltip', props),
  TooltipTrigger: ({ render, children, ...props }: Props) => {
    const element = render as Node | undefined
    return element
      ? { type: element.type, props: { ...element.props, ...props, ...(children !== undefined ? { children } : {}) } }
      : jsx('span', { ...props, children })
  },
  TooltipContent: (props: Props) => jsx('tooltip-content', props),
}))
mock.module('@/components/ui/tabs', () => ({ Tabs, TabsContent, TabsList, TabsTrigger }))
mock.module('@/components/ai-elements/code-block', () => ({ CodeBlock }))
const mermaidApi = {
  initialize: mock(() => {}),
  render: mock(async () => ({ svg: '<svg><text>ok</text></svg>' })),
}

mock.module('mermaid', () => ({ default: mermaidApi }))

const { CodePreviewCanvas } = await import('./code-preview-canvas')

beforeEach(() => {
  close.mockClear()
  writeText.mockClear()
  mermaidApi.initialize.mockClear()
  mermaidApi.render.mockClear()
  mermaidApi.render.mockImplementation(async () => ({ svg: '<svg><text>ok</text></svg>' }))
  lastBlobParts = []
  createdUrl = 'blob:test-url'
  appendedLink = null
  globalThis.navigator = { clipboard: { writeText } } as Navigator
  globalThis.Blob = TestBlob as typeof Blob
  globalThis.URL.createObjectURL = mock(() => createdUrl)
  globalThis.URL.revokeObjectURL = mock(() => {})
  globalThis.document = {
    body: {
      appendChild: (link: { href?: string; download?: string; clicked?: boolean }) => { appendedLink = link },
      removeChild: () => {},
    },
    createElement: () => ({ click() { this.clicked = true } }),
  } as unknown as Document
  globalThis.window = { setTimeout: (callback: () => void) => { callback(); return 1 } } as unknown as Window & typeof globalThis
})

test('renders iframe previews and escapes javascript closing script tags', () => {
  const tree = render({ id: 'js', language: 'javascript', kind: 'javascript', code: 'console.log("x")</script><script>alert(1)' })
  const iframe = walk(tree).find((node) => node.type === 'iframe')

  expect(tabNames(tree)).toEqual(['preview', 'source'])
  expect(iframe?.props.sandbox).toBe('allow-scripts')
  expect(iframe?.props.srcDoc).toContain('<\\/script><script>alert(1)')
  expect(text(tree)).toContain('previewScriptsEnabled')
})

test('shows markdown preview without iframe script notice', () => {
  const tree = render({ id: 'md', language: 'markdown', kind: 'markdown', code: '# Hello' })

  expect(walk(tree).some((node) => node.type === 'streamdown')).toBe(true)
  expect(walk(tree).some((node) => node.type === 'iframe')).toBe(false)
  expect(text(tree)).not.toContain('previewScriptsEnabled')
})

test('source previews start on source tab and use supported language highlighting', () => {
  const tree = render({ id: 'ts', language: 'typescript', kind: 'source', code: 'const x = 1' })
  const block = walk(tree).find((node) => node.type === 'code-block')

  expect(tabNames(tree)).toEqual(['source'])
  expect(activeTab).toBe('source')
  expect(block?.props).toMatchObject({ code: 'const x = 1', language: 'typescript', showLineNumbers: true })
})

test('unsupported source language falls back to plain preformatted code', () => {
  const tree = render({ id: 'txt', language: 'brainfuck', kind: 'source', code: '++--' })

  expect(walk(tree).some((node) => node.type === 'code-block')).toBe(false)
  expect(text(tree)).toContain('++--')
})

test('copy toggles copied state and close delegates to parent', async () => {
  const tree = render({ id: 'html', language: 'html', kind: 'html', code: '<h1>Hi</h1>' })

  await (findByAriaLabel(tree, 'copy')?.props.onClick as () => Promise<void>)()
  click(findByAriaLabel(tree, 'closeCodePreview'))

  expect(writeText).toHaveBeenCalledWith('<h1>Hi</h1>')
  expect(stateValues[0]).toBe(false)
  expect(close).toHaveBeenCalled()
})

test('downloads with language extension and revokes object url', () => {
  const tree = render({ id: 'py', language: 'python', kind: 'source', code: 'print("hi")' })

  click(findByAriaLabel(tree, 'mermaidDownloadLabel'))

  expect(lastBlobParts).toEqual(['print("hi")'])
  expect(appendedLink).toMatchObject({ href: createdUrl, download: 'code.py', clicked: true })
  expect(URL.revokeObjectURL).toHaveBeenCalledWith(createdUrl)
})

test('wraps svg and css previews in runnable documents', () => {
  const svgTree = render({ id: 'svg', language: 'svg', kind: 'svg', code: '<svg><circle /></svg>' })
  const svgIframe = walk(svgTree).find((node) => node.type === 'iframe')
  const cssTree = render({ id: 'css', language: 'css', kind: 'css', code: 'h1 { color: red; }' })
  const cssIframe = walk(cssTree).find((node) => node.type === 'iframe')

  expect(svgIframe?.props.srcDoc).toContain('<body><svg><circle /></svg></body>')
  expect(cssIframe?.props.srcDoc).toContain('CSS Preview')
  expect(cssIframe?.props.srcDoc).toContain('h1 { color: red; }')
})

test('resets active tab when preview payload changes', () => {
  render({ id: 'html', language: 'html', kind: 'html', code: '<p />' })
  effects.forEach((effect) => effect())
  render({ id: 'source', language: 'javascript', kind: 'source', code: 'alert(1)' })
  effects.forEach((effect) => effect())

  expect(stateValues[1]).toBe('source')
})

test('renders mermaid loading state without script iframe', () => {
  const tree = render({ id: 'mmd', language: 'mermaid', kind: 'mermaid', code: 'graph TD; A-->B;' })

  expect(text(tree)).toContain('mermaidRendering')
  expect(walk(tree).some((node) => node.type === 'iframe')).toBe(false)
  expect(tabNames(tree)).toEqual(['preview', 'source'])
})



test('mermaid render effect initializes the renderer and stores rendered svg', async () => {
  const tree = render({ id: 'mmd', language: 'mermaid', kind: 'mermaid', code: 'graph TD; A-->B;' })
  walk(tree)
  const cleanup = effects[1]()
  await Bun.sleep(0)

  expect(mermaidApi.initialize).toHaveBeenCalledWith({ startOnLoad: false, securityLevel: 'strict', theme: 'dark' })
  expect(mermaidApi.render).toHaveBeenCalledWith(expect.stringContaining('mermaid-preview-'), 'graph TD; A-->B;')
  expect(stateValues[2]).toBe('<svg><text>ok</text></svg>')
  expect(stateValues[4]).toBe(false)
  expect(cleanup).toBeFunction()
})

test('mermaid render effect reports errors and ignores results after cleanup', async () => {
  mermaidApi.render.mockImplementationOnce(async () => { throw new Error('bad chart') })
  const errorTree = render({ id: 'bad', language: 'mermaid', kind: 'mermaid', code: 'invalid' })
  walk(errorTree)
  effects[1]()
  await Bun.sleep(0)

  expect(stateValues[3]).toBe('bad chart')
  expect(stateValues[4]).toBe(false)

  let finishRender: ((value: { svg: string }) => void) | undefined
  mermaidApi.render.mockImplementationOnce(() => new Promise((resolve) => { finishRender = resolve }))
  const slowTree = render({ id: 'slow', language: 'mermaid', kind: 'mermaid', code: 'graph TD' })
  walk(slowTree)
  const cleanup = effects[1]() as () => void
  await Promise.resolve()
  cleanup()
  finishRender?.({ svg: '<svg>late</svg>' })
  await Promise.resolve()

  expect(stateValues[2]).toBe('')
  expect(stateValues[4]).toBe(true)
})

test('mermaid controls zoom, fit, pan, and download svg', () => {
  const svgElement = { getBoundingClientRect: () => ({ width: 400, height: 200 }) }
  const diagram = {
    style: { transform: '', transition: '' },
    querySelector: () => svgElement,
  }
  const viewport = { getBoundingClientRect: () => ({ width: 248, height: 148 }) }
  const tree = render(
    { id: 'mmd', language: 'mermaid', kind: 'mermaid', code: 'graph TD; A-->B;' },
    [false, 'preview', '<svg><text>ok</text></svg>', null, false, 1, { x: 0, y: 0 }, false, '', ''],
    [undefined, viewport, diagram]
  )
  const nodes = walk(tree)
  const viewportNode = nodes.find((node) => node.props.onPointerDown)
  const control = (label: string) => nodes.find((node) => resolve(node.props['aria-label']) === label)
  const pointerTarget = {
    setPointerCapture: mock(() => {}),
    releasePointerCapture: mock(() => {}),
  }

  click(control('mermaidZoomIn'))
  expect(stateValues[5]).toBe(1.1)
  click(control('mermaidZoomOut'))
  expect(stateValues[5]).toBe(1)
  click(control('mermaidFitToView'))
  expect(stateValues[5]).toBe(0.5)
  expect(stateValues[6]).toEqual({ x: 0, y: 0 })

  click(control('mermaidDownload'))
  expect(lastBlobParts).toEqual(['<svg><text>ok</text></svg>'])
  expect(appendedLink).toMatchObject({ download: 'diagram.svg', clicked: true })

  ;(viewportNode?.props.onPointerDown as (event: Props) => void)({ clientX: 10, clientY: 20, pointerId: 7, currentTarget: pointerTarget })
  expect(stateValues[7]).toBe(true)
  expect(pointerTarget.setPointerCapture).toHaveBeenCalledWith(7)
  expect(diagram.style.transition).toBe('none')

  stateIndex = 0
  memoIndex = 0
  refIndex = 0
  const draggingTree = CodePreviewCanvas({
    preview: { id: 'mmd', language: 'mermaid', kind: 'mermaid', code: 'graph TD; A-->B;' },
    onClose: close,
  })
  const draggingViewport = walk(draggingTree).find((node) => node.props.onPointerMove)
  ;(draggingViewport?.props.onPointerMove as (event: Props) => void)({ clientX: 40, clientY: 60 })
  expect(diagram.style.transform).toBe('translate(30px, 40px) scale(0.5)')

  ;(draggingViewport?.props.onPointerUp as (event: Props) => void)({ clientX: 40, clientY: 60, pointerId: 7, currentTarget: pointerTarget })
  expect(stateValues[6]).toEqual({ x: 30, y: 40 })
  expect(stateValues[7]).toBe(false)
  expect(pointerTarget.releasePointerCapture).toHaveBeenCalledWith(7)
  expect(diagram.style.transition).toBe('')

  stateIndex = 0
  memoIndex = 0
  refIndex = 0
  const settledTree = CodePreviewCanvas({
    preview: { id: 'mmd', language: 'mermaid', kind: 'mermaid', code: 'graph TD; A-->B;' },
    onClose: close,
  })
  walk(settledTree)
  effects.at(-1)?.()
  expect(diagram.style.transform).toBe('translate(30px, 40px) scale(0.5)')
})

test('mermaid error state renders translated renderer message', () => {
  const tree = render(
    { id: 'bad', language: 'mermaid', kind: 'mermaid', code: 'invalid' },
    [false, 'preview', '', 'syntax error', false]
  )

  expect(text(tree)).toContain('mermaidError:syntax error')
})
