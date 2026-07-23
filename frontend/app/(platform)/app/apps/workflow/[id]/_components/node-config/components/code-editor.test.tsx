import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const editor = function Editor() {}
const writeText = mock(async () => {})
const setCopied = mock(() => {})
const setFullscreen = mock(() => {})
const setPortalMounted = mock(() => {})
let stateValues: unknown[] = []
let stateIndex = 0
let keydownListener: ((event: { key: string }) => void) | undefined

Object.defineProperty(globalThis, 'navigator', { value: { clipboard: { writeText } }, configurable: true })
Object.defineProperty(globalThis, 'document', { value: {
  body: { style: { overflow: '' } },
  addEventListener: (_type: string, listener: (event: { key: string }) => void) => { keydownListener = listener },
  removeEventListener: () => {},
}, configurable: true })
Object.defineProperty(globalThis, 'setTimeout', { value: (callback: () => void) => { callback(); return 1 }, configurable: true })

mock.module('react', () => ({
  memo: (value: unknown) => value,
  useCallback: (value: unknown) => value,
  useEffect: (effect: () => void | (() => void)) => effect()?.(),
  useRef: () => ({ current: null }),
  useState: (initial: unknown) => {
    const index = stateIndex++
    return [stateValues[index] ?? initial, [setCopied, setFullscreen, setPortalMounted][index]]
  },
}))
mock.module('react-dom', () => ({ createPortal: (node: unknown) => node }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('@monaco-editor/react', () => ({ default: editor }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'dark' }) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Copy: component, Check: component, Maximize2: component, X: component, HelpCircle: component }))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/select', () => ({ Select: component, SelectContent: component, SelectItem: component, SelectTrigger: component, SelectValue: component }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: component, TooltipContent: component, TooltipProvider: component, TooltipTrigger: component }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { CodeEditor } = await import('./code-editor')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}

function render(props: Record<string, unknown>, states: unknown[] = []) {
  stateValues = states
  stateIndex = 0
  return (CodeEditor as unknown as (props: Record<string, unknown>) => TreeNode)(props)
}

test('renders the selected language and forwards editor actions', async () => {
  const onChange = mock(() => {})
  const onLanguageChange = mock(() => {})
  const tree = render({ value: 'print(1)', language: 'python', onChange, onLanguageChange, minHeight: 240, className: 'custom' })
  const editors = findAll(tree, (node) => node.type === editor)

  expect(editors).toHaveLength(1)
  expect(editors[0].props).toMatchObject({ height: 240, language: 'python', value: 'print(1)', theme: 'vs-dark' })
  ;(editors[0].props.onChange as (value?: string) => void)(undefined)
  expect(onChange).toHaveBeenCalledWith('')

  const select = findAll(tree, (node) => node.type === component && node.props.value === 'python')[0]
  ;(select.props.onValueChange as (value: string | null) => void)('javascript')
  ;(select.props.onValueChange as (value: string | null) => void)(null)
  expect(onLanguageChange).toHaveBeenCalledWith('javascript')

  const buttons = findAll(tree, (node) => node.type === component && node.props.onClick)
  await (buttons[0].props.onClick as () => Promise<void>)()
  expect(writeText).toHaveBeenCalledWith('print(1)')
  expect(setCopied).toHaveBeenCalledWith(true)
  expect(setCopied).toHaveBeenCalledWith(false)
  ;(buttons[1].props.onClick as () => void)()
  expect(setFullscreen).toHaveBeenCalledWith(true)
})

test('renders a fixed JavaScript language label', () => {
  const tree = render({ value: 'return 1', language: 'javascript', onChange: () => {}, showLanguageSelector: false })
  expect(text(tree)).toContain('codeEditor.languageJavaScript')
  expect(findAll(tree, (node) => node.type === editor)[0].props.language).toBe('javascript')
})

test('registers missing Monaco languages and renders fullscreen Jinja editor', () => {
  const tree = render({ value: '{{ value }}', language: 'jinja2', onChange: () => {}, showLanguageSelector: false }, [true, true, true])
  const editors = findAll(tree, (node) => node.type === editor)
  expect(editors).toHaveLength(2)
  expect(editors.map((node) => [node.props.height, node.props.language])).toEqual([
    [200, 'jinja2'],
    ['100%', 'jinja2'],
  ])
  expect(text(tree)).toContain('codeEditor.jinja2Only')
  expect(text(tree)).toContain('codeEditor.templateEditorTitle')
  keydownListener?.({ key: 'Escape' })
  expect(setFullscreen).toHaveBeenCalledWith(false)

  const register = mock(() => {})
  const setMonarchTokensProvider = mock(() => {})
  const monaco = { languages: { getLanguages: () => [], register, setMonarchTokensProvider } }
  ;(editors[0].props.onMount as (instance: object, monaco: object) => void)({}, monaco)
  ;(editors[1].props.onMount as (instance: object, monaco: object) => void)({}, monaco)
  expect(register).toHaveBeenCalledTimes(2)
  expect(setMonarchTokensProvider).toHaveBeenCalledTimes(4)

  const close = findAll(tree, (node) => node.type === component && node.props.className === 'h-8 w-8')[1]
  ;(close.props.onClick as () => void)()
  expect(setFullscreen).toHaveBeenCalledWith(false)
})
