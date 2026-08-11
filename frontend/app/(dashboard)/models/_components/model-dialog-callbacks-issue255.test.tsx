import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

type Tree = { type: unknown; props: Record<string, unknown> }
type Setter<T> = (value: T | ((current: T) => T)) => void

const jsx = (type: unknown, props: Record<string, unknown> | null) => ({ type, props: props ?? {} })
const element = (name: string) => {
  const Component = ({ children, ...props }: Record<string, unknown>) => jsx(name, { ...props, children })
  Component.displayName = name
  return Component
}
const ui = ({ children }: { children?: ReactNode }) => children

let states: unknown[] = []
let stateIndex = 0
const effects: Array<() => void> = []
const createModel = mock(() => Promise.resolve({}))
const updateModel = mock(() => Promise.resolve({}))
const testModelConfig = mock(() => Promise.resolve({ success: true, message: ' connected ', latency_ms: 12 }))
const discoverModels = mock(() => Promise.resolve({ success: true, message: 'models found', models: [] }))
const toastSuccess = mock(() => undefined)
const toastError = mock(() => undefined)

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState<T>(initial: T): [T, Setter<T>] {
    const index = stateIndex++
    if (states[index] === undefined) states[index] = initial
    return [states[index] as T, (value) => {
      states[index] = typeof value === 'function'
        ? (value as (current: T) => T)(states[index] as T)
        : value
    }]
  },
  useCallback: <T,>(callback: T) => callback,
  useMemo: <T,>(factory: () => T) => factory(),
  useEffect: (effect: () => void) => effects.push(effect),
}))
mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string) => key,
    { has: (key: string) => !key.endsWith('.custom') },
  ),
}))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('lucide-react', () => ({
  Eye: element('eye'), EyeOff: element('eye-off'), Loader2: element('loader'),
  CheckCircle2: element('check-circle'), XCircle: element('x-circle'), Zap: element('zap'), Check: element('check'),
}))
mock.module('@/lib/api/admin/models', () => ({ modelsApi: { createModel, updateModel, testModelConfig, discoverModels } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: (errors: Record<string, string>) => errors.model_id ? { modelId: errors.model_id } : errors,
  normalizeValidationErrors: (error: unknown) => error instanceof Error && error.message === 'validation' ? { model_id: 'invalid' } : {},
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

for (const path of ['button', 'dialog', 'input', 'label', 'select', 'combobox', 'switch', 'textarea', 'tabs', 'popover', 'tooltip', 'field']) {
  const exports: Record<string, unknown> = {}
  const names: Record<string, string[]> = {
    button: ['Button'], dialog: ['Dialog', 'DialogContent', 'DialogDescription', 'DialogFooter', 'DialogHeader', 'DialogTitle'],
    input: ['Input'], label: ['Label'], select: ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue'],
    combobox: ['Combobox', 'ComboboxContent', 'ComboboxEmpty', 'ComboboxInput', 'ComboboxItem', 'ComboboxList'],
    switch: ['Switch'], textarea: ['Textarea'], tabs: ['Tabs', 'TabsContent', 'TabsList', 'TabsTrigger'],
    popover: ['Popover', 'PopoverContent', 'PopoverTrigger'], tooltip: ['Tooltip', 'TooltipContent', 'TooltipTrigger'], field: ['FieldError'],
  }
  for (const name of names[path]) exports[name] = name === 'Dialog' || name === 'Tabs' || name === 'Popover' || name === 'Tooltip' ? ui : element(name)
  mock.module(`@/components/ui/${path}`, () => exports)
}

const { ModelDialog } = await import('./model-dialog')

const providers = [
  { code: 'openai', name: 'OpenAI', base_url: 'https://fake.invalid' },
  { code: 'qwen', name: 'Qwen', base_url: null },
  { code: 'ollama', name: 'Ollama', base_url: null },
] as never
const modelTypes = [
  { code: 'chat', name: 'Chat' },
  { code: 'text_to_image', name: 'Image' },
  { code: 'text_to_video', name: 'Video' },
] as never
const baseProps = { open: true, onOpenChange: mock(() => undefined), onSuccess: mock(() => undefined), providers, modelTypes }

function render(overrides: Record<string, unknown> = {}) {
  stateIndex = 0
  effects.length = 0
  return ModelDialog({ ...baseProps, ...overrides }) as Tree
}

function findAll(node: unknown, predicate: (tree: Tree) => boolean): Tree[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const tree = node as Tree
  return [...(predicate(tree) ? [tree] : []), ...findAll(tree.props.children, predicate)]
}

function validChatState() {
  states = []
  states[0] = 'Coverage model'
  states[1] = 'openai'
  states[2] = 'gpt-fake'
  states[3] = 'chat'
  states[4] = 'https://fake.invalid'
  states[5] = 'fake-key'
  states[11] = '0.7'
  states[12] = '0.9'
  states[13] = '0.1'
  states[14] = '0.2'
  states[15] = '500'
  states[16] = true
  states[17] = true
  states[18] = false
  states[19] = true
  states[44] = 'high'
  states[46] = '{"trace":true}'
  states[47] = '{"custom":1}'
  states[48] = '{"region":"test"}'
}

beforeEach(() => {
  states = []
  createModel.mockReset()
  createModel.mockResolvedValue({})
  updateModel.mockReset()
  updateModel.mockResolvedValue({})
  testModelConfig.mockReset()
  testModelConfig.mockResolvedValue({ success: true, message: ' connected ', latency_ms: 12 })
  discoverModels.mockReset()
  discoverModels.mockResolvedValue({ success: true, message: 'models found', models: [] })
  toastSuccess.mockClear()
  toastError.mockClear()
  baseProps.onOpenChange.mockClear()
  baseProps.onSuccess.mockClear()
})

describe('ModelDialog issue #255 callbacks', () => {
  test('runs field, selector, toggle, provider, and cancel callbacks with fake values', () => {
    validChatState()
    const tree = render()

    for (const node of findAll(tree, (item) => typeof item.props.onChange === 'function')) {
      ;(node.props.onChange as (event: { target: { value: string } }) => void)({ target: { value: 'changed' } })
    }
    for (const node of findAll(tree, (item) => typeof item.props.onCheckedChange === 'function')) {
      ;(node.props.onCheckedChange as (value: boolean) => void)(true)
    }
    for (const node of findAll(tree, (item) => typeof item.props.onValueChange === 'function')) {
      ;(node.props.onValueChange as (value: string) => void)('chat')
    }
    const clickers = findAll(tree, (item) => typeof item.props.onClick === 'function')
    clickers.forEach((node) => (node.props.onClick as () => void)())

    expect(clickers).toHaveLength(3)
    expect(states).toContain('changed')
    expect(baseProps.onOpenChange).toHaveBeenCalledWith(false)
  })

  test('validates bad JSON, then creates and tests a fully configured fake model', async () => {
    validChatState()
    states[46] = '[]'
    let tree = render()
    const form = findAll(tree, (node) => typeof node.props.onSubmit === 'function')[0]
    await (form.props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: () => undefined })
    expect(states[50]).toEqual(expect.objectContaining({ extraBody: 'invalidJSON' }))
    expect(createModel).not.toHaveBeenCalled()

    validChatState()
    tree = render()
    await (findAll(tree, (node) => typeof node.props.onSubmit === 'function')[0].props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: () => undefined })
    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Coverage model', provider: 'openai', model_id: 'gpt-fake',
      capabilities: { vision: true, function_call: true, streaming: false, json_mode: true },
      default_params: expect.objectContaining({ temperature: 0.7, extra_body: { trace: true }, custom: 1 }),
      config: { region: 'test' },
    }))
    expect(baseProps.onSuccess).toHaveBeenCalled()

    const testButton = findAll(tree, (node) => typeof node.props.onClick === 'function' && node.props.type === 'button')
      .find((node) => JSON.stringify(node).includes('testConnection'))
    await (testButton?.props.onClick as () => Promise<void>)()
    expect(testModelConfig).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'fake-key' }))
    expect(toastSuccess).toHaveBeenCalledWith('testSuccess')
  })

  test('maps fake API validation failures without closing either workflow', async () => {
    validChatState()
    createModel.mockRejectedValue(new Error('validation'))
    let tree = render()
    await (findAll(tree, (node) => typeof node.props.onSubmit === 'function')[0].props.onSubmit as (event: { preventDefault: () => void }) => Promise<void>)({ preventDefault: () => undefined })
    expect(states[50]).toEqual({ modelId: 'invalid' })
    expect(baseProps.onSuccess).not.toHaveBeenCalled()

    validChatState()
    testModelConfig.mockRejectedValue(new Error('validation'))
    tree = render()
    const testButton = findAll(tree, (node) => typeof node.props.onClick === 'function')
      .find((node) => JSON.stringify(node).includes('testConnection'))
    await (testButton?.props.onClick as () => Promise<void>)()
    expect(states[52]).toEqual({ success: false, message: 'testFailed' })
    expect(states[51]).toBe(false)
  })
})
