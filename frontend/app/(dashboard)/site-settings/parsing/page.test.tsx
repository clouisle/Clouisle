import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { ApiError } from '@/lib/api/client'

const imageSettings = {
  kb_image_understanding_enabled: false,
  kb_image_understanding_model_id: '',
  kb_image_ocr_model_id: '',
  kb_image_understanding_allow_external: false,
  kb_image_understanding_max_images: 8,
  kb_image_understanding_max_image_bytes: 10485760,
  kb_image_understanding_max_image_pixels: 20000000,
  kb_image_understanding_concurrency: 2,
}
const getKnowledgeBaseImages = mock(() => Promise.resolve(imageSettings))
const updateKnowledgeBaseImages = mock(() => Promise.resolve())
const getModels = mock(() => Promise.resolve({
  items: [
    { id: 'vision-1', name: 'Vision Chat', provider: 'openai', provider_display_name: 'Acme', model_type: 'chat', is_enabled: true, capabilities: { input_modalities: ['text', 'image'] } },
    { id: 'text-1', name: 'Text Chat', provider: 'openai', model_type: 'chat', is_enabled: true, capabilities: { input_modalities: ['text'] } },
  ],
  total: 2,
  page: 1,
  pageSize: 100,
}))
const getModel = mock((id: string) => Promise.resolve({
  id,
  name: 'Saved Model',
  provider: 'openai',
  provider_display_name: 'Acme',
  model_type: 'chat',
  is_enabled: true,
  capabilities: { input_modalities: ['text', 'image'] },
}))
let canUpdate = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
const toastError = mock(() => {})
mock.module('sonner', () => ({ toast: { success: () => {}, error: toastError } }))
mock.module('lucide-react', () => ({ Loader2: () => null, Image: () => null, ImageIcon: () => null }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ onCheckedChange, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { onCheckedChange?: (checked: boolean) => void }) => (
    <input {...props} type="checkbox" onChange={(event) => onCheckedChange?.(event.currentTarget.checked)} />
  ),
}))
// The real SelectItem reaches the owning Select's onValueChange through Radix
// context; the mock does the same so slot selection is actually exercised.
const selectContext = React.createContext<{ onValueChange?: (value: string) => void }>({})
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: React.PropsWithChildren<{ onValueChange?: (value: string) => void }>) => (
    <selectContext.Provider value={{ onValueChange }}><div>{children}</div></selectContext.Provider>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => {
    const { onValueChange } = React.useContext(selectContext)
    return (
      <button type="button" data-value={value} onClick={() => onValueChange?.(value)}>
        {children}
      </button>
    )
  },
  SelectTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/number-input', () => ({ NumberInput: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.PropsWithChildren<React.LabelHTMLAttributes<HTMLLabelElement>>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => <p>{children}</p> }))
mock.module('@/lib/api/admin/site-settings', () => ({ siteSettingsApi: { getKnowledgeBaseImages, updateKnowledgeBaseImages } }))
mock.module('@/lib/api/admin/models', () => ({ modelsApi: { getModels, getModel } }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: () => canUpdate }) }))

// Mock.module must run before this import; a static import would bypass mocks.
const { default: Page } = await import('./page')
let renderer: ReactTestRenderer | null = null
globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let nextRenderer: ReactTestRenderer
  await act(async () => { nextRenderer = create(<Page />) })
  return nextRenderer!
}
const saveButton = (next: ReactTestRenderer) =>
  next.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!
afterEach(() => {
  if (renderer) { act(() => renderer!.unmount()); renderer = null }
  mock.clearAllMocks()
  canUpdate = true
})

test('loads bounded image settings and saves through site settings API', async () => {
  renderer = await render()
  expect(getKnowledgeBaseImages).toHaveBeenCalledTimes(1)
  expect(getModels).toHaveBeenCalledWith({ model_type: ['chat', 'ocr'], is_enabled: true, pageSize: 100 })
  expect(renderer.root.findAll((node) => node.children.includes('Acme / Vision Chat')).length).toBeGreaterThan(0)
  expect(renderer.root.findAll((node) => node.children.includes('Text Chat'))).toHaveLength(0)
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(imageSettings)
})

test('routes dedicated OCR models to the OCR slot only', async () => {
  getModels.mockResolvedValueOnce({
    items: [
      { id: 'vision-1', name: 'Vision Chat', provider: 'openai', provider_display_name: 'Acme', model_type: 'chat', is_enabled: true, capabilities: { input_modalities: ['text', 'image'] } },
      { id: 'ocr-1', name: 'Ocr Only', provider: 'mistral', provider_display_name: 'Mistral', model_type: 'ocr', is_enabled: true, capabilities: { input_modalities: ['image'] } },
    ],
    total: 2,
    page: 1,
    pageSize: 100,
  })
  renderer = await render()
  // Both slots are populated from one request that already includes OCR models.
  expect(getModels).toHaveBeenCalledWith({ model_type: ['chat', 'ocr'], is_enabled: true, pageSize: 100 })
  // Each model is offered by exactly one slot: the dedicated OCR type by the OCR
  // slot, the vision chat model by the description slot.
  expect(renderer.root.findAll((node) => node.children.includes('Mistral / Ocr Only')).length).toBe(1)
  expect(renderer.root.findAll((node) => node.children.includes('Acme / Vision Chat')).length).toBe(1)
})

test('surfaces a legacy chat model saved in the OCR-only slot', async () => {
  getKnowledgeBaseImages.mockResolvedValueOnce({
    ...imageSettings,
    kb_image_ocr_model_id: 'legacy-chat',
  })
  getModel.mockResolvedValueOnce({
    id: 'legacy-chat',
    name: 'Legacy Chat',
    provider: 'openai',
    provider_display_name: 'Acme',
    model_type: 'chat',
    is_enabled: true,
    capabilities: { input_modalities: ['text', 'image'] },
  })
  renderer = await render()
  // Saving again must be rejected by the API, but the admin still needs to see
  // which model the slot points at instead of an empty trigger.
  expect(getModel).toHaveBeenCalledWith('legacy-chat')
  expect(renderer.root.findAll((node) => node.children.includes('Acme / Legacy Chat')).length).toBeGreaterThan(0)
})

test('does not save defaults after settings fail to load', async () => {
  getKnowledgeBaseImages.mockImplementationOnce(() => Promise.reject(new Error('settings unavailable')))
  renderer = await render()
  expect(renderer.root.findAllByType('button').some((button) => button.children.includes('saveChanges'))).toBe(false)
  expect(updateKnowledgeBaseImages).not.toHaveBeenCalled()
})

test('hides save controls without the update permission', async () => {
  canUpdate = false
  renderer = await render()
  expect(renderer.root.findAllByType('button').some((button) => button.children.includes('saveChanges'))).toBe(false)
})

test('allows saving with only an OCR model configured', async () => {
  getKnowledgeBaseImages.mockResolvedValueOnce({
    ...imageSettings,
    kb_image_understanding_enabled: true,
    kb_image_understanding_model_id: '',
    kb_image_ocr_model_id: 'vision-1',
  })
  renderer = await render()
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(expect.objectContaining({
    kb_image_understanding_enabled: true,
    kb_image_understanding_model_id: '',
    kb_image_ocr_model_id: 'vision-1',
  }))
})


test('loads a saved image model that is outside the first model page', async () => {
  getKnowledgeBaseImages.mockResolvedValueOnce({
    ...imageSettings,
    kb_image_understanding_enabled: true,
    kb_image_understanding_model_id: 'saved-99',
  })
  renderer = await render()
  expect(getModel).toHaveBeenCalledWith('saved-99')
  expect(renderer.root.findAll((node) => node.children.includes('Acme / Saved Model')).length).toBeGreaterThan(0)
})

const selectOption = (next: ReactTestRenderer, value: string) =>
  next.root.findAll((node) => node.type === 'button' && node.props['data-value'] === value)[0]
const inputById = (next: ReactTestRenderer, id: string) =>
  next.root.findAll((node) => node.type === 'input' && node.props.id === id)[0]

test('selecting a vision model stores its id', async () => {
  renderer = await render()
  await act(async () => selectOption(renderer!, 'vision-1').props.onClick())
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(
    expect.objectContaining({ kb_image_understanding_model_id: 'vision-1' }),
  )
})

test('choosing the empty option clears the saved vision model', async () => {
  getKnowledgeBaseImages.mockResolvedValueOnce({
    ...imageSettings,
    kb_image_understanding_model_id: 'vision-1',
  })
  renderer = await render()
  await act(async () => selectOption(renderer!, '__none__').props.onClick())
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(
    expect.objectContaining({ kb_image_understanding_model_id: '' }),
  )
})

test('selecting an OCR model stores its id', async () => {
  getModels.mockResolvedValueOnce({
    items: [
      { id: 'ocr-1', name: 'Ocr Only', provider: 'mistral', provider_display_name: 'Mistral', model_type: 'ocr', is_enabled: true, capabilities: { input_modalities: ['image'] } },
    ],
    total: 1,
    page: 1,
    pageSize: 100,
  })
  renderer = await render()
  await act(async () => selectOption(renderer!, 'ocr-1').props.onClick())
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(
    expect.objectContaining({ kb_image_ocr_model_id: 'ocr-1' }),
  )
})

test('still saves when the model list fails to load', async () => {
  getModels.mockImplementationOnce(() => Promise.reject(new Error('models unavailable')))
  renderer = await render()
  // The slots stay empty, but the settings form itself must remain usable.
  expect(renderer.root.findAll((node) => node.children.includes('Acme / Vision Chat'))).toHaveLength(0)
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(imageSettings)
})

test('toggling the external-image switch updates settings', async () => {
  renderer = await render()
  await act(async () => inputById(renderer!, 'kb-image-external').props.onChange({
    currentTarget: { checked: true },
  }))
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(
    expect.objectContaining({ kb_image_understanding_allow_external: true }),
  )
})

test('editing a numeric limit stores it and clearing restores the default', async () => {
  renderer = await render()
  const field = inputById(renderer, 'kb_image_understanding_max_images')
  await act(async () => field.props.onChange(12))
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenLastCalledWith(
    expect.objectContaining({ kb_image_understanding_max_images: 12 }),
  )

  updateKnowledgeBaseImages.mockClear()
  await act(async () => field.props.onChange(''))
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenLastCalledWith(
    expect.objectContaining({ kb_image_understanding_max_images: 8 }),
  )
})

test('blocks saving when image understanding is enabled without a model', async () => {
  getKnowledgeBaseImages.mockResolvedValueOnce({
    ...imageSettings,
    kb_image_understanding_enabled: true,
  })
  renderer = await render()
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).not.toHaveBeenCalled()
  expect(
    renderer.root.findAll((node) => node.children.includes('parsingSettings.modelRequired')).length,
  ).toBeGreaterThan(0)
})

test('maps a field-level save failure onto the offending field', async () => {
  updateKnowledgeBaseImages.mockImplementationOnce(() =>
    Promise.reject(
      new ApiError(1001, 'validation failed', {
        errors: { 'settings.kb_image_ocr_model_id': ['must be an OCR model'] },
      }),
    ),
  )
  renderer = await render()
  await act(async () => saveButton(renderer!).props.onClick())
  expect(
    renderer.root.findAll((node) => node.children.includes('must be an OCR model')).length,
  ).toBeGreaterThan(0)
  expect(toastError).not.toHaveBeenCalled()
})

test('falls back to a toast when the save failure has no field errors', async () => {
  updateKnowledgeBaseImages.mockImplementationOnce(() =>
    Promise.reject(new Error('server down')),
  )
  renderer = await render()
  await act(async () => saveButton(renderer!).props.onClick())
  expect(toastError).toHaveBeenCalledWith('server down')
})
