import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const createModel = mock(async () => ({}))
const updateModel = mock(async () => ({}))
const testModelConfig = mock(async () => ({ success: true, message: 'Connected', latency_ms: 12 }))
const toastSuccess = mock(() => {})
const toastError = mock(() => {})

mock.module('next-intl', () => ({
  useTranslations: () => {
    const translate = (key: string) => key
    translate.has = () => true
    return translate
  },
}))

mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api/admin/models', () => ({
  modelsApi: { createModel, updateModel, testModelConfig },
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: Record<string, unknown>) => <textarea {...props} /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <span role="alert">{children}</span> : null }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange, disabled }: React.PropsWithChildren<{ value: string; onValueChange: (value: string) => void; disabled?: boolean }>) => <select value={value} disabled={disabled} onChange={(event) => onValueChange(event.target.value)}>{children}</select>,
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} /> }))
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TabsContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TabsList: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TabsTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/popover', () => ({
  Popover: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PopoverContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PopoverTrigger: ({ render }: { render: (props: Record<string, unknown>) => React.ReactNode }) => <>{render({})}</>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipTrigger: ({ render }: { render: React.ReactNode | ((props: Record<string, unknown>) => React.ReactNode) }) => <>{typeof render === 'function' ? render({}) : render}</>,
}))

const { ModelDialog } = await import('./model-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const providers = [
  { code: 'openai', base_url: 'https://api.openai.test' },
  { code: 'anthropic', base_url: 'https://api.anthropic.test' },
  { code: 'google', base_url: 'https://api.google.test' },
  { code: 'azure_openai', base_url: 'https://azure.test' },
  { code: 'volcengine', base_url: 'https://volcengine.test' },
  { code: 'deepseek', base_url: 'https://deepseek.test' },
  { code: 'stability', base_url: 'https://stability.test' },
  { code: 'ollama', base_url: 'http://ollama.test' },
] as React.ComponentProps<typeof ModelDialog>['providers']
const modelTypes = [
  { code: 'chat' },
  { code: 'text_to_image' },
  { code: 'text_to_video' },
  { code: 'tts' },
] as React.ComponentProps<typeof ModelDialog>['modelTypes']
const renderers: ReactTestRenderer[] = []

afterEach(() => {
  createModel.mockClear()
  updateModel.mockClear()
  testModelConfig.mockReset()
  testModelConfig.mockResolvedValue({ success: true, message: 'Connected', latency_ms: 12 })
  toastSuccess.mockClear()
  toastError.mockClear()
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(props: Partial<React.ComponentProps<typeof ModelDialog>> = {}) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<ModelDialog open onOpenChange={() => {}} onSuccess={() => {}} providers={providers} modelTypes={modelTypes} {...props} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function input(renderer: ReactTestRenderer, id: string) {
  return renderer.root.findByProps({ id })
}

function change(renderer: ReactTestRenderer, id: string, value: string) {
  act(() => input(renderer, id).props.onChange({ target: { value } }))
}

function selects(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('select')
}

function modelTypeSelect(renderer: ReactTestRenderer) {
  return selects(renderer).find((select) => !select.props.disabled)!
}

function selectValue(renderer: ReactTestRenderer, value: string, occurrence = 0) {
  const select = selects(renderer).filter((candidate) =>
    candidate.findAllByType('option').some((option) => option.props.value === value),
  )[occurrence]!
  act(() => select.props.onChange({ target: { value } }))
}

function buttonWithText(renderer: ReactTestRenderer, text: string) {
  return renderer.root.findAllByType('button').find((button) =>
    button.findAll((node) => node.children.includes(text)).length > 0,
  )!
}

function selectProvider(renderer: ReactTestRenderer, code: string) {
  const button = renderer.root.findAllByType('button').find((candidate) =>
    candidate.findAllByType('span').some((span) => span.children.includes(`providers.${code}`)),
  )!
  act(() => button.props.onClick())
}

describe('model dialog remaining Issue #255 callbacks', () => {
  test('submits Volcengine speech settings through audio callbacks', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'tts' } }))
    selectProvider(renderer, 'volcengine')
    change(renderer, 'name', 'Speech model')
    change(renderer, 'modelId', 'speech-resource')
    change(renderer, 'apiKey', 'app-token')
    change(renderer, 'defaultVoice', 'speaker-1')
    change(renderer, 'speed', '1.25')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'volcengine', model_type: 'tts',
      default_params: { speaker: 'speaker-1', speed: 1.25 },
    }))
  })

  test('handles video fields and honors connection cost cancellation', async () => {
    const confirm = mock(() => false)
    const originalWindow = globalThis.window
    globalThis.window = { confirm } as Window & typeof globalThis
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'text_to_video' } }))
    selectProvider(renderer, 'volcengine')
    change(renderer, 'modelId', 'video-model')
    change(renderer, 'apiKey', 'secret')
    change(renderer, 'videoDuration', '8')
    selectValue(renderer, '16:9')

    await act(async () => buttonWithText(renderer, 'testConnection').props.onClick())
    expect(confirm).toHaveBeenCalledWith('videoTestCostWarning')
    expect(testModelConfig).not.toHaveBeenCalled()

    change(renderer, 'name', 'Video model')
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      default_params: { duration: 8, aspect_ratio: '16:9' },
    }))
    globalThis.window = originalWindow
  })

  test('runs Azure configuration inputs and domestic provider selection', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'azure_openai')
    change(renderer, 'name', 'Azure model')
    change(renderer, 'modelId', 'azure-deployment')
    change(renderer, 'apiKey', 'secret')
    change(renderer, 'apiVersion', '2025-01-01')
    change(renderer, 'deploymentName', 'deployment-a')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      config: { api_version: '2025-01-01', deployment_name: 'deployment-a' },
    }))

    const domestic = render()
    act(() => modelTypeSelect(domestic).props.onChange({ target: { value: 'chat' } }))
    selectProvider(domestic, 'deepseek')
    expect(domestic.root.findByProps({ role: 'combobox' }).findAll((node) => node.children.includes('providers.deepseek'))).not.toHaveLength(0)
  })
})
