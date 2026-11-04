'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Droplets, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { FieldError } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NumberInput } from '@/components/ui/number-input'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { PermissionGuard, useCanPerform } from '@/components/permission-guard'
import { useSiteSettings } from '@/contexts/site-settings-context'
import { siteSettingsApi, type WatermarkSettings } from '@/lib/api/admin/site-settings'
import {
  DEFAULT_WATERMARK_CONTENT,
  WATERMARK_DEFAULTS,
  WATERMARK_LIMITS,
  renderWatermarkText,
} from '@/lib/watermark'
import { WatermarkOverlay } from '@/components/watermark/watermark-overlay'
import { clearValidationError } from '@/lib/validation'

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/
const MAX_CONTENT_LENGTH = 200

/**
 * `<input type="color">` only accepts `#rrggbb`; it silently renders `#abc` or an
 * `#rrggbbaa` value as black, so expand and trim before binding.
 */
function toColorInputValue(color: string): string {
  const value = color.trim()
  if (!HEX_COLOR_PATTERN.test(value)) return '#000000'
  const hex = value.slice(1)
  const expanded =
    hex.length === 3 || hex.length === 4
      ? hex
          .split('')
          .map((char) => char + char)
          .join('')
      : hex
  return `#${expanded.slice(0, 6)}`
}

type NumericKey =
  | 'watermark_opacity'
  | 'watermark_font_size'
  | 'watermark_rotation'
  | 'watermark_gap'

type WatermarkForm = Omit<WatermarkSettings, NumericKey> & Record<NumericKey, number | ''>

const INITIAL_FORM: WatermarkForm = {
  watermark_enabled: WATERMARK_DEFAULTS.enabled,
  watermark_content: DEFAULT_WATERMARK_CONTENT,
  watermark_opacity: WATERMARK_DEFAULTS.opacity,
  watermark_font_size: WATERMARK_DEFAULTS.fontSize,
  watermark_rotation: WATERMARK_DEFAULTS.rotation,
  watermark_gap: WATERMARK_DEFAULTS.gap,
  watermark_color: WATERMARK_DEFAULTS.color,
}

const NUMBER_FIELDS = [
  { key: 'watermark_opacity', limit: WATERMARK_LIMITS.opacity, label: 'watermarkOpacity' },
  { key: 'watermark_font_size', limit: WATERMARK_LIMITS.fontSize, label: 'watermarkFontSize' },
  { key: 'watermark_rotation', limit: WATERMARK_LIMITS.rotation, label: 'watermarkRotation' },
  { key: 'watermark_gap', limit: WATERMARK_LIMITS.gap, label: 'watermarkGap' },
] as const

export default function SiteSettingsWatermarkPage() {
  const t = useTranslations('siteSettings')
  const { settings: publicSettings, refresh: refreshSiteSettings } = useSiteSettings()
  const { canPerform } = useCanPerform()
  const canUpdate = canPerform('admin:settings:update')

  const [loading, setLoading] = React.useState(true)
  const [settingsReady, setSettingsReady] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [form, setForm] = React.useState<WatermarkForm>(INITIAL_FORM)
  const [previewNow, setPreviewNow] = React.useState(() => new Date())

  React.useEffect(() => {
    const timer = setInterval(() => setPreviewNow(new Date()), 10_000)
    const onVisibilityChange = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        setPreviewNow(new Date())
      }
    }
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
    return () => {
      clearInterval(timer)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibilityChange)
      }
    }
  }, [])

  const loadSettings = React.useCallback(async () => {
    try {
      setLoading(true)
      setSettingsReady(false)
      setForm(await siteSettingsApi.getWatermark())
      setSettingsReady(true)
    } catch (error) {
      // Never fall back to the form defaults for saving: that would overwrite the stored
      // settings with values the administrator never saw.
      console.error('Failed to load watermark settings:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  const updateField = <K extends keyof WatermarkForm>(key: K, value: WatermarkForm[K]) => {
    setForm((previous) => ({ ...previous, [key]: value }))
    setFieldErrors((previous) => clearValidationError(previous, key))
  }

  const previewText = renderWatermarkText(form.watermark_content || DEFAULT_WATERMARK_CONTENT, {
    username: 'alice',
    email: 'alice@example.com',
    siteName: publicSettings.site_name,
    now: previewNow,
  })

  const handleSave = async () => {
    if (!canUpdate || !settingsReady) return

    const nextErrors: Record<string, string> = {}
    const content = form.watermark_content.trim()
    if (!content) {
      nextErrors.watermark_content = t('watermarkContentRequired')
    } else if (content.length > MAX_CONTENT_LENGTH) {
      nextErrors.watermark_content = t('watermarkContentTooLong')
    }

    for (const { key, limit } of NUMBER_FIELDS) {
      const value = form[key]
      if (value === '' || value < limit.min || value > limit.max) {
        nextErrors[key] = t('watermarkRangeError')
      }
    }

    const color = form.watermark_color.trim()
    if (color && !HEX_COLOR_PATTERN.test(color)) {
      nextErrors.watermark_color = t('invalidThemeColor')
    }

    if (Object.keys(nextErrors).length > 0) {
      setFieldErrors(nextErrors)
      return
    }

    setFieldErrors({})
    try {
      setSaving(true)
      await siteSettingsApi.updateWatermark({
        watermark_enabled: form.watermark_enabled,
        watermark_content: content,
        watermark_opacity:
          form.watermark_opacity === '' ? WATERMARK_DEFAULTS.opacity : form.watermark_opacity,
        watermark_font_size:
          form.watermark_font_size === ''
            ? WATERMARK_DEFAULTS.fontSize
            : form.watermark_font_size,
        watermark_rotation:
          form.watermark_rotation === '' ? WATERMARK_DEFAULTS.rotation : form.watermark_rotation,
        watermark_gap: form.watermark_gap === '' ? WATERMARK_DEFAULTS.gap : form.watermark_gap,
        watermark_color: color,
      })
      await refreshSiteSettings()
      toast.success(t('saveSuccess'))
    } catch (error) {
      console.error('Failed to save watermark settings:', error)
      toast.error(error instanceof Error ? error.message : t('saveError'))
    } finally {
      setSaving(false)
    }
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

  if (!settingsReady) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-destructive">{t('loadError')}</p>
        <Button onClick={() => void loadSettings()}>{t('retry')}</Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Droplets className="h-5 w-5 text-primary" />
            <CardTitle>{t('watermarkTitle')}</CardTitle>
          </div>
          <CardDescription>{t('watermarkCardDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="watermarkEnabled">{t('watermarkEnabled')}</Label>
              <p className="text-sm text-muted-foreground">{t('watermarkEnabledDescription')}</p>
            </div>
            <Switch
              id="watermarkEnabled"
              checked={form.watermark_enabled}
              onCheckedChange={(checked) => updateField('watermark_enabled', checked)}
              disabled={!canUpdate || saving}
            />
          </div>
          <FieldError>{fieldErrors.watermark_enabled}</FieldError>

          <div className="space-y-2">
            <Label htmlFor="watermarkContent">{t('watermarkContent')}</Label>
            <Input
              id="watermarkContent"
              value={form.watermark_content}
              onChange={(event) => updateField('watermark_content', event.target.value)}
              placeholder={DEFAULT_WATERMARK_CONTENT}
              disabled={!canUpdate || saving}
              aria-invalid={!!fieldErrors.watermark_content}
            />
            <FieldError>{fieldErrors.watermark_content}</FieldError>
            <p className="text-xs text-muted-foreground">{t('watermarkContentDescription')}</p>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            {NUMBER_FIELDS.map(({ key, limit, label }) => (
              <div key={key} className="space-y-2">
                <Label htmlFor={key}>{t(label)}</Label>
                <NumberInput
                  id={key}
                  value={form[key]}
                  onChange={(value) => updateField(key, value)}
                  min={limit.min}
                  max={limit.max}
                  disabled={!canUpdate || saving}
                  aria-invalid={!!fieldErrors[key]}
                />
                <FieldError>{fieldErrors[key]}</FieldError>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <Label htmlFor="watermarkColor">{t('watermarkColor')}</Label>
            <div className="flex items-center gap-2">
              {form.watermark_color ? (
                <>
                  <Input
                    id="watermarkColor"
                    type="color"
                    className="h-9 w-16 p-1"
                    value={toColorInputValue(form.watermark_color)}
                    onChange={(event) => updateField('watermark_color', event.target.value)}
                    disabled={!canUpdate || saving}
                    aria-invalid={!!fieldErrors.watermark_color}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => updateField('watermark_color', '')}
                    disabled={!canUpdate || saving}
                  >
                    {t('watermarkColorAuto')}
                  </Button>
                </>
              ) : (
                <>
                  <span aria-hidden className="h-9 w-16 rounded-md border bg-foreground/70" />
                  <span className="text-sm text-muted-foreground">{t('watermarkColorAuto')}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => updateField('watermark_color', '#000000')}
                    disabled={!canUpdate || saving}
                  >
                    {t('watermarkColorPick')}
                  </Button>
                </>
              )}
            </div>
            <FieldError>{fieldErrors.watermark_color}</FieldError>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('watermarkPreview')}</CardTitle>
          <CardDescription>{t('watermarkPreviewDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative h-64 overflow-hidden rounded-lg border bg-muted/30">
            <WatermarkOverlay
              fixed={false}
              text={previewText}
              opacity={
                form.watermark_opacity === '' ? WATERMARK_DEFAULTS.opacity : form.watermark_opacity
              }
              fontSize={
                form.watermark_font_size === ''
                  ? WATERMARK_DEFAULTS.fontSize
                  : form.watermark_font_size
              }
              rotation={
                form.watermark_rotation === ''
                  ? WATERMARK_DEFAULTS.rotation
                  : form.watermark_rotation
              }
              gap={form.watermark_gap === '' ? WATERMARK_DEFAULTS.gap : form.watermark_gap}
              color={form.watermark_color}
            />
          </div>
        </CardContent>
      </Card>

      <PermissionGuard permission="admin:settings:update">
        <div className="flex justify-end">
          <Button onClick={() => void handleSave()} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('saveChanges')}
          </Button>
        </div>
      </PermissionGuard>
    </div>
  )
}
