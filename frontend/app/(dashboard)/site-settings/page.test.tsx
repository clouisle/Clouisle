import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { ApiError } from '@/lib/api/client'

const settings = {
  site_name: 'Clouisle',
  site_description: '',
  site_url: '',
  site_icon: '',
  default_language: 'en',
  auth_page_layout: 'centered',
  theme_mode: 'system',
  theme_branding_display: 'full',
  icp_record_number: '',
  icp_record_url: '',
  terms_enabled: false,
  terms_url: '',
  terms_text: '',
  privacy_enabled: false,
  privacy_url: '',
  privacy_text: '',
  require_terms_acceptance_on_register: false,
  ...Object.fromEntries(
    [
      'primary',
      'primary_foreground',
      'background',
      'foreground',
      'card',
      'card_foreground',
      'border',
      'ring',
      'sidebar',
      'sidebar_foreground',
      'sidebar_primary',
      'sidebar_primary_foreground',
      'sidebar_accent',
      'sidebar_accent_foreground',
      'sidebar_border',
      'navbar',
      'navbar_foreground',
      'navbar_hover',
      'navbar_hover_foreground',
      'accent',
      'accent_foreground',
      'muted',
      'muted_foreground',
      'chart_1',
      'chart_2',
      'chart_3',
      'chart_4',
      'chart_5',
    ].map((key) => [`theme_${key}_color`, '']),
  ),
}
const getGeneral = mock(() => Promise.resolve(settings))
const updateGeneral = mock(() => Promise.resolve())
const refresh = mock(() => Promise.resolve())
const toastSuccess = mock(() => {})
let canUpdate = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next-themes', () => ({ useTheme: () => ({ resolvedTheme: 'light' }) }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('lucide-react', () => ({ Loader2: () => null }))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children }: React.PropsWithChildren) => <label>{children}</label>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input {...props} type="checkbox" />,
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/components/ui/image-upload', () => ({
  ImageUpload: (props: Record<string, unknown>) => <button data-image-upload {...props} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <div data-select {...props}>{children}</div>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/popover', () => ({
  Popover: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PopoverContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  PopoverTrigger: () => null,
}))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <p role="alert">{children}</p> : null,
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { getGeneral, updateGeneral },
}))
mock.module('@/contexts/site-settings-context', () => ({ useSiteSettings: () => ({ refresh }) }))
mock.module('@/components/permission-guard', () => ({
  PermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
  useCanPerform: () => ({ canPerform: () => canUpdate }),
}))

const { default: SiteSettingsGeneralPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsGeneralPage />)
  })
  return renderer!
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!

afterEach(() => {
  mock.clearAllMocks()
  getGeneral.mockImplementation(() => Promise.resolve(settings))
  updateGeneral.mockImplementation(() => Promise.resolve())
  canUpdate = true
  Object.assign(settings, {
    site_name: 'Clouisle',
    icp_record_url: '',
    terms_enabled: false,
    terms_url: '',
    terms_text: '',
    privacy_enabled: false,
    privacy_url: '',
    privacy_text: '',
    theme_primary_color: '',
  })
})

test('blocks an empty site name before saving general settings', async () => {
  settings.site_name = ' '
  const renderer = await render()

  await act(async () => saveButton(renderer).props.onClick())

  expect(updateGeneral).not.toHaveBeenCalled()
  expect(renderer.root.findByProps({ id: 'siteName' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(1)
  act(() => renderer.unmount())
})

test('disables general settings controls for viewers without update permission', async () => {
  canUpdate = false
  const renderer = await render()

  expect(renderer.root.findByProps({ id: 'siteName' }).props.disabled).toBe(true)
  expect(renderer.root.findByProps({ id: 'termsUrl' }).props.disabled).toBe(true)
  act(() => renderer.unmount())
})

test('updates settings controls and saves the complete configuration', async () => {
  const renderer = await render()

  act(() => {
    renderer.root.findByProps({ id: 'siteName' }).props.onChange({ target: { value: 'New site' } })
    renderer.root.findByProps({ id: 'termsEnabled' }).props.onCheckedChange(true)
    renderer.root.findByProps({ id: 'termsText' }).props.onChange({ target: { value: 'Terms' } })
    renderer.root.findByProps({ 'data-image-upload': true }).props.onChange('/icon.svg')
    renderer.root.findAllByProps({ 'data-select': true })[0].props.onValueChange('dark')
  })
  await act(async () => saveButton(renderer).props.onClick())

  expect(updateGeneral).toHaveBeenCalledWith(expect.objectContaining({
    site_name: 'New site',
    site_icon: '/icon.svg',
    theme_mode: 'dark',
    terms_enabled: true,
    terms_text: 'Terms',
  }))
  expect(refresh).toHaveBeenCalledTimes(1)
  expect(toastSuccess).toHaveBeenCalledWith('saveSuccess')
  act(() => renderer.unmount())
})

test('rejects unsafe URLs, missing legal content, and malformed theme colors', async () => {
  Object.assign(settings, {
    icp_record_url: 'ftp://example.com',
    terms_enabled: true,
    privacy_enabled: true,
    privacy_url: 'not a url',
    theme_primary_color: '#12',
  })
  const renderer = await render()

  await act(async () => saveButton(renderer).props.onClick())

  expect(updateGeneral).not.toHaveBeenCalled()
  expect(renderer.root.findByProps({ id: 'icpRecordUrl' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findByProps({ id: 'termsUrl' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findByProps({ id: 'privacyUrl' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findAllByProps({ role: 'alert' }).some((node) => node.children.includes('invalidThemeColor'))).toBe(true)
  act(() => renderer.unmount())
})

test('maps server validation errors and clears a field error when edited', async () => {
  updateGeneral.mockRejectedValueOnce(new ApiError(1001, 'Invalid', {
    errors: { 'settings.site_name': ['Already used'] },
  }))
  const renderer = await render()

  await act(async () => saveButton(renderer).props.onClick())
  expect(renderer.root.findByProps({ id: 'siteName' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findAllByProps({ role: 'alert' }).some((node) => node.children.includes('Already used'))).toBe(true)

  act(() => renderer.root.findByProps({ id: 'siteName' }).props.onChange({ target: { value: 'Available' } }))
  expect(renderer.root.findByProps({ id: 'siteName' }).props['aria-invalid']).toBe(false)
  act(() => renderer.unmount())
})

test('leaves the page usable when loading settings fails', async () => {
  getGeneral.mockRejectedValueOnce(new Error('offline'))
  const renderer = await render()

  expect(renderer.root.findByProps({ id: 'siteName' }).props.value).toBe('Clouisle')
  expect(saveButton(renderer)).toBeDefined()
  act(() => renderer.unmount())
})

test('formats theme alpha, resets colors, and ignores unsupported select values', async () => {
  const renderer = await render()
  const selects = renderer.root.findAllByProps({ 'data-select': true })

  act(() => {
    renderer.root.findByProps({ id: 'themePrimaryColorPicker' }).props.onChange({ target: { value: '#336699' } })
    selects[1].props.onValueChange('hidden')
    selects[2].props.onValueChange('zh')
    selects[3].props.onValueChange('split')
    selects[0].props.onValueChange('unsupported')
    selects[1].props.onValueChange('unsupported')
    selects[3].props.onValueChange('unsupported')
  })
  const alpha = renderer.root.findByProps({ 'aria-label': 'themePrimaryColor themeColorAlpha' })
  act(() => alpha.props.onChange({ target: { value: '50' } }))
  await act(async () => saveButton(renderer).props.onClick())

  expect(updateGeneral).toHaveBeenLastCalledWith(expect.objectContaining({
    theme_primary_color: '#33669980',
    theme_mode: 'system',
    theme_branding_display: 'hidden',
    default_language: 'zh',
    auth_page_layout: 'split',
  }))

  act(() => renderer.root.findAllByType('button').find((button) => button.children.includes('resetAllThemeColors'))!.props.onClick())
  await act(async () => saveButton(renderer).props.onClick())
  expect(updateGeneral).toHaveBeenLastCalledWith(expect.objectContaining({ theme_primary_color: '' }))
  act(() => renderer.unmount())
})

test('updates every text field, switch, and supported select branch', async () => {
  const renderer = await render()
  const selects = renderer.root.findAllByProps({ 'data-select': true })

  act(() => {
    renderer.root.findByProps({ id: 'siteDescription' }).props.onChange({ target: { value: 'Knowledge hub' } })
    renderer.root.findByProps({ id: 'siteUrl' }).props.onChange({ target: { value: 'https://example.com' } })
    renderer.root.findByProps({ id: 'icpRecordNumber' }).props.onChange({ target: { value: 'ICP-1' } })
    renderer.root.findByProps({ id: 'icpRecordUrl' }).props.onChange({ target: { value: 'https://beian.example.com' } })
    renderer.root.findByProps({ id: 'termsUrl' }).props.onChange({ target: { value: 'https://example.com/terms' } })
    renderer.root.findByProps({ id: 'privacyEnabled' }).props.onCheckedChange(true)
    renderer.root.findByProps({ id: 'privacyUrl' }).props.onChange({ target: { value: 'https://example.com/privacy' } })
    renderer.root.findByProps({ id: 'privacyText' }).props.onChange({ target: { value: 'Privacy' } })
    renderer.root.findByProps({ id: 'requireTermsAcceptanceOnRegister' }).props.onCheckedChange(true)
    selects[0].props.onValueChange('light')
    selects[1].props.onValueChange('name_only')
    selects[1].props.onValueChange('icon_only')
    selects[2].props.onValueChange('')
    selects[3].props.onValueChange('centered')
  })
  await act(async () => saveButton(renderer).props.onClick())

  expect(updateGeneral).toHaveBeenLastCalledWith(expect.objectContaining({
    site_description: 'Knowledge hub',
    site_url: 'https://example.com',
    icp_record_number: 'ICP-1',
    icp_record_url: 'https://beian.example.com',
    terms_url: 'https://example.com/terms',
    privacy_enabled: true,
    privacy_url: 'https://example.com/privacy',
    privacy_text: 'Privacy',
    require_terms_acceptance_on_register: true,
    theme_mode: 'light',
    theme_branding_display: 'icon_only',
    default_language: 'en',
    auth_page_layout: 'centered',
  }))
  act(() => renderer.unmount())
})

test('updates and resets every theme color field', async () => {
  const renderer = await render()
  const colorIds = [
    'themePrimaryColor',
    'themePrimaryForegroundColor',
    'themeBackgroundColor',
    'themeForegroundColor',
    'themeCardColor',
    'themeCardForegroundColor',
    'themeBorderColor',
    'themeRingColor',
    'themeSidebarColor',
    'themeSidebarForegroundColor',
    'themeSidebarPrimaryColor',
    'themeSidebarPrimaryForegroundColor',
    'themeSidebarAccentColor',
    'themeSidebarAccentForegroundColor',
    'themeSidebarBorderColor',
    'themeNavbarColor',
    'themeNavbarForegroundColor',
    'themeNavbarHoverColor',
    'themeNavbarHoverForegroundColor',
    'themeAccentColor',
    'themeAccentForegroundColor',
    'themeMutedColor',
    'themeMutedForegroundColor',
    'themeChart1Color',
    'themeChart2Color',
    'themeChart3Color',
    'themeChart4Color',
    'themeChart5Color',
  ]

  act(() => {
    for (const id of colorIds) {
      renderer.root.findByProps({ id: `${id}Picker` }).props.onChange({ target: { value: '#112233' } })
    }
  })
  await act(async () => saveButton(renderer).props.onClick())
  expect(updateGeneral).toHaveBeenLastCalledWith(expect.objectContaining({
    theme_primary_foreground_color: '#112233',
    theme_background_color: '#112233',
    theme_chart_5_color: '#112233',
  }))

  act(() => {
    for (const button of renderer.root.findAllByType('button').filter((node) => node.children.includes('resetThemeColor'))) {
      button.props.onClick()
    }
  })
  await act(async () => saveButton(renderer).props.onClick())
  expect(updateGeneral).toHaveBeenLastCalledWith(expect.objectContaining({
    theme_primary_foreground_color: '',
    theme_background_color: '',
    theme_chart_5_color: '',
  }))
  act(() => renderer.unmount())
})

test('recovers after legal validation and a failed save without server field errors', async () => {
  updateGeneral.mockRejectedValueOnce(new Error('timeout'))
  const renderer = await render()

  act(() => {
    renderer.root.findByProps({ id: 'termsEnabled' }).props.onCheckedChange(true)
    renderer.root.findByProps({ id: 'privacyEnabled' }).props.onCheckedChange(true)
  })
  await act(async () => saveButton(renderer).props.onClick())
  expect(updateGeneral).not.toHaveBeenCalled()
  expect(renderer.root.findByProps({ id: 'privacyUrl' }).props['aria-invalid']).toBe(true)

  act(() => {
    renderer.root.findByProps({ id: 'termsText' }).props.onChange({ target: { value: 'Terms' } })
    renderer.root.findByProps({ id: 'privacyText' }).props.onChange({ target: { value: 'Privacy' } })
  })
  await act(async () => saveButton(renderer).props.onClick())
  expect(updateGeneral).toHaveBeenCalledTimes(1)
  expect(refresh).not.toHaveBeenCalled()
  expect(renderer.root.findByProps({ id: 'privacyUrl' }).props['aria-invalid']).toBe(false)

  await act(async () => saveButton(renderer).props.onClick())
  expect(refresh).toHaveBeenCalledTimes(1)
  expect(toastSuccess).toHaveBeenCalledWith('saveSuccess')
  act(() => renderer.unmount())
})
