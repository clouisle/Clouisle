import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

type Tree = { type: unknown; props: Record<string, unknown> }
type Setter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Record<string, unknown> | null) => ({ type, props: props ?? {} })
const element = (name: string) => function Element(props: Record<string, unknown>) { return jsx(name, props) }
const Button = element('button')
const Input = element('input')
const Textarea = element('textarea')
const Select = element('select')
let states: unknown[] = []
let stateIndex = 0
const effects: Array<() => void> = []
const clearValidationError = mock((errors: Record<string, string>, key: string) => {
  const next = { ...errors }
  delete next[key]
  return next
})
const clearValidationErrorsByPrefix = mock((errors: Record<string, string>) => errors)
const mapValidationErrors = mock(() => ({}))
const normalizeValidationErrors = mock((error: unknown) => error)

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState<T>(initial: T): [T, Setter<T>] {
    const index = stateIndex++
    states[index] ??= initial
    return [states[index] as T, (value) => {
      states[index] = typeof value === 'function' ? (value as (current: T) => T)(states[index] as T) : value
    }]
  },
  useEffect: (effect: () => void) => effects.push(effect),
  useRef: () => ({ current: null }),
  useCallback: <T,>(callback: T) => callback,
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({ Loader2: element('loader'), Plus: element('plus'), Trash2: element('trash'), ChevronDown: element('chevron') }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: element('dialog'), DialogContent: element('section'), DialogDescription: element('p'),
  DialogFooter: element('footer'), DialogHeader: element('header'), DialogTitle: element('h2'),
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea }))
mock.module('@/components/ui/switch', () => ({ Switch: element('switch') }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: element('collapsible'), CollapsibleContent: element('div'), CollapsibleTrigger: element('trigger') }))
mock.module('@/components/ui/select', () => ({ Select, SelectContent: element('options'), SelectItem: element('option'), SelectTrigger: element('select-trigger'), SelectValue: element('select-value') }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: element('image-upload') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('field-error') }))
mock.module('@/lib/validation', () => ({
  clearValidationError,
  clearValidationErrorsByPrefix,
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('./tool-category-input', () => ({ ToolCategoryInput: element('category-input') }))

const { HttpToolDialog } = await import('./http-tool-dialog')
const baseProps = { open: true, onOpenChange: mock(() => {}), onSave: mock(async () => {}) }

function render(props = baseProps) {
  stateIndex = 0
  effects.length = 0
  return HttpToolDialog(props) as Tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('type' in node)) return []
  const tree = node as Tree
  return [...(predicate(tree) ? [tree] : []), ...findAll(tree.props.children as ReactNode, predicate)]
}

const text = (node: unknown): string => {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return [((node as Tree).props.children)].flat().map(text).join('')
}
const input = (tree: Tree, id: string) => findAll(tree, (node) => node.type === Input && node.props.id === id)[0]
const button = (tree: Tree, label: string) => findAll(tree, (node) => node.type === Button && text(node).includes(label))[0]
const change = (node: Tree, value: string) => (node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })

beforeEach(() => {
  states = []
  clearValidationError.mockClear()
  clearValidationErrorsByPrefix.mockClear()
  mapValidationErrors.mockReset()
  mapValidationErrors.mockReturnValue({})
  normalizeValidationErrors.mockClear()
  baseProps.onOpenChange.mockClear()
  baseProps.onSave.mockClear()
})

describe('HttpToolDialog Issue #255 callbacks', () => {
  test('initializes edit data and exercises field, pair, and parameter callbacks', () => {
    const tool = {
      name: 'fetch_data', display_name: 'Fetch', description: 'desc', icon: 'F', category: 'api', is_enabled: true,
      parameters: [{ name: 'id', type: 'string', required: false, description: '' }],
      http_config: { method: 'POST', url: 'https://api.test/{{id}}', headers: { Authorization: 'token' }, query_params: { page: '1' }, body_template: '{}', timeout: 10, content_type: 'application/json', form_fields: [] },
    } as never
    render({ ...baseProps, tool })
    effects[0]()
    let tree = render({ ...baseProps, tool })

    change(input(tree, 'displayName'), 'Updated')
    change(input(tree, 'description'), 'new description')
    change(input(tree, 'timeout'), '45')
    ;(findAll(tree, (node) => node.type === 'category-input')[0]?.props.onChange as ((value: string) => void) | undefined)?.('search')
    ;(findAll(tree, (node) => node.type === Select && node.props.value === 'POST')[0]?.props.onValueChange as ((value: string) => void) | undefined)?.('PATCH')
    ;(findAll(tree, (node) => node.type === 'switch')[0]?.props.onCheckedChange as ((value: boolean) => void) | undefined)?.(true)
    const parameterInput = findAll(tree, (node) => node.type === Input && node.props.value === 'id')[0]
    if (parameterInput) change(parameterInput, 'item_id')
    ;(findAll(tree, (node) => node.type === Select && node.props.value === 'string')[0]?.props.onValueChange as ((value: string) => void) | undefined)?.('number')
    ;(button(tree, 'httpDialog.addParameter').props.onClick as () => void)()

    tree = render({ ...baseProps, tool })
    expect(states[1]).toBe('Updated')
    expect(states[8]).toBe('PATCH')
    expect(states[13]).toBe(45)
    expect((states[16] as unknown[])).toHaveLength(2)
    expect(clearValidationError).toHaveBeenCalled()
  })

  test('validates required values, then saves filtered HTTP configuration', async () => {
    let tree = render()
    effects[0]()
    tree = render()
    await (button(tree, 'create').props.onClick as () => Promise<void>)()
    expect(states[7]).toEqual(expect.objectContaining({ name: 'error.nameRequired', displayName: 'form.displayNameRequired', url: 'form.urlRequired' }))

    states[0] = 'fetch_data'
    states[1] = 'Fetch Data'
    states[2] = 'description'
    states[8] = 'POST'
    states[9] = 'https://api.test'
    states[10] = [{ key: 'Authorization', value: 'Bearer token' }, { key: '', value: 'ignored' }]
    states[11] = [{ key: 'page', value: '1' }]
    states[12] = '{"id":"{{id}}"}'
    states[13] = 20
    states[14] = 'application/json'
    states[16] = [{ name: 'id', type: 'string', required: true, description: '' }, { name: '', type: 'string', required: false }]
    tree = render()
    await (button(tree, 'create').props.onClick as () => Promise<void>)()

    expect(baseProps.onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'fetch_data',
      parameters: [{ name: 'id', type: 'string', required: true, description: '' }],
      http_config: expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer token' }, query_params: { page: '1' }, body_template: '{"id":"{{id}}"}', content_type: 'application/json' }),
    }))
    expect(states[17]).toBe(false)
  })

  test('maps save validation errors and rethrows unknown failures', async () => {
    states = ['fetch_data', 'Fetch Data', '', '', 'api', 'private', true, {}, 'GET', 'https://api.test']
    const validationFailure = new Error('validation')
    baseProps.onSave.mockRejectedValueOnce(validationFailure)
    mapValidationErrors.mockReturnValueOnce({ url: 'invalid url' })
    let tree = render()
    await (button(tree, 'create').props.onClick as () => Promise<void>)()
    expect(states[7]).toEqual({ url: 'invalid url' })
    expect(normalizeValidationErrors).toHaveBeenCalledWith(validationFailure)

    const unknownFailure = new Error('offline')
    baseProps.onSave.mockRejectedValueOnce(unknownFailure)
    mapValidationErrors.mockReturnValueOnce({})
    tree = render()
    await expect((button(tree, 'create').props.onClick as () => Promise<void>)()).rejects.toThrow('offline')
  })
  test('exercises variable suggestions and optional form controls', async () => {
    states = [
      'upload_file', 'Upload file', 'description', '', 'api', 'private', true,
      { headers: 'headers error', queryParams: 'params error', bodyTemplate: 'body error', formFields: 'form error', parameters: 'parameters error' },
      'POST', 'https://api.test/upload',
      [{ key: 'X-Trace', value: 'trace' }, { key: 'X-Other', value: 'other' }],
      [{ key: 'page', value: '1' }, { key: 'limit', value: '10' }],
      '{{caption}}', 30, 'multipart/form-data',
      [{ name: 'caption', type: 'text', value: '{{caption}}' }, { name: 'attachment', type: 'file', value: '{{file}}' }],
      [{ name: 'id', type: 'string', required: false, description: '' }],
    ]
    const teams = [{ id: 'team-1', name: 'Team one' }]
    let tree = render({ ...baseProps, teams, selectedTeamId: 'team-1', onSelectedTeamChange: mock(() => {}) })

    const nameInput = input(tree, 'name')
    change(nameInput, 'upload_file')
    const urlNode = findAll(tree, (node) => typeof node.type === 'function' && node.props.placeholder === 'httpDialog.urlPlaceholder')[0]
    ;(urlNode.props.onChange as (value: string) => void)('https://api.test/upload')
    const collapsibles = findAll(tree, (node) => node.type === 'collapsible')
    for (const collapsible of collapsibles) {
      ;(collapsible.props.onOpenChange as ((open: boolean) => void) | undefined)?.(true)
    }

    const keyInputs = findAll(tree, (node) => node.type === Input && node.props.placeholder === 'httpDialog.keyPlaceholder')
    change(keyInputs[0], 'X-Request')
    change(keyInputs[1], 'offset')
    ;(button(tree, 'httpDialog.addHeader').props.onClick as () => void)()
    ;(button(tree, 'httpDialog.addParam').props.onClick as () => void)()

    const formName = findAll(tree, (node) => node.type === Input && node.props.placeholder === 'httpDialog.fieldName')[0]
    change(formName, 'caption')
    const textValue = findAll(tree, (node) => typeof node.type === 'function' && node.props.placeholder === '{{value}}')[0]
    ;(textValue.props.onChange as (value: string) => void)('{{caption}}')
    const formType = findAll(tree, (node) => node.type === Select && node.props.value === 'text')[0]
    ;(formType.props.onValueChange as (value: string) => void)('file')

    const contentType = findAll(tree, (node) => node.type === Select && node.props.value === 'multipart/form-data')[0]
    ;(contentType.props.onValueChange as (value: string) => void)('application/json')
    stateIndex = 0
    tree = render({ ...baseProps, teams, selectedTeamId: 'team-1', onSelectedTeamChange: mock(() => {}) })
    const bodyValue = findAll(tree, (node) => typeof node.type === 'function' && node.props.placeholder === 'httpDialog.bodyTemplatePlaceholder')[0]
    ;(bodyValue.props.onChange as (value: string) => void)('{"caption":"{{caption}}"}')

    ;(findAll(tree, (node) => node.type === Select && node.props.value === 'application/json')[0].props.onValueChange as (value: string) => void)('multipart/form-data')
    states[15] = [
      { name: 'caption', type: 'text', value: '{{caption}}' },
      { name: 'attachment', type: 'file', value: '{{file}}' },
    ]
    stateIndex = 0
    tree = render({ ...baseProps, teams, selectedTeamId: 'team-1', onSelectedTeamChange: mock(() => {}) })
    const textValueAfterReset = findAll(tree, (node) => typeof node.type === 'function' && node.props.placeholder === '{{value}}')[0]
    ;(textValueAfterReset.props.onChange as (value: string) => void)('{{caption}}')
    ;(findAll(tree, (node) => node.type === Select && node.props.value === 'text')[0].props.onValueChange as (value: string) => void)('file')
    stateIndex = 0
    tree = render({ ...baseProps, teams, selectedTeamId: 'team-1', onSelectedTeamChange: mock(() => {}) })
    const fileValue = findAll(tree, (node) => typeof node.type === 'function' && node.props.placeholder === '{{file}}')[0]
    ;(fileValue.props.onChange as (value: string) => void)('{{file}}')
    ;(button(tree, 'httpDialog.addField').props.onClick as () => void)()
    const iconButtons = findAll(tree, (node) => node.type === Button && node.props.size === 'icon')
    for (const iconButton of iconButtons) {
      ;(iconButton.props.onClick as (() => void) | undefined)?.()
    }
    expect((states[10] as unknown[])).toHaveLength(2)
    expect((states[11] as unknown[])).toHaveLength(2)
    expect((states[15] as unknown[])).toHaveLength(1)
    expect((states[16] as unknown[])).toEqual([])

    const variableNode = findAll(tree, (node) => typeof node.type === 'function' && node.type.name === 'VariableInput')[0]
    const renderVariable = variableNode.type as (props: Record<string, unknown>) => Tree
    const variableChange = mock(() => {})
    states[22] = false
    states[23] = []
    states[24] = 0
    states[25] = 0
    stateIndex = 22
    let variableTree = renderVariable({ value: '', onChange: variableChange, variables: ['id', 'name'] })
    const variableField = findAll(variableTree, (node) => node.type === Input)[0]
    ;(variableField.props.onChange as (event: { target: { value: string; selectionStart: number } }) => void)({ target: { value: '{{i', selectionStart: 3 } })
    ;(variableField.props.onBlur as () => void)()

    states[22] = true
    states[23] = ['id', 'name']
    states[24] = 3
    states[25] = 0
    stateIndex = 22
    variableTree = renderVariable({ value: '{{i', onChange: variableChange, variables: ['id', 'name'] })
    const suggestionField = findAll(variableTree, (node) => node.type === Input)[0]
    for (const key of ['ArrowDown', 'ArrowUp', 'Enter', 'Escape']) {
      ;(suggestionField.props.onKeyDown as (event: { key: string; preventDefault: () => void }) => void)({ key, preventDefault: () => {} })
    }
    const suggestions = findAll(variableTree, (node) => node.type === 'button')
    ;(suggestions[0]?.props.onMouseEnter as (() => void) | undefined)?.()
    ;(suggestions[0]?.props.onMouseDown as ((event: { preventDefault: () => void }) => void) | undefined)?.({ preventDefault: () => {} })
    const { promise, resolve } = Promise.withResolvers<void>()
    setTimeout(resolve, 0)
    await promise
    expect(variableChange).toHaveBeenCalledWith('{{id}}')
  })

})
