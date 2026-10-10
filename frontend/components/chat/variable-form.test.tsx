import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const hookState: unknown[] = []
let hookIndex = 0

const uploadFile = mock(() => Promise.resolve({ url: '/uploads/new.txt', asset_id: 'asset-single' }))

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: 'fragment' }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: 'fragment' }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void) => effect(),
  useMemo: <T,>(factory: () => T) => factory(),
  useRef: <T,>(initial: T) => ({ current: initial }),
  useState: <T,>(initial: T) => {
    const index = hookIndex++
    if (!(index in hookState)) hookState[index] = initial
    return [hookState[index] as T, (value: T) => { hookState[index] = value }] as const
  },
}))

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('@/lib/api/upload', () => ({ uploadApi: { uploadFile } }))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const { [field]: removed, ...remaining } = errors
    void removed
    return remaining
  },
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
  Select: element('select'),
  SelectContent: element('options'),
  SelectItem: element('option'),
  SelectTrigger: element('trigger'),
  SelectValue: element('value'),
}))
mock.module('lucide-react', () => ({ Upload: element('svg'), X: element('svg'), FileIcon: element('svg'), ImageIcon: element('svg') }))
mock.module('./authenticated-media', () => ({ AuthenticatedImage: element('authenticated-image') }))

// Configure module mocks before loading the component under test.
const { VariableForm, MultiFileUploadInput } = await import('./variable-form')
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
const render = (variables: Variable[], values: Record<string, unknown>, onChange = mock(), onSubmit?: () => void, fieldErrors?: Record<string, string>, onAssetIdsChange = mock()) => {
  hookState.length = 0
  hookIndex = 0
  return VariableForm({ variables, values, onChange, onAssetIdsChange, onSubmit, fieldErrors })
}
const renderMulti = (value: unknown, onChange: (value: unknown) => void, onAssetIdsChange: (assetIds: string[]) => void, reset = false) => {
  if (reset) hookState.length = 0
  hookIndex = 0
  return MultiFileUploadInput({ variable: variable('images', 'images'), value, onChange, onAssetIdsChange })
}


beforeEach(() => {
  uploadFile.mockReset()
  uploadFile.mockResolvedValue({ url: '/uploads/new.txt', asset_id: 'asset-single' })
})

describe('VariableForm', () => {
  test('emits typed scalar and JSON changes', () => {
    const onChange = mock()
    const tree = render([
      variable('title', 'text'), variable('notes', 'paragraph'), variable('count', 'number'),
      variable('checked', 'checkbox'), variable('choice', 'select', { options: ['a'] }),
      variable('enabled', 'boolean'), variable('items', 'array'), variable('config', 'object'),
    ], {}, onChange)

    const inputs = findAll(tree, (node) => node.type === 'input')
    ;(inputs[0].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'hello' } })
    ;(inputs[1].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '3' } })
    const textareas = findAll(tree, (node) => node.type === 'textarea')
    ;(textareas[0].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'details' } })
    ;(textareas[1].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '[1]' } })
    ;(textareas[2].props.onChange as (event: { target: { value: string } }) => void)({ target: { value: '{"ok":true}' } })
    ;(findAll(tree, (node) => node.type === 'checkbox')[0].props.onCheckedChange as (value: boolean) => void)(true)
    const selects = findAll(tree, (node) => node.type === 'select')
    ;(selects[0].props.onValueChange as (value: string) => void)('a')
    ;(selects[1].props.onValueChange as (value: string) => void)('true')

    expect(onChange.mock.calls.map((call) => call[0])).toEqual([
      { title: 'hello' }, { count: 3 }, { notes: 'details' }, { items: [1] },
      { config: { ok: true } }, { checked: true }, { choice: 'a' }, { enabled: true },
    ])
  })

  test('disables invalid required values and submits valid values', () => {
    const variables = [
      variable('items', 'array', { required: true }), variable('config', 'object', { required: true }),
      variable('file', 'file', { required: true }), variable('files', 'files', { required: true }),
      variable('ignored', 'text', { required: true, hidden: true }), variable('checked', 'checkbox', { required: true }),
    ]
    const onSubmit = mock()
    const invalid = render(variables, { items: 'nope', config: '[]' }, mock(), onSubmit)
    expect(findAll(invalid, (node) => node.type === 'button').at(-1)?.props.disabled).toBe(true)

    const valid = render(variables, { items: [1], config: { ok: true }, file: '/a', files: ['/b'], checked: false }, mock(), onSubmit)
    const form = findAll(valid, (node) => node.type === 'form')[0]
    ;(form.props.onSubmit as (event: { preventDefault(): void }) => void)({ preventDefault() {} })
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  test('handles file limits, mocked uploads, removals, and field errors', async () => {
    const onChange = mock()
    const onAssetIdsChange = mock()
    const single = render([variable('file', 'file', { fileConfig: { accept: ['text/plain'], maxSize: 1 } })], {}, onChange, undefined, { file: 'server error' }, onAssetIdsChange)
    const singleInput = findAll(single, (node) => node.type === 'input' && node.props.type === 'file')[0]
    expect(singleInput.props.accept).toBe('text/plain')
    await (singleInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['ok'], 'new.txt')] } })
    expect(uploadFile).toHaveBeenCalledWith(expect.any(File), 'workflow-input')
    expect(onChange).toHaveBeenCalledWith({ file: '/uploads/new.txt' })
    expect(onAssetIdsChange).toHaveBeenCalledWith('file', 'asset-single')

    const existing = render([variable('file', 'file')], { file: '/uploads/old.txt' }, onChange)
    ;(findAll(existing, (node) => node.type === 'button')[0].props.onClick as () => void)()
    expect(onChange).toHaveBeenCalledWith({ file: null })

    uploadFile.mockClear()
    const multiple = render([variable('files', 'files', { fileConfig: { maxFiles: 1 } })], { files: ['/uploads/old.txt'] }, onChange)
    const multiInput = findAll(multiple, (node) => node.type === 'input' && node.props.multiple === true)[0]
    await (multiInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({ target: { files: [new File(['x'], 'extra.txt')] } })
    expect(uploadFile).not.toHaveBeenCalled()
    ;(findAll(multiple, (node) => node.type === 'button').at(-1)?.props.onClick as () => void)()
    expect(onChange).toHaveBeenCalledWith({ files: null })
  })

  test('supports drag-and-drop uploads and renders image previews', async () => {
    const onChange = mock()
    uploadFile.mockClear()

    // 拖拽单文件：onDragEnter/Over/Leave 触发拖拽态，onDrop 上传
    const single = render([variable('doc', 'file')], {}, onChange)
    const singleZone = findAll(single, (node) => typeof node.props.onDrop === 'function')[0]
    singleZone.props.onDragEnter({ preventDefault: mock(), stopPropagation: mock() })
    singleZone.props.onDragOver({ preventDefault: mock(), stopPropagation: mock() })
    singleZone.props.onDragLeave({ preventDefault: mock(), stopPropagation: mock() })
    await (singleZone.props.onDrop as (event: { preventDefault(): void; dataTransfer: { files: File[] } }) => Promise<void>)({
      preventDefault() {},
      dataTransfer: { files: [new File(['x'], 'dropped.txt')] },
    })
    expect(uploadFile).toHaveBeenCalledWith(expect.any(File), 'workflow-input')
    expect(onChange).toHaveBeenCalledWith({ doc: '/uploads/new.txt' })

    // Both variable previews use the authenticated asset renderer.
    const image = render([variable('photo', 'image')], { photo: '/api/v1/upload/files/p.png' }, onChange)
    const preview = findAll(image, (node) => node.type === 'authenticated-image')[0]
    expect(preview.props.src).toBe('/api/v1/upload/files/p.png')


    // 多图：缩略图网格预览 + 移除按钮
    const onChangeMulti = mock()
    const images = render([variable('shots', 'images')], { shots: ['/uploads/a.png', '/uploads/b.png'] }, onChangeMulti)
    const thumbs = findAll(images, (node) => node.type === 'authenticated-image')
    expect(thumbs.map((node) => node.props.src)).toEqual(['/uploads/a.png', '/uploads/b.png'])

    ;(findAll(images, (node) => node.type === 'button' && typeof node.props.onClick === 'function').at(-1)?.props.onClick as () => void)()
    expect(onChangeMulti).toHaveBeenCalledWith({ shots: ['/uploads/a.png'] })

    // 多图拖拽追加：已有 1 张 + 拖入 2 张 → 合并
    uploadFile.mockClear()
    uploadFile.mockResolvedValueOnce({ url: '/uploads/c.png' }).mockResolvedValueOnce({ url: '/uploads/d.png' })
    const onChangeAppend = mock()
    const append = render([variable('shots', 'images')], { shots: ['/uploads/old.png'] }, onChangeAppend)
    const appendZone = findAll(append, (node) => typeof node.props.onDrop === 'function')[0]
    await (appendZone.props.onDrop as (event: { preventDefault(): void; dataTransfer: { files: File[] } }) => Promise<void>)({
      preventDefault() {},
      dataTransfer: { files: [new File(['x'], 'c.png'), new File(['y'], 'd.png')] },
    })
    expect(onChangeAppend).toHaveBeenCalledWith({
      shots: ['/uploads/old.png', '/uploads/c.png', '/uploads/d.png'],
    })

    // 非图片多文件保持文件芯片列表（无 img 预览）
    const docs = render([variable('docs', 'files')], { docs: ['/uploads/a.pdf'] }, onChangeMulti)
    expect(findAll(docs, (node) => node.type === 'img')).toHaveLength(0)
  })
  test('prunes uploaded asset IDs when the controlled value resets before another upload', async () => {
    const onChange = mock()
    const onAssetIdsChange = mock()
    uploadFile.mockResolvedValueOnce({ url: '/api/v1/upload/files/first.png', asset_id: 'asset-first' })
      .mockResolvedValueOnce({ url: '/api/v1/upload/files/second.png', asset_id: 'asset-second' })

    const first = renderMulti([], onChange, onAssetIdsChange, true)
    const firstInput = findAll(first, (node) => node.type === 'input' && node.props.multiple === true)[0]
    await (firstInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({
      target: { files: [new File(['x'], 'first.png')] },
    })
    expect(onAssetIdsChange).toHaveBeenLastCalledWith(['asset-first'])

    const reset = renderMulti([], onChange, onAssetIdsChange)
    expect(onAssetIdsChange).toHaveBeenLastCalledWith([])
    const secondInput = findAll(reset, (node) => node.type === 'input' && node.props.multiple === true)[0]
    await (secondInput.props.onChange as (event: { target: { files: File[] } }) => Promise<void>)({
      target: { files: [new File(['y'], 'second.png')] },
    })
    expect(onAssetIdsChange).toHaveBeenLastCalledWith(['asset-second'])

    const second = renderMulti(['/api/v1/upload/files/second.png'], onChange, onAssetIdsChange)
    const remove = findAll(second, (node) => node.type === 'button' && node.props['aria-label'] === 'removeImage')[0]
    ;(remove.props.onClick as () => void)()
    expect(onAssetIdsChange).toHaveBeenLastCalledWith([])
    expect(onChange).toHaveBeenLastCalledWith(null)
  })
})
