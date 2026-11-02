import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const getWatermark = mock(() => Promise.resolve(loadedSettings))
const updateWatermark = mock((data: Record<string, unknown>) => Promise.resolve(data))
const success = mock(() => {})
const errorToast = mock(() => {})
const refresh = mock(() => Promise.resolve())

const loadedSettings = {
  watermark_enabled: true,
  watermark_content: '{username} {date}',
  watermark_opacity: 20,
  watermark_font_size: 24,
  watermark_rotation: 15,
  watermark_gap: 240,
  watermark_color: '#ff0000',
}

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success, error: errorToast } }))
mock.module('lucide-react', () => ({ Droplets: () => null, Loader2: () => null }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <p role="alert">{children}</p> : null,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children }: React.PropsWithChildren) => <label>{children}</label>,
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: ({
    onChange,
    ...props
  }: {
    id: string
    value: number | ''
    onChange: (value: number | '') => void
  }) => (
    <input
      {...props}
      value={props.value}
      onChange={(event) =>
        onChange(event.target.value === '' ? '' : Number(event.target.value))
      }
    />
  ),
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div data-skeleton /> }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({
    onCheckedChange,
    ...props
  }: {
    checked: boolean
    disabled?: boolean
    onCheckedChange: (checked: boolean) => void
  }) => (
    <input
      {...props}
      type="checkbox"
      onChange={(event) => onCheckedChange(event.target.checked)}
    />
  ),
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => true }),
}))
mock.module('@/contexts/site-settings-context', () => ({
  useSiteSettings: () => ({ settings: { site_name: 'Acme' }, loading: false, refresh }),
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { getWatermark, updateWatermark },
}))

const { default: SiteSettingsWatermarkPage } = await import('./page') // dynamic: mock.module() must register before the module evaluates

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsWatermarkPage />)
  })
  renderers.push(renderer!)
  return renderer!
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root
    .findAllByType('button')
    .find((button) => button.children.includes('saveChanges'))!

const findInput = (renderer: ReactTestRenderer, id: string) =>
  // match host <input> nodes: composite nodes expose the page's own handler props
  renderer.root.findAllByType('input').find((element) => element.props.id === id)

const input = (renderer: ReactTestRenderer, id: string) => findInput(renderer, id)!

const button = (renderer: ReactTestRenderer, label: string) =>
  renderer.root.findAllByType('button').find((node) => node.children.includes(label))

beforeEach(() => {
  getWatermark.mockImplementation(() => Promise.resolve(loadedSettings))
  updateWatermark.mockImplementation((data: Record<string, unknown>) =>
    Promise.resolve(data)
  )
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.clearAllMocks()
})

describe('SiteSettingsWatermarkPage', () => {
  test('renders the loaded watermark configuration', async () => {
    const renderer = await render()
    expect(input(renderer, 'watermarkEnabled').props.checked).toBe(true)
    expect(input(renderer, 'watermarkContent').props.value).toBe('{username} {date}')
    expect(input(renderer, 'watermark_opacity').props.value).toBe(20)
    expect(input(renderer, 'watermark_font_size').props.value).toBe(24)
    expect(input(renderer, 'watermark_rotation').props.value).toBe(15)
    expect(input(renderer, 'watermark_gap').props.value).toBe(240)
    expect(input(renderer, 'watermarkColor').props.value).toBe('#ff0000')
    expect(renderer.root.findAllByProps({ 'data-testid': 'watermark-overlay' })).toHaveLength(1)
  })

  test('saves the full payload and refreshes public site settings', async () => {
    const renderer = await render()
    await act(async () => input(renderer, 'watermarkEnabled').props.onChange({ target: { checked: false } }))
    await act(async () => input(renderer, 'watermarkContent').props.onChange({ target: { value: ' {email} ' } }))
    await act(async () => saveButton(renderer).props.onClick())

    expect(updateWatermark).toHaveBeenCalledWith({
      watermark_enabled: false,
      watermark_content: '{email}',
      watermark_opacity: 20,
      watermark_font_size: 24,
      watermark_rotation: 15,
      watermark_gap: 240,
      watermark_color: '#ff0000',
    })
    expect(refresh).toHaveBeenCalled()
    expect(success).toHaveBeenCalledWith('saveSuccess')
  })

  test('blocks saving when the content is cleared', async () => {
    const renderer = await render()
    await act(async () => input(renderer, 'watermarkContent').props.onChange({ target: { value: '   ' } }))
    await act(async () => saveButton(renderer).props.onClick())

    expect(updateWatermark).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(1)
    expect(renderer.root.findAllByProps({ role: 'alert' })[0].children).toEqual([
      'watermarkContentRequired',
    ])
  })

  test('blocks saving when a number leaves its allowed range', async () => {
    const renderer = await render()
    await act(async () => input(renderer, 'watermark_gap').props.onChange({ target: { value: '10' } }))
    await act(async () => saveButton(renderer).props.onClick())

    expect(updateWatermark).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' })[0].children).toEqual([
      'watermarkRangeError',
    ])
  })

  test('keeps the form unsavable when the initial load fails, then retries', async () => {
    const consoleError = mock(() => {})
    const originalConsoleError = console.error
    console.error = consoleError
    getWatermark.mockImplementationOnce(() => Promise.reject(new Error('offline')))

    try {
      const renderer = await render()
      expect(renderer.root.findAllByType('p').some((node) => node.children.includes('loadError'))).toBe(true)
      expect(button(renderer, 'saveChanges')).toBeUndefined()
      expect(updateWatermark).not.toHaveBeenCalled()

      await act(async () => button(renderer, 'retry')!.props.onClick())
      expect(input(renderer, 'watermarkContent').props.value).toBe('{username} {date}')
    } finally {
      console.error = originalConsoleError
    }
  })

  test('expands a short hex color for the native picker while keeping the stored value', async () => {
    getWatermark.mockImplementationOnce(() => Promise.resolve({ ...loadedSettings, watermark_color: '#abc' }))
    const renderer = await render()

    expect(input(renderer, 'watermarkColor').props.value).toBe('#aabbcc')
    const layer = renderer.root
      .findAllByType('div')
      .find((node) => node.props['data-testid'] === 'watermark-overlay')!
    expect(layer.props.style.color).toBe('#abc')
  })

  test('shows the automatic color state instead of a black swatch', async () => {
    getWatermark.mockImplementationOnce(() => Promise.resolve({ ...loadedSettings, watermark_color: '' }))
    const renderer = await render()

    expect(findInput(renderer, 'watermarkColor')).toBeUndefined()
    expect(button(renderer, 'watermarkColorAuto')).toBeUndefined()
    expect(button(renderer, 'watermarkColorPick')).toBeDefined()

    await act(async () => button(renderer, 'watermarkColorPick')!.props.onClick())
    expect(input(renderer, 'watermarkColor').props.value).toBe('#000000')
  })
})
