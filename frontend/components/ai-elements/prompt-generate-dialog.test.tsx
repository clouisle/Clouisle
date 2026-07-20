import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
let stateValues: unknown[] = []
let stateIndex = 0
const updates: unknown[][] = []
const effects: Array<() => void | (() => void)> = []
const generate = mock(() => Promise.resolve({}))
const toastError = mock(() => {})
const toastSuccess = mock(() => {})

function Dialog() {}
function DialogContent() {}
function DialogDescription() {}
function DialogFooter() {}
function DialogHeader() {}
function DialogTitle() {}
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
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Sparkles: element, Wand2: element, Check: element, Copy: element, ChevronDown: element, Loader2: element }))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error { isValidationError() { return false } },
  promptsApi: { generate },
  parsePromptSSEStream: async function* () { yield { type: 'content_delta', data: { delta: 'Generated prompt' } } },
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/components/ui/button', () => ({ Button: element }))
mock.module('@/components/ui/dialog', () => ({ Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle }))
mock.module('@/components/ui/field', () => ({ FieldError: element }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element }))
mock.module('@/components/ui/label', () => ({ Label: element }))
mock.module('@/components/ui/switch', () => ({ Switch: element }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: element, CollapsibleContent: element, CollapsibleTrigger: element }))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>) => errors,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: () => ({}),
  normalizeValidationErrors: () => ({}),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const { PromptGenerateDialog } = await import('./prompt-generate-dialog')

function render(values: unknown[] = []) {
  stateValues = values
  stateIndex = 0
  updates.length = 10
  for (let index = 0; index < 10; index++) updates[index] = []
  effects.length = 0
  return PromptGenerateDialog({ open: true, onOpenChange: mock(() => {}), onApply: mock(() => {}) }) as { props: Record<string, unknown> }
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return [((node as { props: Record<string, unknown> }).props.children)].flat().map(textContent).join('')
}

function find(node: unknown, predicate: (node: { props: Record<string, unknown> }) => boolean): { props: Record<string, unknown> } | undefined {
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined
  const elementNode = node as { props: Record<string, unknown> }
  if (predicate(elementNode)) return elementNode
  return [elementNode.props.children].flat().map((child) => find(child, predicate)).find(Boolean)
}

test('resets dialog state and rejects empty prompt generation', () => {
  const tree = render()
  effects.forEach((effect) => effect())
  const generateButton = find(tree, (node) => typeof node.props.onClick === 'function' && textContent(node).includes('generate'))
  generateButton?.props.onClick()

  expect(updates[0]).toContain('')
  expect(updates[7]).toContainEqual({ description: 'errors.descriptionRequired' })
  expect(generate).not.toHaveBeenCalled()
})

test('streams generated text and applies it after completion', async () => {
  const apply = mock(() => {})
  const close = mock(() => {})
  stateValues = ['Describe a helper', 'professional', 'balanced', false, true, false, 'Generated prompt', {}, false, false]
  stateIndex = 0
  updates.length = 10
  for (let index = 0; index < 10; index++) updates[index] = []
  const tree = PromptGenerateDialog({ open: true, onOpenChange: close, onApply: apply }) as { props: Record<string, unknown> }
  const generateButton = find(tree, (node) => typeof node.props.onClick === 'function' && textContent(node).includes('regenerate'))
  await generateButton?.props.onClick()

  expect(generate).toHaveBeenCalledWith(expect.objectContaining({ description: 'Describe a helper', language: 'zh' }))
  expect(updates[6]).toContain('Generated prompt')
  expect(updates[5]).toEqual([true, false])
})
