'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Loader2 } from 'lucide-react'
import { ImageUpload } from '@/components/ui/image-upload'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { FieldError } from '@/components/ui/field'
import { siteSettingsApi, type GeneralSettings } from '@/lib/api/admin/site-settings'
import { useSiteSettings } from '@/contexts/site-settings-context'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'

type ThemeColorKey = Extract<keyof GeneralSettings, `theme_${string}_color`>

const THEME_COLOR_KEYS = [
  'theme_primary_color',
  'theme_primary_foreground_color',
  'theme_background_color',
  'theme_foreground_color',
  'theme_card_color',
  'theme_card_foreground_color',
  'theme_border_color',
  'theme_ring_color',
  'theme_sidebar_color',
  'theme_sidebar_foreground_color',
  'theme_sidebar_primary_color',
  'theme_sidebar_primary_foreground_color',
  'theme_sidebar_accent_color',
  'theme_sidebar_accent_foreground_color',
  'theme_sidebar_border_color',
  'theme_navbar_color',
  'theme_navbar_foreground_color',
  'theme_navbar_hover_color',
  'theme_navbar_hover_foreground_color',
  'theme_accent_color',
  'theme_accent_foreground_color',
  'theme_muted_color',
  'theme_muted_foreground_color',
  'theme_chart_1_color',
  'theme_chart_2_color',
  'theme_chart_3_color',
  'theme_chart_4_color',
  'theme_chart_5_color',
] as const satisfies readonly ThemeColorKey[]

const COLOR_INPUT_FALLBACK = '#000000'
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/

function parseThemeColor(value: string) {
  if (!HEX_COLOR_PATTERN.test(value)) {
    return { color: COLOR_INPUT_FALLBACK, alpha: 100 }
  }

  const digits = value.slice(1)
  const color = digits.length <= 4
    ? `#${digits.slice(0, 3).split('').map((char) => `${char}${char}`).join('')}`
    : `#${digits.slice(0, 6)}`
  const alphaHex = digits.length === 4
    ? `${digits[3]}${digits[3]}`
    : digits.length === 8
      ? digits.slice(6, 8)
      : 'ff'

  return { color, alpha: Math.round((Number.parseInt(alphaHex, 16) / 255) * 100) }
}

function formatThemeColor(color: string, alpha: number) {
  if (alpha >= 100) return color
  return `${color}${Math.round((alpha / 100) * 255).toString(16).padStart(2, '0')}`
}

function ThemeColorField({
  id,
  label,
  value,
  error,
  disabled,
  onChange,
}: {
  id: string
  label: string
  value: string
  error?: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  const t = useTranslations('siteSettings')
  const parsed = parseThemeColor(value)

  return (
    <div className="space-y-1">
      <Popover>
        <PopoverTrigger
          render={
            <button
              type="button"
              className="flex w-full items-center gap-2 rounded-md border p-2 text-left hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={disabled}
            >
              <span
                className="h-6 w-8 shrink-0 rounded border bg-[image:linear-gradient(45deg,#ddd_25%,transparent_25%),linear-gradient(-45deg,#ddd_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#ddd_75%),linear-gradient(-45deg,transparent_75%,#ddd_75%)] bg-[length:8px_8px] bg-[position:0_0,0_4px,4px_-4px,-4px_0]"
                aria-hidden="true"
              >
                <span className="block h-full w-full rounded" style={{ background: formatThemeColor(parsed.color, parsed.alpha) }} />
              </span>
              <span className="min-w-0 flex-1 truncate text-xs font-medium">{label}</span>
              <span className="text-xs tabular-nums text-muted-foreground">{parsed.alpha}%</span>
            </button>
          }
        />
        <PopoverContent className="w-64 space-y-4" align="start">
          <div className="flex items-center justify-between gap-3">
            <Label htmlFor={`${id}Picker`}>{label}</Label>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange('')}
              disabled={disabled || !value}
            >
              {t('resetThemeColor')}
            </Button>
          </div>
          <div className="flex items-center gap-3">
            <Input
              id={`${id}Picker`}
              type="color"
              className="h-10 w-14 cursor-pointer p-1"
              value={parsed.color}
              onChange={(e) => onChange(formatThemeColor(e.target.value, parsed.alpha))}
              disabled={disabled}
              aria-label={label}
            />
            <div className="min-w-0 flex-1 text-xs text-muted-foreground">
              <div>{formatThemeColor(parsed.color, parsed.alpha)}</div>
              <div>{t('themeColorAlpha')}: {parsed.alpha}%</div>
            </div>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            step="1"
            value={parsed.alpha}
            onChange={(event) => onChange(formatThemeColor(parsed.color, Number(event.target.value)))}
            disabled={disabled}
            className="w-full accent-primary"
            aria-label={`${label} ${t('themeColorAlpha')}`}
          />
        </PopoverContent>
      </Popover>
      <FieldError>{error}</FieldError>
    </div>
  )
}

function expandThemeColor(value: string) {
  if (!HEX_COLOR_PATTERN.test(value)) return value
  const digits = value.slice(1)
  if (digits.length === 4 || digits.length === 8) {
    const { color, alpha } = parseThemeColor(value)
    return `${color}${Math.round((alpha / 100) * 255).toString(16).padStart(2, '0')}`
  }
  return value
}

function themeColor(value: string, cssVariable: string) {
  return HEX_COLOR_PATTERN.test(value) ? expandThemeColor(value) : `var(${cssVariable})`
}

function ThemePreview({ settings }: { settings: GeneralSettings }) {
  const t = useTranslations('siteSettings')
  const background = themeColor(settings.theme_background_color, '--background')
  const foreground = themeColor(settings.theme_foreground_color, '--foreground')
  const card = themeColor(settings.theme_card_color, '--card')
  const cardForeground = themeColor(settings.theme_card_foreground_color, '--card-foreground')
  const border = themeColor(settings.theme_border_color, '--border')
  const primary = themeColor(settings.theme_primary_color, '--primary')
  const primaryForeground = themeColor(settings.theme_primary_foreground_color, '--primary-foreground')
  const muted = themeColor(settings.theme_muted_color, '--muted')
  const mutedForeground = themeColor(settings.theme_muted_foreground_color, '--muted-foreground')
  const accent = themeColor(settings.theme_accent_color, '--accent')
  const accentForeground = themeColor(settings.theme_accent_foreground_color, '--accent-foreground')
  const sidebar = themeColor(settings.theme_sidebar_color, '--sidebar')
  const sidebarForeground = themeColor(settings.theme_sidebar_foreground_color, '--sidebar-foreground')
  const sidebarPrimary = themeColor(settings.theme_sidebar_primary_color || settings.theme_primary_color, '--sidebar-primary')
  const sidebarPrimaryForeground = themeColor(settings.theme_sidebar_primary_foreground_color || settings.theme_primary_foreground_color, '--sidebar-primary-foreground')
  const sidebarAccent = themeColor(settings.theme_sidebar_accent_color, '--sidebar-accent')
  const sidebarAccentForeground = themeColor(settings.theme_sidebar_accent_foreground_color, '--sidebar-accent-foreground')
  const sidebarBorder = themeColor(settings.theme_sidebar_border_color, '--sidebar-border')
  const navbar = themeColor(settings.theme_navbar_color, '--navbar')
  const navbarForeground = themeColor(settings.theme_navbar_foreground_color, '--navbar-foreground')
  const navbarHover = themeColor(settings.theme_navbar_hover_color, '--navbar-hover')
  const navbarHoverForeground = themeColor(settings.theme_navbar_hover_foreground_color, '--navbar-hover-foreground')
  const chartColors = [
    themeColor(settings.theme_chart_1_color, '--chart-1'),
    themeColor(settings.theme_chart_2_color, '--chart-2'),
    themeColor(settings.theme_chart_3_color, '--chart-3'),
    themeColor(settings.theme_chart_4_color, '--chart-4'),
    themeColor(settings.theme_chart_5_color, '--chart-5'),
  ]

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div>
        <h3 className="font-medium">{t('themePreview')}</h3>
        <p className="text-sm text-muted-foreground">{t('themePreviewDescription')}</p>
      </div>
      <div className="overflow-hidden rounded-xl border text-xs shadow-sm" style={{ background, color: foreground, borderColor: border }}>
        <div className="grid min-h-64 grid-cols-[120px_1fr]">
          <aside className="space-y-3 border-r p-3" style={{ background: sidebar, color: sidebarForeground, borderColor: sidebarBorder }}>
            <div className="h-5 w-20 rounded" style={{ background: sidebarPrimary, color: sidebarPrimaryForeground }} />
            <div className="rounded px-2 py-1 font-medium" style={{ background: sidebarAccent, color: sidebarAccentForeground }}>
              {t('themePreviewNavActive')}
            </div>
            <div className="px-2 py-1 opacity-80">{t('themePreviewNavItem')}</div>
            <div className="px-2 py-1 opacity-80">{t('themePreviewNavItem')}</div>
          </aside>
          <main className="space-y-3 p-4">
            <div className="flex items-center justify-between rounded-md px-3 py-2" style={{ background: navbar, color: navbarForeground }}>
              <div className="font-medium">{t('themePreviewNavbar')}</div>
              <div className="rounded px-2 py-1" style={{ background: navbarHover, color: navbarHoverForeground }}>
                {t('themePreviewHover')}
              </div>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold">{t('themePreviewTitle')}</div>
                <div style={{ color: mutedForeground }}>{t('themePreviewSubtitle')}</div>
              </div>
              <div className="rounded-md px-3 py-1 font-medium" style={{ background: primary, color: primaryForeground }}>
                {t('themePreviewAction')}
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-3 rounded-lg border p-3" style={{ background: card, color: cardForeground, borderColor: border }}>
                <div className="font-medium">{t('themePreviewCard')}</div>
                <div className="rounded-md px-2 py-1" style={{ background: muted, color: mutedForeground }}>
                  {t('themePreviewMuted')}
                </div>
                <div className="rounded-md px-2 py-1" style={{ background: accent, color: accentForeground }}>
                  {t('themePreviewAccent')}
                </div>
              </div>
              <div className="rounded-lg border p-3" style={{ background: card, color: cardForeground, borderColor: border }}>
                <div className="mb-3 font-medium">{t('themePreviewChart')}</div>
                <div className="flex h-24 items-end gap-2">
                  {chartColors.map((color, index) => (
                    <div
                      key={index}
                      className="flex-1 rounded-t"
                      style={{ height: `${36 + index * 10}%`, background: color }}
                    />
                  ))}
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}

export default function SiteSettingsGeneralPage() {
  const t = useTranslations('siteSettings')
  const { refresh: refreshSiteSettings } = useSiteSettings()
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')
  
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [settings, setSettings] = React.useState<GeneralSettings>({
    site_name: 'Clouisle',
    site_description: '',
    site_url: '',
    site_icon: '',
    default_language: 'en',
    auth_page_layout: 'centered',
    theme_mode: 'system',
    theme_primary_color: '',
    theme_primary_foreground_color: '',
    theme_background_color: '',
    theme_foreground_color: '',
    theme_card_color: '',
    theme_card_foreground_color: '',
    theme_border_color: '',
    theme_ring_color: '',
    theme_sidebar_color: '',
    theme_sidebar_foreground_color: '',
    theme_sidebar_primary_color: '',
    theme_sidebar_primary_foreground_color: '',
    theme_sidebar_accent_color: '',
    theme_sidebar_accent_foreground_color: '',
    theme_sidebar_border_color: '',
    theme_navbar_color: '',
    theme_navbar_foreground_color: '',
    theme_navbar_hover_color: '',
    theme_navbar_hover_foreground_color: '',
    theme_accent_color: '',
    theme_accent_foreground_color: '',
    theme_muted_color: '',
    theme_muted_foreground_color: '',
    theme_chart_1_color: '',
    theme_chart_2_color: '',
    theme_chart_3_color: '',
    theme_chart_4_color: '',
    theme_chart_5_color: '',
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
  })

  const errorPathMap = React.useMemo(
    () => Object.fromEntries(
      Object.keys(settings).flatMap((key) => [
        [key, key],
        [`settings.${key}`, key],
      ])
    ),
    [settings]
  )

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, Object.keys(settings)),
    [fieldErrors, settings]
  )

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      const data = await siteSettingsApi.getGeneral()
      setSettings(data)
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    loadSettings()
  }, [loadSettings])

  const handleSave = async () => {
    const nextErrors: Record<string, string> = {}

    if (!settings.site_name.trim()) {
      nextErrors.site_name = t('required')
    }

    const validateUrl = (key: keyof GeneralSettings) => {
      const value = settings[key]
      if (typeof value !== 'string' || !value.trim()) {
        return
      }
      try {
        const url = new URL(value)
        if (!['http:', 'https:'].includes(url.protocol)) {
          nextErrors[key] = t('invalidUrl')
        }
      } catch {
        nextErrors[key] = t('invalidUrl')
      }
    }

    validateUrl('icp_record_url')
    validateUrl('terms_url')
    validateUrl('privacy_url')

    const validateHexColor = (key: ThemeColorKey) => {
      const value = settings[key].trim()
      if (value && !HEX_COLOR_PATTERN.test(value)) {
        nextErrors[key] = t('invalidThemeColor')
      }
    }

    THEME_COLOR_KEYS.forEach(validateHexColor)

    if (settings.terms_enabled && !settings.terms_url.trim() && !settings.terms_text.trim()) {
      nextErrors.terms_url = t('legalEntryRequired')
    }
    if (settings.privacy_enabled && !settings.privacy_url.trim() && !settings.privacy_text.trim()) {
      nextErrors.privacy_url = t('legalEntryRequired')
    }

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    try {
      setSaving(true)
      await siteSettingsApi.updateGeneral(settings)
      await refreshSiteSettings()
      toast.success(t('saveSuccess'))
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), errorPathMap)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to save settings:', error)
    } finally {
      setSaving(false)
    }
  }

  const updateSetting = <K extends keyof GeneralSettings>(key: K, value: GeneralSettings[K]) => {
    setSettings(prev => ({ ...prev, [key]: value }))
    setFieldErrors((prev) => clearValidationError(prev, key))
  }

  const resetThemeColors = () => {
    setSettings((prev) => ({
      ...prev,
      ...Object.fromEntries(THEME_COLOR_KEYS.map((key) => [key, ''])),
    }))
    setFieldErrors((prev) => {
      const nextErrors = { ...prev }
      THEME_COLOR_KEYS.forEach((key) => delete nextErrors[key])
      return nextErrors
    })
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-48" />
          </CardHeader>
          <CardContent className="space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-32" />
            <Skeleton className="h-4 w-48" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-16 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {summaryEntries.length > 0 && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
          {summaryEntries.map(([field, message]) => (
            <FieldError key={field}>{formatValidationSummaryMessage(field, message)}</FieldError>
          ))}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>{t('siteInfo')}</CardTitle>
          <CardDescription>{t('siteInfoDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="siteName">{t('siteName')}</Label>
            <Input
              id="siteName"
              placeholder={t('siteNamePlaceholder')}
              value={settings.site_name}
              onChange={(e) => updateSetting('site_name', e.target.value)}
              disabled={!canUpdate}
              aria-invalid={!!fieldErrors.site_name}
            />
            <FieldError>{fieldErrors.site_name}</FieldError>
          </div>
          <div className="space-y-2">
            <Label htmlFor="siteDescription">{t('siteDescription')}</Label>
            <Textarea
              id="siteDescription"
              placeholder={t('siteDescriptionPlaceholder')}
              rows={3}
              value={settings.site_description}
              onChange={(e) => updateSetting('site_description', e.target.value)}
              disabled={!canUpdate}
              aria-invalid={!!fieldErrors.site_description}
            />
            <FieldError>{fieldErrors.site_description}</FieldError>
          </div>
          <div className="space-y-2">
            <Label htmlFor="siteUrl">{t('siteUrl')}</Label>
            <Input
              id="siteUrl"
              placeholder="https://example.com"
              value={settings.site_url}
              onChange={(e) => updateSetting('site_url', e.target.value)}
              disabled={!canUpdate}
              aria-invalid={!!fieldErrors.site_url}
            />
            <FieldError>{fieldErrors.site_url}</FieldError>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('siteBranding')}</CardTitle>
          <CardDescription>{t('siteBrandingDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label>{t('siteIcon')}</Label>
            <p className="text-sm text-muted-foreground">{t('siteIconDescription')}</p>
            <div className="mt-2">
              <ImageUpload
                value={settings.site_icon}
                onChange={(url) => updateSetting('site_icon', url)}
                previewSize="md"
                category="icons"
                disabled={!canUpdate}
              />
              <FieldError>{fieldErrors.site_icon}</FieldError>
              <p className="text-xs text-muted-foreground mt-2">{t('siteIconHint')}</p>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="themeMode">{t('themeMode')}</Label>
            <p className="text-sm text-muted-foreground">{t('themeModeDescription')}</p>
            <Select
              value={settings.theme_mode}
              onValueChange={(value) => {
                if (value === 'system' || value === 'light' || value === 'dark') {
                  updateSetting('theme_mode', value)
                }
              }}
              disabled={!canUpdate}
            >
              <SelectTrigger id="themeMode" className="w-48">
                <SelectValue>
                  {settings.theme_mode === 'light'
                    ? t('themeModeLight')
                    : settings.theme_mode === 'dark'
                      ? t('themeModeDark')
                      : t('themeModeSystem')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">{t('themeModeSystem')}</SelectItem>
                <SelectItem value="light">{t('themeModeLight')}</SelectItem>
                <SelectItem value="dark">{t('themeModeDark')}</SelectItem>
              </SelectContent>
            </Select>
            <FieldError>{fieldErrors.theme_mode}</FieldError>
          </div>
          <div className="space-y-2">
            <Label htmlFor="brandingDisplay">{t('brandingDisplay')}</Label>
            <p className="text-sm text-muted-foreground">{t('brandingDisplayDescription')}</p>
            <Select
              value={settings.theme_branding_display}
              onValueChange={(value) => {
                if (value === 'full' || value === 'name_only' || value === 'icon_only' || value === 'hidden') {
                  updateSetting('theme_branding_display', value)
                }
              }}
              disabled={!canUpdate}
            >
              <SelectTrigger id="brandingDisplay" className="w-56">
                <SelectValue>
                  {settings.theme_branding_display === 'name_only'
                    ? t('brandingDisplayNameOnly')
                    : settings.theme_branding_display === 'icon_only'
                      ? t('brandingDisplayIconOnly')
                      : settings.theme_branding_display === 'hidden'
                        ? t('brandingDisplayHidden')
                        : t('brandingDisplayFull')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full">{t('brandingDisplayFull')}</SelectItem>
                <SelectItem value="name_only">{t('brandingDisplayNameOnly')}</SelectItem>
                <SelectItem value="icon_only">{t('brandingDisplayIconOnly')}</SelectItem>
                <SelectItem value="hidden">{t('brandingDisplayHidden')}</SelectItem>
              </SelectContent>
            </Select>
            <FieldError>{fieldErrors.theme_branding_display}</FieldError>
          </div>
          <ThemePreview settings={settings} />

          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={resetThemeColors}
              disabled={!canUpdate}
            >
              {t('resetAllThemeColors')}
            </Button>
          </div>

          <div className="space-y-5 rounded-lg border p-4">
            <div>
              <h3 className="font-medium">{t('themeBrandColors')}</h3>
              <p className="text-sm text-muted-foreground">{t('themeColorHint')}</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <ThemeColorField id="themePrimaryColor" label={t('themePrimaryColor')} value={settings.theme_primary_color} error={fieldErrors.theme_primary_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_primary_color', value)} />
              <ThemeColorField id="themePrimaryForegroundColor" label={t('themePrimaryForegroundColor')} value={settings.theme_primary_foreground_color} error={fieldErrors.theme_primary_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_primary_foreground_color', value)} />
            </div>
          </div>

          <div className="space-y-5 rounded-lg border p-4">
            <h3 className="font-medium">{t('themePageAndCards')}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <ThemeColorField id="themeBackgroundColor" label={t('themeBackgroundColor')} value={settings.theme_background_color} error={fieldErrors.theme_background_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_background_color', value)} />
              <ThemeColorField id="themeForegroundColor" label={t('themeForegroundColor')} value={settings.theme_foreground_color} error={fieldErrors.theme_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_foreground_color', value)} />
              <ThemeColorField id="themeCardColor" label={t('themeCardColor')} value={settings.theme_card_color} error={fieldErrors.theme_card_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_card_color', value)} />
              <ThemeColorField id="themeCardForegroundColor" label={t('themeCardForegroundColor')} value={settings.theme_card_foreground_color} error={fieldErrors.theme_card_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_card_foreground_color', value)} />
              <ThemeColorField id="themeBorderColor" label={t('themeBorderColor')} value={settings.theme_border_color} error={fieldErrors.theme_border_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_border_color', value)} />
              <ThemeColorField id="themeRingColor" label={t('themeRingColor')} value={settings.theme_ring_color} error={fieldErrors.theme_ring_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_ring_color', value)} />
            </div>
          </div>

          <div className="space-y-5 rounded-lg border p-4">
            <h3 className="font-medium">{t('themeNavigationColors')}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <ThemeColorField id="themeSidebarColor" label={t('themeSidebarColor')} value={settings.theme_sidebar_color} error={fieldErrors.theme_sidebar_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_color', value)} />
              <ThemeColorField id="themeSidebarForegroundColor" label={t('themeSidebarForegroundColor')} value={settings.theme_sidebar_foreground_color} error={fieldErrors.theme_sidebar_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_foreground_color', value)} />
              <ThemeColorField id="themeSidebarPrimaryColor" label={t('themeSidebarPrimaryColor')} value={settings.theme_sidebar_primary_color} error={fieldErrors.theme_sidebar_primary_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_primary_color', value)} />
              <ThemeColorField id="themeSidebarPrimaryForegroundColor" label={t('themeSidebarPrimaryForegroundColor')} value={settings.theme_sidebar_primary_foreground_color} error={fieldErrors.theme_sidebar_primary_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_primary_foreground_color', value)} />
              <ThemeColorField id="themeSidebarAccentColor" label={t('themeSidebarAccentColor')} value={settings.theme_sidebar_accent_color} error={fieldErrors.theme_sidebar_accent_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_accent_color', value)} />
              <ThemeColorField id="themeSidebarAccentForegroundColor" label={t('themeSidebarAccentForegroundColor')} value={settings.theme_sidebar_accent_foreground_color} error={fieldErrors.theme_sidebar_accent_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_accent_foreground_color', value)} />
              <ThemeColorField id="themeSidebarBorderColor" label={t('themeSidebarBorderColor')} value={settings.theme_sidebar_border_color} error={fieldErrors.theme_sidebar_border_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_sidebar_border_color', value)} />
              <ThemeColorField id="themeNavbarColor" label={t('themeNavbarColor')} value={settings.theme_navbar_color} error={fieldErrors.theme_navbar_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_navbar_color', value)} />
              <ThemeColorField id="themeNavbarForegroundColor" label={t('themeNavbarForegroundColor')} value={settings.theme_navbar_foreground_color} error={fieldErrors.theme_navbar_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_navbar_foreground_color', value)} />
              <ThemeColorField id="themeNavbarHoverColor" label={t('themeNavbarHoverColor')} value={settings.theme_navbar_hover_color} error={fieldErrors.theme_navbar_hover_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_navbar_hover_color', value)} />
              <ThemeColorField id="themeNavbarHoverForegroundColor" label={t('themeNavbarHoverForegroundColor')} value={settings.theme_navbar_hover_foreground_color} error={fieldErrors.theme_navbar_hover_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_navbar_hover_foreground_color', value)} />
            </div>
          </div>

          <div className="space-y-5 rounded-lg border p-4">
            <h3 className="font-medium">{t('themeSupportingColors')}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <ThemeColorField id="themeAccentColor" label={t('themeAccentColor')} value={settings.theme_accent_color} error={fieldErrors.theme_accent_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_accent_color', value)} />
              <ThemeColorField id="themeAccentForegroundColor" label={t('themeAccentForegroundColor')} value={settings.theme_accent_foreground_color} error={fieldErrors.theme_accent_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_accent_foreground_color', value)} />
              <ThemeColorField id="themeMutedColor" label={t('themeMutedColor')} value={settings.theme_muted_color} error={fieldErrors.theme_muted_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_muted_color', value)} />
              <ThemeColorField id="themeMutedForegroundColor" label={t('themeMutedForegroundColor')} value={settings.theme_muted_foreground_color} error={fieldErrors.theme_muted_foreground_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_muted_foreground_color', value)} />
            </div>
          </div>

          <div className="space-y-5 rounded-lg border p-4">
            <h3 className="font-medium">{t('themeChartColors')}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <ThemeColorField id="themeChart1Color" label={t('themeChart1Color')} value={settings.theme_chart_1_color} error={fieldErrors.theme_chart_1_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_chart_1_color', value)} />
              <ThemeColorField id="themeChart2Color" label={t('themeChart2Color')} value={settings.theme_chart_2_color} error={fieldErrors.theme_chart_2_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_chart_2_color', value)} />
              <ThemeColorField id="themeChart3Color" label={t('themeChart3Color')} value={settings.theme_chart_3_color} error={fieldErrors.theme_chart_3_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_chart_3_color', value)} />
              <ThemeColorField id="themeChart4Color" label={t('themeChart4Color')} value={settings.theme_chart_4_color} error={fieldErrors.theme_chart_4_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_chart_4_color', value)} />
              <ThemeColorField id="themeChart5Color" label={t('themeChart5Color')} value={settings.theme_chart_5_color} error={fieldErrors.theme_chart_5_color} disabled={!canUpdate} onChange={(value) => updateSetting('theme_chart_5_color', value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="defaultLanguage">{t('defaultLanguage')}</Label>
            <p className="text-sm text-muted-foreground">{t('defaultLanguageDescription')}</p>
            <Select
              value={settings.default_language}
              onValueChange={(value) => value && updateSetting('default_language', value)}
              disabled={!canUpdate}
            >
              <SelectTrigger id="defaultLanguage" className="w-48">
                <SelectValue>
                  {settings.default_language === 'zh' ? '中文' : 'English'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="zh">中文</SelectItem>
              </SelectContent>
            </Select>
            <FieldError>{fieldErrors.default_language}</FieldError>
          </div>
          <div className="space-y-2">
            <Label htmlFor="authPageLayout">{t('authPageLayout')}</Label>
            <p className="text-sm text-muted-foreground">{t('authPageLayoutDescription')}</p>
            <Select
              value={settings.auth_page_layout}
              onValueChange={(value) => {
                if (value === 'centered' || value === 'split') {
                  updateSetting('auth_page_layout', value)
                }
              }}
              disabled={!canUpdate}
            >
              <SelectTrigger id="authPageLayout" className="w-56">
                <SelectValue>
                  {settings.auth_page_layout === 'split' ? t('authPageLayoutSplit') : t('authPageLayoutCentered')}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="centered">{t('authPageLayoutCentered')}</SelectItem>
                <SelectItem value="split">{t('authPageLayoutSplit')}</SelectItem>
              </SelectContent>
            </Select>
            <FieldError>{fieldErrors.auth_page_layout}</FieldError>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('legalCompliance')}</CardTitle>
          <CardDescription>{t('legalComplianceDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="icpRecordNumber">{t('icpRecordNumber')}</Label>
              <Input
                id="icpRecordNumber"
                placeholder={t('icpRecordNumberPlaceholder')}
                value={settings.icp_record_number}
                onChange={(e) => updateSetting('icp_record_number', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.icp_record_number}
              />
              <FieldError>{fieldErrors.icp_record_number}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="icpRecordUrl">{t('icpRecordUrl')}</Label>
              <Input
                id="icpRecordUrl"
                placeholder="https://beian.miit.gov.cn"
                value={settings.icp_record_url}
                onChange={(e) => updateSetting('icp_record_url', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.icp_record_url}
              />
              <FieldError>{fieldErrors.icp_record_url}</FieldError>
            </div>
          </div>

          <div className="rounded-lg border p-4 space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-1">
                <Label htmlFor="termsEnabled">{t('termsEnabled')}</Label>
                <p className="text-sm text-muted-foreground">{t('termsEnabledDescription')}</p>
              </div>
              <Switch
                id="termsEnabled"
                checked={settings.terms_enabled}
                onCheckedChange={(checked) => updateSetting('terms_enabled', checked)}
                disabled={!canUpdate}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="termsUrl">{t('termsUrl')}</Label>
              <Input
                id="termsUrl"
                placeholder="https://example.com/terms"
                value={settings.terms_url}
                onChange={(e) => updateSetting('terms_url', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.terms_url}
              />
              <FieldError>{fieldErrors.terms_url}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="termsText">{t('termsText')}</Label>
              <Textarea
                id="termsText"
                rows={5}
                placeholder={t('termsTextPlaceholder')}
                value={settings.terms_text}
                onChange={(e) => updateSetting('terms_text', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.terms_text}
              />
              <FieldError>{fieldErrors.terms_text}</FieldError>
            </div>
          </div>

          <div className="rounded-lg border p-4 space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-1">
                <Label htmlFor="privacyEnabled">{t('privacyEnabled')}</Label>
                <p className="text-sm text-muted-foreground">{t('privacyEnabledDescription')}</p>
              </div>
              <Switch
                id="privacyEnabled"
                checked={settings.privacy_enabled}
                onCheckedChange={(checked) => updateSetting('privacy_enabled', checked)}
                disabled={!canUpdate}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="privacyUrl">{t('privacyUrl')}</Label>
              <Input
                id="privacyUrl"
                placeholder="https://example.com/privacy"
                value={settings.privacy_url}
                onChange={(e) => updateSetting('privacy_url', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.privacy_url}
              />
              <FieldError>{fieldErrors.privacy_url}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="privacyText">{t('privacyText')}</Label>
              <Textarea
                id="privacyText"
                rows={5}
                placeholder={t('privacyTextPlaceholder')}
                value={settings.privacy_text}
                onChange={(e) => updateSetting('privacy_text', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.privacy_text}
              />
              <FieldError>{fieldErrors.privacy_text}</FieldError>
            </div>
          </div>

          <div className="flex items-center justify-between gap-4 rounded-lg border p-4">
            <div className="space-y-1">
              <Label htmlFor="requireTermsAcceptanceOnRegister">{t('requireTermsAcceptanceOnRegister')}</Label>
              <p className="text-sm text-muted-foreground">{t('requireTermsAcceptanceOnRegisterDescription')}</p>
            </div>
            <Switch
              id="requireTermsAcceptanceOnRegister"
              checked={settings.require_terms_acceptance_on_register}
              onCheckedChange={(checked) => updateSetting('require_terms_acceptance_on_register', checked)}
              disabled={!canUpdate}
            />
          </div>
        </CardContent>
      </Card>

      <PermissionGuard permission="admin:settings:update">
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('saveChanges')}
          </Button>
        </div>
      </PermissionGuard>
    </div>
  )
}
