'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { Loader2 } from 'lucide-react'
import { ImageUpload } from '@/components/ui/image-upload'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
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
    () => getValidationSummaryEntries(fieldErrors, ['site_name', 'site_description', 'site_url', 'site_icon', 'default_language']),
    [fieldErrors]
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
