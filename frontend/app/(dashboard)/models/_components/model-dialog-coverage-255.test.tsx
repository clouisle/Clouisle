import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const createModel = mock(async () => ({}))
const updateModel = mock(async () => ({}))
const testModelConfig = mock(async () => ({ success: true, message: 'Connected', latency_ms: 12 }))
const testConnection = mock(async () => ({ success: true, message: 'Connected', latency_ms: 12 }))
const discoverModels = mock(async () => ({ success: true, message: '2 models found', models: [] }))
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
  modelsApi: { createModel, updateModel, testConnection, testModelConfig, discoverModels },
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
mock.module('@/components/ui/combobox', () => {
  const ComboboxInput = () => null
  const Combobox = ({
    children,
    items = [],
    value,
    inputValue = '',
    filter,
    onInputValueChange,
    onValueChange,
  }: React.PropsWithChildren<{
    items?: string[]
    value?: string | null
    inputValue?: string
    filter?: (value: string, query: string) => boolean
    onInputValueChange: (value: string, details: { reason: string }) => void
    onValueChange: (value: string | null) => void
  }>) => {
    const inputElement = React.Children.toArray(children).find(
      (child) => React.isValidElement(child) && child.type === ComboboxInput,
    ) as React.ReactElement<Record<string, unknown>> | undefined
    const visibleItems = items.filter((item) => !filter || filter(item, inputValue))
    return (
      <>
        <input
          {...inputElement?.props}
          role="combobox"
          aria-expanded={items.length > 0}
          aria-controls="model-id-options"
          value={inputValue}
          onChange={(event) => onInputValueChange(event.target.value, { reason: 'input-change' })}
        />
        {items.length > 0 && (
          <select
            data-testid="model-id-options"
            value={value || ''}
            onChange={(event) => onValueChange(event.target.value || null)}
          >
            <option value="" />
            {visibleItems.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        )}
      </>
    )
  }
  return {
    Combobox,
    ComboboxInput,
    ComboboxContent: () => null,
    ComboboxEmpty: () => null,
    ComboboxItem: () => null,
    ComboboxList: () => null,
  }
})
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
  { code: 'stability', base_url: 'https://stability.test' },
  { code: 'ollama', base_url: 'http://ollama.test' },
  { code: 'custom', base_url: null },
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
  testConnection.mockReset()
  testConnection.mockResolvedValue({ success: true, message: 'Connected', latency_ms: 12 })
  testModelConfig.mockResolvedValue({ success: true, message: 'Connected', latency_ms: 12 })
  discoverModels.mockReset()
  discoverModels.mockResolvedValue({ success: true, message: '2 models found', models: [] })
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

function switchValue(renderer: ReactTestRenderer, index: number, checked: boolean) {
  act(() => renderer.root.findAllByProps({ type: 'checkbox' })[index].props.onChange({ target: { checked } }))
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

describe('model management dialog', () => {
  test('requires a model type before enabling provider selection, then applies the provider base URL', () => {
    const renderer = render()
    const provider = renderer.root.findAllByProps({ role: 'combobox' }).find(
      (candidate) => candidate.props.id !== 'modelId',
    )!

    expect(provider.props.disabled).toBe(true)
    expect(input(renderer, 'name').props['aria-invalid']).toBe(false)
    expect(JSON.stringify(renderer.toJSON())).toContain('selectModelTypeFirst')

    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    expect(
      renderer.root.findAllByProps({ role: 'combobox' }).find(
        (candidate) => candidate.props.id !== 'modelId',
      )?.props.disabled,
    ).toBe(false)

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

  test('persists a custom provider display name', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'custom')
    change(renderer, 'name', 'Gateway model')
    change(renderer, 'providerDisplayName', '  Acme Gateway  ')
    change(renderer, 'modelId', 'gpt-gateway')
    change(renderer, 'apiKey', 'secret')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'custom',
      provider_display_name: 'Acme Gateway',
    }))
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

  test('tests an existing model with its stored API key when no replacement is entered', async () => {
    const renderer = render({
      model: {
        id: 'model-1', name: 'Existing', provider: 'openai', model_id: 'gpt-existing', model_type: 'chat',
        base_url: 'https://old.test', is_enabled: false, is_default: true, has_api_key: true,
      } as React.ComponentProps<typeof ModelDialog>['model'],
    })

    const testButton = buttonWithText(renderer, 'testConnection')
    expect(testButton.props.disabled).toBe(false)

    await act(async () => testButton.props.onClick())

    expect(testConnection).toHaveBeenCalledWith('model-1')
    expect(testModelConfig).not.toHaveBeenCalled()
    expect(toastSuccess).toHaveBeenCalledWith('testSuccess')
  })

  test('searches discovered models in the model ID input and fills the selected model', async () => {
    const renderer = render()
    discoverModels.mockResolvedValue({
      success: true,
      message: '2 models found',
      models: [
        {
          id: 'gpt-4o',
          name: 'GPT-4o',
          context_length: 128000,
          max_output_tokens: 8192,
          capabilities: { vision: true, function_call: true, streaming: false, json_mode: true },
        },
        { id: 'gpt-4.1', name: 'GPT-4.1' },
      ],
    })
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'openai')
    change(renderer, 'apiKey', 'secret')

    await act(async () => {
      const { promise, resolve } = Promise.withResolvers<void>()
      setTimeout(resolve, 450)
      await promise
    })

    expect(discoverModels).toHaveBeenCalledWith({
      provider: 'openai',
      base_url: 'https://api.openai.test',
      api_key: 'secret',
    })
    expect(JSON.stringify(renderer.toJSON())).toContain('2 models found')

    expect(input(renderer, 'modelId').props.role).toBe('combobox')
    change(renderer, 'modelId', '4.1')
    expect(input(renderer, 'modelId').props.value).toBe('4.1')
    expect(
      renderer.root.findByProps({ 'data-testid': 'model-id-options' })
        .findAllByType('option')
        .map((option) => option.props.value),
    ).toEqual(['', 'gpt-4.1'])
    change(renderer, 'modelId', '')

    selectValue(renderer, 'gpt-4o')
    expect(input(renderer, 'modelId').props.value).toBe('gpt-4o')
    expect(input(renderer, 'name').props.value).toBe('GPT-4o')
    expect(
      renderer.root.findAllByProps({ type: 'checkbox' }).slice(2).map((item) => item.props.checked),
    ).toEqual([true, true, false, true])

    change(renderer, 'name', 'Custom label')
    change(renderer, 'modelId', '')
    selectValue(renderer, 'gpt-4.1')
    expect(input(renderer, 'name').props.value).toBe('Custom label')
    expect(input(renderer, 'contextLength').props.value).toBe('128000')
    expect(input(renderer, 'maxOutputTokens').props.value).toBe('8192')
  })

  test('constructs a rich chat payload from parameters, capabilities, and extension JSON', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'openai')
    change(renderer, 'name', '  Reasoning model  ')
    change(renderer, 'modelId', '  reasoning-1  ')
    change(renderer, 'apiKey', 'secret')
    change(renderer, 'contextLength', '128000')
    change(renderer, 'maxOutputTokens', '8192')
    change(renderer, 'inputPrice', '1.25')
    change(renderer, 'outputPrice', '5.5')
    change(renderer, 'temperature', '0.2')
    change(renderer, 'topP', '0.9')
    change(renderer, 'frequencyPenalty', '-0.1')
    change(renderer, 'presencePenalty', '0.3')
    change(renderer, 'maxTokens', '4096')
    change(renderer, 'extraBody', '{"metadata":{"tier":"gold"}}')
    change(renderer, 'defaultParamsExtension', '{"seed":7,"temperature":1.8}')
    change(renderer, 'configExtension', '{"region":"us-east"}')
    selectValue(renderer, 'high')
    switchValue(renderer, 0, false)
    switchValue(renderer, 1, true)
    switchValue(renderer, 2, true)
    switchValue(renderer, 3, true)
    switchValue(renderer, 4, false)
    switchValue(renderer, 5, true)

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createModel).toHaveBeenCalledWith({
      name: 'Reasoning model', provider: 'openai', provider_display_name: null, model_id: 'reasoning-1', model_type: 'chat',
      base_url: 'https://api.openai.test', api_key: 'secret', context_length: 128000,
      max_output_tokens: 8192, input_price: 1.25, output_price: 5.5,
      default_params: {
        seed: 7, temperature: 0.2, top_p: 0.9, frequency_penalty: -0.1,
        presence_penalty: 0.3, max_tokens: 4096, reasoning_effort: 'high',
        extra_body: { metadata: { tier: 'gold' } },
      },
      capabilities: { vision: true, function_call: true, streaming: false, json_mode: true },
      config: { region: 'us-east' }, is_enabled: false, is_default: true,
    })
  })

  test('blocks invalid extension JSON, clears the field error, and succeeds after correction', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'openai')
    change(renderer, 'name', 'JSON recovery')
    change(renderer, 'modelId', 'json-recovery')
    change(renderer, 'apiKey', 'secret')
    change(renderer, 'defaultParamsExtension', '[]')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))
    expect(createModel).not.toHaveBeenCalled()
    expect(input(renderer, 'defaultParamsExtension').props['aria-invalid']).toBe(true)

    change(renderer, 'defaultParamsExtension', '{"seed":42}')
    expect(input(renderer, 'defaultParamsExtension').props['aria-invalid']).toBe(false)
    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({ default_params: { seed: 42 } }))
  })

  test('recovers a failed connection test and reports the successful retry', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'chat' } }))
    selectProvider(renderer, 'openai')
    change(renderer, 'modelId', 'connection-test')
    change(renderer, 'apiKey', 'secret')
    testModelConfig.mockRejectedValueOnce(new Error('Network unavailable'))

    await act(async () => buttonWithText(renderer, 'testConnection').props.onClick())
    expect(testModelConfig).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'openai', model_id: 'connection-test', api_key: 'secret',
    }))
    expect(JSON.stringify(renderer.toJSON())).toContain('testFailed')

    change(renderer, 'apiKey', 'replacement')
    await act(async () => buttonWithText(renderer, 'testConnection').props.onClick())

    expect(testModelConfig).toHaveBeenLastCalledWith(expect.objectContaining({ api_key: 'replacement' }))
    expect(JSON.stringify(renderer.toJSON())).toContain('Connected')
    expect(toastSuccess).toHaveBeenCalledWith('testSuccess')
  })

  test('constructs Google image parameters and keeps image capabilities null', async () => {
    const renderer = render()
    act(() => modelTypeSelect(renderer).props.onChange({ target: { value: 'text_to_image' } }))
    selectProvider(renderer, 'google')
    change(renderer, 'name', 'Image model')
    change(renderer, 'modelId', 'imagen-test')
    change(renderer, 'apiKey', 'secret')
    selectValue(renderer, '1024x1024')
    selectValue(renderer, 'vivid')
    selectValue(renderer, 'high')
    selectValue(renderer, '16:9')
    selectValue(renderer, '2K')
    selectValue(renderer, 'ALLOW_ADULT')
    selectValue(renderer, 'DONT_ALLOW', 1)
    selectValue(renderer, 'image/jpeg')
    change(renderer, 'googleOutputCompressionQuality', '88')
    change(renderer, 'defaultParamsExtensionImage', '{"seed":9}')

    await act(async () => renderer.root.findByType('form').props.onSubmit({ preventDefault() {} }))

    expect(createModel).toHaveBeenCalledWith(expect.objectContaining({
      provider: 'google', model_type: 'text_to_image', capabilities: null,
      default_params: {
        seed: 9, default_width: 1024, default_height: 1024, style: 'vivid', quality: 'high',
        aspect_ratio: '16:9', image_size: '2K', person_generation: 'ALLOW_ADULT',
        prominent_people: 'DONT_ALLOW', output_mime_type: 'image/jpeg', output_compression_quality: 88,
      },
    }))
  })
})
