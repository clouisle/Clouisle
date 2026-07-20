import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

const createModel = mock(() => Promise.resolve({}))
const updateModel = mock(() => Promise.resolve({}))
const testModelConfig = mock(() => Promise.resolve({ success: true, message: 'Connected', latency_ms: 12 }))
const toastSuccess = mock()
const toastError = mock()
let state: unknown[] = []
let stateIndex = 0

const jsx = (type: unknown, props: Record<string, unknown> | null) => ({ type, props: props ?? {} })
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: 'fragment' }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: 'fragment' }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: () => {},
  useMemo: <T,>(factory: () => T) => factory(),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    if (state.length <= index) state[index] = initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
}))

const translation = (namespace: string) => Object.assign(
  (key: string) => namespace === 'common' ? `common.${key}` : key,
  { has: () => true },
)
mock.module('next-intl', () => ({ useTranslations: translation }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api/admin/models', () => ({
  modelsApi: { createModel, updateModel, testModelConfig },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  formatValidationSummaryMessage: (_field: string, message: string) => message,
  getValidationSummaryEntries: (errors: Record<string, string>, inline: string[]) =>
    Object.entries(errors).filter(([key]) => !inline.includes(key)),
  mapValidationErrors: (errors: Record<string, string>, paths: Record<string, string>) =>
    Object.fromEntries(Object.entries(errors).map(([key, value]) => [paths[key] || key, value])),
  normalizeValidationErrors: (error: { fieldErrors?: Record<string, string> }) => error.fieldErrors || {},
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => jsx(tag, { ...props, children })
const modules: Record<string, string[]> = {
  '@/components/ui/button': ['Button'],
  '@/components/ui/dialog': ['Dialog', 'DialogContent', 'DialogDescription', 'DialogFooter', 'DialogHeader', 'DialogTitle'],
  '@/components/ui/input': ['Input'],
  '@/components/ui/label': ['Label'],
  '@/components/ui/select': ['Select', 'SelectContent', 'SelectItem', 'SelectTrigger', 'SelectValue'],
  '@/components/ui/switch': ['Switch'],
  '@/components/ui/textarea': ['Textarea'],
  '@/components/ui/tabs': ['Tabs', 'TabsContent', 'TabsList', 'TabsTrigger'],
  '@/components/ui/popover': ['Popover', 'PopoverContent', 'PopoverTrigger'],
  '@/components/ui/tooltip': ['Tooltip', 'TooltipContent', 'TooltipTrigger'],
  '@/components/ui/field': ['FieldError'],
}
for (const [path, names] of Object.entries(modules)) {
  mock.module(path, () => Object.fromEntries(names.map((name) => [name, element(name.toLowerCase())])))
}
mock.module('lucide-react', () => Object.fromEntries(
  ['Eye', 'EyeOff', 'Loader2', 'CheckCircle2', 'XCircle', 'Zap', 'Check'].map((name) => [name, element(name)]),
))

const { ModelDialog } = await import('./model-dialog')

type Tree = { type: unknown; props: Record<string, unknown> }
const providers = [
  { code: 'openai', name: 'OpenAI', base_url: 'https://api.openai.com/v1' },
  { code: 'openai_responses', name: 'OpenAI Responses', base_url: 'https://api.openai.com/v1' },
  { code: 'anthropic', name: 'Anthropic', base_url: 'https://api.anthropic.com' },
  { code: 'google', name: 'Google', base_url: 'https://generativelanguage.googleapis.com' },
  { code: 'azure_openai', name: 'Azure OpenAI', base_url: '' },
  { code: 'deepseek', name: 'DeepSeek', base_url: 'https://api.deepseek.com' },
  { code: 'qwen', name: 'Qwen', base_url: 'https://dashscope.aliyuncs.com' },
  { code: 'volcengine', name: 'Volcengine', base_url: 'https://ark.cn-beijing.volces.com' },
  { code: 'runway', name: 'Runway', base_url: 'https://api.dev.runwayml.com' },
  { code: 'stability', name: 'Stability', base_url: 'https://api.stability.ai' },
  { code: 'ollama', name: 'Ollama', base_url: 'http://localhost:11434/v1' },
]
const modelTypes = [
  { code: 'chat', name: 'Chat' },
  { code: 'text_to_image', name: 'Image' },
  { code: 'text_to_video', name: 'Video' },
  { code: 'tts', name: 'TTS' },
]
const onOpenChange = mock()
const onSuccess = mock()

function resolve(node: ReactNode): Tree | ReactNode {
  if (!node || typeof node !== 'object' || !('type' in node)) return node
  const tree = node as Tree
  return typeof tree.type === 'function'
    ? resolve((tree.type as (props: Record<string, unknown>) => ReactNode)(tree.props))
    : tree
}

function findAll(node: ReactNode, predicate: (tree: Tree) => boolean): Tree[] {
  const resolved = resolve(node)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const tree = resolved as Tree
  const matches = predicate(tree) ? [tree] : []
  const children = tree.props.children
  return matches.concat((Array.isArray(children) ? children : [children]).flatMap((child) => findAll(child as ReactNode, predicate)))
}

function find(node: ReactNode, predicate: (tree: Tree) => boolean): Tree {
  const match = findAll(node, predicate)[0]
  if (!match) throw new Error('Element not found')
  return match
}

function render(model?: Parameters<typeof ModelDialog>[0]['model']) {
  stateIndex = 0
  return ModelDialog({ open: true, onOpenChange, onSuccess, providers, modelTypes, model })
}

function change(id: string, value: string) {
  const input = find(render(), (tree) => tree.props.id === id)
  ;(input.props.onChange as (event: { target: { value: string } }) => void)({ target: { value } })
}

function chooseModelType(code = 'chat') {
  state[3] = code
}

function chooseProvider(code: string) {
  state[1] = code
  state[4] = providers.find((provider) => provider.code === code)?.base_url || ''
}

async function submit() {
  const form = find(render(), (tree) => tree.type === 'form')
  await (form.props.onSubmit as (event: { preventDefault(): void }) => Promise<void>)({ preventDefault() {} })
}

beforeEach(() => {
  state = []
  createModel.mockReset()
  createModel.mockResolvedValue({})
  updateModel.mockReset()
  testModelConfig.mockReset()
  testModelConfig.mockResolvedValue({ success: true, message: 'Connected', latency_ms: 12 })
  toastSuccess.mockClear()
  onOpenChange.mockClear()
  onSuccess.mockClear()
})

describe('ModelDialog', () => {
  test('shows required field errors and does not create an invalid model', async () => {
    await submit()

    expect(createModel).not.toHaveBeenCalled()
    const invalidIds = findAll(render(), (tree) => tree.props['aria-invalid'] === true).map((tree) => tree.props.id)
    expect(invalidIds).toContain('name')
    expect(invalidIds).toContain('modelId')
  })

  test('creates an Ollama chat model without requiring an API key', async () => {
    change('name', ' Local model ')
    chooseModelType()
    chooseProvider('ollama')
    change('modelId', ' llama3.2 ')

    await submit()

    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      name: 'Local model',
      provider: 'ollama',
      model_id: 'llama3.2',
      model_type: 'chat',
      api_key: null,
      base_url: 'http://localhost:11434/v1',
    }))
    expect(toastSuccess).toHaveBeenCalledWith('modelCreated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  test('maps API validation errors back to their visible fields', async () => {
    createModel.mockRejectedValue({ fieldErrors: { model_id: 'Already exists' } })
    change('name', 'Duplicate')
    chooseModelType()
    chooseProvider('ollama')
    change('modelId', 'duplicate')

    await submit()

    expect(find(render(), (tree) => tree.props.children === 'Already exists')).toBeDefined()
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(onSuccess).not.toHaveBeenCalled()
  })
})
