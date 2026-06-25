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
    auth_page_layout: 'centered',
    theme_mode: 'system',
    theme_primary_color: '',
    theme_primary_foreground_color: '',
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

    const validateHexColor = (key: 'theme_primary_color' | 'theme_primary_foreground_color') => {
      const value = settings[key].trim()
      if (value && !/^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value)) {
        nextErrors[key] = t('invalidThemeColor')
      }
    }

    validateHexColor('theme_primary_color')
    validateHexColor('theme_primary_foreground_color')

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
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="themePrimaryColor">{t('themePrimaryColor')}</Label>
              <Input
                id="themePrimaryColor"
                placeholder="#3b82f6"
                value={settings.theme_primary_color}
                onChange={(e) => updateSetting('theme_primary_color', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.theme_primary_color}
              />
              <FieldError>{fieldErrors.theme_primary_color}</FieldError>
            </div>
            <div className="space-y-2">
              <Label htmlFor="themePrimaryForegroundColor">{t('themePrimaryForegroundColor')}</Label>
              <Input
                id="themePrimaryForegroundColor"
                placeholder="#ffffff"
                value={settings.theme_primary_foreground_color}
                onChange={(e) => updateSetting('theme_primary_foreground_color', e.target.value)}
                disabled={!canUpdate}
                aria-invalid={!!fieldErrors.theme_primary_foreground_color}
              />
              <FieldError>{fieldErrors.theme_primary_foreground_color}</FieldError>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{t('themeColorHint')}</p>
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
          <div className="grid gap-4 md:grid-cols-2">
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
