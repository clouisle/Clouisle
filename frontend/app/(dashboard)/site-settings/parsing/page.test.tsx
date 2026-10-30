import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

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
mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
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
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <div data-value={value}>{children}</div>,
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
  expect(getModels).toHaveBeenCalledWith({ model_type: ['chat'], is_enabled: true, pageSize: 100 })
  expect(renderer.root.findAll((node) => node.children.includes('Acme / Vision Chat')).length).toBeGreaterThan(0)
  expect(renderer.root.findAll((node) => node.children.includes('Text Chat'))).toHaveLength(0)
  await act(async () => saveButton(renderer!).props.onClick())
  expect(updateKnowledgeBaseImages).toHaveBeenCalledWith(imageSettings)
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
