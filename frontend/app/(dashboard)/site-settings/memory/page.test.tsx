import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const memorySettings = {
  memory_async_extraction_enabled: true,
  memory_extraction_model_id: 'model-1',
  memory_extraction_cooldown_seconds: 180,
  memory_extraction_max_pending_turns: 6,
}
const getMemory = mock(() => Promise.resolve(memorySettings))
const updateMemory = mock(() => Promise.resolve())
const getModels = mock(() =>
  Promise.resolve({
    items: [{ id: 'model-1', name: 'GPT-4o Mini', provider: 'openai', provider_display_name: 'Acme AI' }],
    total: 1,
    page: 1,
    pageSize: 100,
  })
)
let canUpdate = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
mock.module('lucide-react', () => ({
  Loader2: () => null,
  Brain: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
type SwitchProps = React.InputHTMLAttributes<HTMLInputElement> & {
  onCheckedChange?: (checked: boolean) => void
}
mock.module('@/components/ui/switch', () => ({
  Switch: ({ onCheckedChange, ...props }: SwitchProps) => (
    <input
      {...props}
      type="checkbox"
      onChange={(event) => onCheckedChange?.(event.currentTarget.checked)}
    />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: (props: Record<string, unknown>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children }: React.PropsWithChildren) => <label>{children}</label>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: {
    getMemory,
    updateMemory,
  },
}))
mock.module('@/lib/api/admin/models', () => ({
  modelsApi: {
    getModels,
  },
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))

const { default: SiteSettingsMemoryPage } = await import('./page')

let renderer: ReactTestRenderer | null = null

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let nextRenderer: ReactTestRenderer
  await act(async () => {
    nextRenderer = create(<SiteSettingsMemoryPage />)
  })
  return nextRenderer!
}

const saveButton = (nextRenderer: ReactTestRenderer) =>
  nextRenderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!

afterEach(() => {
  if (renderer) {
    act(() => renderer!.unmount())
    renderer = null
  }
  mock.clearAllMocks()
  canUpdate = true
})

test('loads memory settings and saves successfully', async () => {
  renderer = await render()

  expect(getMemory).toHaveBeenCalledTimes(1)
  expect(getModels).toHaveBeenCalledTimes(1)
  const modelLabel = 'Acme AI / GPT-4o Mini'
  expect(renderer!.root.findAll((node) => node.children.includes(modelLabel))).toHaveLength(2)


  await act(async () => saveButton(renderer!).props.onClick())

  expect(updateMemory).toHaveBeenCalledWith({
    memory_async_extraction_enabled: true,
    memory_extraction_model_id: 'model-1',
    memory_extraction_cooldown_seconds: 180,
    memory_extraction_max_pending_turns: 6,
  })
})

test('does not allow saving defaults when memory settings fail to load', async () => {
  getMemory.mockImplementationOnce(() => Promise.reject(new Error('settings unavailable')))

  renderer = await render()

  expect(renderer!.root.findAllByType('button').some((button) => button.children.includes('saveChanges'))).toBe(false)
  expect(updateMemory).not.toHaveBeenCalled()
})

test('keeps loaded settings safe to save when model loading fails', async () => {
  getModels.mockImplementationOnce(() => Promise.reject(new Error('models unavailable')))

  renderer = await render()

  await act(async () => saveButton(renderer!).props.onClick())

  expect(updateMemory).toHaveBeenCalledWith({
    memory_async_extraction_enabled: true,
    memory_extraction_model_id: 'model-1',
    memory_extraction_cooldown_seconds: 180,
    memory_extraction_max_pending_turns: 6,
  })
})

test('disables and hides save when user lacks permission', async () => {
  canUpdate = false
  renderer = await render()

  expect(getMemory).toHaveBeenCalledTimes(1)
  expect(renderer.root.findByProps({ id: 'cooldown-seconds' }).props.disabled).toBe(true)
  expect(
    renderer.root.findAllByType('button').some((button) => button.children.includes('saveChanges')),
  ).toBe(false)
})
