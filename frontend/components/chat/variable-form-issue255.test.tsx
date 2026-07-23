import { beforeEach, describe, expect, mock, spyOn, test } from 'bun:test'
import type { ReactNode } from 'react'

const uploadFile = mock(() => Promise.resolve({ url: '/uploads/new.txt' }))
const clearValidationError = mock((errors: Record<string, string>, name: string) => {
  const next = { ...errors }
  delete next[name]
  return next
})
const stateSetters: ReturnType<typeof mock>[] = []

class ApiError extends Error {
  constructor(public code: number, public data?: unknown) {
    super('request failed')
  }
}

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: 'fragment' }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: 'fragment' }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void) => effect(),
  useMemo: <T,>(factory: () => T) => factory(),
  useRef: <T,>(initial: T) => ({ current: initial }),
  useState: <T,>(initial: T | (() => T)) => {
    const setter = mock((next: T | ((previous: T) => T)) =>
      typeof next === 'function' ? (next as (previous: T) => T)({ title: 'server error' } as T) : undefined
    )
    stateSetters.push(setter)
    return [typeof initial === 'function' ? (initial as () => T)() : initial, setter] as const
  },
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('@/lib/api/upload', () => ({ uploadApi: { uploadFile } }))
mock.module('@/lib/api', () => ({ ApiError }))
mock.module('@/lib/validation', () => ({
  clearValidationError,
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>, fields: string[]) =>
    Object.entries(errors).filter(([field]) => fields.includes(field)),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('checkbox') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('alert') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'), SelectContent: element('options'), SelectItem: element('option'),
  SelectTrigger: element('trigger'), SelectValue: element('value'),
}))
mock.module('lucide-react', () => ({ Upload: element('svg'), X: element('svg'), FileIcon: element('svg'), ImageIcon: element('svg') }))

const { VariableForm, useVariableForm } = await import('./variable-form')
type Variable = Parameters<typeof VariableForm>[0]['variables'][number]
type Tree = { type: unknown; props: Record<string, unknown> }

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function' ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props)) : tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const tree = resolved as Tree
  const matches = predicate(tree) ? [tree] : []
  const children = tree.props.children
  for (const child of Array.isArray(children) ? children : [children]) matches.push(...findAll(child as ReactNode, predicate))
  return matches
}

const variable = (name: string, type: Variable['type'], extra: Partial<Variable> = {}): Variable => ({ name, type, required: false, ...extra })
const render = (variables: Variable[], values: Record<string, unknown>, onChange = mock(), onSubmit?: () => void, fieldErrors?: Record<string, string>) =>
  VariableForm({ variables, values, onChange, onSubmit, fieldErrors })

beforeEach(() => {
  uploadFile.mockReset()
  uploadFile.mockResolvedValue({ url: '/uploads/new.txt' })
  stateSetters.length = 0
  clearValidationError.mockClear()
  spyOn(console, 'error').mockImplementation(() => {})
})

describe('VariableForm issue #255 coverage', () => {
  test('emits typed changes and initializes defaults', () => {
    const onChange = mock()
    const tree = render([
      variable('title', 'text'), variable('notes', 'paragraph'), variable('count', 'number'),
      variable('checked', 'checkbox'), variable('choice', 'select', { options: ['a'] }),
      variable('enabled', 'boolean'), variable('items', 'array'), variable('config', 'object'),
    ], {}, onChange)

    const inputs = findAll(tree, (node) => node.type === 'input')
    ;(inputs[0].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'hello' } })
    ;(inputs[1].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '' } })
    const textareas = findAll(tree, (node) => node.type === 'textarea')
    ;(textareas[0].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'details' } })
    ;(textareas[1].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '{}' } })
    ;(textareas[1].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'bad' } })
    ;(textareas[2].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '[]' } })
    ;(textareas[2].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '{"ok":true}' } })
    ;(findAll(tree, (node) => node.type === 'checkbox')[0].props.onCheckedChange as (value: boolean) => void)(true)
    const selects = findAll(tree, (node) => node.type === 'select')
    ;(selects[0].props.onValueChange as (value: string) => void)('a')
    ;(selects[1].props.onValueChange as (value: string) => void)('true')

    expect(onChange.mock.calls.map((call) => call[0])).toContainEqual({ config: { ok: true } })
    const defaults = mock()
    const defaultTree = render([
      variable('flag', 'boolean', { default: 'true' }), variable('amount', 'number', { default: '4' }),
      variable('label', 'text', { default: 'ready' }),
    ], {}, defaults)
    findAll(defaultTree, () => false)
    expect(defaults.mock.calls.map((call) => call[0])).toEqual([
      { flag: true }, { amount: 4 }, { label: 'ready' },
    ])
  })

  test('validates values, reports server errors, submits, and hides empty forms', () => {
    expect(render([variable('hidden', 'text', { hidden: true })], {})).toBeNull()
    const variables = [
      variable('items', 'array', { required: true }), variable('config', 'object', { required: true }),
      variable('file', 'file', { required: true }), variable('files', 'files', { required: true }),
      variable('checked', 'checkbox', { required: true }),
    ]
    const invalid = render(variables, { items: 'nope', config: '[]' }, mock(), mock(), { config: 'server error' })
    expect(findAll(invalid, (node) => node.type === 'button').at(-1)?.props.disabled).toBe(true)
    expect(findAll(invalid, (node) => node.type === 'alert').some((node) => node.props.children === 'config: server error')).toBe(true)

    const onSubmit = mock()
    const valid = render(variables, { items: [1], config: { ok: true }, file: '/a', files: ['/b'], checked: false }, mock(), onSubmit)
    const form = findAll(valid, (node) => node.type === 'form')[0]
    ;(form.props.onSubmit as (event: { preventDefault(): void }) => void)({ preventDefault() {} })
    expect(onSubmit).toHaveBeenCalledTimes(1)

    const blockedSubmit = mock()
    const blocked = render([variable('required', 'text', { required: true })], {}, mock(), blockedSubmit)
    ;(findAll(blocked, (node) => node.type === 'form')[0].props.onSubmit as (event: { preventDefault(): void }) => void)({ preventDefault() {} })
    expect(blockedSubmit).not.toHaveBeenCalled()
  })

  test('validates and resets hook state while clearing changed server errors', () => {
    const variables = [
      variable('title', 'text', { required: true }),
      variable('count', 'number', { default: '2' }),
      variable('checked', 'checkbox', { default: 'true' }),
      variable('hidden', 'text', { hidden: true, required: true }),
    ]
    const hook = useVariableForm(variables)
    expect(hook.values).toEqual({ count: 2, checked: true })
    expect(hook.needsInput).toBe(true)
    expect(hook.isValid).toBe(false)
    expect(hook.validate()).toBe(false)

    hook.setValues({ title: 'ready', count: 2, checked: true })
    expect(clearValidationError).toHaveBeenCalledWith(expect.any(Object), 'title')
    hook.reset()
    expect(stateSetters.at(-2)).toHaveBeenCalledWith({ count: 2, checked: true })
    expect(stateSetters.at(-1)).toHaveBeenCalledWith({})
  })

  test('handles single-file limits, uploads, API errors, and removal', async () => {
    const onChange = mock()
    const oversized = render([variable('file', 'file', { fileConfig: { accept: ['text/plain'], maxSize: 1 } })], {}, onChange)
    const oversizedInput = findAll(oversized, (node) => node.type === 'input' && node.props.type === 'file')[0]
    expect(oversizedInput.props.accept).toBe('text/plain')
    await (oversizedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [] } })
    await (oversizedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File([new Uint8Array(1_048_577)], 'large.txt')] } })
    expect(uploadFile).not.toHaveBeenCalled()

    const success = render([variable('image', 'image')], {}, onChange)
    const successInput = findAll(success, (node) => node.type === 'input' && node.props.type === 'file')[0]
    expect(successInput.props.accept).toBe('image/*')
    await (successInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['ok'], 'new.png')] } })
    expect(onChange).toHaveBeenCalledWith({ image: '/uploads/new.txt' })

    uploadFile.mockRejectedValueOnce(new ApiError(1001, { allowed: ['.pdf', '.txt'] }))
    const failed = render([variable('file', 'file')], {}, onChange)
    const setterStart = stateSetters.length
    const failedInput = findAll(failed, (node) => node.type === 'input' && node.props.type === 'file')[0]
    await (failedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['bad'], 'bad.exe')] } })
    expect(stateSetters.slice(setterStart).some((setter) =>
      setter.mock.calls.some((call) => call[0] === 'invalidFileTypeWithAllowed:.pdf, .txt')
    )).toBe(true)

    const existing = render([variable('file', 'file')], { file: '/uploads/old.txt' }, onChange)
    ;(findAll(existing, (node) => node.type === 'button')[0].props.onClick as () => void)()
    expect(onChange).toHaveBeenCalledWith({ file: null })
  })

  test('handles multi-file limits, upload failures, success, and removals', async () => {
    const onChange = mock()
    const oversized = render([variable('files', 'files', { fileConfig: { maxSize: 1 } })], {}, onChange)
    const oversizedInput = findAll(oversized, (node) => node.type === 'input' && node.props.multiple === true)[0]
    await (oversizedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [] } })
    await (oversizedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File([new Uint8Array(1_048_577)], 'large.txt')] } })
    expect(uploadFile).not.toHaveBeenCalled()

    const limited = render([variable('files', 'files', { fileConfig: { maxFiles: 1 } })], { files: ['/uploads/old.txt'] }, onChange)
    const limitedInput = findAll(limited, (node) => node.type === 'input' && node.props.multiple === true)[0]
    await (limitedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['x'], 'extra.txt')] } })
    expect(uploadFile).not.toHaveBeenCalled()

    uploadFile.mockRejectedValueOnce(new ApiError(1001))
    const failed = render([variable('images', 'images')], {}, onChange)
    const setterStart = stateSetters.length
    const failedInput = findAll(failed, (node) => node.type === 'input' && node.props.multiple === true)[0]
    expect(failedInput.props.accept).toBe('image/*')
    await (failedInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['x'], 'bad.bin')] } })
    expect(stateSetters.slice(setterStart).some((setter) =>
      setter.mock.calls.some((call) => call[0] === 'invalidFileType')
    )).toBe(true)

    uploadFile.mockResolvedValueOnce({ url: '/uploads/a.txt' }).mockResolvedValueOnce({ url: '/uploads/b.txt' })
    const success = render([variable('files', 'files', { fileConfig: { accept: ['text/plain'], maxFiles: 3 } })], { files: ['/uploads/old.txt', 3] }, onChange)
    const successInput = findAll(success, (node) => node.type === 'input' && node.props.multiple === true)[0]
    expect(successInput.props.accept).toBe('text/plain')
    await (successInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['a'], 'a.txt'), new File(['b'], 'b.txt')] } })
    expect(onChange).toHaveBeenCalledWith({ files: ['/uploads/old.txt', '/uploads/a.txt', '/uploads/b.txt'] })
    ;(findAll(success, (node) => node.type === 'button').at(-1)?.props.onClick as () => void)()
    expect(onChange).toHaveBeenCalledWith({ files: null })
  })
})
