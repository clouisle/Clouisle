import { beforeEach, expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const component = function Component() {}
const importUrl = mock(async () => ({ id: 'doc-1' }))
const push = mock(() => {})
const toastSuccess = mock(() => {})
let normalizedErrors: Record<string, string> = {}
let stateValues: unknown[] = []
let stateIndex = 0
let updates: unknown[][] = []
let effects: Array<() => void | (() => void)> = []

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    return [stateValues[index] ?? initial, (value: unknown) => updates[index].push(value)] as const
  },
  useMemo: <T,>(factory: () => T) => factory(),
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void | (() => void)) => effects.push(effect),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('lucide-react', () => ({ Link: component, Loader2: component }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({ knowledgeBasesApi: { importUrl } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  getValidationSummaryEntries: (errors: Record<string, string>, fields: string[]) =>
    fields.flatMap((field) => errors[field] ? [[field, errors[field]]] : []),
  normalizeValidationErrors: () => normalizedErrors,
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))
mock.module('@/components/ui/button', () => ({ Button: component }))
mock.module('@/components/ui/input', () => ({ Input: component }))
mock.module('@/components/ui/label', () => ({ Label: component }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: component,
  DialogContent: component,
  DialogDescription: component,
  DialogFooter: component,
  DialogHeader: component,
  DialogTitle: component,
}))
mock.module('@/components/ui/field', () => ({ Field: component, FieldError: component }))

const { ImportUrlDialog } = await import('./import-url-dialog')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function render(values: unknown[] = [], open = true, onOpenChange = mock(() => {}), onSuccess = mock(() => {})) {
  stateValues = values
  stateIndex = 0
  updates = Array.from({ length: 4 }, () => [])
  effects = []
  const tree = ImportUrlDialog({ open, onOpenChange, knowledgeBaseId: 'kb-1', onSuccess }) as TreeNode
  return { tree, onOpenChange, onSuccess }
}

function find(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode | undefined {
  if (Array.isArray(node)) return node.map((child) => find(child, predicate)).find(Boolean)
  if (!node || typeof node !== 'object' || !('props' in node)) return undefined
  const current = node as TreeNode
  if (predicate(current)) return current
  return find(current.props.children, predicate)
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textContent).join('')
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return textContent((node as TreeNode).props.children)
}

function submit(tree: TreeNode) {
  const form = find(tree, (node) => node.type === 'form')
  return (form?.props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault() {} })
}

beforeEach(() => {
  importUrl.mockClear()
  importUrl.mockImplementation(async () => ({ id: 'doc-1' }))
  push.mockClear()
  toastSuccess.mockClear()
  normalizedErrors = {}
})

test('forwards controlled close actions and resets fields whenever opened', () => {
  const closed = render([], false)
  effects.forEach((effect) => effect())
  expect(updates).toEqual([[], [], [], []])
  expect(closed.tree.props).toMatchObject({ open: false, onOpenChange: closed.onOpenChange })

  const opened = render(['old-url', 'old-name', false, { url: 'old-error' }])
  expect(find(opened.tree, (node) => node.props['data-testid'] === 'kb-import-url-dialog')).toBeTruthy()
  expect(find(opened.tree, (node) => node.props['data-testid'] === 'kb-import-url-dialog-cancel')).toBeTruthy()
  effects.forEach((effect) => effect())
  expect(updates[0]).toEqual([''])
  expect(updates[1]).toEqual([''])
  expect(updates[3]).toEqual([{}])

  find(opened.tree, (node) => node.props.type === 'button')?.props.onClick?.()
  expect(opened.onOpenChange).toHaveBeenCalledWith(false)
})

test('rejects missing and malformed URLs, then clears a field error as the user edits', async () => {
  const empty = render()
  await submit(empty.tree)
  expect(updates[3]).toEqual([{ url: 'urlRequired' }])
  expect(importUrl).not.toHaveBeenCalled()

  const invalid = render(['not a url', '', false, { url: 'urlInvalid', name: 'nameInvalid' }])
  await submit(invalid.tree)
  expect(updates[3]).toContainEqual({ url: 'urlInvalid' })
  expect(importUrl).not.toHaveBeenCalled()

  const urlInput = find(invalid.tree, (node) => node.props.id === 'url')
  urlInput?.props.onChange?.({ target: { value: 'https://example.com' } })
  expect(updates[0]).toContain('https://example.com')
  const clearUrl = updates[3].find((update) => typeof update === 'function') as (errors: Record<string, string>) => Record<string, string>
  expect(clearUrl({ url: 'urlInvalid', name: 'nameInvalid' })).toEqual({ name: 'nameInvalid' })
  expect(textContent(invalid.tree)).toContain('url: urlInvalid')
})

test('disables submission and shows importing feedback while loading', () => {
  const { tree } = render(['https://example.com', '', true, {}])
  const submitButton = find(tree, (node) => node.props.type === 'submit')

  expect(submitButton?.props.disabled).toBe(true)
  expect(textContent(submitButton)).toContain('importing')
})

test('trims values, submits, closes, reports success, and navigates to platform preview', async () => {
  const rendered = render(['  https://example.com/page  ', '  Example page  ', false, {}])
  await submit(rendered.tree)

  expect(importUrl).toHaveBeenCalledWith('kb-1', 'https://example.com/page', 'Example page')
  expect(updates[2]).toEqual([true, false])
  expect(toastSuccess).toHaveBeenCalledWith('urlImported')
  expect(rendered.onOpenChange).toHaveBeenCalledWith(false)
  expect(rendered.onSuccess).toHaveBeenCalledTimes(1)
  expect(push).toHaveBeenCalledWith('/app/kb/kb-1/documents/preview?docs=doc-1')
})

test('surfaces normalized API field errors and always leaves loading state', async () => {
  normalizedErrors = { url: 'blocked URL', name: 'duplicate name' }
  importUrl.mockImplementation(async () => { throw new Error('validation failed') })
  const { tree, onOpenChange, onSuccess } = render(['https://example.com', 'Example', false, {}])
  await submit(tree)

  expect(updates[2]).toEqual([true, false])
  expect(updates[3]).toContainEqual(normalizedErrors)
  expect(onOpenChange).not.toHaveBeenCalled()
  expect(onSuccess).not.toHaveBeenCalled()
  expect(push).not.toHaveBeenCalled()
})
