import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const createModel = mock(async () => ({}))
const updateModel = mock(async () => ({}))
const testModelConfig = mock(async () => ({ success: true, message: 'Connected' }))

mock.module('next-intl', () => ({
  useTranslations: () => {
    const translate = (key: string) => key
    translate.has = () => true
    return translate
  },
}))

mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
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
  { code: 'ollama', base_url: 'http://ollama.test' },
] as React.ComponentProps<typeof ModelDialog>['providers']
const modelTypes = [{ code: 'chat' }, { code: 'text_to_image' }] as React.ComponentProps<typeof ModelDialog>['modelTypes']
const renderers: ReactTestRenderer[] = []

afterEach(() => {
  createModel.mockClear()
  updateModel.mockClear()
  testModelConfig.mockClear()
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

function modelTypeSelect(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('select').find((select) => !select.props.disabled)!
}

function selectProvider(renderer: ReactTestRenderer, code: string) {
  const button = renderer.root.findAllByType('button').find((candidate) =>
    candidate.findAllByType('span').some((span) => span.children.includes(`providers.${code}`)),
  )!
  act(() => button.props.onClick())
}

describe('model management dialog', () => {
  test('requires a model type before enabling provider selection, then applies the provider base URL', () => {
    const renderer = render()
    const provider = renderer.root.findByProps({ role: 'combobox' })

    expect(provider.props.disabled).toBe(true)
    expect(input(renderer, 'name').props['aria-invalid']).toBe(false)
    expect(JSON.stringify(renderer.toJSON())).toContain('selectModelTypeFirst')

    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    expect(renderer.root.findByProps({ role: 'combobox' }).props.disabled).toBe(false)

    selectProvider(renderer, 'openai')
    expect(input(renderer, 'baseUrl').props.value).toBe('https://api.openai.test')
  })

  test('shows accessible validation errors without calling the create API', async () => {
    const renderer = render()
    const form = renderer.root.findByType('form')

    await act(async () => form.props.onSubmit({ preventDefault() {} }))

    expect(createModel).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(' '))).toContain('nameRequired')
    expect(input(renderer, 'name').props['aria-invalid']).toBe(true)
  })

  test('creates a selected enabled model and reports success', async () => {
    const onOpenChange = mock(() => {})
    const onSuccess = mock(() => {})
    const renderer = render({ onOpenChange, onSuccess })

    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'openai')
    change(renderer, 'name', 'GPT test')
    change(renderer, 'modelId', 'gpt-test')
    change(renderer, 'apiKey', 'secret')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      name: 'GPT test', provider: 'openai', model_id: 'gpt-test', model_type: 'chat',
      base_url: 'https://api.openai.test', api_key: 'secret', is_enabled: true, is_default: false,
    }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  test('prefills edit fields, locks provider identity, and sends editable changes to update', async () => {
    const onSuccess = mock(() => {})
    const renderer = render({
      onSuccess,
      model: {
        id: 'model-1', name: 'Existing', provider: 'openai', model_id: 'gpt-existing', model_type: 'chat',
        base_url: 'https://old.test', is_enabled: false, is_default: true, has_api_key: true,
      } as React.ComponentProps<typeof ModelDialog>['model'],
    })

    expect(renderer.root.findAllByType('select').find((select) => select.props.disabled)?.props.disabled).toBe(true)
    expect(renderer.root.findByProps({ role: 'combobox' }).props.disabled).toBe(true)
    expect(input(renderer, 'modelId').props.disabled).toBe(true)
    expect(JSON.stringify(renderer.toJSON())).toContain('apiKeyConfigured')

    change(renderer, 'name', 'Renamed')
    change(renderer, 'baseUrl', 'https://new.test')
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(updateModel).toHaveBeenCalledWith('model-1', expect.objectContaining({
      name: 'Renamed', base_url: 'https://new.test', is_enabled: false, is_default: true,
    }))
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })
})
